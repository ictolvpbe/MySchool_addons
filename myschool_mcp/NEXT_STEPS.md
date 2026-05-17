# `myschool_mcp` — Volgende stappen

> Snapshot van de toestand op 2026-05-16. Module is volledig
> geschreven maar nog **niet getest tegen een live Odoo** — wachtend
> op hostings-setup van de appfoundry-server.

## Wat klaar is

- Module-skeleton (manifest, __init__, security-groep, access csv).
- Registry + decorator (`models/mcp_registry.py`) met group-check +
  in-memory sliding-window rate-limiter.
- HTTP-controller (`controllers/mcp.py`) met JSON-RPC 2.0 dispatch
  (initialize, notifications/initialized, ping, tools/list,
  tools/call) + X-API-Key auth via `res.users.apikeys._check_credentials`.
- Settings-tab (`models/mcp_config.py` + view) voor rate-limit +
  provider-toggle.
- 14 appfoundry-tools (`providers/appfoundry.py`): list_projects,
  list_my_items, list_items, get_item, list_stages,
  list_active_sprints, get_sprint, get_release_progress, set_stage,
  assign, post_comment, update_item, link_blocked_by, create_item.
- Provider-helpers (`providers/base.py`): resolve_item (id of
  "MSA-42"), resolve_project, resolve_stage, resolve_user,
  resolve_or_create_tags, serializers + lichte markdown→HTML
  renderer.
- 7 testcases (`tests/test_mcp_appfoundry.py`): initialize-
  handshake, unauth → 401, tools/list, unknown tool, list_my_items,
  create_item, set_stage, post_comment.
- README, USER_MANUAL, DEVELOPER-docs.

## Pre-deploy checklist

- [ ] Hosting voor appfoundry-Odoo opgezet (TLS, reverse proxy zodat
      `/mcp` doorgelaten wordt).
- [ ] Module deploybaar naar die server (extra-addons-pad ge-mount).
- [ ] `myschool_appfoundry` al geïnstalleerd op die server (deps).

## Deploy + smoke test

1. **Install op de hosted server**:
   ```bash
   odoo -d <db> -i myschool_mcp --stop-after-init
   ```
2. **Reverse proxy controle**: header `X-API-Key` moet door (nginx
   forward by default, maar sommige WAFs strippen onbekende headers).
3. **Smoke test** (zie USER_MANUAL.md sectie "Smoke test met curl"):
   - `initialize` → 200 + `serverInfo.name=myschool-mcp`
   - `tools/list` zonder key → 401
   - `tools/list` met geldige key → 14 tools
4. **Test-suite**:
   ```bash
   odoo -d <testdb> -i myschool_mcp \
     --test-tags myschool_mcp --stop-after-init
   ```

## Eerste end-to-end

1. **API-key**: maak er één voor je eigen Odoo-account
   (Preferences → Account Security).
2. **Claude Code config**:
   ```bash
   claude mcp add --transport http myschool \
     https://appfoundry.<host>/mcp \
     --header "X-API-Key: ..."
   ```
3. **In een Claude-sessie**:
   - "List my open AppFoundry items"
   - "Get me MSA-42 in detail"
   - "Set MSA-42 to In Review and post a comment 'WIP — testing'"
4. **Verifieer in Odoo-UI**: open MSA-42, chatter toont de comment
   onder jouw naam, stage staat op In Review.

## Bekende issues / aandachtspunten

- **`res.users.apikeys._generate` met scope=`'rpc'`** matched onze
  controller die `scope='rpc'` doorgeeft aan `_check_credentials`.
  Als gebruikers een andere scope kiezen bij key-creatie zou auth
  falen — documenteer dit duidelijk (zie USER_MANUAL §3).
- **Rate-limit** zit per Python-proces (in-memory). Bij multi-worker
  Odoo (gunicorn met N workers) tel je per worker. Voor onze schaal
  (handvol devs) onbelangrijk; bij echte multi-user productie ooit
  vervangen door een Redis- of ir.config_parameter-counter.
- **Stage-resolutie**: case-insensitive prefix-match. "in" zou per
  ongeluk "In Progress" of "In Review" kunnen matchen (eerste wint).
  Documenteer of voeg strict-mode toe als dit verwarrend wordt.
- **Markdown-renderer is licht** (alleen bold/italic/code/bullets/
  paragrafen). Geen links, tabellen, blockquotes. Voldoende voor
  commit-messages; upgrade naar `mistune` of `markdown2` library als
  meer nodig blijkt.

## Toekomstige uitbreiding (v2+)

Zie ook `DEVELOPER.md` §"Beperkingen / nog te doen".

**Lage hangende vruchten**:
- `betask`-provider (5-6 tools: list, get, retry, reset_error,
  rerun_pending).
- `sysevent`-provider (audit-zoekfunctie).
- `sap_sync`-provider (list_runs, approve_run, cancel_run).
- Per-tool argument-`title` voor betere AI-context in tools/list.

**Architectuur-uitbreiding**:
- SSE-stream voor server→client notifications.
- MCP Resources + Prompts.
- Pagineren (cursor) voor lijst-tools > 500.
- OAuth ipv API-key voor SSO.

## Bestanden waar de logica zit

| Wat | Pad |
|---|---|
| Manifest | `__manifest__.py` |
| HTTP-controller | `controllers/mcp.py` |
| Tool-registry | `models/mcp_registry.py` |
| Settings-model | `models/mcp_config.py` |
| Settings-view | `views/res_config_settings_views.xml` |
| Provider-helpers | `providers/base.py` |
| AppFoundry tools | `providers/appfoundry.py` |
| Security | `security/mcp_security.xml`, `security/ir.model.access.csv` |
| Tests | `tests/test_mcp_appfoundry.py` |
| User docs | `README.md`, `USER_MANUAL.md` |
| Dev docs | `DEVELOPER.md`, `NEXT_STEPS.md` (dit bestand) |

## Plan-bestand

Het volledige design-plan zit in
`/home/demm/.claude/plans/refactored-conjuring-candle.md`.
Bewaar/verplaats dat als je het wil archiveren bij de module.
