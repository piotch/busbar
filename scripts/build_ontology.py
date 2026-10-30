"""Compatibility entry point; prefer `busbar build-ontology`."""
from busbar.build_ontology import main

if __name__ == "__main__":
    raise SystemExit(main())
