"""Capture every declared source independently and write a compact run summary."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from rdflib import RDF

from .capture_catalogue import PUB, capture, load_declarations


def run(output, summary_path, storage_uri=None):
    graph, hashes = load_declarations()
    results = []
    for specification in sorted(map(str, graph.subjects(RDF.type, PUB.CaptureSpecification))):
        try:
            record, path = capture(graph, hashes, specification, output, storage_uri)
            comparison = record.get("comparison", {})
            result = {
                "specification": specification, "status": record["status"],
                "observation": record.get("manifest_uri", str(path)),
                "dataset_count": record.get("dataset_count"),
                "newly_listed": len(comparison.get("newly_listed", [])) if comparison else None,
                "no_longer_listed": len(comparison.get("no_longer_listed", [])) if comparison else None,
            }
            if record.get("error"):
                result["error"] = record["error"]
        except Exception as exc:
            result = {"specification": specification, "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(json.dumps(result))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps({
        "completed_at": datetime.now(timezone.utc).isoformat(), "sources": results,
    }, indent=2) + "\n")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.cwd() / "captures")
    parser.add_argument("--summary", type=Path, default=Path.cwd() / "build/capture-summary.json")
    parser.add_argument("--storage-uri")
    args = parser.parse_args(argv)
    results = run(args.output, args.summary, args.storage_uri)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write("## Catalogue observations\n\n| Source | Outcome | Datasets | Added | No longer listed |\n|---|---|---:|---:|---:|\n")
            for row in results:
                stream.write(f"| {row['specification']} | {row['status']} | {row.get('dataset_count')} | {row.get('newly_listed')} | {row.get('no_longer_listed')} |\n")
    return 0 if results and all(row["status"] == "success" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
