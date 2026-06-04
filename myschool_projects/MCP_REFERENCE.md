# MySchool Projects — MCP reference (project-data pushen)

Deze gids beschrijft hoe een Claude-sessie (of andere MCP-client) project-
data naar de **myschool_projects**-app stuurt via de MySchool MCP-server.

## 1. Verbinding

| Wat | Waarde |
|---|---|
| Endpoint | `POST http(s)://<host>/mcp` (lokaal: `http://localhost:8069/mcp`) |
| Auth-header | `X-API-Key: <odoo-apikey>` |
| API-key | Odoo → Preferences → Account Security → New API Key (scope `rpc` of leeg) |
| Rechten | key-user heeft `group_mcp_user` + `group_projects_manager` nodig (schrijven). `group_myschool_core_admin` impliceert beide. |
| Provider aan | `myschool_mcp.provider_projects` = True (default) |

Registreren in Claude Code:
```
claude mcp add --transport http myschool http://<host>/mcp --header "X-API-Key: ..."
```
Acties verschijnen in de Odoo-chatter onder de key-user.

## 2. Datamodel

**Project** (`myschool.project`)
- `name`, `code` (uniek; voor lookups), `parent_id` (→ sub-project / WBS),
  `responsible`, `members`, `date_start`, `date_end`, `description`
- `state` ∈ `new` · `active` · `on_hold` · `done` · `cancelled`
- `progress` (berekend; rollt op uit sub-projecten of leaf-taken)

**Work item** (`myschool.project.task`) — het werk binnen een project
- `name`, `item_type` ∈ `task` · `milestone` · `phase` · `epic` · `bug`
- `project_id`, `parent_id` (→ self-hiërarchie / sub-items)
- `assigned_id`, `state` ∈ `todo` · `in_progress` · `blocked` · `done` · `cancelled`
- `priority` ∈ `0`(Low) · `1`(Normal) · `2`(High) · `3`(Critical)
- `date_start`, `date_deadline` (formaat `YYYY-MM-DD`), `planned_hours`
- `milestone_id` (→ doel-milestone), `depends_on_ids`, `tag_ids` (labels)
- Een **milestone** = work item met `item_type = milestone`.
- Een item **met kinderen** geldt als "summary" (voortgang rolt op).

Resolutie: projecten op **id of code** (case-insensitief); work items op
**id**; milestones op **id of naam** binnen het project. Gebruikers op
**login, id of `"me"`**.

## 3. Tools

### Read
| Tool | Parameters |
|---|---|
| `projects_list` | `parent?`, `top_level_only=true`, `my_only=false`, `limit=100` |
| `projects_get` | `project` → project + children + milestones + dependencies |
| `projects_tree` | `project?` → geneste WBS-boom van projecten |
| `projects_list_items` | `project`, `item_type?`, `state?`, `assignee?`, `open_only=false`, `limit=200` |
| `projects_search` | `query`, `project?`, `item_type?`, `state?`, `assignee?`, `limit=50` (kruis-project zoeken op naam) |

### Write
| Tool | Parameters |
|---|---|
| `projects_create_subproject` | `name`*, `parent?`, `code?`, `responsible?`, `state=new`, `date_start?`, `date_end?` |
| `projects_create_item` | `project`*, `name`*, `item_type=task`, `parent?`, `assignee?`, `state=todo`, `priority='1'`, `date_start?`, `date_deadline?`, `planned_hours?`, `milestone?`, `tags?` (lijst namen), `description?` |
| `projects_update_item` | `item`* (id), + elk veld om te wijzigen; `parent`/`milestone`/`assignee` = id (of naam/login); `tags` (vervangt); `false`/`0` wist |
| `projects_set_status` | `item`* (id), `state`* — snelle status-shortcut |
| `projects_add_milestone` | `project`*, `name`*, `date?`, `state=todo`, `description?` (shortcut voor create_item type=milestone) |
| `projects_set_dependency` | `project`*, `depends_on`*, `remove=false` (project-niveau) |

\* = verplicht.

## 4. Een volledig project pushen (voorbeeld-flow)

1. **Project** — `projects_create_subproject {name:"OLVP-ICT", code:"OLVP-ICT", state:"active"}`
2. **Milestones** — `projects_add_milestone {project:"OLVP-ICT", name:"Netwerk live", date:"2026-09-01"}`
3. **Fases (containers)** — `projects_create_item {project:"OLVP-ICT", name:"Fase 1 — Netwerk", item_type:"phase"}`
4. **Taken onder een fase, gekoppeld aan een milestone** —
   `projects_create_item {project:"OLVP-ICT", name:"Switch config", parent:<phase_id>, assignee:"jan.peeters", state:"todo", priority:"2", date_deadline:"2026-08-20", milestone:"Netwerk live"}`
5. **Sub-projecten (grote WBS-takken)** — `projects_create_subproject {name:"Servers", parent:"OLVP-ICT"}`
6. **Controleren** — `projects_get {project:"OLVP-ICT"}` / `projects_tree` / `projects_list_items {project:"OLVP-ICT"}`

## 5. Belangrijke aandachtspunten

- **Geen upsert / idempotentie.** `create_*` maakt altijd een nieuw record.
  Bij her-uitvoeren ontstaan dubbels. Wil je idempotent werken: gebruik een
  uniek `code` per project en check eerst met `projects_list` /
  `projects_list_items` vóór je aanmaakt.
- **Volgorde:** maak parent-items (fases) en milestones aan vóór de taken die
  ernaar verwijzen — `parent`/`milestone` verwachten een bestaand id (of
  milestone-naam binnen hetzelfde project).
- **Hiërarchie zit op id.** `projects_list_items` geeft een platte lijst met
  `parent_id`; bouw de boom client-side (of gebruik `projects_tree` voor
  project-niveau).
- **Cycli & cross-project** worden server-side geweigerd (parent/milestone
  moet in hetzelfde project; geen recursie) → je krijgt een MCP-fout terug.
- **Datums** altijd `YYYY-MM-DD`. **Priority** is een string `'0'..'3'`.
