import logging

from ble_link_python_implementation.session import BleLinkSession


BLE_LINK_STATUS_COMPLETE = 4


class BleEncrypt:
    def __init__(self) -> None:
        self.session = BleLinkSession()
        self.auth_context = None
        self.last_response = None

    def start(self) -> None:
        """
        Start a fresh Python-side crypto session.

        For now this only initializes the auth handshake state; encryption and
        decryption remain separate work if you want to replace the native path
        entirely.
        """
        self.session = BleLinkSession()
        self.auth_context = None
        self.last_response = None
        logging.info("Python BLE auth session started")

    def handle_link_packet(self, data: bytes) -> tuple[int, bytes]:
        """
        Process one packet during the authentication handshake.
        """
        if not data:
            raise ValueError("Handshake packet cannot be empty.")

        response, status = self.session.process(bytes(data))
        self.auth_context = self.session.md5_value
        self.last_response = response
        return status, bytes(response or b"")

    def encrypt(self, plaintext: bytes) -> bytes:
        return self.session.encrypt(bytes(plaintext))

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self.session.decrypt(bytes(ciphertext))
