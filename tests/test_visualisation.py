"""Contract tests for the optional static ontology atlas projection."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atlas_export', ROOT / 'visualisation/export_graph.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class AtlasProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = export.build()
        cls.nodes = {node['id']: node for node in cls.data['nodes']}

    def test_checked_in_projection_is_current(self):
        self.assertEqual(self.data, json.loads((ROOT / 'visualisation/graph.json').read_text()))

    def test_projection_is_deterministic(self):
        self.assertEqual(self.data, export.build())

    def test_links_have_resolvable_endpoints_and_provenance(self):
        for link in self.data['links']:
            self.assertIn(link['source'], self.nodes)
            self.assertIn(link['target'], self.nodes)
            self.assertTrue(link['sources'])
            for source in link['sources']:
                self.assertTrue((ROOT / source).is_file())

    def test_layers_and_unique_identities(self):
        self.assertEqual(len(self.nodes), len(self.data['nodes']))
        layers = {layer['id'] for layer in self.data['layers']}
        for node in self.nodes.values():
            self.assertIn(node['layer'], layers)
        self.assertEqual(self.nodes['https://busbar.example/id/grid/catalogues/busbar']['layer'], 'catalogue')
        self.assertEqual(self.nodes['https://busbar.example/id/grid/uk/dno/ukpn']['layer'], 'identities')
        self.assertEqual(self.nodes['https://busbar.example/grid#DistributionNetworkOperator']['layer'], 'grid')

    def test_input_fingerprints_match_current_files(self):
        self.assertEqual(self.data['files'], [item['path'] for item in self.data['inputs']])
        for item in self.data['inputs']:
            self.assertEqual(item['sha256'], hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest())

    def test_recorded_series_metadata_is_joined_without_duplicating_identity(self):
        series = 'https://busbar.example/id/grid/uk/dno/enwl/series/ecr'
        node = self.nodes[series]
        self.assertEqual(node['layer'], 'catalogue')
        self.assertEqual(node['label'], 'SP ENW - Embedded Capacity Register 2 - 1MW & Above')
        self.assertIn('definitions/grid/uk/dno/enwl/series.ttl', node['sources'])
        self.assertIn('editions/grid/uk/dno/enwl/ecr.ttl', node['sources'])
        links = {(link['source'], link['predicate'], link['target']): link for link in self.data['links']}
        theme = (series, 'dcat:theme', 'https://busbar.example/grid#DistributionProject1MWAndAbove')
        self.assertEqual(links[theme]['sources'], ['definitions/grid/uk/dno/enwl/series.ttl'])
        edition = 'https://busbar.example/id/grid/uk/dno/enwl/editions/ecr/2026-10-20'
        self.assertIn((edition, 'dcat:inSeries', series), links)
        self.assertIn((series, 'dcat:last', edition), links)
        for identifier in (edition, edition + '/csv', series + '/distributions/latest-csv'):
            self.assertEqual(self.nodes[identifier]['layer'], 'editions')
            self.assertFalse(self.nodes[identifier]['detail'])
        provenance = (edition + '/csv', 'prov:wasDerivedFrom', series + '/distributions/latest-csv')
        self.assertEqual(links[provenance]['sources'], ['editions/grid/uk/dno/enwl/ecr.ttl'])

    def test_unified_projection_includes_property_assertions_and_catalogue_records(self):
        property_id = 'https://busbar.example/publishing#maintainedBy'
        node = self.nodes[property_id]
        self.assertEqual(node['kind'], 'property')
        self.assertNotIn('views', node)
        links = {(link['source'], link['predicate'], link['target']) for link in self.data['links']}
        self.assertIn((property_id, 'rdfs:domain', 'http://www.w3.org/ns/dcat#Catalog'), links)
        self.assertIn((property_id, 'rdfs:range', 'http://www.w3.org/ns/org#Organization'), links)
        series = self.nodes['https://busbar.example/id/grid/uk/dno/enwl/series/ecr']
        self.assertEqual(series['kind'], 'entity')
        organization = self.nodes['https://busbar.example/id/grid/uk/dno/enwl']
        self.assertEqual(organization['kind'], 'entity')
        theme = self.nodes['https://busbar.example/grid#DistributionProject1MWAndAbove']
        self.assertEqual(theme['kind'], 'concept')

    def test_editions_and_anonymous_distributions_are_available(self):
        details = [node for node in self.nodes.values() if node['detail']]
        self.assertTrue(any('dcat:Dataset' in node['types'] for node in details))
        self.assertTrue(any('dcat:Distribution' in node['types'] for node in details))


if __name__ == '__main__':
    unittest.main()
