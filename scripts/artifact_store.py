"""Compatibility import; new code should use busbar.artifact_store."""
from busbar.artifact_store import artifact_bytes, manifest_reference, storage_reference

__all__ = ["artifact_bytes", "manifest_reference", "storage_reference"]
