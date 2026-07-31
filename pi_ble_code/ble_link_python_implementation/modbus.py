"""Modbus validation mirrored from BluettiCrypt."""


def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc & 0xFFFF


def modbus_format_check(packet: bytes) -> int:
    if len(packet) <= 4 or packet[1] not in (3, 6, 0x10):
        return -1
    expected = modbus_crc16(packet[:-2])
    received = packet[-2] | (packet[-1] << 8)
    return packet[1] if expected == received else -1


def refresh_modbus_crc(packet: bytes) -> bytes:
    if len(packet) < 3:
        raise ValueError("Modbus packet is too short")
    return packet[:-2] + modbus_crc16(packet[:-2]).to_bytes(2, "little")
