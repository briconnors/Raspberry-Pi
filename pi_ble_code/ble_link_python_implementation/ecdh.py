# ECDH key generation/shared-secret operations
from cryptography.hazmat.primitives.asymmetric import ec

from .aes import decrypt_receive_pack, encrypt_sending_pack
from .protocol import check_protocol_format, pack_protocol_message
from .signatures import pack_sign, pack_verify


def client_public_gen() -> tuple[bytes, ec.EllipticCurvePrivateKey]:
    """
    Generate a fresh P-256 ECDH key pair.

    Returns:
        public_key: 64 bytes, encoded as X || Y
        private_key: retained for shared-secret calculation
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()

    x = public_numbers.x.to_bytes(32, "big")
    y = public_numbers.y.to_bytes(32, "big")
    public_key = x + y

    if len(public_key) != 0x40:
        raise ValueError("Client public key must be 64 bytes")

    return public_key, private_key


def ecdh_key_agreement_data(
    output: bytearray,
    auth_context: bytes,
) -> ec.EllipticCurvePrivateKey:
    """
    Build the 128-byte ECDH response payload.

    Layout:
        0x00-0x3F: client public key
        0x40-0x7F: ECDSA signature
    """
    if len(output) < 0x80:
        raise ValueError("Output buffer must be at least 128 bytes")

    if len(auth_context) != 0x10:
        raise ValueError("Authentication context must be 16 bytes")

    public_key, private_key = client_public_gen()
    output[0x00:0x40] = public_key

    # Match the native implementation: sign public_key || auth_context.
    output[0x40:0x50] = auth_context
    signature = pack_sign(bytes(output[0x00:0x50]))

    if len(signature) != 0x40:
        raise ValueError("ECDH signature must be 64 bytes")

    output[0x40:0x80] = signature
    return private_key


def client_calculate_secret(
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_key: bytes,
) -> bytes:
    """
    Compute the raw P-256 ECDH shared secret from a peer public key.

    The peer key must be 64 bytes in X || Y form.
    """
    if len(peer_public_key) != 0x40:
        raise ValueError("Peer public key must be 64 bytes")

    peer_x = int.from_bytes(peer_public_key[:0x20], "big")
    peer_y = int.from_bytes(peer_public_key[0x20:], "big")

    try:
        peer_numbers = ec.EllipticCurvePublicNumbers(
            peer_x,
            peer_y,
            ec.SECP256R1(),
        )
        peer_key = peer_numbers.public_key()
    except ValueError as exc:
        raise ValueError("Peer public key is not a valid P-256 point") from exc

    shared_secret = private_key.exchange(ec.ECDH(), peer_key)

    if len(shared_secret) != 0x20:
        raise ValueError("Shared secret must be 32 bytes")

    return shared_secret

#pack_sign and ecdsa_verify are built in
def pack_ecdh_response(
    auth_context: bytes,
) -> tuple[bytes, ec.EllipticCurvePrivateKey]:
    """
    Build the complete protocol-framed ECDH response.

    Returns:
        packet: Complete ** protocol packet.
        private_key: Client private key retained for later shared-secret calculation.
    """
    ecdh_data = bytearray(0x80)
    private_key = ecdh_key_agreement_data(
        output=ecdh_data,
        auth_context=auth_context,
    )

    packet = pack_protocol_message(
        function_code=5,
        payload=bytes(ecdh_data),
    )

    return packet, private_key


def ecdh_key_agreement_respond_check(
    packet: bytes,
    md5_value: bytes,
) -> bytes:
    """
    Verify the battery's function-code 4 ECDH packet.

    Returns:
        The battery's 64-byte P-256 public key in X || Y format.
    """
    if len(md5_value) != 0x10:
        raise ValueError("MD5 value must be exactly 16 bytes")

    # Header 4 bytes + public key 64 bytes + signature 64 bytes
    if len(packet) < 0x84:
        raise ValueError("ECDH packet is too short")

    if packet[2] != 0x04:
        raise ValueError(
            f"Expected ECDH function code 4, got {packet[2]}"
        )

    peer_public_key = packet[0x04:0x44]
    signature = packet[0x44:0x84]

    if len(peer_public_key) != 0x40:
        raise ValueError("Peer public key must be 64 bytes")

    if len(signature) != 0x40:
        raise ValueError("ECDH signature must be 64 bytes")

    signed_data = peer_public_key + md5_value

    if not pack_verify(
        data=signed_data,
        signature=signature,
    ):
        raise ValueError("Battery ECDH signature verification failed")

    return peer_public_key


def proc_ecdh(
    context: object,
    encrypted_packet: bytes,
) -> tuple[bytes | None, int]:
    """
    Process the ECDH handshake stage.

    Python wrapper returns:
        function 4 -> encrypted function-5 response, status 2
        function 6 -> no response, status 3

    Note: native proc_ecdh() itself returns 0 after handling function 4;
    status 2 is maintained by the surrounding handshake state machine.
    """
    if not encrypted_packet:
        raise ValueError("[cryptModule]: proc ecdh param fail")

    md5_value = getattr(context, "md5_value", None)
    handshake_key = getattr(context, "handshake_key", None)

    if not isinstance(md5_value, bytes) or len(md5_value) != 0x10:
        raise ValueError("Context md5_value must be 16 bytes")

    if not isinstance(handshake_key, bytes) or len(handshake_key) != 0x10:
        raise ValueError("Context handshake_key must be 16 bytes")

    packet = decrypt_receive_pack(
        encrypted_packet,
        handshake_key,
        md5_value,
    )

    if len(packet) < 6:
        raise ValueError("Decrypted ECDH packet is too short")

    result = check_protocol_format(packet)
    if result != 0:
        raise ValueError(f"Protocol format error: {result}")

    function_code = packet[2]

    if function_code == 4:
        peer_public_key = ecdh_key_agreement_respond_check(
            packet,
            md5_value,
        )

        response, private_key = pack_ecdh_response(md5_value)

        shared_secret = client_calculate_secret(
            private_key,
            peer_public_key,
        )

        context.private_key = private_key
        context.shared_secret = shared_secret

        encrypted_response = encrypt_sending_pack(
            response,
            handshake_key,
            md5_value,
        )

        return encrypted_response, 2

    if function_code == 6:
        if packet[3] != 1:
            raise ValueError(
                f"Function-6 payload length must be 1, got {packet[3]}"
            )

        result_code = packet[4]

        if result_code != 0:
            raise ValueError(
                f"[cryptModule]: ECDH key agreement failed: {result_code}"
            )

        context.state = 3
        return None, 3

    raise ValueError(
        f"[cryptModule]: unexpected ECDH function code: {function_code}"
    )