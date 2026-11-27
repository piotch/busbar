import unittest

from busbar import check_edition
from busbar.capture_catalogue import load_declarations
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, SH

SCHEMA = URIRef("https://busbar.example/id/grid/uk/dno/enwl/schemas/ecr/v1")


class CheckEditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph, _ = load_declarations()
        cls.schema = check_edition.load_schema(graph, SCHEMA)
        cls.names = [column["name"] for column in cls.schema["columns"]]

    def header(self):
        # The publisher's columns: odd spacing, trailing spaces, and others we ignore.
        titles = [next(iter(column["titles"])).upper().replace(" ", "  ") + " " for column in self.schema["columns"]]
        return ["Export MPAN / MSID", *reversed(titles), "geopoint"]

    def row(self, values):
        return ["ignored", *reversed([values.get(name, "") for name in self.names]), "ignored"]

    def run_check(self, *rows, header=None):
        lines = [header or self.header(), *rows]
        content = "\ufeff" + "\n".join(";".join(f'"{cell}"' for cell in line) for line in lines) + "\n"
        return check_edition.check(self.schema, content.encode())

    def test_columns_take_the_notation_of_their_concept(self):
        self.assertEqual(self.names[:3], ["customer_name", "customer_site", "address_line_1"])
        self.assertIn("gsp", self.names)
        self.assertIn("accepted_export", self.names)

    def test_column_without_a_concept_is_named_after_its_iri(self):
        graph, _ = load_declarations()
        graph.remove((URIRef(f"{SCHEMA}/columns/grid-supply-point"), DCTERMS.subject, None))
        names = [column["name"] for column in check_edition.load_schema(graph, SCHEMA)["columns"]]
        self.assertIn("grid-supply-point", names)
        self.assertNotIn("gsp", names)

    def test_schema_lists_only_the_columns_busbar_uses(self):
        self.assertEqual(len(self.names), 20)
        self.assertIn("connection_status", self.names)
        self.assertNotIn("geopoint", self.names)

    def test_statuses_match_ignoring_case_and_spaces(self):
        report = self.run_check(
            self.row({"connection_status": "CONNECTED", "date_connected": "2016-03-01"}),
            self.row({"connection_status": " accepted  To Connect ", "date_accepted": "2023-09-14"}),
        )
        self.assertEqual(report["header"], [])
        self.assertEqual(report["columns"], {})
        self.assertTrue(report["conforms"])

    def test_unknown_status_is_reported(self):
        report = self.run_check(self.row({"connection_status": "ENERGISED"}), self.row({"connection_status": "ENERGISED"}))
        problem = report["columns"]["connection_status"]
        self.assertEqual(problem["problems"], {"not an allowed value": 2})
        self.assertEqual(problem["samples"], ["ENERGISED"])
        self.assertFalse(report["conforms"])

    def test_null_markers_ignore_case_but_required_column_must_be_filled(self):
        report = self.run_check(self.row({"connection_status": "data NOT available", "primary": "Data Not Available"}))
        self.assertEqual(report["columns"], {"connection_status": {"problems": {"missing": 1}, "samples": []}})

    def test_datatypes_and_date_formats(self):
        report = self.run_check(self.row({"connection_status": "Connected", "connected_export": "12,5", "date_accepted": "21/08/2023"}))
        self.assertEqual(set(report["columns"]), {"connected_export", "date_accepted"})
        self.assertEqual(report["columns"]["date_accepted"]["problems"], {"not a date (%Y-%m-%d)": 1})

    def test_coordinates_outside_the_british_national_grid_are_reported(self):
        report = self.run_check(
            self.row({"connection_status": "Connected", "easting": "350000", "northing": "1300000"}),
            self.row({"connection_status": "Connected", "easting": "-2.2", "northing": "1400000"}),
        )
        self.assertEqual(report["columns"], {
            "easting": {"problems": {"below 0": 1}, "samples": ["-2.2"]},
            "northing": {"problems": {"above 1300000": 1}, "samples": ["1400000"]},
        })

    def test_allowed_numbers_are_compared_by_value(self):
        report = self.run_check(*(self.row({"connection_status": "Connected", "voltage": value})
                                  for value in ("11", "11.0", "33.00", "0.4150", "6.6")))
        self.assertEqual(report["columns"], {})
        report = self.run_check(self.row({"connection_status": "Connected", "voltage": "11.5"}))
        self.assertEqual(report["columns"]["voltage"]["problems"], {"not an allowed value": 1})

    def test_file_that_is_not_utf8_or_empty_gets_a_report(self):
        for content in ("\xe9;\n".encode("latin-1"), b""):
            report = check_edition.check(self.schema, content)
            self.assertFalse(report["conforms"])
            self.assertIn("error", report)

    def test_range_on_a_text_column_is_rejected(self):
        graph, _ = load_declarations()
        graph.add((URIRef(f"{SCHEMA}/columns/postcode"), SH.minInclusive, Literal(0)))
        with self.assertRaisesRegex(ValueError, "numeric column"):
            check_edition.load_schema(graph, SCHEMA)

    def test_renamed_column_stops_the_check(self):
        header = self.header()
        header[header.index("CONNECTION  STATUS ")] = "Status"
        report = self.run_check(self.row({"connection_status": "Connected"}), header=header)
        self.assertEqual(report["header"], [{"column": "connection_status", "found": "missing"}])
        self.assertNotIn("columns", report)
        self.assertFalse(report["conforms"])

    def test_duplicated_column_is_reported(self):
        header = self.header()
        header[0] = "Grid Supply Point"
        report = self.run_check(self.row({"connection_status": "Connected"}), header=header)
        self.assertEqual(report["header"], [{"column": "gsp", "found": "several times"}])

    def test_other_columns_may_change_freely(self):
        header = self.header()
        header[-1] = "A column ENWL added"
        report = self.run_check(self.row({"connection_status": "Connected"}) + ["new"], header=header + ["Another"])
        self.assertTrue(report["conforms"])


if __name__ == "__main__":
    unittest.main()
