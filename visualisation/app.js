import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { allowsLink, fitBounds, relatedLayers } from './view-utils.js';
import { buildCatalogueLayout } from './atlas-layout.js';
import { buildGridLayout } from './grid-layout.js';

const $ = id => document.getElementById(id);
const response = await fetch('./graph.json', { cache: 'no-store' });
if (!response.ok) throw new Error(`graph.json: HTTP ${response.status}`);
const data = await response.json();
const byId = new Map(data.nodes.map(node => [node.id, node]));
const layerIndex = new Map(data.layers.map((layer, i) => [layer.id, i]));
const catalogueLayout = buildCatalogueLayout(data.nodes, data.links);
const gridLayout = buildGridLayout(data.nodes, data.links);
let activeLayers = [], planeWidth = 36, planeDepth = 22;
const layerY = id => (activeLayers.indexOf(id) - (activeLayers.length - 1) / 2) * gap * Math.sqrt(planeWidth * planeDepth / (36 * 22));
const adjacency = new Map(data.nodes.map(node => [node.id, []]));
for (const link of data.links) {
  adjacency.get(link.source).push(link);
  if (link.target !== link.source) adjacency.get(link.target).push(link);
}
const scene = new THREE.Scene();
scene.background = new THREE.Color('#f4f1e9');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
$('scene').append(renderer.domElement);
const labels = new CSS2DRenderer();
labels.domElement.className = 'labels';
Object.assign(labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' });
$('scene').append(labels.domElement);
const camera = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 0.1, 1500);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.085;
controls.minDistance = 3;
controls.maxDistance = 1500;
controls.screenSpacePanning = true;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const nodeGeometry = new THREE.SphereGeometry(0.19, 8, 5);
const propertyGeometry = new THREE.OctahedronGeometry(0.22);
let drawing = new THREE.Group();
scene.add(drawing);
let positions = new Map(), meshes = [], nodeLabels = [], groupLabels = [], planes = [], lineSets = [];
let selected = null, focused = null, travel = null, gap = 6, dirty = true;
let edgeLabels = [], hoveredLink = null;
let layerConnections = new Map();
const hoverElement = document.createElement('div');
hoverElement.className = 'edge-label hovered';
const hoverLabel = new CSS2DObject(hoverElement);
hoverLabel.visible = false;
scene.add(hoverLabel);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const colors = data.layers.map(layer => new THREE.Color(layer.color));
const paper = new THREE.Color('#f4f1e9');
const hoverStroke = lineObject([], '#344e2b', 1);
hoverStroke.material.depthTest = false;
hoverStroke.renderOrder = 1;
hoverStroke.visible = false;
scene.add(hoverStroke);

function lineObject(segments, color, opacity) {
  const geometry = new THREE.BufferGeometry().setFromPoints(segments);
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
}
function disposeDrawing() {
  drawing.traverse(object => {
    if (object.isCSS2DObject) object.element.remove();
    if (object.geometry && object.geometry !== nodeGeometry && object.geometry !== propertyGeometry) object.geometry.dispose();
    if (object.material) object.material.dispose();
  });
  scene.remove(drawing);
  drawing = new THREE.Group();
  scene.add(drawing);
}
function rebuild() {
  disposeDrawing();
  positions = new Map(); meshes = []; nodeLabels = []; groupLabels = []; planes = []; lineSets = [];
  const visible = data.nodes.filter(node => !node.detail || $('details').checked);
  activeLayers = data.layers.filter(layer => visible.some(node => node.layer === layer.id)).map(layer => layer.id);
  if (focused !== null && !activeLayers.includes(data.layers[focused].id)) focused = null;
  const grouped = visible.some(node => catalogueLayout.positions.has(node.id));
  planeWidth = grouped ? Math.max(36, catalogueLayout.width + 4) : 36;
  planeDepth = grouped ? Math.max(22, catalogueLayout.depth + 4) : 22;
  const gridScale = { x:(planeWidth-5)/gridLayout.width, z:(planeDepth-5)/gridLayout.depth };
  const margin = 2;
  data.layers.forEach((layer, index) => {
    const nodes = visible.filter(node => node.layer === layer.id);
    if (!nodes.length) return;
    const columns = Math.max(3, Math.ceil(Math.sqrt(nodes.length * 1.65)));
    const rows = Math.ceil(nodes.length / columns);
    const y = layerY(layer.id);
    const width = planeWidth, depth = planeDepth;
    const xStep = Math.min(5.7, (width - margin * 2) / columns);
    const zStep = Math.min(4.5, (depth - margin * 2) / Math.max(rows, 1));
    // Stable grouping by RDF type, then display name, not a force-directed layout.
    nodes.sort((a, b) => a.types.join().localeCompare(b.types.join()) || a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
    const corners = [new THREE.Vector3(-width/2,y,-depth/2), new THREE.Vector3(width/2,y,-depth/2), new THREE.Vector3(width/2,y,depth/2), new THREE.Vector3(-width/2,y,depth/2)];
    const surface = new THREE.Mesh(
      new THREE.PlaneGeometry(width, depth),
      new THREE.MeshBasicMaterial({ color: colors[index], transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }),
    );
    surface.rotation.x = -Math.PI / 2;
    surface.position.y = y - 0.025;
    surface.renderOrder = -1;
    drawing.add(surface); planes.push({ plane: surface, index, surface: true });
    const outline = [];
    corners.forEach((p, i) => outline.push(p, corners[(i + 1) % 4]));
    const plane = lineObject(outline, colors[index], 0.43);
    drawing.add(plane); planes.push({ plane, index });
    const grid = [];
    for (let x = -width/2+3; x < width/2; x += 3) grid.push(new THREE.Vector3(x,y,-depth/2),new THREE.Vector3(x,y,depth/2));
    for (let z = -depth/2+3; z < depth/2; z += 3) grid.push(new THREE.Vector3(-width/2,y,z),new THREE.Vector3(width/2,y,z));
    const gridLines = lineObject(grid, colors[index], 0.075);
    drawing.add(gridLines); planes.push({ plane: gridLines, index, grid: true });
    const title = document.createElement('div');
    title.className = 'plane-label'; title.dataset.layer = layer.id;
    title.textContent = `${String(index + 1).padStart(2, '0')} / ${layer.title.toUpperCase()}`;
    const titleObject = new CSS2DObject(title);
    titleObject.position.set(-width/2+8, y, depth/2+1);
    if (['catalogue', 'editions'].includes(layer.id)) addPublisherGroups(layer, y, visible);
    if (layer.id === 'grid') addGridGroups(y, gridScale);
    drawing.add(titleObject);
    planes.push({ title, titleObject, index });
    nodes.forEach((node, i) => {
      const col = i % columns, row = Math.floor(i / columns);
      const gridPosition = gridLayout.positions.get(node.id);
      const groupedPosition = gridPosition ? [gridPosition[0]*gridScale.x,gridPosition[1]*gridScale.z] : catalogueLayout.positions.get(node.id);
      const position = groupedPosition ? new THREE.Vector3(groupedPosition[0], y, groupedPosition[1])
        : new THREE.Vector3((col - (columns-1)/2)*xStep, y, (row-(rows-1)/2)*zStep);
      positions.set(node.id, position);
      const material = new THREE.MeshBasicMaterial({ color: colors[index], wireframe: true, transparent: true, opacity: 0.85 });
      const mesh = new THREE.Mesh(node.kind === 'property' ? propertyGeometry : nodeGeometry, material);
      mesh.position.copy(position); mesh.userData.node = node;
      mesh.userData.baseScale = node.types.includes('dcat:DatasetSeries') ? 1.35 : node.types.includes('dcat:Distribution') ? 0.65
        : node.layer === 'grid' ? (node.kind === 'entity' ? 0.6 : node.kind === 'property' ? 0.8 : 1.15) : 1;
      drawing.add(mesh); meshes.push(mesh);
      const element = document.createElement('div');
      element.className = 'node-label'; element.textContent = node.label;
      if(node.layer === 'grid') element.classList.add(node.kind === 'entity' ? 'reference-node' : node.kind === 'property' ? 'property-node' : 'schema-node');
      const label = new CSS2DObject(element);
      label.position.copy(position).add(new THREE.Vector3(0, 0.48, 0));
      drawing.add(label);
      nodeLabels.push({ node, element, label, index, sparse: nodes.length < 35 || i % Math.ceil(nodes.length / 16) === 0 });
    });
  });
  edgeLabels = []; setHoveredLink(null);
  for (const isCross of [false, true]) {
    const lines = lineObject([], isCross ? '#8d967e' : '#9b9f90', isCross ? 0.045 : 0.09);
    lines.userData.cross = isCross;
    drawing.add(lines); lineSets.push(lines);
  }
  const highlight = lineObject([], '#637e54', 0.85);
  drawing.add(highlight); lineSets.push(highlight);
  updateSelection();
  $('stats').title = 'Local RDF projection (not build/news-catalogues.owl)\n' +
    (data.inputs || []).map(input => `${input.path} · SHA-256 ${input.sha256}`).join('\n');
  updateButtons();
  dirty = true;
}
function addGridGroups(y, scale) {
  const index=layerIndex.get('grid');
  const rectangle = (box,color,opacity) => {
    const x=box.left*scale.x,z=box.top*scale.z,w=box.width*scale.x,d=box.depth*scale.z;
    const corners=[[x,z],[x+w,z],[x+w,z+d],[x,z+d]],segments=[];
    corners.forEach(([cx,cz],i)=>{ const next=corners[(i+1)%4];segments.push(new THREE.Vector3(cx,y,cz),new THREE.Vector3(next[0],y,next[1])); });
    const lines=lineObject(segments,color,opacity);drawing.add(lines);return lines;
  };
  for(const group of gridLayout.groups) {
    const frame=rectangle(group,group.color,0.25);planes.push({plane:frame,index,neighbourhood:true});
    const button=document.createElement('button');button.className='grid-group-label';
    button.dataset.gridGroup=group.id;button.textContent=group.title;
    button.title=`${group.title} · ${group.ids.length} terms. Click to fit. Display grouping only, not an ontology assertion.`;
    button.onclick=event=>{
      event.stopPropagation();focusGridGroup(group.id);
    };
    const label=new CSS2DObject(button);label.position.set((group.left+group.width/2)*scale.x,y,(group.top+0.8)*scale.z);
    drawing.add(label);groupLabels.push({label,group:{label:group.title},index});
  }
  const hierarchy=[];
  for(const link of data.links) {
    if(!['rdfs:subClassOf','skos:broader'].includes(link.predicate)) continue;
    const a=gridLayout.positions.get(link.source),b=gridLayout.positions.get(link.target);
    if(!a||!b||gridLayout.membership.get(link.source)!==gridLayout.membership.get(link.target)) continue;
    hierarchy.push(...linkPoints(new THREE.Vector3(a[0]*scale.x,y,a[1]*scale.z),new THREE.Vector3(b[0]*scale.x,y,b[1]*scale.z),false));
  }
  const branches=lineObject(hierarchy,'#6b8161',0.08);drawing.add(branches);planes.push({plane:branches,index,hierarchy:true});
  const cards=[];
  for(const card of gridLayout.cards) {
    const x=card.left*scale.x,z=card.top*scale.z,w=card.width*scale.x,d=card.depth*scale.z;
    cards.push(new THREE.Vector3(x,y,z+d),new THREE.Vector3(x,y,z),new THREE.Vector3(x,y,z),new THREE.Vector3(x+w,y,z));
  }
  const brackets=lineObject(cards,'#809179',0.12);drawing.add(brackets);planes.push({plane:brackets,index,grid:true});
  for(const band of gridLayout.bands) {
    rectangle(band,'#a4ad99',0.12);
    const element=document.createElement('div');element.className='grid-band-label';element.textContent=band.title;
    const label=new CSS2DObject(element);label.position.set((band.left+band.width/2)*scale.x,y,(band.top+0.4)*scale.z);
    drawing.add(label);groupLabels.push({label,group:{label:band.title},index});
  }
}
function focusGridGroup(id) {
  const group=gridLayout.groups.find(group=>group.id===id);
  choose(null);focused=layerIndex.get('grid');updateButtons();updateSelection();
  const points=group.ids.filter(id=>positions.has(id)).map(id=>positions.get(id));
  points.push(new THREE.Vector3((group.left+group.width/2)*(planeWidth-5)/gridLayout.width,layerY('grid'),(group.top+0.7)*(planeDepth-5)/gridLayout.depth));
  framePoints(points);
}
function addPublisherGroups(layer, y, visible) {
  const familySegments = [];
  const visibleIds = new Set(visible.filter(node => node.layer === layer.id).map(node => node.id));
  for (const family of catalogueLayout.families) {
    if (family.ids.filter(id => visibleIds.has(id)).length < 2) continue;
    const x=family.left, z=family.top, w=family.width, d=family.depth;
    const corners = [[x,z],[x+w,z],[x+w,z+d],[x,z+d]];
    corners.forEach(([cx,cz], i) => {
      const next=corners[(i+1)%4]; familySegments.push(new THREE.Vector3(cx,y,cz),new THREE.Vector3(next[0],y,next[1]));
    });
  }
  drawing.add(lineObject(familySegments, '#a08e78', 0.16));
  for (const group of catalogueLayout.groups) {
    const ids = group.ids.filter(id => visible.some(node => node.id === id && node.layer === layer.id));
    if (!ids.length) continue;
    const x = group.left, z = group.top, w = group.width, d = group.depth;
    const corners = [[x,z],[x+w,z],[x+w,z+d],[x,z+d]];
    const segments = [];
    corners.forEach(([cx,cz], i) => {
      const next = corners[(i+1)%4]; segments.push(new THREE.Vector3(cx,y,cz), new THREE.Vector3(next[0],y,next[1]));
    });
    const frame = lineObject(segments, '#a08e78', 0.22);
    drawing.add(frame);
    const button = document.createElement('button'); button.className = 'publisher-label';
    button.dataset.publisher = group.id;
    button.textContent = `${group.label} / ${ids.length}`;
    button.title = `${group.label}: ${group.seriesCount} series; click to fit this publisher group. Grouping follows explicit publisher and parent links; proximity is not an RDF assertion.`;
    button.onclick = event => {
      event.stopPropagation(); choose(null); focused = layerIndex.get(layer.id); updateButtons(); updateSelection();
      framePoints(group.ids.filter(id => positions.has(id)).map(id => positions.get(id)));
    };
    const label = new CSS2DObject(button); label.position.set(x+w/2,y,z+0.45); drawing.add(label);
    groupLabels.push({ label, group, index: layerIndex.get(layer.id) });
  }
}
function linkCurve(a, b, cross) {
  const mid = a.clone().lerp(b, 0.5);
  if (cross) mid.x += Math.min(3, a.distanceTo(b) * 0.12);
  else mid.y += Math.min(0.7, a.distanceTo(b) * 0.08);
  return new THREE.QuadraticBezierCurve3(a, mid, b);
}
function linkPoints(a, b, cross) {
  const points = linkCurve(a, b, cross).getPoints(12), segments = [];
  for (let i = 0; i < points.length - 1; i++) segments.push(points[i], points[i+1]);
  return segments;
}
function isCross(link) {
  return byId.get(link.source).layer !== byId.get(link.target).layer;
}
function activeLink(link) {
  return positions.has(link.source) && positions.has(link.target) && allowsLink(
    link, $('predicate-filter').value, $('links').checked, id => byId.get(id).layer,
  );
}
function selectionLinks() {
  return selected ? adjacency.get(selected).filter(activeLink) : [];
}
function updateBackgroundLinks() {
  for (const lines of lineSets.slice(0, -1)) {
    const points = [], segmentLinks = [];
    for (const link of data.links) {
      if (!activeLink(link) || isCross(link) !== lines.userData.cross || link.source === link.target) continue;
      const segments = linkPoints(positions.get(link.source), positions.get(link.target), isCross(link));
      points.push(...segments);
      for (let i = 0; i < segments.length; i += 2) segmentLinks.push(link);
    }
    lines.geometry.dispose(); lines.geometry = new THREE.BufferGeometry().setFromPoints(points);
    lines.userData.segmentLinks = segmentLinks;
  }
  const count = data.links.filter(activeLink).length;
  $('stats').textContent = `${positions.size} entities / ${count} visible links`;
}
function updateSelection() {
  setHoveredLink(null);
  updateBackgroundLinks();
  for (const { label } of edgeLabels) { drawing.remove(label); label.element.remove(); }
  edgeLabels = [];
  const relations = selectionLinks();
  layerConnections = relatedLayers(selected, relations, id => byId.get(id).layer);
  const connected = new Set(relations.flatMap(link => [link.source, link.target]));
  for (const mesh of meshes) {
    const id = mesh.userData.node.id;
    const index = layerIndex.get(mesh.userData.node.layer);
    const dim = selected && positions.has(selected) ? !connected.has(id) && selected !== id : focused !== null && focused !== index;
    mesh.material.color.copy(colors[index]).lerp(paper, dim ? 0.7 : 0);
    mesh.scale.setScalar(id === selected ? 1.7 : connected.has(id) ? Math.max(1.15,mesh.userData.baseScale) : mesh.userData.baseScale);
  }
  const points = [], segmentLinks = [];
  for (const link of relations) {
    const a = positions.get(link.source), b = positions.get(link.target);
    const cross = byId.get(link.source).layer !== byId.get(link.target).layer;
    if (a && b && (!cross || $('links').checked)) {
      const segments = linkPoints(a, b, cross);
      points.push(...segments);
      for (let i = 0; i < segments.length; i += 2) segmentLinks.push(link);
      const element = document.createElement('div');
      element.className = 'edge-label'; element.textContent = link.predicate;
      const label = new CSS2DObject(element);
      label.position.copy(linkCurve(a, b, cross).getPoint(0.5));
      drawing.add(label); edgeLabels.push({ link, label });
      // Arrowhead marks the RDF object's end of the directed assertion.
      if (a.distanceTo(b) > 0.6) {
        const direction = b.clone().sub(a).normalize();
        const side = new THREE.Vector3().crossVectors(direction, new THREE.Vector3(0, 0, 1));
        if (side.lengthSq() < 0.01) side.crossVectors(direction, new THREE.Vector3(0, 1, 0));
        side.normalize().multiplyScalar(0.12);
        const tip = b.clone().addScaledVector(direction, -0.28);
        const base = tip.clone().addScaledVector(direction, -0.3);
        points.push(tip, base.clone().add(side), tip, base.clone().sub(side));
        segmentLinks.push(link, link);
      }
    }
  }
  const highlight = lineSets.at(-1);
  highlight.geometry.dispose();
  highlight.geometry = new THREE.BufferGeometry().setFromPoints(points);
  highlight.userData.segmentLinks = segmentLinks;
  lineSets.slice(0, -1).forEach(lines => {
    lines.visible = !lines.userData.cross || $('links').checked;
    lines.material.opacity = selected && positions.has(selected) ? 0.018 : lines.userData.cross ? 0.045 : 0.09;
  });
  const hasSelection = Boolean(selected && positions.has(selected));
  const selectedLayer = hasSelection ? byId.get(selected).layer : null;
  for (const { plane, title, index, grid, surface, neighbourhood, hierarchy } of planes) {
    const layer = data.layers[index];
    const active = focused === index;
    const origin = layer.id === selectedLayer;
    const count = layerConnections.get(layer.id)?.nodes.size || 0;
    const participating = origin || layerConnections.has(layer.id);
    const dim = focused !== null && !active;
    if (plane) {
      if (hasSelection) plane.material.opacity = surface ? (origin ? 0.1 : participating ? 0.075 : 0)
        : hierarchy ? (participating ? 0.055 : 0.008)
        : neighbourhood ? (participating ? 0.18 : 0.035)
        : grid ? (participating ? 0.085 : 0.008)
        : (origin ? 0.95 : participating ? 0.75 : 0.055);
      else plane.material.opacity = surface ? (active ? 0.12 : 0)
        : hierarchy ? (active ? 0.38 : dim ? 0.015 : 0.08)
        : neighbourhood ? (active ? 0.48 : dim ? 0.08 : 0.2)
        : dim ? (grid ? 0.02 : 0.12) : active ? (grid ? 0.18 : 0.85) : (grid ? 0.075 : 0.43);
    }
    if (title) {
      title.style.opacity = hasSelection ? (participating ? '1' : '0.15') : dim ? '0.3' : active ? '1' : '0.85';
      title.style.color = hasSelection && participating ? layer.color : '';
      title.classList.toggle('participating', hasSelection && participating);
      title.textContent = `${String(index+1).padStart(2,'0')} / ${layer.title.toUpperCase()}` +
        (hasSelection && participating ? ` · ${origin ? 'SELECTED' : ''}${origin && count ? ' / ' : ''}${count ? `${count} RELATED` : ''}` : '');
    }
  }
  for (const item of nodeLabels) {
    item.element.classList.toggle('selected', item.node.id === selected);
    item.connected = connected.has(item.node.id);
  }
  $('fit-selection').disabled = !selected || !positions.has(selected);
  if (selected) renderRelations();
  updateButtons();
  dirty = true;
}
function safeViewport() {
  const header = document.querySelector('header').getBoundingClientRect();
  const toolbar = document.querySelector('.toolbar').getBoundingClientRect();
  let left = innerWidth >= 900 ? $('layers').getBoundingClientRect().right + 24 : 20;
  let right = innerWidth - 24, top = header.bottom + 18, bottom = toolbar.top - 22;
  if (!$('inspector').hidden) {
    const inspector = $('inspector').getBoundingClientRect();
    if (innerWidth >= 700) right = inspector.left - 24;
    else bottom = Math.min(bottom, inspector.top - 18);
  }
  if (right - left < 180) left = 20;
  return { left, top, width: Math.max(120, right-left), height: Math.max(100, bottom-top) };
}
function fitSelection() {
  if (!selected || !positions.has(selected)) return;
  controls.update(); camera.updateMatrixWorld();
  const points = [positions.get(selected).clone()];
  for (const link of selectionLinks()) {
    const a = positions.get(link.source), b = positions.get(link.target);
    // Include curve excursions as well as endpoints in the fitted volume.
    points.push(...linkCurve(a, b, isCross(link)).getPoints(12));
  }
  framePoints(points);
}
function framePoints(input, direction = null) {
  if (!input.length) return;
  const points = input.flatMap(point => [point.clone(), point.clone().add(new THREE.Vector3(0, 0.65, 0))]);
  const back = direction ? direction.clone().normalize() : new THREE.Vector3(0,0,1).applyQuaternion(camera.quaternion);
  const right = direction ? new THREE.Vector3().crossVectors(camera.up, back).normalize() : new THREE.Vector3(1,0,0).applyQuaternion(camera.quaternion);
  const up = direction ? new THREE.Vector3().crossVectors(back, right).normalize() : new THREE.Vector3(0,1,0).applyQuaternion(camera.quaternion);
  const bounds = fitBounds(points.map(p => [p.dot(right), p.dot(up), p.dot(back)]),
    { width: innerWidth, height: innerHeight }, safeViewport(), THREE.MathUtils.degToRad(camera.fov));
  const target = right.clone().multiplyScalar(bounds.center[0] + bounds.shift[0])
    .addScaledVector(up, bounds.center[1] + bounds.shift[1]).addScaledVector(back, bounds.center[2]);
  moveTo(target.clone().addScaledVector(back, bounds.distance), target);
}
function setHoveredLink(link) {
  if (hoveredLink === link) return;
  hoveredLink = link;
  hoverLabel.visible = Boolean(link);
  hoverStroke.visible = Boolean(link);
  hoverStroke.geometry.dispose();
  hoverStroke.geometry = new THREE.BufferGeometry();
  if (link) {
    const a = positions.get(link.source), b = positions.get(link.target);
    hoverStroke.geometry.setFromPoints(linkPoints(a, b, isCross(link)));
    hoverLabel.position.copy(linkCurve(a, b, isCross(link)).getPoint(0.5));
    hoverElement.textContent = link.predicate;
  }
  dirty = true;
}
function moveTo(position, target) {
  if (reducedMotion) {
    camera.position.copy(position); controls.target.copy(target); controls.update();
  } else travel = { from: camera.position.clone(), to: position, startTarget: controls.target.clone(), target, start: performance.now() };
}
function reset() {
  focused = null;
  const points = [];
  for (const x of [-planeWidth/2, planeWidth/2]) for (const z of [-planeDepth/2, planeDepth/2])
    for (const y of [layerY(activeLayers[0]), layerY(activeLayers.at(-1))]) points.push(new THREE.Vector3(x,y,z));
  framePoints(points, new THREE.Vector3(0.64,0.48,0.72));
  updateButtons(); updateSelection();
}
function focusLayer(index, plan = false) {
  focused = index;
  const y = layerY(data.layers[index].id);
  const points = [];
  for (const x of [-planeWidth/2, planeWidth/2]) for (const z of [-planeDepth/2, planeDepth/2]) points.push(new THREE.Vector3(x,y,z));
  framePoints(points, plan ? new THREE.Vector3(0,1,0.001) : new THREE.Vector3(0.13,0.88,0.56));
  updateButtons(); updateSelection();
}
function updateButtons() {
  $('layer-count-key').hidden = !selected;
  $('grid-neighbourhoods').hidden = focused !== layerIndex.get('grid');
  document.querySelectorAll('#layer-buttons button').forEach(button => {
    button.hidden = !activeLayers.includes(data.layers[Number(button.dataset.index)].id);
    const active = Number(button.dataset.index) === focused;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
    const layer = data.layers[Number(button.dataset.index)];
    const count = layerConnections.get(layer.id)?.nodes.size || 0;
    const origin = Boolean(selected && byId.get(selected).layer === layer.id);
    const participating = origin || layerConnections.has(layer.id);
    button.classList.toggle('related-layer', Boolean(selected && participating));
    button.classList.toggle('selection-layer', origin);
    button.classList.toggle('unrelated-layer', Boolean(selected && !participating));
    button.dataset.relatedCount = count;
    const badge = button.querySelector('.layer-count');
    badge.textContent = count; badge.hidden = !selected || !count;
    badge.setAttribute('aria-label', `${count} related ${count === 1 ? 'node' : 'nodes'}`);
    button.title = layer.subtitle + (selected ? `\n${origin ? 'Contains the selected entity. ' : ''}${count} related ${count === 1 ? 'node' : 'nodes'} in the current filters.` : '');
  });
}
function choose(id, center = false) {
  selected = id;
  if (!id) { $('inspector').hidden = true; updateSelection(); return; }
  const node = byId.get(id);
  if (node.detail && !$('details').checked) { $('details').checked = true; rebuild(); }
  const layer = data.layers[layerIndex.get(node.layer)];
  $('entity-layer').textContent = layer.title.toUpperCase();
  $('entity-title').textContent = node.label;
  $('entity-id').textContent = node.id;
  $('entity-types').replaceChildren(...node.types.map(type => {
    const span = document.createElement('span'); span.textContent = type; return span;
  }));
  $('entity-description').textContent = node.description || 'No description is asserted in the local source files.';
  $('entity-sources').replaceChildren(...node.sources.map(source => {
    const a = document.createElement('a'); a.textContent = source; a.href = '../' + source;
    a.target = '_blank'; a.rel = 'noopener'; return a;
  }));
  $('inspector').hidden = false;
  if (center) focused = layerIndex.get(node.layer);
  updateButtons(); updateSelection();
  // All entry points frame the selected neighbourhood, not just its centre.
  fitSelection();
}
function renderRelations() {
  const id = selected;
  const relations = selectionLinks();
  $('relation-count').textContent = `(${relations.length}/${adjacency.get(id).length} visible)`;
  $('relations').replaceChildren();
  for (const layer of [...data.layers].reverse()) {
    const group = layerConnections.get(layer.id);
    if (!group?.links.length) continue;
    const section = document.createElement('section'); section.className = 'relation-group'; section.dataset.layer = layer.id;
    section.style.setProperty('--layer-color', layer.color);
    const heading = document.createElement('h3'); heading.className = 'relation-group-heading';
    const title = document.createElement('span'); title.textContent = layer.title;
    const count = document.createElement('small');
    count.textContent = `${group.nodes.size} ${group.nodes.size === 1 ? 'node' : 'nodes'} · ${group.links.length} ${group.links.length === 1 ? 'link' : 'links'}`;
    heading.append(title, count); section.append(heading);
    const buttons = group.links.map(link => {
    const outgoing = link.source === id, other = byId.get(outgoing ? link.target : link.source);
    const button = document.createElement('button'); button.className = 'relation';
    const predicate = document.createElement('small');
    predicate.textContent = `${outgoing ? '→' : '←'} ${link.predicate}`;
    const name = document.createElement('span'); name.textContent = other.label;
    button.title = `${link.source} → ${link.predicate} → ${link.target}\n${link.sources.join('\n')}`;
    button.append(predicate, name); button.onclick = () => choose(other.id, true);
    button.onpointerenter = () => setHoveredLink(link);
    button.onpointerleave = () => setHoveredLink(null);
    button.onfocus = () => setHoveredLink(link);
    button.onblur = () => setHoveredLink(null);
    return button;
    });
    section.append(...buttons); $('relations').append(section);
  }
  if (!relations.length) {
    const empty = document.createElement('p'); empty.className = 'empty';
    empty.textContent = 'No connections match the current relationship and visibility filters.';
    $('relations').append(empty);
  }
}
for (let index = data.layers.length - 1; index >= 0; index--) {
  const layer = data.layers[index];
  const button = document.createElement('button'); button.dataset.index = index;
  button.style.setProperty('--layer-color', layer.color);
  button.innerHTML = `<span class="number">${String(index+1).padStart(2,'0')}</span><span class="swatch" style="background:${layer.color}"></span><span class="layer-name">${layer.title}</span><span class="layer-count" hidden></span>`;
  button.title = layer.subtitle;
  button.onclick = () => { choose(null); focusLayer(index); };
  $('layer-buttons').append(button);
}
for (const group of gridLayout.groups) {
  const button=document.createElement('button');button.textContent=group.title;
  button.dataset.gridFocus=group.id;button.onclick=()=>focusGridGroup(group.id);
  $('grid-neighbourhoods').append(button);
}
$('reset').onclick = reset;
$('close').onclick = () => choose(null);
$('plan').onclick = () => focusLayer(focused ?? layerIndex.get(activeLayers.at(-1)), true);
$('details').onchange = () => {
  if (selected && byId.get(selected).detail) choose(null);
  rebuild(); if (selected) fitSelection();
};
function changeLinks() {
  updateSelection();
  if (selected) fitSelection();
}
$('links').onchange = changeLinks;
$('predicate-filter').onchange = changeLinks;
$('fit-selection').onclick = fitSelection;
for (const predicate of [...new Set(data.links.map(link => link.predicate))].sort()) {
  const option = document.createElement('option'); option.value = predicate;
  option.textContent = predicate; $('predicate-filter').append(option);
}
$('spacing').oninput = () => {
  gap = Number($('spacing').value); rebuild();
  if (selected) fitSelection(); else if (focused !== null) focusLayer(focused);
};
function search() {
  const query = $('search').value.trim().toLowerCase();
  const results = $('search-results'); results.replaceChildren(); results.hidden = !query;
  if (!query) return;
  const score = node => {
    const local = node.short.split(':').slice(1).join(':').toLowerCase();
    if (node.id.toLowerCase() === query || local === query || node.label.toLowerCase() === query) return 10;
    if (node.label.toLowerCase().replaceAll(' ', '') === query.replaceAll(' ', '')) return 8;
    return node.label.toLowerCase().startsWith(query) ? 5 : 0;
  };
  const matches = data.nodes.filter(node => `${node.label} ${node.short} ${node.id} ${node.types.join(' ')}`.toLowerCase().includes(query))
    .sort((a, b) => score(b) - score(a) || a.label.localeCompare(b.label));
  for (const node of matches.slice(0, 30)) {
    const button = document.createElement('button');
    const title = document.createElement('span'); title.textContent = node.label;
    const sub = document.createElement('small'); sub.textContent = `${node.types.join(' · ')} / ${data.layers[layerIndex.get(node.layer)].title}`;
    button.append(title, sub); button.onclick = () => { choose(node.id, true); results.hidden = true; $('search').blur(); };
    results.append(button);
  }
  if (!matches.length || matches.length > 30) {
    const message = document.createElement('div'); message.className = 'empty';
    message.textContent = matches.length ? `${matches.length} matches — refine your search to see more.` : 'No matching entities.';
    results.append(message);
  }
}
$('search').oninput = search;
$('search').onfocus = search;
$('search').onkeydown = event => {
  if (event.key === 'Enter') $('search-results').querySelector('button')?.click();
};
document.addEventListener('keydown', event => {
  if (event.key === '/' && document.activeElement.tagName !== 'INPUT') { event.preventDefault(); $('search').focus(); }
  if (event.key === 'Escape') { $('search-results').hidden = true; $('search').blur(); choose(null); }
});
document.addEventListener('pointerdown', event => {
  if (!event.target.closest('.search, #search-results')) $('search-results').hidden = true;
});
function pickLink() {
  // Background assertions stay inert, even when a selection is active.
  if (!selected || !positions.has(selected)) return null;
  const lines = lineSets.at(-1);
  if (!lines?.visible) return null;
  raycaster.params.Line.threshold = 4 * 2 * camera.position.distanceTo(controls.target) *
    Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / innerHeight;
  const hit = raycaster.intersectObject(lines, false)[0];
  return hit ? lines.userData.segmentLinks[Math.floor(hit.index / 2)] : null;
}
function pick(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.set((event.clientX-rect.left)/rect.width*2-1, -(event.clientY-rect.top)/rect.height*2+1);
  raycaster.setFromCamera(pointer, camera);
  return raycaster.intersectObjects(meshes, false)[0]?.object.userData.node;
}
let down = null;
renderer.domElement.addEventListener('pointerdown', event => { down = { x:event.clientX, y:event.clientY }; });
renderer.domElement.addEventListener('pointerup', event => {
  if (event.button === 0 && down && Math.hypot(event.clientX-down.x,event.clientY-down.y) < 5) {
    choose(pick(event)?.id ?? null);
  }
  down = null;
});
renderer.domElement.addEventListener('pointermove', event => {
  if (event.buttons) { $('tooltip').hidden = true; setHoveredLink(null); return; }
  const node = pick(event), link = node ? null : pickLink();
  setHoveredLink(link);
  // Relation hovers use only the compact in-scene predicate label.
  $('tooltip').hidden = !node;
  renderer.domElement.style.cursor = node ? 'pointer' : link ? 'help' : 'grab';
  if (node) {
    $('tooltip').textContent = `${node.label} · ${node.types.join(', ')}`;
    $('tooltip').style.left = `${Math.min(event.clientX+15, innerWidth-345)}px`;
    $('tooltip').style.top = `${Math.min(event.clientY+15, innerHeight-65)}px`;
  }
});
renderer.domElement.addEventListener('pointerleave', () => { $('tooltip').hidden = true; setHoveredLink(null); });
controls.addEventListener('start', () => { travel = null; $('tooltip').hidden = true; setHoveredLink(null); });
controls.addEventListener('change', () => { dirty = true; });
function resize() {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); labels.setSize(innerWidth, innerHeight); dirty = true;
}
window.addEventListener('resize', () => { resize(); if (selected) fitSelection(); });
resize(); rebuild(); reset();
$('notice').hidden = true;
function animate(now) {
  requestAnimationFrame(animate);
  if (travel) {
    const t = Math.min(1, (now-travel.start)/750), ease = t*t*(3-2*t);
    camera.position.lerpVectors(travel.from, travel.to, ease);
    controls.target.lerpVectors(travel.startTarget, travel.target, ease);
    dirty = true; if (t === 1) travel = null;
  }
  controls.update();
  if (!dirty) return;
  camera.updateMatrixWorld();
  const occupied = [
    { left: 0, top: 0, right: innerWidth, bottom: 100 },
    $('layers').getBoundingClientRect(),
    { left: 0, top: innerHeight - 125, right: innerWidth, bottom: innerHeight },
  ];
  if (!$('inspector').hidden) occupied.push($('inspector').getBoundingClientRect());
  for (const { title, titleObject } of planes) {
    if (!title) continue;
    title.style.marginLeft = '0px';
    if (!title.classList.contains('participating')) continue;
    const point = titleObject.position.clone().project(camera);
    const x = (point.x+1)*innerWidth/2, y = (1-point.y)*innerHeight/2;
    const width = title.getBoundingClientRect().width || title.textContent.length*6.6+16;
    const safe = safeViewport();
    const center = Math.max(safe.left+width/2,Math.min(safe.left+safe.width-width/2,x));
    title.style.marginLeft = `${center-x}px`;
    occupied.push({left:center-width/2-5,right:center+width/2+5,top:y-15,bottom:y+15});
  }
  for (const { label, group, index } of groupLabels) {
    const point=label.position.clone().project(camera);
    const x=(point.x+1)*innerWidth/2, y=(1-point.y)*innerHeight/2;
    const width=Math.min(175, (group.label.length+6)*5.5);
    const rect={left:x-width/2-3,right:x+width/2+3,top:y-12,bottom:y+12};
    const collision=occupied.some(r=>rect.left<r.right && rect.right>r.left && rect.top<r.bottom && rect.bottom>r.top);
    const candidate = !selected && (index === focused || (focused === null && data.layers[index].id === 'catalogue'));
    label.visible = candidate && point.z>-1 && point.z<1 && x>0 && x<innerWidth && y>0 && y<innerHeight && !collision;
    if (label.visible) occupied.push(rect);
  }
  // Greedy screen-space decluttering: selected labels first, then neighbours.
  const ordered = [...nodeLabels].sort((a, b) => {
    const priority = item => (item.node.id === selected ? 10 : item.connected ? 5 : item.index === focused ? 2 : 0)
      + (item.node.types.includes('dcat:DatasetSeries') ? 1 : item.node.layer === 'grid' ? (item.node.kind === 'entity' ? -1 : item.node.kind === 'property' ? 0 : 1.5) : 0);
    return priority(b) - priority(a);
  });
  for (const item of ordered) {
    const isSelected = item.node.id === selected;
    const near = camera.position.distanceTo(item.label.position) < 34;
    const candidate = isSelected || (selected && positions.has(selected) ? item.connected : (focused !== null ? item.index === focused : near || item.sparse));
    const projected = item.label.position.clone().project(camera);
    const x = (projected.x + 1) * innerWidth / 2, y = (1 - projected.y) * innerHeight / 2;
    const width = Math.min(180, item.node.label.length * 6.2);
    const rect = { left: x-width/2-5, right: x+width/2+5, top: y-10, bottom: y+10 };
    const inView = projected.z > -1 && projected.z < 1 && x > 0 && x < innerWidth && y > 0 && y < innerHeight;
    const collision = occupied.some(r => rect.left < r.right && rect.right > r.left && rect.top < r.bottom && rect.bottom > r.top);
    item.label.visible = candidate && inView && (isSelected || !collision);
    if (item.label.visible) occupied.push(rect);
    item.element.style.opacity = isSelected ? '1' : item.connected ? '0.95' : item.node.layer === 'grid' && item.node.kind === 'entity' ? '0.55' : '0.8';
  }
  for (const { link, label } of edgeLabels) {
    const point = label.position.clone().project(camera);
    const x = (point.x+1)*innerWidth/2, y = (1-point.y)*innerHeight/2;
    const width = link.predicate.length*6+16;
    const rect = { left:x-width/2, right:x+width/2, top:y-12, bottom:y+12 };
    const collision = occupied.some(r => rect.left < r.right && rect.right > r.left && rect.top < r.bottom && rect.bottom > r.top);
    label.visible = link !== hoveredLink && point.z > -1 && point.z < 1 && x > 0 && x < innerWidth && y > 100 && y < innerHeight-125 && !collision;
    if (label.visible) occupied.push(rect);
  }
  renderer.render(scene, camera); labels.render(scene, camera); dirty = false;
}
requestAnimationFrame(animate);
