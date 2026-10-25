"""Encrypted archive format (AES-256-GCM, scrypt key derivation).

Layout::

    b"RISENC1\\n" | uint32 big-endian header length | header JSON (UTF-8) | ciphertext+tag

The header (KDF parameters, salt, nonce and non-sensitive metadata such as
creation time) is authenticated as associated data, so tampering with either
the header or the ciphertext is detected on decryption.
"""

from __future__ import annotations

import base64
import json
import os
import struct
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from ris.errors import DecryptionError

MAGIC = b"RISENC1\n"
FORMAT_VERSION = 1
MIN_PASSPHRASE = 10
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1


def check_passphrase(passphrase: str) -> None:
    if len(passphrase or "") < MIN_PASSPHRASE:
        raise DecryptionError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters.")


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


def encrypt(data: bytes, passphrase: str, meta: dict[str, Any] | None = None) -> bytes:
    check_passphrase(passphrase)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = {
        "format_version": FORMAT_VERSION, "cipher": "AES-256-GCM", "kdf": "scrypt",
        "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
        "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
        "meta": meta or {},
    }
    hbytes = json.dumps(header, sort_keys=True).encode("utf-8")
    key = _derive(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    ct = AESGCM(key).encrypt(nonce, data, hbytes)
    return MAGIC + struct.pack(">I", len(hbytes)) + hbytes + ct


def read_header(blob: bytes) -> dict[str, Any]:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 4:
        raise DecryptionError("This is not an encrypted Resume Intelligence Studio archive.")
    (hlen,) = struct.unpack(">I", blob[len(MAGIC): len(MAGIC) + 4])
    if hlen > 64 * 1024:
        raise DecryptionError("The archive header is invalid.")
    start = len(MAGIC) + 4
    try:
        return json.loads(blob[start: start + hlen].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DecryptionError("The archive header is damaged.") from exc


def decrypt(blob: bytes, passphrase: str) -> tuple[bytes, dict[str, Any]]:
    header = read_header(blob)
    (hlen,) = struct.unpack(">I", blob[len(MAGIC): len(MAGIC) + 4])
    start = len(MAGIC) + 4
    hbytes = blob[start: start + hlen]
    ct = blob[start + hlen:]
    if header.get("format_version", 0) > FORMAT_VERSION:
        raise DecryptionError("This archive was written by a newer version of the application.")
    try:
        salt = base64.b64decode(header["salt"])
        nonce = base64.b64decode(header["nonce"])
        n, r, p = int(header["n"]), int(header["r"]), int(header["p"])
    except (KeyError, ValueError, TypeError) as exc:
        raise DecryptionError("The archive header is incomplete.") from exc
    if not (2 ** 10 <= n <= 2 ** 20 and 1 <= r <= 32 and 1 <= p <= 16):
        raise DecryptionError("The archive uses unsupported key-derivation parameters.")
    key = _derive(passphrase or "", salt, n, r, p)
    try:
        return AESGCM(key).decrypt(nonce, ct, hbytes), header
    except InvalidTag as exc:
        raise DecryptionError("Wrong passphrase, or the archive has been altered.") from exc


def is_encrypted(blob_head: bytes) -> bool:
    return blob_head.startswith(MAGIC)
