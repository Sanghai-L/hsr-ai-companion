"""Ed25519 signatures over domain-separated canonical JSON."""
import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.knowledge.package import unique_object

DOMAIN = b"HSR-COMPANION-RELEASE-v1\x00"


def key_id(public):
    return hashlib.sha256(public).hexdigest()


def test_key():
    """Only a test identity. Never promote it to the production trust store."""
    key = Ed25519PrivateKey.generate()
    return key.private_bytes_raw(), trust_record(key, test_only=True)


def trust_record(key, *, test_only):
    public = key.public_key().public_bytes_raw()
    return {"key_id": key_id(public), "public_key": base64.b64encode(public).decode(), "test_only": test_only}


def sign(document, private):
    key = Ed25519PrivateKey.from_private_bytes(private)
    return {"algorithm": "Ed25519", "key_id": key_id(key.public_key().public_bytes_raw()),
            "value": base64.b64encode(key.sign(DOMAIN + canonical(document))).decode()}


def verify(document, signature, trusted_keys, *, allow_test=False):
    try:
        if not isinstance(document, dict) or not isinstance(signature, dict):
            raise ValueError()
        if set(signature) != {"algorithm", "key_id", "value"} or signature["algorithm"] != "Ed25519":
            raise ValueError()
        record = next((r for r in trusted_keys if r["key_id"] == signature["key_id"]), None)
        if record is None or type(record["test_only"]) is not bool:
            raise ValueError()
        if document.get("channel") not in {"test", "production"}:
            raise ValueError()
        if record["test_only"] != (document["channel"] == "test") or (record["test_only"] and not allow_test):
            raise ValueError()
        public = base64.b64decode(record["public_key"], validate=True)
        if key_id(public) != record["key_id"]:
            raise ValueError()
        Ed25519PublicKey.from_public_bytes(public).verify(
            base64.b64decode(signature["value"], validate=True), DOMAIN + canonical(document))
        return {"key_id": record["key_id"], "channel": document["channel"], "verified": True}
    except (InvalidSignature, ValueError, TypeError, KeyError, StopIteration) as error:
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布签名、签名者或发布通道不可信") from error


def load_trust(path):
    try:
        if path.stat().st_size > 65536:
            raise ValueError()
        value = json.loads(path.read_bytes(), object_pairs_hook=unique_object)
        if set(value) != {"schema_version", "keys"} or value["schema_version"] != 1 or not isinstance(value["keys"], list):
            raise ValueError()
        if len(value["keys"]) > 20 or len({r["key_id"] for r in value["keys"]}) != len(value["keys"]):
            raise ValueError()
        return value["keys"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CompanionError(ErrorCode.INVALID_INPUT, "本地发布信任配置不可用") from error
