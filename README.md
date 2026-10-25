<p align="center">
  <img src="docs/images/busbar.png" alt="Busbar logo" width="240">
</p>

<h1 align="center">Busbar</h1>

Busbar is an open-source catalogue of open datasets about the UK electricity grid. It records where datasets come from, what they describe, their geographic and temporal coverage, and their publication history, using established metadata standards to organise this information.

The project starts from a practical observation: finding a dataset is only the first step towards using it. Grid data is published across many organisations, with different formats, definitions and update cycles. Busbar helps users identify comparable datasets and follow successive publications, providing a clearer foundation for grid modelling, simulation and digital twin projects.

The core catalogue describes those datasets in two standard files, both written in [Turtle](https://www.w3.org/TR/turtle/) (`.ttl`). Shared organization and catalogue definitions extend this foundation (see below).

| File | What it contains | Standard |
|---|---|---|
| `busbar-ontology.ttl` | The vocabulary: network concepts (substations, circuits, projects…), dataset types, publishers, areas | OWL 2, SKOS |
| `catalogue.ttl` | The datasets: who publishes each one, what it covers, and every edition and file | DCAT 3, Dublin Core |

The ontology defines network concepts such as `busbar:GridSupplyPoint`, and the catalogue uses them. UKPN and Northern Powergrid publisher references now reuse the shared organization identities under `definitions/`, rather than separate uppercase identifiers.

![Historical Busbar ontology and catalogue map](docs/images/busbar-map.png)

*Historical diagram of the initial domain model and catalogue. It predates the shared organization identities and ORG/SKOS DNO-classification changes and is not an exact representation of the current ontology.*

## Shared organizations and catalogue identities

- UKPN and Northern Powergrid are `org:Organization` instances, classified as DNOs
  through `org:classification` and the local SKOS scheme in `vocabulary/grid-roles.ttl`.
- ReferenceWorks is defined in `definitions/organisations/referenceworks.ttl`.
- ReferenceWorks publishes and maintains Busbar, whose identity is defined in
  `definitions/grid/catalogues/busbar.ttl`.
- Busbar's series membership, editions and distributions remain in `catalogue.ttl`.
  Its catalogue identity is `https://busbar.example/id/grid/catalogues/busbar`.
- UKPN/NPG source catalogues keep their separate identities under
  `grid/uk/dno/{dno}/catalogue` and their publisher responsibilities.

See [shared foundation](docs/shared-foundation.md). No curated ECR-to-source mapping
or DNO/DSO equivalence has been asserted yet.
