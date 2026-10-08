<p align="center">
  <img src="docs/images/busbar.png" alt="Busbar logo" width="240">
</p>

<h1 align="center">Busbar</h1>

Busbar is an open-source catalogue of open datasets about the UK electricity grid. It records where datasets come from, what they describe, their geographic and temporal coverage, and their publication history, using established metadata standards to organise this information.

The project starts from a practical observation: finding a dataset is only the first step towards using it. Grid data is published across many organisations, with different formats, definitions and update cycles. Busbar helps users identify comparable datasets and follow successive publications, providing a clearer foundation for grid modelling, simulation and digital twin projects.

This repository describes those datasets in two standard files, both written in [Turtle](https://www.w3.org/TR/turtle/) (`.ttl`).

| File | What it contains | Standard |
|---|---|---|
| `busbar-ontology.ttl` | The vocabulary: network concepts (substations, circuits, projects…), dataset types, publishers, areas | OWL 2, SKOS |
| `catalogue.ttl` | The datasets: who publishes each one, what it covers, and every edition and file | DCAT 3, Dublin Core |

The ontology defines the words, and the catalogue uses them. For example, the catalogue says a series is published by `id:UKPN` and describes `busbar:GridSupplyPoint`. Both terms are defined in the ontology.

![Busbar Ontology Map: Figure 1 shows every class of the network ontology with its inheritance and relations; Figure 2 shows how the catalogue describes datasets](docs/images/busbar-map.png)

*Figure 1 (top) shows every class of `busbar-ontology.ttl`: indented boxes inherit from the box above, and each line is a relation to another class. Figure 2 (bottom) shows how `catalogue.ttl` describes a dataset with DCAT and what it points to in the ontology.*
