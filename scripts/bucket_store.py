# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.36,<2", "python-dotenv>=1,<2"]
# ///
"""Persist catalogue history in a dedicated S3-compatible bucket prefix.

pull/check are read-only remotely. push writes immutable history; publish writes
versioned exports and updates exports/latest.json only after all files upload.
No operation deletes remote objects or changes bucket policy.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

from artifact_store import storage_reference

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    endpoint: str
    bucket: str = "busbar"
    prefix: str = "catalogue-history"
    region: str = "fsn1"

    @classmethod
    def from_env(cls):
        endpoint = os.environ.get("BUCKET_URL", "").strip()
        if "://" not in endpoint:
            endpoint = "https://" + endpoint
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("BUCKET_URL must be an HTTPS endpoint, not a bucket path or credential URL")
        bucket = os.environ.get("BUCKET_NAME", "busbar")
        prefix = os.environ.get("BUCKET_PREFIX", "catalogue-history").strip("/")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", bucket):
            raise ValueError("Invalid BUCKET_NAME")
        if not prefix or any(p in (".", "..", "") for p in prefix.split("/")) or "\\" in prefix:
            raise ValueError("BUCKET_PREFIX must be a nonempty safe prefix")
        return cls(endpoint.rstrip("/"), bucket, prefix, os.environ.get("BUCKET_REGION", "fsn1"))

    @property
    def uri(self):
        return f"s3://{self.bucket}/{self.prefix}"

    def key(self, relative):
        return self.prefix + "/" + relative


def client_for(settings):
    import boto3
    from botocore.config import Config
    access = os.environ.get("BUCKET_ACCESS_KEY")
    secret = os.environ.get("BUCKET_SECRET_KEY")
    if not access or not secret:
        raise ValueError("BUCKET_ACCESS_KEY and BUCKET_SECRET_KEY are required")
    return boto3.client(
        "s3", endpoint_url=settings.endpoint, region_name=settings.region,
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(connect_timeout=15, read_timeout=60, retries={"max_attempts": 4, "mode": "standard"},
                      request_checksum_calculation="when_required", response_checksum_validation="when_required",
                      s3={"addressing_style": "path"}),
    )


def error_code(exc):
    return str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))


def read_remote(client, settings, relative):
    body = client.get_object(Bucket=settings.bucket, Key=settings.key(relative))["Body"]
    try:
        content = body.read(MAX_BYTES + 1)
    finally:
        body.close()
    if len(content) > MAX_BYTES:
        raise ValueError("Remote file exceeds the 50 MiB limit")
    return content


def put_immutable(client, settings, relative, content, content_type="application/octet-stream"):
    digest = hashlib.sha256(content).hexdigest()
    try:
        client.head_object(Bucket=settings.bucket, Key=settings.key(relative))
    except Exception as exc:
        if error_code(exc) not in ("404", "NoSuchKey", "NotFound"):
            raise
    else:
        if read_remote(client, settings, relative) != content:
            raise ValueError("Refusing to overwrite different archived content")
        return False
    try:
        client.put_object(Bucket=settings.bucket, Key=settings.key(relative), Body=content,
                          ContentType=content_type, Metadata={"sha256": digest}, IfNoneMatch="*")
    except Exception as exc:
        if error_code(exc) not in ("412", "PreconditionFailed"):
            raise
        if read_remote(client, settings, relative) != content:
            raise ValueError("Concurrent archive write has different content") from exc
        return False
    return True


def valid_relative(relative, kind):
    if kind == "objects":
        return bool(re.fullmatch(r"objects/sha256/[0-9a-f]{64}\.rdf", relative))
    return bool(re.fullmatch(r"observations/[A-Za-z0-9_.+-]+\.json", relative))


def validate_history(settings, relative, content):
    if relative.startswith("objects/"):
        digest = PurePosixPath(relative).stem
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Archived object SHA-256 mismatch")
        return
    record = json.loads(content)
    if record.get("status") not in ("success", "failed"):
        raise ValueError("Invalid observation status")
    if record.get("manifest_uri") != storage_reference(settings.uri, relative):
        raise ValueError("Observation needs a portable manifest_uri matching this bucket prefix")
    if record.get("artifact_uri"):
        artifact_path = record.get("artifact_path", "")
        if not valid_relative(artifact_path, "objects"):
            raise ValueError("Observation needs a safe artifact_path")
        if record["artifact_uri"] != storage_reference(settings.uri, artifact_path):
            raise ValueError("Observation artifact_uri does not match this bucket prefix")
        if record.get("content_hash") != "sha256:" + PurePosixPath(artifact_path).stem:
            raise ValueError("Observation hash and artifact path disagree")
    elif record["status"] == "success":
        raise ValueError("Successful observation has no artifact")


def pull(client, settings, output):
    count = 0
    for kind, prefix in (("objects", "objects/sha256/"), ("observations", "observations/")):
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=settings.bucket, Prefix=settings.key(prefix))
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.startswith(settings.prefix + "/"):
                    raise ValueError("Unexpected key outside archive prefix")
                relative = key[len(settings.prefix) + 1:]
                if not valid_relative(relative, kind):
                    raise ValueError("Unexpected or unsafe archive key")
                if obj.get("Size", 0) > MAX_BYTES:
                    raise ValueError("Remote file exceeds capture limit")
                content = read_remote(client, settings, relative)
                validate_history(settings, relative, content)
                path = output / relative
                if path.exists():
                    if path.read_bytes() != content:
                        raise ValueError("Local archive conflicts with remote history; use a clean output directory")
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(path.suffix + ".tmp")
                    temporary.write_bytes(content)
                    temporary.replace(path)
                count += 1
    return count


def push(client, settings, output):
    files = sorted(output.glob("objects/sha256/*.rdf")) + sorted(output.glob("observations/*.json"))
    # Validate the whole archive before writing anything remotely.
    for path in files:
        relative = path.relative_to(output).as_posix()
        kind = "objects" if relative.startswith("objects/") else "observations"
        if not valid_relative(relative, kind):
            raise ValueError("Unexpected archive filename")
        validate_history(settings, relative, path.read_bytes())
        if kind == "observations":
            record = json.loads(path.read_text())
            if record.get("artifact_path") and not (output / record["artifact_path"]).is_file():
                raise ValueError("Observation references a missing local artifact")
    written = 0
    # Objects precede manifests, so visible observations reference durable evidence.
    for path in files:
        relative = path.relative_to(output).as_posix()
        content_type = "application/json" if path.suffix == ".json" else "application/octet-stream"
        written += put_immutable(client, settings, relative, path.read_bytes(), content_type)
    return written


def publish(client, settings, build, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run identifier")
    summary = json.loads((build / "capture-summary.json").read_text())
    if not summary.get("sources") or any(r["status"] != "success" for r in summary["sources"]):
        raise ValueError("Only successful capture runs can publish latest exports")
    files = {"observations.trig": "application/trig", "news-catalogues.owl": "application/rdf+xml",
             "capture-summary.json": "application/json"}
    # Require all exports before any publish write.
    contents = {name: (build / name).read_bytes() for name in files}
    index = {"run_id": run_id, "published_at": datetime.now(timezone.utc).isoformat(), "files": {}}
    for name, content in contents.items():
        relative = f"exports/{run_id}/{name}"
        put_immutable(client, settings, relative, content, files[name])
        index["files"][name] = {"uri": storage_reference(settings.uri, relative),
                                 "sha256": hashlib.sha256(content).hexdigest()}
    client.put_object(Bucket=settings.bucket, Key=settings.key("exports/latest.json"),
                      Body=(json.dumps(index, indent=2) + "\n").encode(), ContentType="application/json")
    return index


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "pull", "push", "publish"])
    parser.add_argument("--captures", type=Path, default=ROOT / "captures")
    parser.add_argument("--build", type=Path, default=ROOT / "build")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        client = client_for(settings)
        if args.command == "check":
            client.head_bucket(Bucket=settings.bucket)
            print("Bucket is accessible (read-only check; write capability not tested)")
        elif args.command == "pull":
            print(f"Restored {pull(client, settings, args.captures)} history files")
        elif args.command == "push":
            print(f"Stored {push(client, settings, args.captures)} new history files")
        else:
            if not args.run_id:
                raise ValueError("publish requires --run-id")
            publish(client, settings, args.build, args.run_id)
            print("Published versioned exports and latest index")
        return 0
    except Exception as exc:
        # Never print SDK request dumps or credential-bearing configuration.
        print(f"Storage operation failed: {type(exc).__name__} ({error_code(exc) or 'configuration/integrity error'})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
