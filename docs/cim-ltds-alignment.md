# CIM/LTDS alignment: evidence and pending review

## Completed: the DNO glossary definition

`grid:DistributionNetworkOperator` is a local SKOS classification, not an invented
claim that an external DNO OWL class exists. Its definition is transcribed from:

- Release: [LTDS Grid Modelling v2-1-1](https://cim.bsigroup.com/releases/ltds/ltds-grid-modelling-v2-1-1-r15/).
- Document: **LTDS Grid Modelling Annex 2 - Data Exchange Specifications v7**.
- Locator: **section 6, Terms, Definitions and Abbreviated Terms, page 75**.
- Entry: **Distribution Network Operator (DNO)**.

> A DNO is a company that owns, operates and maintains an electric distribution network in Great Britain.

Only line breaks were normalized. The concept points through `dct:source` to the
bibliographic document resource in
`definitions/references/ltds-grid-modelling-v2-1-1.ttl`. That resource records the
release, document title and locator. No PDF copy, local download path or file hash
is stored in the project.

The supplied release's Stage 2 publication notes identify it as governing the May
2026 cycle; this is a version-specific citation, not a claim that the release is
the latest for every later cycle.

## Completed inspection, not ontology alignment

The supplied release was inspected for organization, role and ownership concepts:

- Its ten RDFS files and nine SHACL files do not include the organization,
  DNO/DSO-role, market-role or ownership schema terms investigated.
- The wider bundled UML model does contain `Organisation`, `OrganisationRole`,
  `MarketRole`, ownership concepts and a European Network Codes extension
  `DistributionSystemOperator`.
- In that model DSO specializes `SystemOperator`, then
  `PowerSystemOrganisationRole`, then `OrganisationRole`.
- Presence in the wider UML model does not mean inclusion in an LTDS exchange profile.
- The glossary definition does not establish DNO/DSO equivalence.

No `owl:equivalentClass`, `owl:sameAs` or `skos:exactMatch` mapping is asserted.

## Pending: review the original grid-domain ontology

`busbar-ontology.ttl` is a grid-domain model hosted by the catalogue project.
Its substations, projects and capacity concepts are not merely catalogue metadata.
They need a separate, concept-by-concept review before claiming CIM/LTDS alignment.

| Area to review | Questions to resolve |
|---|---|
| Sites and substations | Does Busbar's distinction between a physical site and a functional substation match the intended CIM/LTDS constructs? |
| GSP, BSP and primary roles | Are these local operational classifications, containers, or actual specializations of a CIM class? Do meanings differ by DNO? |
| Nodes and connectivity | Do Busbar nodes represent CIM connectivity nodes, topological nodes, or a source-specific abstraction? |
| Circuits and transformers | What is the resource granularity: a source row, circuit, equipment object, winding or terminal? |
| Projects | Distinguish connection-register projects from planned grid changes and LTDS Difference Models. These are not automatically equivalent. |
| Capacity and forecasts | Compare quantity, units, assessment basis, season, scenario and time coverage, not just matching field names. |
| Identifiers | Establish uniqueness and persistence scope across source datasets, publication cycles and CIM models. Do not join on a similarly named mRID without evidence. |
| Ownership and operation | Keep organizations, roles, asset ownership and operational participation distinct. |
| OWL constraints | Check whether cardinalities and domain/range declarations are domain truths or assumptions inherited from particular source tables. |

For each reviewed term, record:

1. Busbar definition and the source-data use case it serves.
2. Exact target term, namespace, profile version and documentary locator.
3. Whether the target is in the base model, an extension, or an exchanged profile.
4. Relationship: equivalent, narrower, broader, related, or deliberately local.
5. Evidence, limitations and reviewer decision.

Use mappings appropriate to the resource types: SKOS mappings for concepts,
OWL/RDFS axioms for classes and properties only when their semantics justify them.
Similar names alone are not evidence of equivalence.

This is a review backlog, not a completed crosswalk. No substation, project or
capacity mapping is introduced by documenting it.
