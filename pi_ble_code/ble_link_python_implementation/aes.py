"""AES-CBC framing used by the Bluetti BLE link."""

import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


PARTITION_KEY = bytes.fromhex("4496d42ca1a070c831d8b1c05f8a9844")
COM_AES_KEY = bytes(
    value ^ ((index << 3) + 1)
    for index, value in enumerate(PARTITION_KEY)
)


def zero_pad(data: bytes) -> bytes:
    size = max(16, ((len(data) + 15) // 16) * 16)
    return data.ljust(size, b"\x00")


def iot_aes_cbc_encrypt_data(data: bytes, key: bytes, iv: bytes) -> bytes:
    if len(key) not in (16, 32) or len(iv) != 16:
        raise ValueError("AES key/IV length is invalid")
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(zero_pad(data)) + encryptor.finalize()


def iot_aes_cbc_decrypt_data(data: bytes, key: bytes, iv: bytes) -> bytes:
    if not data or len(data) % 16:
        raise ValueError("AES ciphertext must contain complete blocks")
    if len(key) not in (16, 32) or len(iv) != 16:
        raise ValueError("AES key/IV length is invalid")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def generate_aes_key(auth_md5: bytes) -> bytes:
    if len(auth_md5) != 16:
        raise ValueError("Authentication MD5 must be 16 bytes")
    return bytes(a ^ b for a, b in zip(auth_md5, COM_AES_KEY))


def encrypt_sending_pack(packet: bytes, key: bytes, iv: bytes) -> bytes:
    return (
        len(packet).to_bytes(2, "big")
        + iot_aes_cbc_encrypt_data(packet, key, iv)
    )


def decrypt_receive_pack(packet: bytes, key: bytes, iv: bytes) -> bytes:
    if len(packet) < 18:
        raise ValueError("Encrypted handshake packet is too short")
    plaintext_length = int.from_bytes(packet[:2], "big")
    plaintext = iot_aes_cbc_decrypt_data(packet[2:], key, iv)
    if plaintext_length > len(plaintext):
        raise ValueError("Encrypted handshake length exceeds plaintext")
    return plaintext[:plaintext_length]


def iot_communciate_aes_cbc_encrypt(
    plaintext: bytes,
    shared_secret: bytes,
    random_value: int | None = None,
) -> bytes:
    if len(shared_secret) != 32:
        raise ValueError("ECDH shared secret must be 32 bytes")
    value = secrets.randbits(32) if random_value is None else random_value
    random_bytes = (value & 0xFFFFFFFF).to_bytes(4, "little")
    iv = hashlib.md5(random_bytes).digest()
    header = len(plaintext).to_bytes(2, "big") + random_bytes
    return header + iot_aes_cbc_encrypt_data(plaintext, shared_secret, iv)


def iot_communciate_aes_cbc_decrypt(
    packet: bytes,
    shared_secret: bytes,
) -> bytes:
    if len(packet) < 22:
        raise ValueError("Encrypted data packet is too short")
    plaintext_length = int.from_bytes(packet[:2], "big")
    iv = hashlib.md5(packet[2:6]).digest()
    plaintext = iot_aes_cbc_decrypt_data(packet[6:], shared_secret, iv)
    if plaintext_length > len(plaintext):
        raise ValueError("Encrypted data length exceeds plaintext")
    return plaintext[:plaintext_length]
