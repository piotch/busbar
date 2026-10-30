import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from busbar import bucket_store as store


class S3Error(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.puts = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise S3Error("404")
        return {}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise S3Error("PreconditionFailed")
        self.objects[key] = kwargs["Body"]
        self.puts.append(kwargs)

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):
        # Separate pages exercise iteration over all historical objects.
        for key, content in sorted(self.objects.items()):
            if key.startswith(Prefix):
                yield {"Contents": [{"Key": key, "Size": len(content)}]}


class BucketStoreTests(unittest.TestCase):
    def setUp(self):
        self.settings = store.Settings("https://s3.example", "busbar", "catalogue-history")
        self.client = MemoryS3()

    def history(self, root):
        content = b"original response bytes"
        digest = hashlib.sha256(content).hexdigest()
        artifact = f"objects/sha256/{digest}.rdf"
        path = root / artifact
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        relative = "observations/one.json"
        record = {"status": "success", "artifact_path": artifact,
                  "artifact_uri": self.settings.uri + "/" + artifact,
                  "content_hash": "sha256:" + digest,
                  "manifest_uri": self.settings.uri + "/" + relative}
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(record))
        return artifact

    def test_endpoint_without_scheme_and_defaults(self):
        with patch.dict(os.environ, {"BUCKET_URL": "fsn1.your-objectstorage.com"}, clear=True):
            settings = store.Settings.from_env()
        self.assertEqual(settings.endpoint, "https://fsn1.your-objectstorage.com")
        self.assertEqual(settings.uri, "s3://busbar/catalogue-history")

    def test_unsafe_configuration_is_rejected(self):
        for env in ({"BUCKET_URL": "http://s3.example"},
                    {"BUCKET_URL": "https://user:secret@s3.example"},
                    {"BUCKET_URL": "s3.example", "BUCKET_PREFIX": "../escape"}):
            with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                store.Settings.from_env()

    def test_history_roundtrip_is_append_only_and_uses_conditional_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.history(root / "source")
            self.assertEqual(store.push(self.client, self.settings, root / "source"), 2)
            self.assertTrue(all(p["IfNoneMatch"] == "*" for p in self.client.puts))
            self.assertEqual(store.push(self.client, self.settings, root / "source"), 0)
            self.assertEqual(store.pull(self.client, self.settings, root / "restored"), 2)
            for path in (root / "source").rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (root / "restored" / path.relative_to(root / "source")).read_bytes())

    def test_archive_collision_is_never_overwritten(self):
        self.client.objects[self.settings.key("observations/one.json")] = b"previous"
        with self.assertRaisesRegex(ValueError, "overwrite"):
            store.put_immutable(self.client, self.settings, "observations/one.json", b"different")
        self.assertEqual(len(self.client.puts), 0)

    def test_nonportable_manifests_rejected_before_remote_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.history(root)
            path = root / "observations/one.json"
            record = json.loads(path.read_text())
            record["artifact_uri"] = "file:///some/laptop/capture.rdf"
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "artifact_uri"):
                store.push(self.client, self.settings, root)
        self.assertEqual(len(self.client.puts), 0)

    def test_unsafe_remote_keys_are_rejected(self):
        self.client.objects[self.settings.key("observations/../../escape.json")] = b"{}"
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "unsafe"):
            store.pull(self.client, self.settings, Path(directory))

    def test_failed_run_cannot_replace_latest_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "capture-summary.json").write_text(json.dumps({"sources": [{"status": "failed"}]}))
            with self.assertRaisesRegex(ValueError, "successful"):
                store.publish(self.client, self.settings, root, "run-1")
        self.assertEqual(len(self.client.puts), 0)

    def test_publish_updates_latest_only_after_versioned_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "capture-summary.json").write_text(json.dumps({"sources": [{"status": "success"}]}))
            (root / "observations.trig").write_text("# history")
            (root / "news-catalogues.owl").write_text("<rdf/>")
            index = store.publish(self.client, self.settings, root, "run-1")
        self.assertEqual(self.client.puts[-1]["Key"], self.settings.key("exports/latest.json"))
        self.assertEqual(len(index["files"]), 3)
        self.assertNotIn("IfNoneMatch", self.client.puts[-1])


if __name__ == "__main__":
    unittest.main()
