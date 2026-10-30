"""Compatibility entry point; prefer `busbar bucket`."""
from busbar.bucket_store import main

if __name__ == "__main__":
    raise SystemExit(main())
