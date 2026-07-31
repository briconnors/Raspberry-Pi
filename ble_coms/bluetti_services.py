#"""Authenticate with an EL400 and monitor/control it over encrypted BLE."""
#by primarily by Palina with MQTT added by Bri
import argparse
import asyncio
import logging
import os
import time
from typing import Optional

import _bluetti_crypt
import config
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from ble_encrypt import BLE_LINK_STATUS_COMPLETE, BleEncrypt
from bluetti_mqtt.core import (
    DeviceCommand,
    ReadHoldingRegisters,
    WriteSingleRegister,
)

class BluettiController:
    def __init__(
        self,
        address: str,
        slave_addr: int,
        ac_off_interval: float,
    ) -> None:
        self.address = address
        self.slave_addr = slave_addr
        self.ac_off_interval = ac_off_interval
        self.crypto = BleEncrypt()
        self.client: Optional[BleakClient] = None

        self.authenticated = False
        self.auth_complete = asyncio.Event()
        self.handshake_lock = asyncio.Lock()
        self.sn_query_sent = False

        # Exactly one normal Modbus command may be outstanding at a time.
        self.command_lock = asyncio.Lock()
        self.response_event = asyncio.Event()
        self.pending_command: Optional[DeviceCommand] = None
        self.pending_response: Optional[bytes] = None
        self.pending_error: Optional[Exception] = None

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

    async def write_register(self, register: int, value: int, label: str) -> None:
        command = WriteSingleRegister(register, value, self.slave_addr)
        await self.execute_command(command, f"Write {label}")
        print(f"[WRITE SUCCESS] {label} = {value}", flush=True)

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
            elif isinstance(command, ReadHoldingRegisters):
                expected_bytes = command.quantity * 2
                if len(plaintext) != command.response_size():
                    raise RuntimeError("Invalid read-response length")
                if plaintext[2] != expected_bytes:
                    raise RuntimeError("Read response has an unexpected byte count")

            self.pending_response = plaintext
            self.response_event.set()
        except Exception as exc:
            if self.pending_command is not None:
                self.pending_error = exc
                self.response_event.set()
            print(f"Decrypt/parse error: {exc}", flush=True)

    async def poll_telemetry_loop(self) -> None:
        print("Starting telemetry polling loop", flush=True)
        while self.is_connected:
            for label, register, count in POLL_REGISTERS:
                if not self.is_connected:
                    return
                try:
                    values = await self.read_registers(register, count, label)
                    if register == APP_HOME_DATA_REG and len(values) >= 3:
                        print(f"State of charge: {values[2]}%", flush=True)
                except Exception as exc:
                    print(f"Error reading {label}: {exc}", flush=True)
                await asyncio.sleep(1.5)
            await asyncio.sleep(5.0)

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
        return False

    async def periodic_ac_output_off_loop(self) -> None:
        while await self.sleep_while_connected(self.ac_off_interval):
            try:
                print("[TIMER] Turning AC output off", flush=True)
                await self.write_register(AC_SWITCH_REG, 0, "AC output")
            except Exception as exc:
                print(f"Failed to turn AC output off: {exc}", flush=True)

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

            tasks.append(asyncio.create_task(self.poll_telemetry_loop()))
            if self.ac_off_interval > 0:
                tasks.append(
                    asyncio.create_task(self.periodic_ac_output_off_loop())
                )
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=DEFAULT_DEVICE_ADDRESS)
    parser.add_argument(
        "--slave-address",
        type=lambda value: int(value, 0),
        choices=range(0, 248),
        default=1,
        metavar="ADDRESS",
        help="Modbus slave address (default: 1)",
    )
    parser.add_argument(
        "--ac-off-interval",
        type=float,
        default=0,
        metavar="SECONDS",
        help="periodically turn AC output off; disabled by default",
    )
    args = parser.parse_args()
    if args.ac_off_interval < 0:
        parser.error("--ac-off-interval cannot be negative")
    return args


async def main() -> None:
    args = parse_args()
    binary_path = _bluetti_crypt.__file__
    print(f"Compiled binary: {binary_path}")
    print(f"Last modified: {time.ctime(os.path.getmtime(binary_path))}")
    controller = BluettiController(
        args.address,
        args.slave_address,
        args.ac_off_interval,
    )
    await controller.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as exc:
        print(f"Fatal error: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(1)