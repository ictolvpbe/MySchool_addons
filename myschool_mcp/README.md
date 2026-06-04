# myschool_mcp — Model Context Protocol server in Odoo

Stelt MySchool-data en -acties beschikbaar aan AI-assistenten (Claude
Code, andere MCP-clients) via een geïntegreerde HTTP-controller in
Odoo. Auth gebeurt via de native `res.users.apikeys` — elke gebruiker
hangt een eigen key aan zijn account zodat acties in chatter onder zijn
eigen naam verschijnen.

## Snelle setup

### 1. Installeer en upgrade

```
odoo -u myschool_mcp -d <db>
```

### 2. Maak een API-key (per gebruiker)

In Odoo: **Preferences → Account Security → New API Key** met scope
`rpc`. Bewaar de gegenereerde sleutel — Odoo toont hem maar één keer.

### 3. Smoke-test met curl

```bash
HOST=https://appfoundry.olvp.be    # of http://localhost:8069 in dev
KEY=<jouw api-key>

# Initialize handshake — werkt ook zonder key
curl -sX POST $HOST/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'

# Lijst van tools — vereist auth
curl -sX POST $HOST/mcp \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# Roep een tool aan
curl -sX POST $HOST/mcp \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"appfoundry_list_my_items","arguments":{}}}'
```

### 4. Verbind Claude Code

```bash
claude mcp add --transport http myschool \
  https://appfoundry.olvp.be/mcp \
  --header "X-API-Key: <jouw api-key>"
```

Of in `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "myschool": {
      "transport": "http",
      "url": "https://appfoundry.olvp.be/mcp",
      "headers": { "X-API-Key": "..." }
    }
  }
}
```

Verifieer met `claude mcp list` — zou `myschool` als verbonden moeten
tonen, inclusief alle `appfoundry_*` tools.

## Architectuur

```
controllers/mcp.py          POST /mcp endpoint (JSON-RPC 2.0)
models/mcp_registry.py      decorator + dispatch + rate-limit
models/mcp_config.py        Instellingen via res.config.settings
providers/base.py           gedeelde serializers + resolvers
providers/appfoundry.py     14 tools voor projecten/items/sprints/...
```

Een nieuwe provider toevoegen: drop een nieuw bestand
`providers/<naam>.py`, registreer er tools via
`@McpRegistry.tool(name='<prefix>_xxx', ...)`, en import het in
`providers/__init__.py`.

## V1-tools (appfoundry-prefix)

| Tool | Doel |
|---|---|
| `appfoundry_list_projects` | Projecten (filter op lidmaatschap) |
| `appfoundry_list_my_items` | Open items op mijn naam |
| `appfoundry_list_items` | Algemene zoek-tool |
| `appfoundry_get_item` | Volledige item-details + chatter |
| `appfoundry_list_stages` | Beschikbare kanban-stages |
| `appfoundry_list_active_sprints` | Actieve sprints |
| `appfoundry_get_sprint` | Sprint-details met items |
| `appfoundry_get_release_progress` | Release-status (% + open bugs) |
| `appfoundry_set_stage` | Item naar andere stage |
| `appfoundry_assign` | Toewijzen aan gebruiker |
| `appfoundry_post_comment` | Chatter-comment (markdown) |
| `appfoundry_update_item` | Velden aanpassen |
| `appfoundry_link_blocked_by` | Dependency vastleggen |
| `appfoundry_create_item` | Nieuw item aanmaken |

Items kunnen overal aangeroepen worden met **id** of **display-code**
(bv. `"MSA-42"`).

## Beheer

**Settings → Technical → MCP Server Settings** (admin only):

- **Rate-limit**: per gebruiker maximaal N calls per venster (default
  60/min). Niet voor security; om runaway-loops te dempen.
- **Providers**: schakel een hele provider tijdelijk uit zonder
  module-uninstall.

**Audit**: elke geslaagde tool-call → `sys_event` met code `MCP-CALL`.
Fouten → `MCP-ERROR`. Zichtbaar in **Operations → Systeemevents →
Alle events** (filter op source=MCP).

**Per-tool autorisatie**: read-tools vereisen `group_appfoundry_user`,
write/create tools vereisen `group_appfoundry_manager`. De
poortwachter is `group_mcp_user` — wordt impliciet gegeven aan
`myschool_core.group_myschool_core_admin`.

## Veelvoorkomende workflows

**Pick up a story → werk → status updaten**:

```
"List my open items in project MSA"
→ Claude calls appfoundry_list_my_items({"project_code": "MSA"})

"Show me the details of MSA-42"
→ Claude calls appfoundry_get_item({"item": "MSA-42"})

(werkt aan de code)

"Set MSA-42 to In Review and post a comment with the commit message"
→ Claude calls appfoundry_set_stage + appfoundry_post_comment
```

**Sprint-overzicht**:

```
"What's on my plate this sprint?"
→ Claude calls appfoundry_list_active_sprints + appfoundry_list_my_items
```

## Tests

```
odoo -d <testdb> -i myschool_mcp --test-tags myschool_mcp --stop-after-init
```

## Toekomst (out-of-scope v1)

- SSE-stream voor server→client notifications (real-time chatter pushes).
- Resources / Prompts (MCP-onderdelen voor "context attach" en
  herbruikbare prompts).
- Bijkomende providers: `betask`, `sysevent`, `sap_sync`, ...
- OAuth in plaats van API-key voor SSO-integraties.
