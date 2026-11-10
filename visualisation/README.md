# Ontology atlas

An explorable Three.js line drawing of Busbar's local RDF, arranged in seven conceptual viewing layers. These layers are presentation choices, **not** an RDF hierarchy or an assertion that the ontologies are equivalent.

## Open

From the repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Visit **http://localhost:8000/visualisation/**. Do not open `index.html` via `file://`: the graph loads with `fetch`.

No JavaScript build step is needed. Three.js **0.170.0** and its controls/label renderer load from jsDelivr; optional fonts load from Google Fonts, with local fallbacks. Internet access is needed for Three.js. The RDF projection is local; there is no analytics or external dataset fetching.

## Explore

- Drag to orbit, scroll/pinch to zoom, right-drag to pan (two-finger drag on touch).
- The atlas has one unified view of schema and catalogue records. Choose a layer at left to focus it; **Plan view** looks down on that layer.
- Catalogue records are arranged in labelled **publisher groups**, with compact series-family boxes. Larger markers identify series; smaller markers identify files. Editions and distributions sit next to their parent series, with recorded editions aligned above that family on their separate layer. Focus the Catalogue layer to read the publisher labels, then click a label to frame its group. Labels are decluttered in the overview. Grouping follows asserted `dct:publisher`, `dcat:inSeries` and `dcat:distribution` links; it does not add RDF assertions.
- Click an entity to inspect its types, description, source files and incoming/outgoing assertions. Selection frames the entity and its visible neighbours in the space left by the inspector, navigation and toolbar, retaining your viewing direction. **Fit selection + neighbours** repeats this at any time. Select a connected entity in the inspector to move to it. Arrowheads on highlighted links point toward the RDF object.
- Selecting an entity highlights its own plane and every layer containing a visible related node, with subtle layer-coloured washes, stronger outlines and readable titles. Uninvolved layers fade. The stack list shows **unique related-node counts** per layer (the selected node itself is excluded). Matching colours connect the stack, plane titles and inspector sections.
- Inspector connections are grouped by the other endpoint's layer, showing both unique-node and assertion counts. Several predicates leading to the same node count once in the stack but remain separate links in the inspector. Predicate, cross-layer and edition/file filters update all three representations together. Clearing the selection removes the badges and returns to normal layer focus.
- **Relationships** isolates an RDF predicate (for example `dct:publisher`, `busbar:describes` or `dcat:inSeries`) in both the scene and inspector. It composes with the cross-layer and edition/file toggles. The inspector shows visible versus total assertion counts; filters do not remove RDF data.
- Selected-neighbourhood links have decluttered predicate labels. Hover one of these links for a compact predicate label, without a large tooltip. Background links do not react to the mouse. Hover or keyboard-focus an inspector connection to identify its line; its title retains directed endpoints and source-file provenance.
- Search names, IRIs or types across the entire atlas. `/` focuses search, Enter selects the first result, Escape closes details. Search and inspector navigation provide keyboard access to entities.
- **Recorded editions** is a separate layer for capture-generated metadata from `editions/`, visible by default. Series remain in **Curated catalogue**, joined to their declarations by the same URI.
- **All editions & files** is enabled by default, including the original catalogue's dataset editions and anonymous file distributions. Untick it for a lighter overview. Search reveals these automatically when needed.
- Toggle cross-layer links or change the layer spacing. **Reset view** restores the overview without changing the data filters or selection.
- Labels are decluttered in screen space; zoom or focus to see more. Tooltips and search expose full names.

### Unified view and grouping

Named classes/datatypes, properties, SKOS concepts/schemes, organizations and catalogue records share one view. Properties use diamond-like markers; their asserted domain/range and other relationships appear when both endpoints are included. The view is still a selective projection, not all triples in the repository or a complete OWL reasoner.

Family and publisher placement is stable across the editions toggle. The root series' asserted publisher takes precedence for a family; if no publisher is asserted, the group is labelled **Publisher not asserted**. Multiple publisher/parent assertions are resolved lexically for one deterministic placement only; all the original assertions remain in the graph. Smaller family boxes are layout decorations, not extra relationship edges.

### Grid domain neighbourhoods

Focus **Grid domain** to see five thematic neighbourhoods—Network structure, Projects & connections, Capacity & observations, Geography & responsibility, Dataset classifications—and a **Shared attributes** strip. Click a heading or use the neighbourhood shortcuts under the layer list to frame a group. Classes/concepts get larger markers, properties smaller diamonds and reference instances smaller, quieter markers in separate bands. Other-layer labels stay quiet while a layer is focused.

`grid-layout-config.js` contains the reviewed display seeds and shared-attribute exceptions. `grid-layout.js` then follows explicit subclass/broader/scheme assertions, places properties by domain (or range if no included named domain is available), and groups reference instances by their declared type. Parent classes sit above subclass branches; existing subclass/broader edges are more visible when the grid layer is focused. Small brackets associate properties with their layout anchor; they are decorations, not new RDF edges.

Ambiguous/unresolved properties go into Shared attributes. New terms without a known assignment remain visible in **Other grid terms**. Multiple hierarchy parents are resolved deterministically for packing only; all original assertions remain available in the scene and inspector. The layout does not infer class equivalence, property ownership or ontology membership from visual proximity. Recorded catalogue data and publisher grouping are unchanged.

## Refresh the projection

After editing RDF, run from the repository root:

```bash
uv run python visualisation/export_graph.py
# Or, with dependencies already installed:
.venv/bin/python visualisation/export_graph.py
```

Reload the page. `graph.json` is checked in so viewing needs only a static HTTP server. The exporter uses rdflib, already a project dependency, and never accesses the network. The JSON records a SHA-256 digest for every input; hover over the entity/link counts to inspect them. Projection contract tests detect an export that no longer matches the current inputs.

### Relationship to the ontology builds

The atlas reads the canonical RDF inputs directly, **not** `build/news-catalogues.owl` or `build/observations.trig`. Rebuilding those alone does not refresh the atlas; rerun the exporter too.

- `busbar build-ontology` makes a flat viewer projection of current declarations and one successful archived catalogue capture per source. It deliberately excludes the original grid ontology, original curated catalogue and recorded editions.
- `busbar build-observations` preserves separate named graphs for definitions, the curated catalogue, recorded editions, observation metadata and publisher snapshots.
- The atlas includes the grid ontology, current declarations, original catalogue and recorded edition metadata. It preserves per-file assertion provenance but does not render the historical snapshot graphs.

The recent series changes moved publisher-derived titles, publisher references, latest-file distributions and recorded editions into `editions/`. Those are now included; the ENWL series retains its theme/classification from `definitions/` while connecting to its captured edition and file provenance. No equivalence with the older catalogue's ENWL series is inferred. The dedicated recorded-editions layer separates capture results from declarations. Snapshot datasets are not silently merged into this view.

## Scope and fidelity

The exporter reads `busbar-ontology.ttl`, `catalogue.ttl`, `vocabulary/*.ttl`, `definitions/**/*.ttl` and `editions/**/*.ttl`. It includes named typed entities, classes, properties and concepts, plus anonymous DCAT distributions with deterministic canonical blank-node identifiers. Blank-node IDs in the inspector are local projection identifiers, not public IRIs.

Edges are **only asserted triples whose endpoints are included**. Each edge preserves its predicate, direction and source file(s). No relationships are inferred from layer placement, and no inferred domain/range shortcuts are added. Multiple predicates between the same entities can overlap visually; the inspector lists them individually and gives assertion provenance on hover.

This is a selective atlas, not a complete RDF editor or OWL reasoner: anonymous restrictions, literal-valued attributes and untyped external endpoints are not drawn as nodes. Some literal descriptions are shown in the inspector. The standards layer contains the repository's minimal local declarations, not complete external vocabularies. Private captured file bytes, catalogue snapshots, historical observation graphs, SHACL files and the bundled LTDS/CIM artifacts are not included. Only the public RDF metadata under `editions/` is added; no private CSV data is read or exported. The original grid domain remains subject to the review described in `docs/cim-ltds-alignment.md`.

## Development checks and follow-up

```bash
node --test visualisation/*.test.mjs
.venv/bin/python -m unittest discover -s tests -p test_visualisation.py -v
```

[The improvement backlog](BACKLOG.md) records completed work and remaining follow-up.

Catalogue placement is deterministic by publisher and series family; the Grid domain uses reviewed thematic neighbourhoods and assertion-based families. Remaining layers use type/name grids. Proximity carries no additional semantic meaning. Layer assignment is a display convention, and each entity appears once even when several source files describe it.
