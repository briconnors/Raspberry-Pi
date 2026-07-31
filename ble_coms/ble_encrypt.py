import logging

import bluetti_crypt


BLE_LINK_STATUS_COMPLETE = 4


class BleEncrypt:
    def __init__(self) -> None:
        self.crypto_client = None

    def start(self) -> None:
        """
        Start a fresh Bluetti crypto session.

        Bluetti's reference code uses the direct constructor.
        This should be run with Python 3.12, not Python 3.14.
        """
        self.crypto_client = bluetti_crypt.BluettiCrypt()

        if self.crypto_client is None:
            raise RuntimeError(
                "BluettiCrypt() failed to create a crypto client."
            )

        logging.info(
            "Bluetti crypto module started, version=%s",
            self.crypto_client.get_software_version(),
        )

    def handle_link_packet(
        self,
        data: bytes,
    ) -> tuple[int, bytes]:
        """
        Process one packet during the authentication handshake.

        Returns:
            status: Bluetti authentication state.
            response: Bytes to send directly back to the device.
        """
        if self.crypto_client is None:
            raise RuntimeError(
                "Crypto client has not been started."
            )

        if not data:
            raise ValueError(
                "Handshake packet cannot be empty."
            )

        logging.info(
            "Handshake input: %s",
            data.hex(),
        )

        result = (
            self.crypto_client
            .ble_crypt_link_handler(bytes(data))
        )

        if not isinstance(result, (list, tuple)):
            raise RuntimeError(
                "Unexpected ble_crypt_link_handler return type: "
                f"{type(result).__name__}"
            )

        if len(result) != 2:
            raise RuntimeError(
                "Unexpected ble_crypt_link_handler result length: "
                f"{len(result)}"
            )

        message, status = result

        response = bytes(message)
        status = int(status)

        logging.info(
            "Handshake status=%s response=%s",
            status,
            response.hex(),
        )

        return status, response

    def encrypt(
        self,
        plaintext: bytes,
    ) -> bytes:
        """
        Encrypt a valid plaintext Bluetti protocol command.
        """
        if self.crypto_client is None:
            raise RuntimeError(
                "Crypto client has not been started."
            )

        if not plaintext:
            raise ValueError(
                "Plaintext command cannot be empty."
            )

        logging.info(
            "Encrypting plaintext: %s",
            plaintext.hex(),
        )

        encrypted = bytes(
            self.crypto_client.encrypt_data(
                bytes(plaintext)
            )
        )

        if not encrypted:
            raise RuntimeError(
                "encrypt_data() returned an empty result."
            )

        logging.info(
            "Encrypted result: %s",
            encrypted.hex(),
        )

        return encrypted

    def decrypt(
        self,
        ciphertext: bytes,
    ) -> bytes:
        """
        Decrypt incoming Bluetti data after authentication
        has reached status 4.
        """
        if self.crypto_client is None:
            raise RuntimeError(
                "Crypto client has not been started."
            )

        if not ciphertext:
            raise ValueError(
                "Ciphertext cannot be empty."
            )

        logging.info(
            "Decrypting ciphertext: %s",
            ciphertext.hex(),
        )

        plaintext = bytes(
            self.crypto_client.decrypt_data(
                bytes(ciphertext)
            )
        )

        if not plaintext:
            raise RuntimeError(
                "decrypt_data() returned an empty result."
            )

        logging.info(
            "Decrypted result: %s",
            plaintext.hex(),
        )

        return plaintext