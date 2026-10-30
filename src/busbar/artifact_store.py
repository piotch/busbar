"""Resolve archived evidence locally while keeping published references portable."""
import hashlib
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlparse


def storage_reference(base, relative):
    parsed = urlparse(base)
    if parsed.scheme != "s3" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Storage base must be an s3://bucket/prefix URI")
    if parsed.username or parsed.password or ".." in PurePosixPath(parsed.path).parts:
        raise ValueError("Invalid storage base")
    return base.rstrip("/") + "/" + relative


def artifact_bytes(record, observation_path):
    relative = record.get("artifact_path")
    if relative:
        if not re.fullmatch(r"objects/sha256/[0-9a-f]{64}\.rdf", relative):
            raise ValueError("Invalid capture-relative artifact path")
        path = observation_path.parent.parent / relative
    else:
        parsed = urlparse(record["artifact_uri"])
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError("A capture-relative artifact_path is required for nonlocal URIs")
        path = Path(unquote(parsed.path))
    content = path.read_bytes()
    if "sha256:" + hashlib.sha256(content).hexdigest() != record["content_hash"]:
        raise ValueError("Artifact SHA-256 mismatch")
    return content


def manifest_reference(record, observation_path):
    return record.get("manifest_uri") or observation_path.resolve().as_uri()
