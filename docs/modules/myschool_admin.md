# myschool_admin

Admin-laag bovenop `myschool_core`. UI + workflow voor school-administrators om organisaties, services en periodes te beheren. Bevat school-specifieke views, action-menus en admin-only configuration.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `mail`, `myschool_core`, `web` |
| Wordt gebruikt door | `activiteiten`, `planner`, `myschool_sync` |

## Doel

`myschool_core` heeft het data-model maar geen rijke UI. `myschool_admin` voegt:

- **Admin-views**: tabs, kanban, calendar voor org/person/period management
- **Actions + wizards**: bulk-acties (deactiveren werknemers, bulk-rol-toekenning)
- **Settings-tab**: school-specifieke configuratie via `res.config.settings`

## Categorie-fit

Deze module is bewust gescheiden van `core` om:

- `core` headless-bruikbaar te houden (MCP, sync, API-clients zonder web-deps)
- Theme + UI-aanpassingen lokaal in deze module te kunnen doen

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_core`](myschool_core.md) — fundament (depends op deze)
- [`myschool_sync`](myschool_sync.md) — replicatie (gebruikt admin-views)
- [`myschool_theme`](myschool_theme.md) — styling-laag
