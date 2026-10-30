"""Compatibility entry point; prefer `busbar capture-all`."""
from busbar.capture_all import main

if __name__ == "__main__":
    raise SystemExit(main())
