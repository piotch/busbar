"""Compatibility entry point; prefer `busbar capture`."""
from busbar.capture_catalogue import main

if __name__ == "__main__":
    raise SystemExit(main())
