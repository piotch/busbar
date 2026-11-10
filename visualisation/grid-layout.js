import { GRID_GROUPS } from './grid-layout-config.js';

// Display-only grouping and tree/card packing. Never adds or rewrites RDF links.
export function buildGridLayout(nodes, links, definitions = GRID_GROUPS) {
  const grid = nodes.filter(node => node.layer === 'grid');
  const byId = new Map(grid.map(node => [node.id, node]));
  const byShort = new Map(grid.map(node => [node.short, node]));
  const compare = (a,b) => byId.get(a).label.localeCompare(byId.get(b).label) || a.localeCompare(b);
  const outgoing = new Map(grid.map(node => [node.id, []]));
  for (const link of links) if (outgoing.has(link.source)) outgoing.get(link.source).push(link);
  for (const values of outgoing.values()) values.sort((a,b) => a.predicate.localeCompare(b.predicate) || a.target.localeCompare(b.target));
  const membership = new Map(), placement = new Map();
  for (const group of definitions) for (const short of group.seeds) {
    const node = byShort.get(short);
    if (node) { membership.set(node.id, group.id); placement.set(node.id, { rule: 'reviewed layout seed', owner: null }); }
  }
  const targets = (id, predicates) => outgoing.get(id).filter(link => predicates.includes(link.predicate) && byId.has(link.target));
  const assign = (node, candidates, rule) => {
    const available = candidates.filter(link => membership.has(link.target));
    const groups = new Set(available.map(link => membership.get(link.target)));
    if (groups.size !== 1) return false;
    const owner = available[0].target;
    membership.set(node.id, membership.get(owner)); placement.set(node.id, { rule, owner }); return true;
  };
  // Resolve schemes/parents before properties and reference instances. Repeat for
  // arbitrary subclass depth; cycles without seeds are left in the fallback box.
  let changed = true;
  while (changed) {
    changed = false;
    for (const node of [...grid].sort((a,b) => compare(a.id,b.id))) {
      if (membership.has(node.id) || node.kind === 'property' || node.kind === 'entity') continue;
      changed = assign(node, targets(node.id, ['rdfs:subClassOf','skos:broader','skos:inScheme','skos:topConceptOf']), 'asserted hierarchy / scheme') || changed;
    }
  }
  for (const node of [...grid].sort((a,b) => compare(a.id,b.id))) {
    if (membership.has(node.id)) continue;
    if (node.kind === 'property') {
      const domains = targets(node.id, ['rdfs:domain']);
      if (domains.length && assign(node, domains, 'asserted domain')) continue;
      if (!domains.length && assign(node, targets(node.id, ['rdfs:range']), 'asserted range')) continue;
      membership.set(node.id, 'shared'); placement.set(node.id, { rule: 'shared / unresolved property domain', owner: null });
    } else if (node.kind === 'entity') assign(node, targets(node.id, ['rdf:type']), 'asserted type');
  }
  for (const node of grid) if (!membership.has(node.id)) {
    membership.set(node.id, 'other'); placement.set(node.id, { rule: 'unassigned layout term', owner: null });
  }
  const groups = [...definitions, { id:'other', title:'Other grid terms', color:'#999487', seeds:[] }]
    .map(definition => ({ ...definition, ids:grid.filter(node => membership.get(node.id) === definition.id).map(node => node.id).sort(compare) }))
    .filter(group => group.ids.length);
  const positions = new Map(), cards = [], bands = [];
  for (const group of groups) {
    const anchors = group.ids.filter(id => !['property','entity'].includes(byId.get(id).kind));
    const anchorIds = new Set(anchors), parent = new Map();
    for (const id of anchors) {
      const candidates = targets(id, ['rdfs:subClassOf','skos:broader','skos:inScheme','skos:topConceptOf'])
        .filter(link => anchorIds.has(link.target) && link.target !== id)
        .sort((a,b) => Number(a.predicate.includes('Scheme') || a.predicate === 'skos:topConceptOf') - Number(b.predicate.includes('Scheme') || b.predicate === 'skos:topConceptOf') || a.target.localeCompare(b.target));
      for (const candidate of candidates) {
        let ancestor = candidate.target; const seen = new Set([id]);
        while (parent.has(ancestor) && !seen.has(ancestor)) { seen.add(ancestor); ancestor = parent.get(ancestor); }
        if (!seen.has(ancestor)) { parent.set(id,candidate.target); break; }
      }
    }
    const properties = new Map(anchors.map(id => [id,[]])), loose = [];
    for (const id of group.ids.filter(id => byId.get(id).kind === 'property')) {
      const owner = placement.get(id).owner;
      if (properties.has(owner)) properties.get(owner).push(id); else loose.push(id);
    }
    const children = id => anchors.filter(child => parent.get(child) === id).sort(compare);
    const tree = id => {
      const props = properties.get(id), descendants = children(id).map(tree);
      const columns = Math.min(3, Math.max(1,props.length));
      const ownWidth = 5.2, ownDepth = 2.3 + Math.ceil(props.length/3)*1.1;
      const target=Math.max(18,...descendants.map(child=>child.width));
      let x=0,z=0,rowDepth=0,childWidth=0;
      const childOffsets=[];
      for (const child of descendants) {
        if (x>0 && x+child.width>target) { x=0;z+=rowDepth+1.2;rowDepth=0; }
        childOffsets.push([x,z]);childWidth=Math.max(childWidth,x+child.width);
        x+=child.width+1.2;rowDepth=Math.max(rowDepth,child.depth);
      }
      return { id, props, columns, descendants, childOffsets, childWidth, ownWidth, ownDepth,
        width:Math.max(ownWidth,childWidth), depth:ownDepth+(descendants.length ? 1.4+z+rowDepth : 0) };
    };
    const roots = anchors.filter(id=>!parent.has(id)).sort(compare).map(tree);
    const area = roots.reduce((sum,root)=>sum+root.width*root.depth,0);
    const targetWidth = Math.max(10, Math.sqrt(area*1.35), ...roots.map(root=>root.width));
    const local = new Map(), localCards = [];
    const place = (root,x,z) => {
      const center=x+root.width/2;
      local.set(root.id,[center,z+0.8]);
      root.props.forEach((id,i)=>local.set(id,[center+((i%3)-Math.min(2,root.props.length-1)/2)*1.4,z+2+Math.floor(i/3)*1.1]));
      localCards.push({ root:root.id, left:center-root.ownWidth/2, top:z, width:root.ownWidth, depth:root.ownDepth });
      root.descendants.forEach((child,i)=>{
        const [cx,cz]=root.childOffsets[i];
        place(child,x+(root.width-root.childWidth)/2+cx,z+root.ownDepth+1.4+cz);
      });
    };
    let x=0, z=2.4, rowDepth=0, usedWidth=0;
    for (const root of roots) {
      if (x>0 && x+root.width>targetWidth) { x=0; z+=rowDepth+1.4; rowDepth=0; }
      place(root,x+0.8,z); usedWidth=Math.max(usedWidth,x+root.width+1.6); x+=root.width+1.4; rowDepth=Math.max(rowDepth,root.depth);
    }
    z+=rowDepth+1.6;
    const packBand = (ids,title,kind) => {
      if (!ids.length) return;
      const width=Math.max(10,usedWidth), columns=Math.max(3,Math.floor((width-1.6)/1.4));
      ids.forEach((id,i)=>local.set(id,[0.8+(i%columns)*1.4,z+1.3+Math.floor(i/columns)*1.1]));
      const depth=2+Math.ceil(ids.length/columns)*1.1;
      bands.push({ group:group.id,title,kind,left:0,top:z,width,depth });
      z+=depth+0.7; usedWidth=Math.max(usedWidth,width);
    };
    packBand(loose,'Shared properties','properties');
    packBand(group.ids.filter(id=>byId.get(id).kind==='entity'),'Reference instances','instances');
    group.width=Math.max(10,usedWidth); group.depth=z+0.6; group.local=local; group.cards=localCards;
  }
  // Five neighbourhoods in two rows, with shared attributes as a footer strip.
  const primary=groups.filter(group=>group.id!=='shared'), shared=groups.find(group=>group.id==='shared');
  const rowDepths=[Math.max(0,...primary.slice(0,3).map(group=>group.depth)),Math.max(0,...primary.slice(3,6).map(group=>group.depth))];
  const width=Math.max(...[primary.slice(0,3),primary.slice(3,6)].map(row=>row.reduce((sum,group)=>sum+group.width,0)+Math.max(0,row.length-1)*2.4),shared?.width||0);
  const primaryDepth=rowDepths[0]+(primary.length>3 ? rowDepths[1]+2.4 : 0);
  if (shared) {
    const anchors=shared.ids.filter(id=>!['property','entity'].includes(byId.get(id).kind));
    const props=shared.ids.filter(id=>byId.get(id).kind==='property');
    const instances=shared.ids.filter(id=>byId.get(id).kind==='entity');
    const anchorWidth=Math.max(6,anchors.length*5.5), columns=Math.max(1,Math.floor((width-anchorWidth-2)/4));
    shared.local=new Map();shared.cards=[];
    anchors.forEach((id,i)=>{
      shared.local.set(id,[2.8+i*5.5,2.6]);
      shared.cards.push({root:id,left:i*5.5,top:1.8,width:5.2,depth:3.4});
    });
    const loose=[];
    for (const id of props) {
      const owner=placement.get(id).owner,index=anchors.indexOf(owner);
      if(index>=0) shared.local.set(id,[2.8+index*5.5,4]);else loose.push(id);
    }
    loose.forEach((id,i)=>shared.local.set(id,[anchorWidth+2+(i%columns)*4,2.6+Math.floor(i/columns)*1.3]));
    const instanceZ=Math.max(6,3+Math.ceil(loose.length/columns)*1.3);
    instances.forEach((id,i)=>shared.local.set(id,[1.4+i*3,instanceZ+1.4]));
    for(let i=bands.length-1;i>=0;i--) if(bands[i].group==='shared') bands.splice(i,1);
    if(instances.length) bands.push({group:'shared',title:'Reference instances',kind:'instances',left:0,top:instanceZ,width,depth:2.6});
    shared.depth=instanceZ+3;
  }
  const depth=primaryDepth+(shared ? shared.depth+2.4 : 0);
  for (let row=0;row<2;row++) {
    const members=primary.slice(row*3,row*3+3);
    const rowWidth=members.reduce((sum,group)=>sum+group.width,0)+Math.max(0,members.length-1)*2.4;
    let x=-rowWidth/2;
    for (const group of members) { group.left=x;group.top=(row===0 ? 0 : rowDepths[0]+2.4)-depth/2;x+=group.width+2.4; }
  }
  if (shared) { shared.left=-width/2; shared.top=primaryDepth+2.4-depth/2; shared.width=width; }
  for (const group of groups) {
    for (const [id,[x,z]] of group.local) positions.set(id,[group.left+x,group.top+z]);
    for (const card of group.cards) cards.push({ ...card, group:group.id, left:card.left+group.left,top:card.top+group.top });
    for (const band of bands.filter(band=>band.group===group.id)) { band.left+=group.left;band.top+=group.top; }
    delete group.local; delete group.cards; delete group.seeds;
  }
  return { groups,positions,membership,placement,cards,bands,width,depth };
}
