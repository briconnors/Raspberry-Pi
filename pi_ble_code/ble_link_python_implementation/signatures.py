"""ECDSA helpers mirrored from the native Bluetti crypto module."""

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils


SIGN_PRIVATE_KEY = bytes.fromhex(
    "4f19a16e3e87bdd9bd24d3e5495b8804"
    "1511943cbc8b969ade9641d0f56af337"
)
VERIFY_PUBLIC_KEY = bytes.fromhex(
    "a73abf5d2232c8c1c72e68304343c272"
    "495e3a8fd6f30ea96de2f4b3ce60b251"
    "ee21ac667cf8a71e18b46b664eaeffe3"
    "c489f24f695b6411db7e22ccc85a8594"
)


def _private_key() -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(
        int.from_bytes(SIGN_PRIVATE_KEY, "big"),
        ec.SECP256R1(),
    )


def _verify_key() -> ec.EllipticCurvePublicKey:
    x = int.from_bytes(VERIFY_PUBLIC_KEY[:32], "big")
    y = int.from_bytes(VERIFY_PUBLIC_KEY[32:], "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def pack_sign(data: bytes) -> bytes:
    """Return the native 64-byte raw P-256 signature, encoded as r || s."""
    digest = hashlib.sha256(data).digest()
    der = _private_key().sign(
        digest,
        ec.ECDSA(utils.Prehashed(hashes.SHA256())),
    )
    r, s = utils.decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def pack_verify(data: bytes, signature: bytes) -> bool:
    """Mirror BluettiCrypt::pack_verify for a raw r || s signature."""
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    digest = hashlib.sha256(data).digest()
    try:
        _verify_key().verify(
            utils.encode_dss_signature(r, s),
            digest,
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
    except InvalidSignature:
        return False
    return True

