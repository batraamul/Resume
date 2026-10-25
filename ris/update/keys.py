"""Public keys that may sign update manifests (Ed25519, raw 32-byte keys in base64).

Only public keys belong here. The matching private key is stored as the repository secret
``RIS_UPDATE_SIGNING_KEY`` (and by the maintainer, offline). To rotate keys, add the new public key,
release a version signed with the old key, then sign later releases with the new key and remove the old one.
"""

PUBLIC_KEYS: tuple[str, ...] = (
    "EV7QZWtR4Rw9nE34+WCC+rzo0LFrBXO/gJwNB3Y5iCA=",
)

#: The GitHub repository that publishes releases.
REPOSITORY = "batraamul/Resume"
