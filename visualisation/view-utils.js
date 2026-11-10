// Dependency-free view calculations, also exercised by node --test.
export function allowsLink(link, predicate, crossLayer, layerOf) {
  return (!predicate || link.predicate === predicate) &&
    (crossLayer || layerOf(link.source) === layerOf(link.target));
}

// Group already-filtered incident assertions by the other endpoint's layer.
// A node reached by several predicates (or in both directions) counts once.
export function relatedLayers(selected, links, layerOf) {
  const groups = new Map();
  if (!selected) return groups;
  for (const link of links) {
    if (link.source !== selected && link.target !== selected) continue;
    const other = link.source === selected ? link.target : link.source;
    const layer = layerOf(other);
    if (!groups.has(layer)) groups.set(layer, { nodes: new Set(), links: [] });
    const group = groups.get(layer);
    if (other !== selected) group.nodes.add(other);
    group.links.push(link);
  }
  return groups;
}

// Coordinates are expressed in the current camera's right/up/backward basis.
// Reserve enough depth for every point, then move the optical centre so the
// bounds land in the unobstructed part of the full-window viewport.
export function fitBounds(points, viewport, safe, verticalFov, padding = 1.18) {
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const point of points) for (let i = 0; i < 3; i++) {
    min[i] = Math.min(min[i], point[i]); max[i] = Math.max(max[i], point[i]);
  }
  const center = min.map((value, i) => (value + max[i]) / 2);
  const tanV = Math.tan(verticalFov / 2), aspect = viewport.width / viewport.height;
  // Solve the perspective inequalities point by point, including depth, rather
  // than fitting a larger camera-aligned bounding box around an oblique stack.
  const shiftX = ((safe.left + safe.width / 2) / viewport.width * 2 - 1) * aspect * tanV;
  const shiftY = (1 - (safe.top + safe.height / 2) / viewport.height * 2) * tanV;
  const left = (safe.left / viewport.width * 2 - 1) * aspect * tanV;
  const right = ((safe.left + safe.width) / viewport.width * 2 - 1) * aspect * tanV;
  const top = (1 - safe.top / viewport.height * 2) * tanV;
  const bottom = (1 - (safe.top + safe.height) / viewport.height * 2) * tanV;
  let distance = 8;
  for (const point of points) {
    const x = (point[0]-center[0])*padding, y = (point[1]-center[1])*padding, z = point[2]-center[2];
    distance = Math.max(distance, z+1,
      (-x-left*z)/(shiftX-left), (x+right*z)/(right-shiftX),
      (-y-bottom*z)/(shiftY-bottom), (y+top*z)/(top-shiftY));
  }
  return { center, distance, shift: [-shiftX * distance, -shiftY * distance] };
}
