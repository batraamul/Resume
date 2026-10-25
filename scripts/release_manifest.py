#!/usr/bin/env python3
"""Release tooling: build, sign and verify the update manifest; extract release notes; create signing keys.

    python scripts/release_manifest.py build  --dir dist/release --version 1.1.0 --tag v1.1.0 [--repo owner/name]
    python scripts/release_manifest.py sign   --manifest dist/release/ris-update.json      # key from $RIS_UPDATE_SIGNING_KEY
    python scripts/release_manifest.py verify --manifest dist/release/ris-update.json
    python scripts/release_manifest.py notes  --version 1.1.0
    python scripts/release_manifest.py genkey --out signing-key.txt

The private key is read from the environment variable RIS_UPDATE_SIGNING_KEY (a GitHub Actions secret) or
from a file given with --key-file. It is never printed or written to the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PATTERNS = [
    (re.compile(r"-windows-x64-setup\.exe$"), "windows-x64", "windows-installer"),
    (re.compile(r"-macos-arm64\.dmg$"), "macos-arm64", "macos-dmg"),
    (re.compile(r"-macos-x64\.dmg$"), "macos-x64", "macos-dmg"),
    (re.compile(r"-linux-x86_64\.tar\.gz$"), "linux-x86_64", "linux-tar"),
    (re.compile(r"_amd64\.deb$"), "linux-x86_64", "linux-deb"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def changelog_notes(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else f"Resume Intelligence Studio {version}."


def cmd_build(args) -> int:
    from ris.update.keys import REPOSITORY
    from ris.update.manifest import UpdateAsset, build_manifest

    repo = args.repo or REPOSITORY
    folder = Path(args.dir)
    assets = []
    sums = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("ris-update") or path.name == "SHA256SUMS.txt":
            continue
        digest = sha256(path)
        sums.append(f"{digest}  {path.name}")
        for rx, plat, kind in PATTERNS:
            if rx.search(path.name):
                assets.append(UpdateAsset(platform=plat, kind=kind, name=path.name,
                                          url=f"https://github.com/{repo}/releases/download/{args.tag}/{path.name}",
                                          sha256=digest, size=path.stat().st_size))
    if not assets:
        print("No installer files found.", file=sys.stderr)
        return 1
    released = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = build_manifest(args.version, released, changelog_notes(args.version.lstrip("v")), assets, repo)
    (folder / "ris-update.json").write_bytes(data)
    (folder / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"Manifest with {len(assets)} installer(s) written to {folder / 'ris-update.json'}")
    return 0


def _key(args):
    from ris.update.manifest import load_private_key

    if args.key_file:
        text = Path(args.key_file).read_text(encoding="utf-8")
    else:
        text = os.environ.get("RIS_UPDATE_SIGNING_KEY", "")
    if not text.strip():
        print("No signing key: set RIS_UPDATE_SIGNING_KEY or pass --key-file.", file=sys.stderr)
        sys.exit(2)
    return load_private_key(text)


def cmd_sign(args) -> int:
    from ris.update import keys
    from ris.update.manifest import sign, verify_manifest

    manifest = Path(args.manifest)
    data = manifest.read_bytes()
    sig = sign(data, _key(args))
    # Refuses to write a signature the application would not accept.
    verify_manifest(data, sig, keys.PUBLIC_KEYS, json.loads(data).get("repository", ""))
    Path(str(manifest) + ".sig").write_bytes(sig)
    print(f"Signed {manifest.name} (verified against the application's public key).")
    return 0


def cmd_verify(args) -> int:
    from ris.update import keys
    from ris.update.manifest import UpdateError, verify_manifest

    manifest = Path(args.manifest)
    try:
        m = verify_manifest(manifest.read_bytes(), Path(args.sig or (str(manifest) + ".sig")).read_bytes(),
                            keys.PUBLIC_KEYS, json.loads(manifest.read_bytes()).get("repository", ""))
    except UpdateError as exc:
        print(f"INVALID: {exc.user_message}", file=sys.stderr)
        return 1
    print(f"Valid signature: version {m.version}, {len(m.assets)} asset(s): " + ", ".join(a.name for a in m.assets))
    if args.dir:
        bad = [a.name for a in m.assets if sha256(Path(args.dir) / a.name) != a.sha256]
        if bad:
            print("Checksum mismatch: " + ", ".join(bad), file=sys.stderr)
            return 1
        print("All installer checksums match.")
    return 0


def cmd_notes(args) -> int:
    print(changelog_notes(args.version.lstrip("v")))
    return 0


def cmd_genkey(args) -> int:
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    out = Path(args.out)
    if out.exists():
        print(f"{out} already exists; refusing to overwrite a key.", file=sys.stderr)
        return 1
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(base64.b64encode(raw).decode() + "\n")
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("Private key written to", out, "(store it as the RIS_UPDATE_SIGNING_KEY secret, then delete the file).")
    print("Public key for ris/update/keys.py:", base64.b64encode(pub).decode())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dir", required=True)
    b.add_argument("--version", required=True)
    b.add_argument("--tag", required=True)
    b.add_argument("--repo", default="")
    s = sub.add_parser("sign")
    s.add_argument("--manifest", required=True)
    s.add_argument("--key-file", default="")
    v = sub.add_parser("verify")
    v.add_argument("--manifest", required=True)
    v.add_argument("--sig", default="")
    v.add_argument("--dir", default="")
    n = sub.add_parser("notes")
    n.add_argument("--version", required=True)
    g = sub.add_parser("genkey")
    g.add_argument("--out", required=True)
    args = ap.parse_args()
    return {"build": cmd_build, "sign": cmd_sign, "verify": cmd_verify, "notes": cmd_notes,
            "genkey": cmd_genkey}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
