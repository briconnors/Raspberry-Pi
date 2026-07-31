from __future__ import annotations

from dataclasses import dataclass, field

from .aes import (
    generate_aes_key,
    iot_communciate_aes_cbc_decrypt,
    iot_communciate_aes_cbc_encrypt,
)
from .authentication import AUTH_STATUS_ECDH, proc_authen
from .ecdh import (
    proc_ecdh,
)
from .modbus import modbus_format_check


@dataclass
class BleLinkSession:
    """Python implementation of the native BLE link state machine."""

    state: int = 1
    md5_value: bytes | None = None
    handshake_key: bytes | None = None
    shared_secret: bytes | None = None
    private_key: object | None = None
    history: list[bytes] = field(default_factory=list)

    def process(self, packet: bytes) -> tuple[bytes | None, int]:
        if self.state == 1: #initial authentication
            response, md5_value, status = proc_authen(packet)
            if md5_value is not None:
                self.md5_value = md5_value
                self.handshake_key = generate_aes_key(md5_value)
            if status == AUTH_STATUS_ECDH:
                self.state = AUTH_STATUS_ECDH
        elif self.state == 2: #ECDH key agreement
            response, status = proc_ecdh(self, packet)
        elif self.state == 3: #serial - number validation
            plaintext = self.decrypt(packet)
            if modbus_format_check(plaintext) < 0:
                raise ValueError("Serial-number response is not valid Modbus")
            response, status = None, 4
            self.state = 4 #connection is ready
        else:
            return None, 4

        if response is not None:
            self.history.append(response)
        return response, status

    @property
    def authenticated(self) -> bool:
        return self.state == 4

    def encrypt(self, plaintext: bytes) -> bytes:
        if self.shared_secret is None:
            raise RuntimeError("ECDH shared secret is unavailable")
        return iot_communciate_aes_cbc_encrypt(
            plaintext,
            self.shared_secret,
        )

    def decrypt(self, ciphertext: bytes) -> bytes:
        if self.shared_secret is None:
            raise RuntimeError("ECDH shared secret is unavailable")
        return iot_communciate_aes_cbc_decrypt(
            ciphertext,
            self.shared_secret,
        )
