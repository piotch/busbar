# Ontology atlas — next improvements

## Completed

- [x] **1. Selection framing.** Fit a selected entity and its visible, predicate-filtered neighbours into the space left by navigation, inspector and toolbar; retain the viewing direction. Provide a repeatable “Fit selection + neighbours” action.
- [x] **2. Relationship exploration.** Predicate filter shared by scene and inspector, labels on selected-neighbourhood links (decluttered), and compact predicate hovers restricted to the selected neighbourhood. Background links are inert; full direction/provenance details remain in the inspector.

- [x] **3. Meaningful grouping within layers.** Deterministic publisher blocks with compact series-family boxes. Editions and distributions follow explicit parent links; recorded metadata stays on its own aligned layer. Publisher labels frame a group; larger series and smaller file markers clarify hierarchy. Grouping never adds RDF edges.
- **4. Model / Catalogue presets — tried and removed.** Removed at user request: one unified view is more useful. Publisher grouping, named property declarations and asserted domain/range links are retained. Anonymous OWL restrictions remain explicitly out of scope.

- [x] **Grid domain neighbourhoods.** Reviewed thematic seeds, assertion-driven class/concept families and nearby properties, quieter reference-instance bands and a shared-attributes strip. Focus shortcuts and clickable headings; fallback placement retains unknown terms. No RDF modifications.

- [x] **Connected-layer treatment.** Selection highlights all participating planes, adds filter-aware unique-neighbour counts to the stack, and groups inspector assertions by the other endpoint's layer. Distinct node and link totals are explicit; uninvolved layers fade. No new background hover interactions.

## Later

- [ ] Optional collapse/expand of publisher groups; currently click-to-frame is implemented, not collapse.

- [ ] **5. Shareable views and visible provenance.** Encode selection, layer, filters and camera in a URL; add a compact projection information panel with input fingerprints, freshness and exclusions.
