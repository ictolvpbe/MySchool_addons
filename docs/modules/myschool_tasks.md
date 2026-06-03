# myschool_tasks

Work-in-progress module — geen `__manifest__.py` aanwezig op huidige branches.

## Status

| Onderdeel | Stand |
|---|---|
| Status | WIP / placeholder |
| Manifest | ontbreekt — niet installable |
| Vermoedelijke scope | Algemene tasks-module (alternatief voor of bovenop Odoo's standaard tasks) |

## Wat is er?

Folder met code-stubs, geen complete Odoo-module.

## Bedoeling

Speculatief op basis van naam:

- Lichte tasks-functionaliteit voor school-context (afwijkend van Odoo's `project` of `myschool_appfoundry`)
- Mogelijk koppeling met `myschool_dashboard` voor per-user taken-overzicht
- Of: workflow-extension van bestaande modules

Te bepalen door author bij activatie.

## Verhouding

Bij activatie te bepalen vs:

- [`myschool_appfoundry`](myschool_appfoundry.md) — dev-tasks
- [`myschool_devhub`](myschool_devhub.md) — project-tasks
- [`myschool_dashboard`](myschool_dashboard.md) — taken-aggregator
- Odoo's standaard `project.task`-model (zou een refactor-baseline kunnen zijn)

## Open punten

- Manifest schrijven + dependencies bepalen
- Scope verduidelijken in [Werf D / ADR 0003](../decisions/)
- TBD voor next activator
