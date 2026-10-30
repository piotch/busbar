"""Read bundled RDF resources, or their canonical files in an editable checkout."""
from importlib.resources import files
from pathlib import Path

from rdflib import Graph


def source_root():
    """Return the source checkout only when running directly from its src tree."""
    root = Path(__file__).resolve().parents[2]
    if (root / "src/busbar/resources.py").resolve() == Path(__file__).resolve() and (root / "pyproject.toml").is_file():
        return root
    return None


def data_root():
    bundled = files("busbar").joinpath("data")
    if bundled.is_dir():
        return bundled
    # Hatch editable installs expose Python modules in src/; RDF remains at the
    # repository root so there is one canonical, Git-managed copy of each file.
    root = source_root()
    if root is not None:
        return root
    raise FileNotFoundError("Busbar's bundled RDF resources are missing")


def load_graph(name, *, root=None):
    """Load a Turtle resource into a fresh graph (no network access)."""
    resource = (data_root() if root is None else root).joinpath(name)
    return Graph().parse(data=resource.read_bytes(), format="turtle")


def load_catalogue():
    """Return the bundled curated catalogue as a new rdflib.Graph."""
    return load_graph("catalogue.ttl")


def load_ontology():
    """Return the bundled grid-domain ontology as a new rdflib.Graph."""
    return load_graph("busbar-ontology.ttl")


def turtle_files(directory, prefix=""):
    """Yield stable relative names and resources, including zip Traversables."""
    for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
        name = prefix + child.name
        if child.is_dir():
            yield from turtle_files(child, name + "/")
        elif child.name.endswith(".ttl"):
            yield name, child
