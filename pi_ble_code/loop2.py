"""
loop.py - Control and document Bluetti Battery / Inverter registers over BLE.

========================================================================================
REGISTER DOCUMENTATION & USAGE
========================================================================================
1. TELEMETRY & SOC REGISTERS (Read-Only)
   - APP_HOME_DATA_REG = 100
     Length: 20 words (Reads 100 to 119)
     - Reg 100: Total Battery Voltage (uint16, divide by 10 for Volts)
     - Reg 101: Total Battery Current (int16, divide by 10 for Amps; + Chg, - Dsg)
     - Reg 102: Battery State of Charge / SOC (uint16, 0-100 %)
     - Reg 103: Pack Charging Status (uint16, 0=Standby, 1=Chg, 2=Dsg)
     - Reg 104: Time-to-Full (uint16, Minutes)
     - Reg 105: Time-to-Empty (uint16, Minutes)
     - Reg 120-121: Total DC Power (uint32, Watts, 32-bit word swap)
     - Reg 122-123: Total AC Power (int32, Watts, 32-bit word swap)
     - Reg 124-125: Total PV Power (uint32, Watts, 32-bit word swap)
     - Reg 126-127: Total Grid Power (int32, Watts, 32-bit word swap)

2. POWER SWITCHES & CONTROLS (Read/Write)
   - AC_SWITCH_REG = 2011          (0 = Off, 1 = On) -> Toggles AC Inverter Output
   - DC_SWITCH_REG = 2012          (0 = Off, 1 = On) -> Toggles DC Port Outputs
   - CTRL_GRID_REG = 2207          (0 = Off, 1 = On) -> Grid Charging Permission
   - AC_INPUT_SET_REG = 2306       (0 = Off, 1 = On) -> AC Input Setting Toggle
   - DC_INPUT_SWITCH = 2307        (0 = Off, 1 = On) -> DC Input Switch Toggle
   - AC_INPUT_SWITCH = 2308        (0 = Off, 1 = On) -> AC Grid Input Toggle

3. WORKING MODE & TIME-CONTROL SCHEDULE REGISTERS (Read/Write)
   - WORKING_MODE_REG = 2005       (0 = Standard UPS, 1 = PV Priority, 2 = TOU, 5 = V2_TIME_CTRL_UPS)
   - CTRL_EVENT_REG = 2006         (Write 0x0100 / 256 to clear all V2 schedule entries)
   - SYSTEM_TIME_REG = 2001        (Write System RTC: [YY, MM, DD, HH, MM, SS, TZ])
   - WORKING_TIME_START_REG = 2030 (Persistent 6-slot schedule start)
     Each slot = 3 registers / 6 bytes:
       - Reg 0 (Word): Action Flag (0=Disabled, 1=Charge, 2=Discharge, 3=Standby)
       - Reg 1 (Bytes): Start Hour (uint8), Start Minute (uint8)
       - Reg 2 (Bytes): End Hour (uint8), End Minute (uint8)
     Slots:
       Slot 1: Reg 2030-2032 | Slot 2: Reg 2033-2035 | Slot 3: Reg 2036-2038
       Slot 4: Reg 2039-2041 | Slot 5: Reg 2042-2044 | Slot 6: Reg 2045-2047
========================================================================================
"""
from ble_coms import json_serializer

import argparse
import asyncio
from datetime import datetime, time as datetime_time
import logging
import struct
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from ble_encrypt import BLE_LINK_STATUS_COMPLETE, BleEncrypt
from bluetti_mqtt.core import (
    DeviceCommand,
    ReadHoldingRegisters,
    WriteMultipleRegisters,
    WriteSingleRegister,
)

DEFAULT_DEVICE_ADDRESS = "DC:B4:D9:52:82:5E"
NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
WRITE_PACING_DELAY = 1.0

# Documented Registers
# --- Telemetry & System Status Registers ---
APP_HOME_DATA_REG = 100        # [R] Telemetry block: SOC (102), Volts and Amps (100-101), & V2 Total AC Power (142)

# --- Real-Time Clock & Operating Mode Registers ---
SYSTEM_TIME_REG = 2001         # [R/W] System RTC time array: [YY, MM, DD, HH, MM, SS, TimeZone]
WORKING_MODE_REG = 2005        # [R/W] Operating mode: 0=Standard, 1=PV Priority, 2=Custom/TOU, 5=V2 Time-Control
CTRL_EVENT_REG = 2006          # [R/W] Event trigger register; write 0x0100 (256) to clear all V2 time schedules

# --- Output Power Switches ---
AC_SWITCH_REG = 2011           # [R/W][Boolean] Master AC inverter output switch: 0=Off, 1=On
DC_SWITCH_REG = 2012           # [R/W][Boolean] Master DC port output switch: 0=Off, 1=On

# --- Input Power Controls & Permissions ---
CTRL_GRID_REG = 2207           # [R/W][Boolean] AC Grid charging permission switch: 0=Disabled, 1=Enabled
AC_INPUT_SET_REG = 2306        # [R/W][Boolean] AC grid input configuration setting: 0=Disabled, 1=Enabled
DC_INPUT_SWITCH_REG = 2307     # [R/W][Boolean] Solar / DC input acceptance switch: 0=Off, 1=On
AC_INPUT_SWITCH_REG = 2308     # [R/W][Boolean] AC grid line input acceptance switch: 0=Off, 1=On

# --- V2 Persistent Schedule Block ---
WORKING_TIME_START_REG = 2030  # [R/W] Start of persistent 6-slot schedule array (2030-2047, 3 words per slot)

# Protocol Constants
V2_TIME_CTRL_UPS = 5           # Target value for WORKING_MODE_REG (2005) to activate V2 scheduled UPS mode
CLEAR_WORKING_TIME_EVENT = 0x0100  # Command payload written to CTRL_EVENT_REG (2006) to clear schedule slots
TIME_FLAG_CHARGE = 1           # Schedule slot action flag: Charge battery from grid during window
TIME_FLAG_DISCHARGE = 2        # Schedule slot action flag: Allow/force battery discharge during window
TIME_FLAG_STANDBY = 3          # Schedule slot action flag: Idle / Standby mode during window
WORKING_TIME_SLOT_COUNT = 6    # Maximum number of persistent schedule slots supported by V2 protocol

POLL_REGISTERS = (
    # --- Discrete Switch States ---
    ("DC Output Switch", DC_SWITCH_REG, 1),             # [R/W][Boolean] Reads current DC output port state
    ("AC Output Switch", AC_SWITCH_REG, 1),             # [R/W][Boolean] Reads current AC inverter output state
    ("DC Input Switch", DC_INPUT_SWITCH_REG, 1),        # [R/W][Boolean] Reads current DC input acceptance state
    ("AC Input Switch", AC_INPUT_SWITCH_REG, 1),        # [R/W][Boolean] Reads current AC grid input line state

    # --- Charging Settings ---
    ("Grid Charging Permission", CTRL_GRID_REG, 1),     # [R/W][Boolean] Reads current grid charging permission
    ("AC Input Setting", AC_INPUT_SET_REG, 1),          # [R/W][Boolean] Reads current AC input setting

    # --- Telemetry & Power Blocks ---
    ("Home Telemetry Block", APP_HOME_DATA_REG, 45),     # [R] Reads battery Volts Amps, SOC%, and V2 Total AC Power (142)
    ("AC/DC Load Info Block", 1400, 35),                # [R] Reads V2 Total DC Load (1400) & Total AC Load (1420)
    ("PV Input Info Block", 1200, 10),                  # [R] Reads V2 Solar PV Input Power (1200)
)

class BluettiController:
    def __init__(
        self,
        address: str,
        slave_addr: int,
        ac_off_interval: float,
        charge_window: Optional[tuple[datetime_time, datetime_time]],
        discharge_window: Optional[tuple[datetime_time, datetime_time]],
        clear_schedule: bool,
        set_ac: Optional[int],
        set_dc: Optional[int],
        set_dc_input: Optional[int],
        set_ac_input: Optional[int],
        sync_time: bool,
        telemetry_callback: Optional[callable] = None, 
    ) -> None:
        self.address = address
        self.slave_addr = slave_addr
        self.ac_off_interval = ac_off_interval
        self.charge_window = charge_window
        self.discharge_window = discharge_window
        self.clear_schedule = clear_schedule
        self.set_ac = set_ac
        self.set_dc = set_dc
        self.set_dc_input = set_dc_input
        self.set_ac_input = set_ac_input
        self.sync_time = sync_time

        self.crypto = BleEncrypt()
        self.client: Optional[BleakClient] = None

        self.authenticated = False
        self.auth_complete = asyncio.Event()
        self.handshake_lock = asyncio.Lock()
        self.sn_query_sent = False

        self.command_lock = asyncio.Lock()
        self.response_event = asyncio.Event()
        self.pending_command: Optional[DeviceCommand] = None
        self.pending_response: Optional[bytes] = None
        self.pending_error: Optional[Exception] = None

        self.latest_state = {} # storage for telemetry to format
        self.command_callback = None # callback for external command handling
        self.telemetry_callback = telemetry_callback # callback for external telemetry handling
        self.schedule_callback = None

    async def write_packet(self, packet: bytes, label: str) -> None:
        if self.client is None or not self.client.is_connected:
            raise RuntimeError("BLE client is unavailable or disconnected")
        print(f"[{label}] {packet.hex(' ')}", flush=True)
        await self.client.write_gatt_char(WRITE_UUID, packet, response=True)

    async def send_sn_query(self) -> None:
        if self.sn_query_sent:
            return
        command = ReadHoldingRegisters(11127, 4)
        await self.write_packet(
            self.crypto.encrypt(bytes(command.cmd)),
            "Encrypted SN query",
        )
        self.sn_query_sent = True

    async def execute_command(
        self,
        command: DeviceCommand,
        label: str,
        timeout: float = 10.0,
    ) -> bytes:
        async with self.command_lock:
            self.response_event.clear()
            self.pending_command = command
            self.pending_response = None
            self.pending_error = None
            try:
                await self.write_packet(
                    self.crypto.encrypt(bytes(command.cmd)),
                    label,
                )
                try:
                    await asyncio.wait_for(self.response_event.wait(), timeout)
                except TimeoutError as exc:
                    raise RuntimeError(f"Timed out waiting for {label}") from exc

                if self.pending_error is not None:
                    raise self.pending_error
                if self.pending_response is None:
                    raise RuntimeError(f"{label} completed without a response")
                return self.pending_response
            finally:
                self.pending_command = None
                self.pending_response = None
                self.pending_error = None
                self.response_event.clear()

    async def write_register(self, register: int, value: int, label: str) -> str:
        command = WriteSingleRegister(register, value, self.slave_addr)
        response = await self.execute_command(command, f"Write {label}")
        status = (
            "WRITE SENT; ACK UNDECRYPTABLE"
            if response == b""
            else "WRITE SUCCESS"
        )
        print(f"[{status}] {label} (Reg {register}) = {value}", flush=True)
        return status
    
    async def read_registers(
        self,
        register: int,
        count: int,
        label: str,
    ) -> list[int]:
        command = ReadHoldingRegisters(register, count, self.slave_addr)
        response = await self.execute_command(command, f"Read {label}")
        data = command.parse_response(response)
        values = [
            int.from_bytes(data[index : index + 2], byteorder="big")
            for index in range(0, len(data), 2)
        ]
        global ac_output
        global dc_output
        global ac_input
        global dc_input
        global grid_permission
        global ac_input_setting

        if label == "DC Output Switch":
            dc_output = values[0]
        elif label == "AC Output Switch":
            ac_output = values[0]
        elif label == "DC Input Switch":
            dc_input = values[0]
        elif label == "AC Input Switch":
            ac_input = values[0]
        elif label == "Grid Charging Permission":
            grid_permission = values[0]
        elif label == "AC Input Setting":
            ac_input_setting = values[0]
        elif label == "Home Telemetry Block":
            pass
        print(f"Finished storing values inside variables")

        print(f"[READ] {label}: {values}", flush=True)
        return values

    def notification_callback(
        self,
        sender: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        asyncio.create_task(self.process_notification(sender, bytes(data)))

    async def process_notification(
        self,
        _sender: BleakGATTCharacteristic,
        raw: bytes,
    ) -> None:
        if not self.authenticated:
            async with self.handshake_lock:
                try:
                    status, response = self.crypto.handle_link_packet(raw)
                    if response:
                        await self.write_packet(response, "Handshake response")
                    if status == 3 and not self.sn_query_sent:
                        await self.send_sn_query()
                    if status == BLE_LINK_STATUS_COMPLETE:
                        self.authenticated = True
                        self.auth_complete.set()
                        print("*** AUTHENTICATION COMPLETE ***", flush=True)
                except Exception as exc:
                    print(f"Handshake error: {exc}", flush=True)
            return

        try:
            plaintext = self.crypto.decrypt(raw)
            command = self.pending_command
            if command is None:
                print(
                    f"Ignoring unsolicited Modbus frame: {plaintext.hex(' ')}",
                    flush=True,
                )
                return

            if len(plaintext) < 3:
                raise RuntimeError("Truncated Modbus response")
            if plaintext[0] != command.cmd[0]:
                print("Ignoring response for another Modbus slave", flush=True)
                return
            if not command.is_valid_response(plaintext):
                raise RuntimeError("Modbus response CRC validation failed")
            if command.is_exception_response(plaintext):
                code = plaintext[2]
                raise RuntimeError(
                    f"Modbus exception 0x{code:02X} for function "
                    f"0x{command.function_code:02X}"
                )
            if plaintext[1] != command.function_code:
                print("Ignoring response for another Modbus function", flush=True)
                return

            if isinstance(command, WriteSingleRegister):
                if len(plaintext) != command.response_size():
                    raise RuntimeError("Invalid write-response length")
                if plaintext[:6] != bytes(command.cmd[:6]):
                    raise RuntimeError("Write response does not echo the command")
            elif isinstance(command, WriteMultipleRegisters):
                if len(plaintext) != command.response_size():
                    raise RuntimeError("Invalid multi-write response length")
                if plaintext[:6] != bytes(command.cmd[:6]):
                    raise RuntimeError(
                        "Multi-write response does not echo address and count"
                    )
            elif isinstance(command, ReadHoldingRegisters):
                expected_bytes = command.quantity * 2
                if len(plaintext) != command.response_size():
                    raise RuntimeError("Invalid read-response length")
                if plaintext[2] != expected_bytes:
                    raise RuntimeError("Read response has an unexpected byte count")

            self.pending_response = plaintext
            self.response_event.set()
        except Exception as exc:
            command = self.pending_command
            if (
                str(exc) == "decrypt_data() returned an empty result."
                and isinstance(
                    command,
                    (WriteSingleRegister, WriteMultipleRegisters),
                )
            ):
                self.pending_response = b""
                self.response_event.set()
                print(
                    "[WARNING] Device write response could not be decrypted; "
                    "continuing because the write was delivered",
                    flush=True,
                )
                return
            if command is not None:
                self.pending_error = exc
                self.response_event.set()
            print(f"Decrypt/parse error: {exc}", flush=True)

    async def poll_telemetry_loop(self) -> None:
        print("Starting telemetry polling loop...", flush=True)

        soc = 0
        voltage = 0.0
        current = 0.0
        pv_watts = 0
        grid_watts = 0
        ac_watts = 0
        dc_watts = 0

        while self.is_connected:
            for label, register, count in POLL_REGISTERS:
                if not self.is_connected:
                    return
                try:
                    values = await self.read_registers(register, count, label)

                    # 1. Base Home Data (Reg 100)
                    if register == APP_HOME_DATA_REG and len(values) >= 20:
                        voltage = values[0] / 10.0
                        current_raw = values[1]
                        current = (
                            current_raw if current_raw < 32768 else current_raw - 65536
                        ) / 10.0
                        soc = values[2]

                        # V1 Legacy fallback (Word 28)
                        if len(values) >= 30 and values[28] > 0 and values[28] < 10000:
                            ac_watts = values[28]

                        # V2 Total AC Load Power: Words 42 & 43 (Regs 142-143)
                        if len(values) >= 44:
                            ac_v2 = (values[43] << 16) | values[42]
                            if ac_v2 > 0 and ac_v2 < 10000:
                                ac_watts = ac_v2

                    # 2. Dedicated PV Info Block (Reg 1200) - PV Input
                    elif register == 1200 and len(values) >= 2:
                        pv_watts = values[0] if values[0] < 65535 else ((values[1] << 16) | values[0])

                    # 3. AC/DC Load Info Block (Reg 1400)
                    elif register == 1400 and len(values) >= 22:
                        # Word 0 & 1: Total DC Load Power
                        dc_1400 = (values[1] << 16) | values[0]
                        if dc_1400 > 0 and dc_1400 < 10000:
                            dc_watts = dc_1400

                        # Word 20 & 21: Total AC Load Power (Regs 1420-1421)
                        ac_1400 = (values[21] << 16) | values[20]
                        if ac_1400 > 0 and ac_1400 < 10000:
                            ac_watts = ac_1400

                except Exception as exc:
                    print(f"Error reading {label}: {exc}", flush=True)
                await asyncio.sleep(1.0)

            # Print Clean Telemetry Summary
            print("\n=================== TELEMETRY ===================", flush=True)
            print(f" SOC:          {soc}%", flush=True)
            print(f" Battery:      {voltage:.1f} V | {current:.1f} A", flush=True)
            print(" ---------------- INPUTS ----------------", flush=True)
            print(f" Solar (PV):   {pv_watts} W", flush=True)
            print(f" Grid (AC):    {grid_watts} W", flush=True)
            print(" ---------------- OUTPUTS ---------------", flush=True)
            print(f" AC Load:      {ac_watts} W", flush=True)
            print(f" DC Load:      {dc_watts} W", flush=True)
            print("=================================================\n", flush=True)

            callback = getattr(self, "telemetry_callback", None)
            if callback:
                state_payload = {
                    "soc": soc,
                    "voltage": voltage,
                    "current": current,
                    "pv_watts": pv_watts,
                    "grid_watts": grid_watts,
                    "ac_watts": ac_watts,
                    "dc_watts": dc_watts,

                    "ac_output": ac_output,
                    "dc_output": dc_output,
                    "ac_input": ac_input,
                    "dc_input": dc_input,

                    "grid_permission": grid_permission,
                    "ac_input_setting": ac_input_setting,
                }
                self.latest_state = state_payload.copy() # store the latest state/telemetry for external access
                try:
                    res = callback(state_payload)
                    # If the callback is an async function (returns a coroutine), await it
                    print("mqtt branch")
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as exc:
                    print(f"Error in telemetry callback: {exc}", flush=True)
            if self.command_callback:
                await self.command_callback(self)
            if self.schedule_callback:
                await self.schedule_callback(self)

            await asyncio.sleep(3.0)

    @property
    def is_connected(self) -> bool:
        return bool(
            self.client is not None
            and self.client.is_connected
            and self.authenticated
        )

    async def sleep_while_connected(self, duration: float) -> bool:
        deadline = asyncio.get_running_loop().time() + duration
        while self.is_connected:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return True
            await asyncio.sleep(min(1.0, remaining))
        False

    async def set_grid_enabled(self, enabled: bool) -> None:
        await self.write_register(
            CTRL_GRID_REG,
            int(enabled),
            f"CTRL_GRID {'on' if enabled else 'off'}",
        )

    async def sync_system_rtc(self) -> None:
        """Sync local time to system RTC (Reg 2001)."""
        now = datetime.now()
        payload = struct.pack(
            "!BBBBBB",
            now.year % 100,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
        )
        command = WriteMultipleRegisters(
            SYSTEM_TIME_REG, payload, self.slave_addr
        )
        await self.execute_command(command, "Sync System RTC Time")
        print(f"[RTC SUCCESS] Synced system time to {now.isoformat()}", flush=True)

    async def set_app_working_schedule(
        self,
        charge_window: Optional[tuple[datetime_time, datetime_time]],
        discharge_window: Optional[tuple[datetime_time, datetime_time]],
    ) -> str:
        """Install persistent six-slot V2 charge/discharge schedule starting at Reg 2030."""
        entries: list[tuple[int, datetime_time, datetime_time]] = []
        if charge_window is not None:
            entries.append((TIME_FLAG_CHARGE, *charge_window))
        if discharge_window is not None:
            entries.append((TIME_FLAG_DISCHARGE, *discharge_window))
        entries.sort(key=lambda item: (item[1].hour, item[1].minute))

        standby = datetime_time(0, 0)
        while len(entries) < WORKING_TIME_SLOT_COUNT:
            entries.append((TIME_FLAG_STANDBY, standby, standby))

        payload = b"".join(
            struct.pack(
                "!HBBBB",
                action,
                start.hour,
                start.minute,
                end.hour,
                end.minute,
            )
            for action, start, end in entries
        )

        if charge_window is not None:
            await self.set_grid_enabled(True)

        await self.write_register(
            WORKING_MODE_REG,
            V2_TIME_CTRL_UPS,
            "V2 scheduled charge/discharge working mode",
        )
        await asyncio.sleep(WRITE_PACING_DELAY)
        command = WriteMultipleRegisters(
            WORKING_TIME_START_REG,
            payload,
            self.slave_addr,
        )
        response = await self.execute_command(
            command,
            "Write V2 working-time schedule",
        )
        status = (
            "WRITE SENT; ACK UNDECRYPTABLE"
            if response == b""
            else "WRITE SUCCESS"
        )
        return status
    
    async def clear_app_working_schedule(self) -> None:
        """Clear all persistent V2 working-time schedule entries via Reg 2006."""
        await self.write_register(
            CTRL_EVENT_REG,
            CLEAR_WORKING_TIME_EVENT,
            "clear V2 working-time schedule",
        )

    async def apply_user_switches(self) -> None:
        """Apply CLI switch write commands."""
        if self.set_ac is not None:
            await self.write_register(AC_SWITCH_REG, self.set_ac, "AC Output Switch")
            await asyncio.sleep(WRITE_PACING_DELAY)
        if self.set_dc is not None:
            await self.write_register(DC_SWITCH_REG, self.set_dc, "DC Output Switch")
            await asyncio.sleep(WRITE_PACING_DELAY)
        if self.set_dc_input is not None:
            await self.write_register(
                DC_INPUT_SWITCH_REG, self.set_dc_input, "DC Input Switch"
            )
            await asyncio.sleep(WRITE_PACING_DELAY)
        if self.set_ac_input is not None:
            await self.write_register(
                AC_INPUT_SWITCH_REG, self.set_ac_input, "AC Input Switch"
            )
            await asyncio.sleep(WRITE_PACING_DELAY)

    async def run(self) -> None:
        print(f"Searching for device at {self.address}...", flush=True)
        device = await BleakScanner.find_device_by_address(
            self.address,
            timeout=15.0,
        )
        if device is None:
            raise RuntimeError(f"Could not find device at {self.address}")

        client = BleakClient(device, timeout=25.0)
        self.client = client
        tasks: list[asyncio.Task[None]] = []
        try:
            await client.connect()
            print(f"Connected to {device.name or device.address}", flush=True)
            self.crypto.start()
            await client.start_notify(NOTIFY_UUID, self.notification_callback)
            await asyncio.wait_for(self.auth_complete.wait(), timeout=45.0)

            # Apply writes requested via CLI arguments
            if self.sync_time:
                await self.sync_system_rtc()
            await self.apply_user_switches()

            if self.clear_schedule:
                await self.clear_app_working_schedule()
            elif (
                self.charge_window is not None
                or self.discharge_window is not None
            ):
                await self.set_app_working_schedule(
                    self.charge_window,
                    self.discharge_window,
                )

            # Continuous Monitoring Task
            tasks.append(asyncio.create_task(self.poll_telemetry_loop()))

            print("Running. Press Ctrl+C to exit.", flush=True)
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if client.is_connected:
                try:
                    await client.stop_notify(NOTIFY_UUID)
                except Exception:
                    pass
                await client.disconnect()
            self.client = None
            print("Disconnected safely", flush=True)


def parse_clock_time(value: str) -> datetime_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}; expected 24-hour HH:MM"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--address", default=DEFAULT_DEVICE_ADDRESS)
    parser.add_argument(
        "--slave-address",
        type=lambda value: int(value, 0),
        choices=range(0, 248),
        default=1,
        metavar="ADDRESS",
        help="Modbus slave address (default: 1; Gen 2 IoT boxes use 0)",
    )
    parser.add_argument(
        "--ac-off-interval",
        type=float,
        default=0,
        metavar="SECONDS",
        help="Periodically turn AC output off",
    )

    # Output & Input Controls
    parser.add_argument("--set-ac", type=int, choices=[0, 1], help="Set AC Output (0=Off, 1=On)")
    parser.add_argument("--set-dc", type=int, choices=[0, 1], help="Set DC Output (0=Off, 1=On)")
    parser.add_argument("--set-dc-input", type=int, choices=[0, 1], help="Set DC Input Switch (0=Off, 1=On)")
    parser.add_argument("--set-ac-input", type=int, choices=[0, 1], help="Set AC Input Switch (0=Off, 1=On)")
    parser.add_argument("--sync-time", action="store_true", help="Sync local time to battery RTC")

    # Schedule Options
    parser.add_argument("--charge-start", type=parse_clock_time, metavar="HH:MM")
    parser.add_argument("--charge-end", type=parse_clock_time, metavar="HH:MM")
    parser.add_argument("--discharge-start", type=parse_clock_time, metavar="HH:MM")
    parser.add_argument("--discharge-end", type=parse_clock_time, metavar="HH:MM")
    parser.add_argument(
        "--clear-schedule",
        action="store_true",
        help="Clear all persistent V2 working-time schedule entries",
    )

    args = parser.parse_args()

    for name in ("charge", "discharge"):
        start = getattr(args, f"{name}_start")
        end = getattr(args, f"{name}_end")
        if (start is None) != (end is None):
            parser.error(f"--{name}-start and --{name}-end must be provided together")

    if args.clear_schedule and any(
        value is not None
        for value in (
            args.charge_start,
            args.charge_end,
            args.discharge_start,
            args.discharge_end,
        )
    ):
        parser.error("--clear-schedule cannot be combined with schedule time options")
    return args

async def process_mqtt_command(controller):
    command = json_serializer.latest_command
    # if there's no command exit immediately
    if command is None:
        return
    print(f"MQTT command received: {command}")
    # extracts command parameters from the JSON payload
    request = command.get("request")
    target = command.get("target") 
    value = command.get("value")
    # update storage for actuator state
    actuator = json_serializer.actuator
    actuator.request = request
    actuator.value = value
    actuator.target = target
    # prevent reading requests fed through command request pipeline
    if request != "write":
        json_serializer.latest_command = None
        actuator.action = False
        actuator.flag = "Ignored non write request"
        return
    try:
        # set the registers based on the target of the controller
        if target == "ac_output":
            actuator.flag = await controller.write_register(AC_SWITCH_REG, value, "AC Output Switch")
        elif target == "dc_output":
            actuator.flag = await controller.write_register(DC_SWITCH_REG, value, "DC Output Switch")
        elif target == "ac_input":
            actuator.flag = await controller.write_register(AC_INPUT_SWITCH_REG, value, "AC Input Switch")
        elif target == "dc_input":
            actuator.flag = await controller.write_register(DC_INPUT_SWITCH_REG, value, "DC Input Switch")
        elif target == "grid_permission":
            actuator.flag = await controller.write_register(CTRL_GRID_REG, value, "Grid Charging Permission")
        elif target == "ac_input_setting":
            actuator.flag = await controller.write_register(AC_INPUT_SET_REG, value, "AC Input Setting")
        else:
            raise ValueError(f"Unknown MQTT target: {target}")
        actuator.action = True
    except Exception as exc:
        actuator.action = False
        actuator.flag = str(exc)
        print(exc)
    finally:
        # prevent running the same command again
        json_serializer.latest_command = None

async def process_mqtt_schedule(controller):
    schedule = json_serializer.latest_schedule
    # if there's no schedule exit immediately
    if schedule is None:
        return
    print(f"MQTT schedule received: {schedule}")
    # extracts parameters from the JSON payload
    request = schedule.get("request")
    charge_start = schedule.get("charge_start")
    charge_end = schedule.get("charge_end")
    discharge_start = schedule.get("discharge_start")
    discharge_end = schedule.get("discharge_end")

    charge_window = (
        parse_clock_time(charge_start),
        parse_clock_time(charge_end),
)
    discharge_window = (
        parse_clock_time(discharge_start),
        parse_clock_time(discharge_end),
)
    # update storage for actuator state
    actuator = json_serializer.actuator
    actuator.request = request
    actuator.value = {
        "charge": charge_window,
        "discharge": discharge_window,
    }
    actuator.target = "schedule"
    # prevent reading requests fed through command request pipeline
    if request != "write":
        json_serializer.latest_schedule = None
        actuator.action = False
        actuator.flag = "Ignored non write request"
        return
    try:
        actuator.flag = await controller.set_app_working_schedule(charge_window, discharge_window)
        actuator.action = True
    except Exception as exc:
        actuator.action = False
        actuator.flag = str(exc)
        print(exc)
    finally:
        # prevent running the same command again
        json_serializer.latest_schedule = None

async def main() -> None:
    args = parse_args()
    # writeable registers from serial terminal
    if args is not None:
        controller = BluettiController(
            address=args.address,
            slave_addr=args.slave_address,
            ac_off_interval=args.ac_off_interval,
            charge_window=(
                (args.charge_start, args.charge_end)
                if args.charge_start is not None
                else None
            ),
            discharge_window=(
                (args.discharge_start, args.discharge_end)
                if args.discharge_start is not None
                else None
            ),
            clear_schedule=args.clear_schedule,
            set_ac=args.set_ac,
            set_dc=args.set_dc,
            set_dc_input=args.set_dc_input,
            set_ac_input=args.set_ac_input,
            sync_time=args.sync_time,

            telemetry_callback=json_serializer.json_publish_battery_state,
        )
    controller.command_callback = process_mqtt_command
    controller.schedule_callback = process_mqtt_schedule
    await controller.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as exc:
        print(f"Fatal error: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(1)