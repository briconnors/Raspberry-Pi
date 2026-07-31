# generic ** framing and checksum

INVALID_SUM = 0xFFFFFFFF #checksum
EXPECTED_FUNC_LENGTHS = { #expected payload lengths
    1: 4,
    2: 4,
    3: 1,
    4: 0x80,
    5: 0x80,
    6: 1,
}


def calculate_sum(data: bytes) -> int:
    """
    Calculate Bluetti's 16-bit additive protocol checksum.

    The original function accumulates bytes into an unsigned
    16-bit value, so overflow wraps modulo 65536.
    """
    if not data:
        return INVALID_SUM
    return sum(data) & 0xFFFF

def check_func_len(function_code: int, length: int) -> int:
    """
    Returns:
         0  function code exists and length is correct
        -1  function code exists but length is incorrect
        -2  unknown function code
    """
    expected_length = EXPECTED_FUNC_LENGTHS.get(function_code)

    if expected_length is None:
        return -2

    if length != expected_length:
        return -1

    return 0

def check_protocol_format(data: bytes) -> int:
    """
    Returns:
         0          valid packet
        0xFFFF9F00  null/too short
        0xFFFF9EFF  invalid format
    """
    packet_len = len(data)

    if packet_len < 7:
        return 0xFFFF9F00 #invalid input error

    # Header must be "**"
    if data[0:2] != b"**":
        print("[cryptModule]: bluetooth link protocol head error")
        return 0xFFFF9EFF #invalid protocol format fail

    function_code = data[2]
    payload_len = data[3]

    if check_func_len(function_code, payload_len) < 0:
        return 0xFFFF9EFF

    # Decompiled condition: payload_len + 5 < total packet length
    if payload_len + 5 >= packet_len: 
        return 0xFFFF9EFF 

    calculated_checksum = calculate_sum(data[2:packet_len - 2])

    # CONCAT11(data[-2], data[-1]) creates a big-endian 16-bit value.
    received_checksum = (data[-2] << 8) | data[-1]

    if calculated_checksum != received_checksum:
        return 0xFFFF9EFF

    return 0

def pack_protocol_message(function_code: int, payload: bytes) -> bytes:
    """
    [0:2]   Header: "**"
    [2]     Function code
    [3]     Payload length
    [4:N]   Payload
    [-2:]   16-bit checksum, big-endian, second-to-last to last byte
    """

    if payload is None or len(payload) < 1:
        raise ValueError(
            "[cryptModule]: packet protocol message param fail"
        )

    if not 0 <= function_code <= 0xFF:
        raise ValueError("function_code must fit in one byte")

    if len(payload) > 0xFF:
        raise ValueError("payload length must fit in one byte")

    packet_without_checksum = (
        b"**"
        + bytes([function_code])
        + bytes([len(payload)])
        + payload
    )

    checksum = calculate_sum(packet_without_checksum[2:])

    return packet_without_checksum + checksum.to_bytes(2, "big")