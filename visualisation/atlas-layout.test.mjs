import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildCatalogueLayout } from './atlas-layout.js';
const data = JSON.parse(readFileSync(new URL('./graph.json', import.meta.url)));
const byId = new Map(data.nodes.map(node => [node.id, node]));
const layout = buildCatalogueLayout(data.nodes, data.links);
const base = 'https://busbar.example/id/grid/uk/dno/enwl';

test('series, editions and files share a publisher and parent-series family', () => {
  const series = base + '/series/ecr';
  for (const id of [series, base+'/editions/ecr/2026-10-20', base+'/editions/ecr/2026-10-20/csv', series+'/distributions/latest-csv']) {
    assert.equal(layout.publisherOf.get(id), base);
    assert.equal(layout.familyOf.get(id), series);
    assert.ok(layout.positions.has(id));
  }
});
test('publisher groups and family tiles do not overlap or duplicate identities', () => {
  const seen = new Set();
  for (const group of layout.groups) for (const id of group.ids) {
    assert.ok(!seen.has(id)); seen.add(id);
    const [x,z] = layout.positions.get(id);
    assert.ok(x > group.left && x < group.left+group.width);
    assert.ok(z > group.top && z < group.top+group.depth);
  }
  const coordinates = [...layout.positions.values()].map(p => p.join(','));
  assert.equal(new Set(coordinates).size, coordinates.length);
  for (const a of layout.groups) for (const b of layout.groups) if (a !== b) {
    assert.ok(a.left+a.width <= b.left || b.left+b.width <= a.left || a.top+a.depth <= b.top || b.top+b.depth <= a.top);
  }
});
test('layout is deterministic regardless of RDF enumeration order', () => {
  const again = buildCatalogueLayout([...data.nodes].reverse(), [...data.links].reverse());
  assert.deepEqual([...layout.positions].sort(), [...again.positions].sort());
});
test('unasserted publishers are not guessed from URI spelling', () => {
  const node = { id:'looks-like-enwl', label:'Unassigned', layer:'catalogue', kind:'entity', types:['dcat:DatasetSeries'] };
  const result = buildCatalogueLayout([node], []);
  assert.equal(result.publisherOf.get(node.id), '__unassigned__');
});
test('publisher grouping excludes schema properties without removing them from the atlas', () => {
  const property = byId.get('https://busbar.example/publishing#maintainedBy');
  assert.equal(property.kind, 'property');
  assert.ok(!layout.positions.has(property.id));
  assert.ok(layout.positions.has(base+'/series/ecr'));
});
