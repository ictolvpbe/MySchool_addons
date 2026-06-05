# myschool_projects

MySchool Projects — generieke, hiërarchische projectbeheer-app als aanvulling op `myschool_appfoundry` (dat dev/agile-gericht is). Bedoeld om organisatorische trajecten zoals **olvp-ict** op te volgen: sub-projecten (WBS), opgerolde voortgang, getypeerde work items (task/milestone/phase/epic/bug), milestones, dependencies en een OpenProject-achtige work-packages-workspace. Volledig benaderbaar via de MySchool MCP-server (provider `projects`).

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta — in `origin/Dev`, live op odoo-dev, 19 unit-tests groen |
| Manifest | `application=True`, version 0.1, self-contained |
| Dependencies | `base`, `mail`, `myschool_core` |
| Models-locatie | IN de module (`myschool_projects/models/`), prefix `myschool.project.*` |
| MCP-provider | `myschool_mcp/providers/projects.py` met 11 tools |
| Referentie-doc | [`myschool_projects/MCP_REFERENCE.md`](../../myschool_projects/MCP_REFERENCE.md) — push-flow voor andere sessies |

> **Architectuurkeuze:** de modellen wonen in de addon zelf (zoals AppFoundry met `appfoundry.*`), niet in `myschool_core`. Een PM-app is een applicatie *bovenop* het fundament, geen gedeeld core-concept. De "models-in-core"-regel geldt enkel voor fundamentele concepten die door meerdere modules gebruikt worden (org/person/process). Geen betask-pipeline → directe ORM create/write.

## Kern-functionaliteit

- **Hiërarchische projecten (WBS)** — sub-projecten via `parent_id`/`child_ids` (`_parent_store`), cycle-guard.
- **Voortgang-rollup (drie-traps)** — heeft sub-projecten → gemiddelde van children; anders heeft leaf-taken → % afgewerkt (milestones + containers + cancelled niet meegeteld); anders handmatige `progress_own`.
- **Getypeerd, unified work-item-model** — één model `myschool.project.task` met `item_type` (task/milestone/phase/epic/bug) + zelf-hiërarchie. Een milestone is dus géén apart model maar een type.
- **Milestone als organiserend anker** — work items krijgen `milestone_id` (doel-milestone, zelfde project) + `milestone_progress`.
- **Dependencies** — op project- én item-niveau (`depends_on_ids`/`dependent_ids`, self-M2M, self-dep-guard).
- **Categorieën + tags** — projecten klasseerbaar via `category_id`; items taggbaar.
- **Klassieke views** — kanban / list / form / search / graph / pivot / calendar.
- **Custom OWL-workspace** — zie onder.

## Modellen

### `myschool.project`
| Veld | Type | Doel |
|---|---|---|
| `name`, `code` | char | Naam + uniek korte code (case-insensitive MCP-lookup) |
| `category_id` | m2o | Klassering → `myschool.project.category` |
| `parent_id` / `child_ids` | m2o / o2m | WBS-hiërarchie (`_parent_store`, `parent_path`) |
| `responsible_id` / `member_ids` | m2o / m2m | Verantwoordelijke + teamleden (`res.users`) |
| `date_start` / `date_end` | date | Planning |
| `state` | selection | new / active / on_hold / done / cancelled |
| `progress_own` / `progress` | float | Handmatig vs. opgerolde (stored, recursive) voortgang |
| `task_ids` / `milestone_ids` | o2m | Work items (milestones = items met `item_type='milestone'`) |
| `depends_on_ids` / `dependent_ids` | m2m | Project-dependencies |

Erft `mail.thread` + `mail.activity.mixin`.

### `myschool.project.task` (unified work item)
| Veld | Type | Doel |
|---|---|---|
| `name`, `sequence` | char / int | Titel + handmatige volgorde |
| `item_type` | selection | task / milestone / phase / epic / bug |
| `project_id` | m2o | Project (cascade) |
| `parent_id` / `child_ids` | m2o / o2m | Zelf-hiërarchie (`_parent_store`); item mét kinderen = "cluster"/summary |
| `assigned_id` | m2o | Toegewezen gebruiker |
| `state` | selection | todo / in_progress / blocked / done / cancelled |
| `priority` | selection | Low / Normal / High / Critical |
| `date_start` / `date_deadline` / `planned_hours` | date / float | Planning |
| `milestone_id` / `milestone_progress` | m2o / float | Doel-milestone (zelfde project) + % done gekoppelde items |
| `tag_ids` | m2m | Tags |
| `depends_on_ids` / `dependent_ids` | m2m | Item-dependencies |

Erft `mail.thread` + `mail.activity.mixin`.

### `myschool.project.category` / `myschool.project.tag`
Beheermodellen: unieke `name`, `color`, (category ook `sequence`, `description`, computed `project_count`).

## Custom OWL-workspace

Client-action `myschool_projects_workspace` (`static/src/{js,xml,css}/project_workspace.*`), OpenProject-geïnspireerd:

- **WBS-sidebar** — recursieve project-tree, resizable splitter (localStorage), zoekbalk (op naam/code), rechtsklik-contextmenu (Add Project / Add sub / Rename / Properties / Delete).
- **View-switcher** — Table / Overview / Board / List / Calendar. Board/List/Calendar **embedden de native Odoo-views** (scoped op project) → drag-drop/group-by/filters gratis.
- **Work-packages-tabel** (default "Table") — hiërarchische tabel met indent + carets, type/status-badges, kolomconfiguratie (tandwiel, localStorage), zoekbalk, inline rename + statuswijziging, **drag-reorder + re-parent** (incl. drop-zone onderaan = top-level laatste, outdent-contextmenu), rechtsklik-contextmenu's. Een item mét kinderen toont als type **Cluster** (summary) met opgerolde voortgang; milestone = ◆.

## Security

Per `security/myschool_projects_security.xml`:
- `group_projects_user` — projecten lezen; work items CRUD (geen unlink).
- `group_projects_manager` — volledige toegang (CRUD op alles).
- MySchool core-admin → automatisch `group_projects_manager`.

## MCP-integratie

`myschool_mcp` exposeert de app via 11 `projects_*`-tools (volledige push-flow + datamodel in [`MCP_REFERENCE.md`](../../myschool_projects/MCP_REFERENCE.md)). Aanroepen met id óf `code`/`display_code`.

**Read**: `projects_list` · `projects_get` (incl. milestones/depends_on/blocks) · `projects_tree` (geneste WBS) · `projects_list_items` · `projects_search`

**Write**: `projects_create_subproject` · `projects_create_item` · `projects_update_item` · `projects_set_status` · `projects_add_milestone` · `projects_set_dependency`

Autorisatie: read-tools → `group_projects_user`, write-tools → `group_projects_manager`.

## Verwante modules

- [`myschool_appfoundry`](myschool_appfoundry.md) — dev/agile-gericht PM (stories/sprints/releases); `myschool_projects` is de generieke tegenhanger voor organisatorische trajecten.
- [`myschool_mcp`](myschool_mcp.md) — MCP-server (dependent op deze provider).
- [`myschool_core`](myschool_core.md) — fundament (org/person/users).

## Roadmap / open punten

- **Volgende features**: filter/group-bar in de custom tabel · opgeslagen views in de sidebar · Timeline/Gantt (`web_gantt` = Enterprise → custom via uitgefactoreerde GraphCanvas) · project-templates · deadline-reminder-cron.
- **Fase 2**: baseline/change-control, budget, resource-capaciteit, risk/issue-register.
- **Fase 3**: GraphCanvas — visuele WBS/netwerk-weergave (consolideert processcomposer + appfoundry-canvas + project-WBS).
- **Branch-stand**: de module-code leeft op `Dev`; deze docs-structuur op `Dev-Docs-structure` (branches nog te verzoenen).
