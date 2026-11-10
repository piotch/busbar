import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildGridLayout } from './grid-layout.js';
import { GRID_GROUPS } from './grid-layout-config.js';
const data=JSON.parse(readFileSync(new URL('./graph.json',import.meta.url)));
const layout=buildGridLayout(data.nodes,data.links);
const byShort=new Map(data.nodes.map(node=>[node.short,node]));
const id=short=>byShort.get(short).id;

test('all current grid terms occupy exactly one neighbourhood with no overlapping markers',()=>{
  const grid=data.nodes.filter(node=>node.layer==='grid');
  assert.equal(layout.positions.size,grid.length);
  assert.equal(new Set([...layout.positions.values()].map(point=>point.join(','))).size,grid.length);
  assert.deepEqual(layout.groups.map(group=>group.id),GRID_GROUPS.map(group=>group.id));
  const ids=layout.groups.flatMap(group=>group.ids);
  assert.equal(new Set(ids).size,grid.length);
  for(const group of layout.groups) for(const nodeId of group.ids){
    const [x,z]=layout.positions.get(nodeId);
    assert.ok(x>group.left&&x<group.left+group.width,nodeId);
    assert.ok(z>group.top&&z<group.top+group.depth,nodeId);
  }
});
test('reviewed seed terms resolve to actual grid nodes',()=>{
  for(const group of GRID_GROUPS) for(const short of group.seeds){
    assert.equal(byShort.get(short)?.layer,'grid',short);
    assert.equal(layout.membership.get(id(short)),group.id,short);
  }
});
test('properties follow asserted domains before ranges, with explicit shared exceptions',()=>{
  assert.equal(layout.membership.get(id('busbar:connectedToCircuit')),'projects');
  assert.equal(layout.placement.get(id('busbar:connectedToCircuit')).owner,id('busbar:Project'));
  assert.equal(layout.placement.get(id('busbar:connectedToCircuit')).rule,'asserted domain');
  assert.equal(layout.membership.get(id('busbar:firmCapacity')),'capacity');
  assert.equal(layout.membership.get(id('busbar:hasTransformer')),'network');
  assert.equal(layout.membership.get(id('busbar:timestamp')),'shared');
});
test('instances and concepts follow asserted types and schemes',()=>{
  assert.equal(layout.membership.get(id('id:Yorkshire')),'geography');
  assert.equal(layout.placement.get(id('id:Yorkshire')).owner,id('busbar:DistributionArea'));
  assert.equal(layout.membership.get(id('id:gsp-input-all')),'network');
  assert.equal(layout.membership.get(id('grid:DistributionProject1MWAndAbove')),'projects');
  assert.equal(layout.membership.get(id('id:ltds')),'classifications');
});
test('subclasses form branches beneath their parent class',()=>{
  for(const [child,parent] of [['busbar:TransformerSubstation','busbar:Substation'],['busbar:GridSupplyPoint','busbar:TransformerSubstation'],['busbar:DistributionProject','busbar:Project']]){
    assert.ok(layout.positions.get(id(child))[1]>layout.positions.get(id(parent))[1]);
    assert.equal(layout.membership.get(id(child)),layout.membership.get(id(parent)));
  }
});
test('packing is deterministic and never mutates RDF inputs',()=>{
  const before=JSON.stringify(data);
  const again=buildGridLayout([...data.nodes].reverse(),[...data.links].reverse());
  assert.deepEqual([...layout.positions].sort(),[...again.positions].sort());
  assert.equal(JSON.stringify(data),before);
});
test('unknown nodes remain visible in a fallback neighbourhood',()=>{
  const node={id:'urn:unknown',short:'unknown:Class',label:'Unknown class',kind:'class',layer:'grid',types:['owl:Class']};
  const result=buildGridLayout([...data.nodes,node],data.links);
  assert.equal(result.membership.get(node.id),'other');
  assert.ok(result.positions.has(node.id));
});
test('cyclic subclass assertions do not cause recursive layout failure',()=>{
  const nodes=['A','B'].map(value=>({id:value,short:value,label:value,kind:'class',layer:'grid',types:['owl:Class']}));
  const links=[{source:'A',target:'B',predicate:'rdfs:subClassOf'},{source:'B',target:'A',predicate:'rdfs:subClassOf'}];
  const result=buildGridLayout(nodes,links,[{id:'network',title:'Network',color:'#64826c',seeds:['A']}]);
  assert.equal(result.positions.size,2);
});
