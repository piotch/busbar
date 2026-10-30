"""Command-line interface for Busbar."""
import argparse
from importlib import import_module

COMMANDS = {
    "capture": ("capture_catalogue", "Capture one source or validate declarations"),
    "capture-all": ("capture_all", "Capture all declared sources"),
    "build-observations": ("build_observations", "Export named observation graphs as TriG"),
    "build-ontology": ("build_ontology", "Export a flat RDF/XML viewer ontology"),
    "bucket": ("bucket_store", "Manage optional S3-compatible storage"),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        commands.add_parser(name, help=help_text, add_help=False)
    args, remaining = parser.parse_known_args(argv)
    module = import_module(f".{COMMANDS[args.command][0]}", package="busbar")
    return module.main(remaining)
