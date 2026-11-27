"""Check a series file against a schema version declared in definitions/.

The schema (W3C CSVW) states the publisher's columns Busbar uses, their datatypes,
the markers the publisher writes for "no value", and, with SHACL's sh:in, the
values a column may take (CSVW has no list of allowed values), and with
sh:minInclusive / sh:maxInclusive the range of a numeric column. Column titles, null markers
and controlled values are compared ignoring case and repeated spaces: publishers
change capitalisation between editions, the meaning stays the same. Declared
columns are found by title wherever they are; the file's other columns are
ignored, so a column the publisher adds goes unnoticed.

The check only reads the file. It changes nothing and records nothing; what to
do with a file that does not conform is the pipeline's decision. Files can hold
personal data, so the report shows sample values only for columns that failed a
datatype or allowed-value check.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import sys
import unicodedata

from rdflib import BNode, Namespace, RDF, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, SH, SKOS, XSD

from .capture_catalogue import load_declarations

CSVW = Namespace("http://www.w3.org/ns/csvw#")
SAMPLES = 3
NUMBERS = {
    "decimal": re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)"),
    "integer": re.compile(r"[+-]?\d+"),
}
# CSVW date formats use Unicode LDML field patterns.
DATE_FIELDS = {"yyyy": "%Y", "MM": "%m", "dd": "%d", "HH": "%H", "mm": "%M", "ss": "%S"}
DEFAULT_DATE_FORMATS = {"date": "yyyy-MM-dd", "datetime": "yyyy-MM-ddTHH:mm:ss"}


def normalise(text):
    """The single comparison rule: Unicode-compatible form, spaces collapsed, case ignored."""
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def strptime_format(pattern):
    return re.sub("|".join(DATE_FIELDS), lambda match: DATE_FIELDS[match.group()], pattern)


def allowed_values(graph, column, base):
    """Numbers are compared by value (11 and 11.0 are the same voltage), text by normalised form."""
    values = graph.value(column, SH["in"])
    if values is None:
        return None
    if base in NUMBERS:
        return {Decimal(str(value)) for value in Collection(graph, values)}
    return {normalise(str(value)) for value in Collection(graph, values)}


def bound(graph, column, predicate):
    value = graph.value(column, predicate)
    return Decimal(str(value)) if value is not None else None


def datatype(graph, column):
    node = graph.value(column, CSVW.datatype)
    if node is None:
        return "string", None
    if isinstance(node, BNode):
        base = str(graph.value(node, CSVW.base) or "string")
        # Namespace is a str: CSVW.format would be str.format.
        pattern = graph.value(node, CSVW["format"])
        return base, str(pattern) if pattern is not None else None
    if isinstance(node, URIRef) and str(node).startswith(str(XSD)):
        return str(node)[len(str(XSD)):], None
    raise ValueError(f"Unsupported datatype {node} on {column}")


def column_name(graph, column):
    """The standard name is the notation of the concept the column is about
    (dct:subject); a column without one is named after the end of its IRI."""
    concept = graph.value(column, DCTERMS.subject)
    notation = graph.value(concept, SKOS.notation) if concept is not None else None
    return str(notation) if notation is not None else str(column).rstrip("/").rpartition("/")[2]


def load_schema(graph, schema):
    if (schema, RDF.type, CSVW.Schema) not in graph:
        raise ValueError(f"No CSVW schema declared as {schema}")
    columns = []
    for column in Collection(graph, graph.value(schema, CSVW.column)):
        base, pattern = datatype(graph, column)
        if base in DEFAULT_DATE_FORMATS:
            pattern = strptime_format(pattern or DEFAULT_DATE_FORMATS[base])
        elif base != "string" and base not in NUMBERS:
            raise ValueError(f"Unsupported datatype {base} on {column}")
        minimum, maximum = bound(graph, column, SH.minInclusive), bound(graph, column, SH.maxInclusive)
        if base not in NUMBERS and (minimum is not None or maximum is not None):
            raise ValueError(f"A range is only allowed on a numeric column, not on {column}")
        columns.append({
            "name": column_name(graph, column),
            "titles": {normalise(str(title)) for title in graph.objects(column, CSVW.titles)},
            "base": base,
            "format": pattern,
            "required": bool(graph.value(column, CSVW.required)),
            "allowed": allowed_values(graph, column, base),
            "minimum": minimum,
            "maximum": maximum,
        })
    return {
        "schema": str(schema),
        "nulls": {normalise(str(marker)) for marker in graph.objects(schema, CSVW.null)},
        "columns": columns,
    }


def valid_value(column, value):
    base = column["base"]
    if base in NUMBERS:
        return NUMBERS[base].fullmatch(value) is not None
    if column["format"] is not None:
        try:
            datetime.strptime(value, column["format"])
        except ValueError:
            return False
    return True


def locate_columns(schema, header):
    """Find each declared column by title, in any order; other columns are ignored."""
    titles = [normalise(title) for title in header]
    positions, problems = [], []
    for column in schema["columns"]:
        matches = [position for position, title in enumerate(titles) if title in column["titles"]]
        if len(matches) == 1:
            positions.append(matches[0])
        else:
            problems.append({"column": column["name"], "found": "missing" if not matches else "several times"})
    return positions, problems


def is_allowed(column, value):
    if column["allowed"] is None:
        return True
    key = Decimal(value) if column["base"] in NUMBERS else normalise(value)
    return key in column["allowed"]


def check(schema, content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return {"schema": schema["schema"], "error": f"The file is not UTF-8 text ({exc})", "conforms": False}
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
    if not rows:
        return {"schema": schema["schema"], "error": "The file is empty", "conforms": False}
    header, records = rows[0], [row for row in rows[1:] if row]
    positions, header_problems = locate_columns(schema, header)
    report = {"schema": schema["schema"], "rows": len(records), "header": header_problems}
    if header_problems:
        report["conforms"] = False
        return report

    width = len(header)
    report["rows_of_wrong_length"] = sum(len(row) != width for row in records)
    problems = {}
    for position, column in zip(positions, schema["columns"]):
        counts, samples = Counter(), Counter()
        for row in records:
            if len(row) != width:
                continue
            value = row[position].strip()
            if normalise(value) in schema["nulls"]:
                if column["required"]:
                    counts["missing"] += 1
                continue
            if not valid_value(column, value):
                counts[f"not a {column['base']}" + (f" ({column['format']})" if column["format"] else "")] += 1
                samples[value] += 1
            elif not is_allowed(column, value):
                counts["not an allowed value"] += 1
                samples[value] += 1
            elif column["minimum"] is not None and Decimal(value) < column["minimum"]:
                counts[f"below {column['minimum']}"] += 1
                samples[value] += 1
            elif column["maximum"] is not None and Decimal(value) > column["maximum"]:
                counts[f"above {column['maximum']}"] += 1
                samples[value] += 1
        if counts:
            problems[column["name"]] = {
                "problems": dict(counts),
                "samples": [value for value, _ in samples.most_common(SAMPLES)],
            }
    report["columns"] = problems
    report["conforms"] = not problems and not report["rows_of_wrong_length"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="The CSV file to check")
    parser.add_argument("--schema", help="Schema version IRI (default: the only declared schema)")
    args = parser.parse_args(argv)
    graph, _ = load_declarations()
    if args.schema:
        schema = URIRef(args.schema)
    else:
        declared = sorted(graph.subjects(RDF.type, CSVW.Schema))
        if len(declared) != 1:
            parser.error("Several schemas are declared; name one with --schema")
        schema = declared[0]
    report = check(load_schema(graph, schema), args.file.read_bytes())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["conforms"] else 1


if __name__ == "__main__":
    sys.exit(main())
