# myschool_devhub

DevHub — development project management met agile workflow. Alternatief voor of opvolger van `myschool_appfoundry`. Te evalueren welke de standaard wordt voor MySchool-development (zie [Werf D / ADR 0003](../decisions/)).

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `base`, `mail`, `myschool_core`, `process_mapper` |

## Doel

Vergelijkbaar met `myschool_appfoundry`: items, sprints, stages, releases. Verschilt door:

- Diepere integratie met [`process_mapper`](process_mapper.md) (BPMN-flow per project)
- Mogelijk andere data-modellen voor non-software projecten
- Knowledge-management-integratie

## Relatie met myschool_appfoundry

Beide modules dekken project-management. Werf D moet kiezen:

1. **Standaardiseer op één** — een van beide deprecaten + records migreren
2. **Twee modules, twee scopes** — appfoundry voor software-dev, devhub voor algemeen
3. **Vervang door Odoo `project`-addon** — gebruik standaard Odoo + custom velden

Open punt; te documenteren in ADR 0003.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_appfoundry`](myschool_appfoundry.md) — vergelijkbaar concept (te evalueren)
- [`process_mapper`](process_mapper.md) — depends op deze
- [`myschool_core`](myschool_core.md) — fundament
