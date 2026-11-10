// Deterministic display grouping from explicit publisher / parent assertions.
// These computed memberships and positions are NOT additional RDF statements.
export function buildCatalogueLayout(nodes, links) {
  const byId = new Map(nodes.map(node => [node.id, node]));
  const members = nodes.filter(node => ['catalogue', 'editions'].includes(node.layer) && node.kind === 'entity');
  const memberIds = new Set(members.map(node => node.id));
  const parents = new Map(), publishers = new Map();
  const add = (map, key, value) => { if (!map.has(key)) map.set(key, []); map.get(key).push(value); };
  for (const link of links) {
    if (link.predicate === 'dct:publisher') add(publishers, link.source, link.target);
    if (link.predicate === 'dcat:inSeries' && memberIds.has(link.source) && memberIds.has(link.target)) add(parents, link.source, link.target);
    if (link.predicate === 'dcat:distribution' && memberIds.has(link.source) && memberIds.has(link.target)) add(parents, link.target, link.source);
  }
  for (const map of [parents, publishers]) for (const values of map.values()) values.sort();
  const rootOf = id => {
    const seen = new Set();
    while (parents.has(id) && !byId.get(id)?.types.includes('dcat:DatasetSeries')) {
      if (seen.has(id)) return [...seen].sort()[0];
      seen.add(id); id = parents.get(id)[0];
    }
    return id;
  };
  const groups = new Map(), familyOf = new Map(), publisherOf = new Map();
  for (const node of members) {
    const root = rootOf(node.id);
    const publisher = publishers.get(root)?.[0] || publishers.get(node.id)?.[0] || '__unassigned__';
    familyOf.set(node.id, root); publisherOf.set(node.id, publisher);
    if (!groups.has(publisher)) groups.set(publisher, { id: publisher,
      label: byId.get(publisher)?.label || 'Publisher not asserted', families: new Map(), ids: [] });
    const group = groups.get(publisher); group.ids.push(node.id);
    if (!group.families.has(root)) group.families.set(root, []);
    group.families.get(root).push(node.id);
  }
  const compare = (a, b) => byId.get(a).label.localeCompare(byId.get(b).label) || a.localeCompare(b);
  const sortedGroups = [...groups.values()].sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
  for (const group of sortedGroups) {
    const tiles = [...group.families].sort(([a], [b]) => compare(a, b)).map(([root, ids]) => {
      const ordered = [], seen = new Set();
      const visit = id => {
        if (seen.has(id)) return; seen.add(id); ordered.push(id);
        ids.filter(child => parents.get(child)?.[0] === id).sort(compare).forEach(visit);
      };
      visit(root); ids.sort(compare).forEach(visit);
      const columns = Math.max(2, Math.ceil(Math.sqrt(ordered.length * 1.4)));
      return { root, ids: ordered, columns, width: columns * 1.05 + 0.8,
        depth: Math.ceil(ordered.length / columns) * 1.1 + 0.9 };
    });
    const area = tiles.reduce((sum, tile) => sum + tile.width * tile.depth, 0);
    const targetWidth = Math.max(8, Math.sqrt(area * 1.5), ...tiles.map(tile => tile.width));
    let x = 0, z = 1.4, rowDepth = 0, usedWidth = 0;
    group.local = new Map(); group.tiles = [];
    for (const tile of tiles) {
      if (x > 0 && x + tile.width > targetWidth) { x = 0; z += rowDepth; rowDepth = 0; }
      group.tiles.push({ root: tile.root, ids: tile.ids, left: x+0.2, top: z+0.15, width: tile.width-0.3, depth: tile.depth-0.25 });
      tile.ids.forEach((id, i) => group.local.set(id, [x + 0.65 + (i % tile.columns) * 1.05,
        z + 0.6 + Math.floor(i / tile.columns) * 1.1]));
      usedWidth = Math.max(usedWidth, x + tile.width); x += tile.width;
      rowDepth = Math.max(rowDepth, tile.depth);
    }
    group.width = usedWidth + 0.5; group.depth = z + rowDepth + 0.5;
  }
  const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(sortedGroups.length))));
  const cellWidth = Math.max(10, ...sortedGroups.map(group => group.width)) + 2;
  const cellDepth = Math.max(6, ...sortedGroups.map(group => group.depth)) + 2;
  const width = columns * cellWidth, depth = Math.ceil(sortedGroups.length / columns) * cellDepth;
  const positions = new Map(), families = [];
  sortedGroups.forEach((group, i) => {
    group.left = (i % columns) * cellWidth - width / 2;
    group.top = Math.floor(i / columns) * cellDepth - depth / 2;
    for (const [id, [x, z]] of group.local) positions.set(id, [group.left+x, group.top+z]);
    for (const tile of group.tiles) families.push({ ...tile, left: tile.left+group.left, top: tile.top+group.top });
    delete group.tiles;
    group.seriesCount = [...group.families.keys()].filter(id => byId.get(id).types.includes('dcat:DatasetSeries')).length;
    delete group.local; delete group.families;
  });
  return { groups: sortedGroups, families, positions, publisherOf, familyOf, width, depth };
}
