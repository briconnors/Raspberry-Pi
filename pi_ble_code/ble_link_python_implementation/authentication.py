import hashlib
from .protocol import (
    pack_protocol_message,
    check_protocol_format)


AUTH_STATUS_ECDH = 2

def generate_md5_value_by_random(random_value: bytes) -> bytes:
    """
    Generate the 16-byte authentication context from a 4-byte value.

    Native behavior:
        MD5(random_value[3], random_value[2],
            random_value[1], random_value[0])
    """
    if len(random_value) != 4:
        raise ValueError("Random value must be exactly 4 bytes")

    reversed_value = random_value[::-1]
    return hashlib.md5(reversed_value).digest()

def pack_ble_authen_request(md5_value: bytes) -> bytes:
    """
    Build the initial BLE authentication request.

    Native payload:
        MD5 digest bytes 8 through 11
    """
    if len(md5_value) != 0x10:
        raise ValueError("MD5 value must be exactly 16 bytes")

    payload = md5_value[0x08:0x0C]

    return pack_protocol_message(
        function_code=2,
        payload=payload,
    )

def generate_aes_key(
    md5_value: bytes,
    com_aes_key: bytes,
) -> bytes:
    """
    Derive the 16-byte AES key used for the BLE authentication session.

    Native behavior:
        aes_key[i] = md5_value[i] ^ com_aes_key[i]
    """
    if len(md5_value) != 0x10:
        raise ValueError("MD5 value must be exactly 16 bytes")

    if len(com_aes_key) != 0x10:
        raise ValueError("Communication AES key must be exactly 16 bytes")

    return bytes(
        md5_byte ^ com_key_byte
        for md5_byte, com_key_byte in zip(md5_value, com_aes_key)
    )

def proc_authen(
    packet: bytes,
) -> tuple[bytes | None, bytes | None, int]:
    """
    Process the initial authentication stage.

    Returns:
        response_packet:
            Function-code 2 packet to send, or None.

        md5_value:
            16-byte MD5 authentication value, or None.

        status:
            2 when the function-code 3 ACK moves the session to ECDH;
            otherwise 0 while authentication continues.
    """
    result = check_protocol_format(packet)

    if result != 0:
        raise ValueError(f"Protocol format error: {result}")

    function_code = packet[2]

    if function_code == 1:
        # Function 1 has a four-byte challenge payload.
        random_value = packet[4:8]

        md5_value = generate_md5_value_by_random(random_value)

        response = pack_ble_authen_request(md5_value)

        return response, md5_value, 0

    if function_code == 3:
        result_code = packet[4]

        if result_code != 0:
            raise ValueError(
                f"Bluetooth authentication failed: {result_code}"
            )

        return None, None, AUTH_STATUS_ECDH

    raise ValueError(
        f"Unexpected authentication function code: {function_code}"
    )

