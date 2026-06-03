# myschool_appfoundry

AppFoundry — development project-management module met agile workflow. Items (user stories, bugs, tasks, improvements), Kanban-board met configurable stages, sprint-planning, release-management. Wordt gebruikt door `myschool_mcp` als provider — de 14 v1-MCP-tools werken tegen AppFoundry-data.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, gebruikt voor MySchool-development |
| Dependencies | `base`, `mail`, `myschool_core`, `myschool_theme` |
| Documentatie in-module | TODO (manifest aanwezig, README niet) |
| MCP-provider | `myschool_mcp/providers/appfoundry.py` met 14 tools |

## Kern-functionaliteit

Volgens `__manifest__.py` description:

- **User stories, bugs, tasks, improvements** als verschillende item-types
- **Kanban-board** met configurable stages (Backlog, In Progress, In Review, Done, ...)
- **Sprint-planning** met velocity-tracking
- **Release-management** met progress-tracking (% complete, open bugs)
- **Built-in process-mapping** met SVG canvas editor

## Item-entity

(Op basis van MCP-tools `appfoundry_*`; volledige model-schema TODO)

| Veld | Type | Doel |
|---|---|---|
| `display_code` | char | Externe identifier in format `MSA-NNN` (project-prefix + nummer) |
| `name` | char | Titel |
| `description` | text/html | Beschrijving |
| `type` | selection | Story / Bug / Task / Improvement |
| `stage_id` | m2o | Huidige Kanban-stage |
| `assignee_ids` | m2m | Toegewezen gebruiker(s) |
| `sprint_id` | m2o | Huidige sprint |
| `release_id` | m2o | Geplande release |
| `tag_ids` | m2m | Tags (vrije labels) |
| `blocked_by_ids` | m2m | Dependency-links naar andere items |

## Sprint + release

- **Sprint** = tijdgebonden iteratie (2-3 weken typisch). Items zijn aan een sprint gekoppeld; velocity = sum van story-points van completed items per sprint.
- **Release** = milestone. Items zijn gekoppeld via `release_id`. Release-progress = % completed items, gefilterd op open bugs.

## MCP-integratie

`myschool_mcp` exposeert AppFoundry via 14 tools. Zie [`myschool_mcp.md`](myschool_mcp.md) voor volledige lijst. Belangrijkste:

**Read**:
- `appfoundry_list_projects` — alle projecten
- `appfoundry_list_my_items` — open items voor huidige user
- `appfoundry_get_item` — full detail incl. chatter

**Write**:
- `appfoundry_set_stage` — verplaats item naar andere stage
- `appfoundry_post_comment` — comment toevoegen aan chatter (markdown)
- `appfoundry_create_item` — nieuw item

Items aanroepen met id óf `display_code` (bv. `"MSA-42"`).

## Per-tool autorisatie

Per [`myschool_mcp/security/mcp_security.xml`](../../myschool_mcp/security/mcp_security.xml):
- Read-tools → `group_appfoundry_user`
- Write/create-tools → `group_appfoundry_manager`

## Verwante modules

- [`myschool_mcp`](myschool_mcp.md) — MCP-server (dependent op deze)
- [`myschool_devhub`](myschool_devhub.md) — alternatief project-management (te evalueren in [Werf D / ADR 0003](../decisions/) voor non-software projecten)
- [`process_mapper`](../../process_mapper/) — BPMN-process-mapping (mogelijk dezelfde process-engine als AppFoundry's process-mapping?)

## Open punten

- **Eigen README/USER_MANUAL/DEVELOPER** ontbreekt nog in de module-dir
- **Categorie-fit**: AppFoundry is gespecialiseerd op software-development. Voor andere project-types (school-administratie, organisatorisch) wordt Odoo's standaard `project`-addon overwogen (Werf D, [`../decisions/`](../decisions/) bij volgende update)
- **Multi-project scope**: huidig vooral gericht op MSA (MySchool Admin) prefix; uitbreiding naar andere project-codes is mogelijk maar niet uitgebreid gedocumenteerd
