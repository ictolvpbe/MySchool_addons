# myschool_mcp

Geïntegreerde Model Context Protocol (MCP) server als Odoo-module. Stelt MySchool-data en -acties beschikbaar voor Claude Code, claude.ai web en andere MCP-clients via een HTTP-controller op `/mcp` (JSON-RPC 2.0). Auth gebeurt via Odoo's native `res.users.apikeys` — elke gebruiker hangt een eigen API-key aan zijn account zodat acties in chatter onder zijn naam verschijnen.

## Status

| Onderdeel | Stand |
|---|---|
| Module-code | Volledig geschreven (1 commit `myschool_mcp : start`, 2684 inserts) |
| Tests | 7 testcases in `tests/test_mcp_appfoundry.py` |
| Documentatie in-module | `README.md` + `USER_MANUAL.md` + `DEVELOPER.md` + `NEXT_STEPS.md` |
| Branch | `Dev-MCP` (cherry-pick van `Dev-Admin-and-Core` op 2026-06-03) |
| Live-test | ⏳ Lokaal werkstation (Niveau 1) in progress |
| Deploy op myschool-ict (prod) | ⏳ Pending na lokale validatie |

## Dependencies

- `base` + `mail` (Odoo standaard)
- `myschool_core` (school-organisatie, personen)
- `myschool_appfoundry` (project-management entities — appfoundry-provider werkt hierop)

## Architectuur

```
controllers/mcp.py          POST /mcp endpoint (JSON-RPC 2.0)
models/mcp_registry.py      decorator + dispatch + rate-limit
models/mcp_config.py        Instellingen via res.config.settings
providers/base.py           gedeelde serializers + resolvers
providers/appfoundry.py     14 tools voor projecten/items/sprints/...
```

Provider-pattern: nieuwe MCP-tools toevoegen = nieuw bestand `providers/<naam>.py`, registreer tools via `@McpRegistry.tool(name='<prefix>_xxx', ...)`, import in `providers/__init__.py`.

## V1-tools (appfoundry-prefix)

14 tools voor AppFoundry-workflow:
- **Read**: `list_projects`, `list_my_items`, `list_items`, `get_item`, `list_stages`, `list_active_sprints`, `get_sprint`, `get_release_progress`
- **Write**: `set_stage`, `assign`, `post_comment`, `update_item`, `link_blocked_by`, `create_item`

Items aanroepen kan met **id** of **display-code** (bv. `"MSA-42"`).

## Auth

- Per-user API-key via **Preferences → Account Security → New API Key**, scope `rpc`
- HTTP-header: `X-API-Key: <key>`
- Voor Claude Code: `claude mcp add --transport http myschool <URL>/mcp --header "X-API-Key: <key>"`

## Test- en deploy-strategie

**Niveau 1 — Lokaal werkstation** (validatie module-correctness):
- Module installen in lokale dev-Odoo (`odoo-dev` DB)
- Test-suite: `odoo -d <db> -i myschool_mcp --test-tags myschool_mcp --stop-after-init`
- Smoke-test via `curl` (zie [`../../myschool_mcp/USER_MANUAL.md`](../../myschool_mcp/USER_MANUAL.md))
- Claude Code via `localhost:8069/mcp`

**Niveau 2 — Test-instance** (real HAProxy → Caddy → Odoo chain):
- Branch `Dev-MCP` deployen via Semaphore-template met `addons_branch_override=Dev-MCP`
- Target: `myschool-test.olvp.be` of `myschool-dev.olvp.be`
- Module-install via Odoo UI of `podman exec ... odoo -d <db> -i myschool_mcp`

**Niveau 3 — Productie** (`myschool-ict.olvp.be`):
- Pas na niveau 1+2 groen
- Merge `Dev-MCP` → `master` + Semaphore prod-run (`target_env=prod`)

## Beheer

**Settings → Technical → MCP Server Settings** (admin only):
- **Rate-limit**: per gebruiker maximaal N calls/venster (default 60/min). Niet voor security; om runaway-loops te dempen.
- **Providers**: toggle hele providers uit zonder module-uninstall.

**Audit**: elke geslaagde tool-call → `sys_event` met code `MCP-CALL`. Fouten → `MCP-ERROR`. Zichtbaar via **Operations → Systeemevents → Alle events** (filter `source=MCP`).

**Per-tool autorisatie**:
- Read-tools vereisen `group_appfoundry_user`
- Write/create-tools vereisen `group_appfoundry_manager`
- Poortwachter: `group_mcp_user` (impliciet gegeven aan `myschool_core.group_myschool_core_admin`)

## Detail-documentatie

- **Gebruikers**: [`myschool_mcp/USER_MANUAL.md`](../../myschool_mcp/USER_MANUAL.md) — API-key setup, Claude Code config, voorbeelden per tool
- **Developers**: [`myschool_mcp/DEVELOPER.md`](../../myschool_mcp/DEVELOPER.md) — architectuur, nieuwe providers schrijven, registry-API
- **Next steps**: [`myschool_mcp/NEXT_STEPS.md`](../../myschool_mcp/NEXT_STEPS.md) — deploy-checklist, bekende issues, v2-roadmap

## Open punten

Uit `NEXT_STEPS.md`:
- Rate-limit is per-Python-proces (in-memory) — bij multi-worker Odoo telt per worker
- Stage-resolutie is case-insensitive prefix-match — kan ambigueus zijn
- Markdown-renderer ondersteunt enkel bold/italic/code/bullets/paragrafen (geen tabellen/links)

Toekomstige uitbreidingen (v2+):
- SSE-stream voor server→client notifications
- MCP Resources + Prompts (i.p.v. enkel Tools)
- Pagineren (cursor) voor lijst-tools > 500 items
- OAuth via id.olvp.be i.p.v. API-key (zie [[project-mcp-and-itsm]] memory)
- Bijkomende providers: `betask`, `sysevent`, `sap_sync`, `documenter` (TBD)

## Gerelateerde docs

- [`../decisions/0001-mcp-as-odoo-module.md`](../decisions/0001-mcp-as-odoo-module.md) — waarom MCP IN Odoo i.p.v. extern proces
- [`../operations/module-install.md`](../operations/module-install.md) — algemene module-install-procedure
