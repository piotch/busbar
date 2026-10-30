"""Compatibility entry point; prefer `busbar build-observations`."""
from busbar.build_observations import main

if __name__ == "__main__":
    raise SystemExit(main())
