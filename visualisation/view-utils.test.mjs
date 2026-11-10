import test from 'node:test';
import assert from 'node:assert/strict';
import { fitBounds, allowsLink, relatedLayers } from './view-utils.js';

test('layer summaries count unique neighbours while preserving every assertion and direction', () => {
  const links = [
    {source:'a',target:'b',predicate:'dcat:first'},
    {source:'a',target:'b',predicate:'dcat:last'},
    {source:'b',target:'a',predicate:'dcat:inSeries'},
    {source:'a',target:'c',predicate:'dct:publisher'},
    {source:'d',target:'a',predicate:'dcat:dataset'},
    {source:'unrelated',target:'c',predicate:'dct:publisher'},
  ];
  const layerOf = id => ({a:'catalogue',b:'editions',c:'identities',d:'catalogue'})[id];
  const groups = relatedLayers('a', links, layerOf);
  assert.deepEqual([...groups.get('editions').nodes], ['b']);
  assert.equal(groups.get('editions').links.length, 3);
  assert.deepEqual([...groups.get('identities').nodes], ['c']);
  assert.deepEqual([...groups.get('catalogue').nodes], ['d']);
  assert.equal([...groups.values()].reduce((sum,g) => sum+g.links.length, 0), 5);
});
test('layer summaries respect composed predicate and cross-layer filters', () => {
  const links = [{source:'a',target:'b',predicate:'dct:publisher'}, {source:'a',target:'c',predicate:'dcat:dataset'}];
  const layerOf = id => id === 'b' ? 'identities' : 'catalogue';
  const filtered = links.filter(link => allowsLink(link, '', false, layerOf));
  assert.deepEqual([...relatedLayers('a',filtered,layerOf).keys()], ['catalogue']);
  const publishers = links.filter(link => allowsLink(link, 'dct:publisher', true, layerOf));
  assert.deepEqual([...relatedLayers('a',publishers,layerOf).keys()], ['identities']);
});
test('clearing selection and isolated nodes leave no stale neighbour counts', () => {
  const link = {source:'a',target:'b',predicate:'rdf:type'};
  assert.equal(relatedLayers(null,[link],()=> 'grid').size, 0);
  assert.equal(relatedLayers('a',[],()=> 'grid').size, 0);
});
test('self-assertions remain inspectable without counting the selected node as a neighbour', () => {
  const link = {source:'a',target:'a',predicate:'skos:related'};
  const groups = relatedLayers('a',[link],()=> 'grid');
  assert.equal(groups.get('grid').nodes.size, 0);
  assert.deepEqual(groups.get('grid').links,[link]);
});

const fov = 38 * Math.PI / 180;
function checkFit(points, viewport, safe) {
  const fit = fitBounds(points, viewport, safe, fov);
  assert.ok(Number.isFinite(fit.distance) && fit.distance > 0);
  const tanV = Math.tan(fov / 2), aspect = viewport.width / viewport.height;
  for (const point of points) {
    const depth = fit.distance - (point[2] - fit.center[2]);
    assert.ok(depth > 0);
    const x = ((point[0] - fit.center[0] - fit.shift[0]) / (depth * tanV * aspect) + 1) * viewport.width / 2;
    const y = (1 - (point[1] - fit.center[1] - fit.shift[1]) / (depth * tanV)) * viewport.height / 2;
    assert.ok(x >= safe.left && x <= safe.left + safe.width, `x=${x} outside safe viewport`);
    assert.ok(y >= safe.top && y <= safe.top + safe.height, `y=${y} outside safe viewport`);
  }
}
const corners = [];
for (const x of [-18, 18]) for (const y of [-20, 20]) for (const z of [-11, 11]) corners.push([x, y, z]);

test('fits a neighbourhood between navigation, inspector and toolbar', () => {
  checkFit(corners, { width:1440, height:1000 }, { left:266, top:120, width:800, height:720 });
});
test('fits above a mobile inspector sheet', () => {
  checkFit(corners, { width:390, height:844 }, { left:20, top:110, width:346, height:210 });
});
test('handles isolated entities and off-centre bounds', () => {
  checkFit([[12, 18, -5]], { width:1440, height:1000 }, { left:266, top:120, width:800, height:720 });
  checkFit(corners.map(p => p.map(v => v+100)), { width:1440, height:1000 }, { left:266, top:120, width:800, height:720 });
});
test('predicate and cross-layer filters compose without changing graph assertions', () => {
  const link = { source:'a', target:'b', predicate:'dct:publisher' };
  const layerOf = id => id === 'a' ? 'catalogue' : 'identities';
  assert.equal(allowsLink(link, '', true, layerOf), true);
  assert.equal(allowsLink(link, 'dct:publisher', true, layerOf), true);
  assert.equal(allowsLink(link, 'rdf:type', true, layerOf), false);
  assert.equal(allowsLink(link, '', false, layerOf), false);
  assert.equal(allowsLink(link, 'dct:publisher', false, () => 'same'), true);
  assert.deepEqual(link, { source:'a', target:'b', predicate:'dct:publisher' });
});
