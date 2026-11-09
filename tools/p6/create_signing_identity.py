"""Create a local, DPAPI-protected signing identity, without publishing it."""
import argparse
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from companion.contracts import canonical
from companion.release.private_key import protect
from companion.release.signing import trust_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    private_path = args.output / "maintainer.dpapi"
    public_path = args.output / "trust.json"
    if private_path.exists() or public_path.exists():
        raise FileExistsError("已有签名身份，不覆盖或自动轮换")
    key = Ed25519PrivateKey.generate()
    with private_path.open("xb") as stream:
        stream.write(protect(key.private_bytes_raw()))
    public_path.write_bytes(canonical({"schema_version": 1, "keys": [trust_record(key, test_only=False)]}))
    print(str(public_path))


if __name__ == "__main__":
    main()
