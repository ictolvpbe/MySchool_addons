# `myschool_mcp` — User Manual

> Voor admins en eindgebruikers (devs die Claude Code aan AppFoundry
> willen koppelen). Voor module-uitbreiding zie `DEVELOPER.md`.

## Inhoud

1. [Wat is dit?](#wat-is-dit)
2. [Installatie](#installatie)
3. [Per-user setup (API-key)](#per-user-setup-api-key)
4. [Verbinden vanaf Claude Code](#verbinden-vanaf-claude-code)
5. [Smoke test met curl](#smoke-test-met-curl)
6. [Werken met de tools](#werken-met-de-tools)
7. [Beheer (admin)](#beheer-admin)
8. [Audit-trail](#audit-trail)
9. [Troubleshooting](#troubleshooting)
10. [Security overwegingen](#security-overwegingen)

---

## Wat is dit?

`myschool_mcp` is een geïntegreerde **Model Context Protocol-server**
in Odoo. Het stelt AppFoundry-data en -acties (en later andere
MySchool-modules) beschikbaar aan AI-assistenten zoals Claude Code.

**Wat het oplost**:
- Pick-up van openstaande user stories zonder copy-paste vanuit de
  browser ("wat staat er op mijn naam in MSA?")
- Status updaten vanuit een ontwikkelsessie ("zet MSA-42 op In Review
  en post de commit message als comment")
- Sprint/release-context ophalen ("wat staat er deze sprint op mijn
  bord?")

**Hoe het werkt**:
- HTTP-endpoint `POST /mcp` op de Odoo-server, spreekt JSON-RPC 2.0.
- Authentificatie via native Odoo API-keys (per gebruiker eigen key).
- Alle acties verschijnen in chatter onder de **echte** gebruikersnaam.
- Tools registreren zich via een decorator-registry; nieuwe modules
  voegen later eigen tools toe in hun eigen `providers/`-bestand.

## Installatie

### 1. Module installeren

```bash
# Op de Odoo-server, in de mappen-structuur waar je addons staan:
odoo -d <db> -i myschool_mcp --stop-after-init
```

Of via UI: **Apps → Update Apps List → "MySchool MCP Server" →
Install**.

### 2. Verifiëren

```bash
# Vraag de capabilities op (geen auth nodig voor initialize)
curl -sX POST https://<jouw-odoo-host>/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'
```

Verwacht antwoord (verkort):
```json
{"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"2025-03-26",
  "capabilities":{"tools":{"listChanged":false}},
  "serverInfo":{"name":"myschool-mcp","version":"0.1.0"}}}
```

Als je een 404 krijgt: controleer dat de module geïnstalleerd is
(Apps-lijst) en dat Odoo de manifest correct heeft gelezen
(server-logs).

## Per-user setup (API-key)

Elke gebruiker maakt zijn **eigen** API-key. Acties verschijnen
nadien in chatter onder die naam — geen gedeelde "bot"-account.

### Stappen

1. In Odoo: klik je avatar (rechtsboven) → **Preferences**.
2. Tab **Account Security** → **New API Key**.
3. Geef het een naam, bv. `Claude Code MCP — laptop`.
4. **Scope**: laat op `rpc` (standaard). Onze controller accepteert
   alle keys met scope `rpc` of zonder scope-restrictie.
5. **Expiration**: kies een datum (~1 jaar) of laat leeg voor
   persistent. Aanrader: 1 jaar voor productie, eindeloos voor dev.
6. **Bewaar de gegenereerde sleutel direct** — Odoo toont hem maar
   één keer. Sla op in een password manager.

### Vereiste rechten

Je gebruiker moet in de groep **`MCP User`** zitten (de poortwachter).
Standaard wordt deze groep impliciet aan **MySchool Admin** gegeven —
dus admins hebben automatisch toegang.

Voor read-only tools (de meeste `*_list_*` en `*_get_*`) volstaat
**AppFoundry User**. Voor write/create tools (`*_set_*`, `*_create_*`,
`*_assign`, `*_post_comment`, ...) heb je **AppFoundry Manager** nodig.

## Verbinden vanaf Claude Code

### Optie A — CLI

```bash
claude mcp add --transport http myschool \
  https://<jouw-odoo-host>/mcp \
  --header "X-API-Key: <jouw-key>"
```

Verifieer: `claude mcp list` toont `myschool` als verbonden.

### Optie B — settings.json

In `~/.claude/settings.json` (of project-local
`.claude/settings.local.json`):

```json
{
  "mcpServers": {
    "myschool": {
      "transport": "http",
      "url": "https://<jouw-odoo-host>/mcp",
      "headers": { "X-API-Key": "<jouw-key>" }
    }
  }
}
```

### Verifiëren in Claude

In een Claude Code-sessie typ:
```
List my open AppFoundry items
```

Claude zou `appfoundry_list_my_items` moeten aanroepen en je items
tonen. Werkt dat → setup OK.

## Smoke test met curl

Handig om te zien of het endpoint leeft zonder afhankelijkheid van
Claude Code.

```bash
HOST=https://<jouw-odoo-host>
KEY=<jouw-api-key>

# 1. Initialize (geen auth)
curl -sX POST $HOST/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'

# 2. Lijst van beschikbare tools (auth verplicht)
curl -sX POST $HOST/mcp \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq .

# 3. Lijst mijn openstaande items
curl -sX POST $HOST/mcp \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"appfoundry_list_my_items","arguments":{}}}' | jq .

# 4. Detail van een item via display-code
curl -sX POST $HOST/mcp \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call",
       "params":{"name":"appfoundry_get_item",
                 "arguments":{"item":"MSA-42"}}}' | jq .
```

## Werken met de tools

Item-referenties accepteren overal **id** (integer) of **display-code**
(string, bv. `"MSA-42"`).

### Read-tools (vereisen AppFoundry User)

| Tool | Doel |
|---|---|
| `appfoundry_list_projects` | Projecten waar ik lid van ben |
| `appfoundry_list_my_items` | Mijn openstaande items |
| `appfoundry_list_items` | Algemene zoek (project + stage + type + tag + ...) |
| `appfoundry_get_item` | Full item-details incl. chatter |
| `appfoundry_list_stages` | Beschikbare kanban-stages |
| `appfoundry_list_active_sprints` | Sprints in state="active" |
| `appfoundry_get_sprint` | Sprint-details met alle items |
| `appfoundry_get_release_progress` | Release-status (% + open bugs) |

### Write-tools (vereisen AppFoundry Manager)

| Tool | Doel |
|---|---|
| `appfoundry_set_stage` | Item naar andere stage |
| `appfoundry_assign` | Toewijzen aan gebruiker (login/id/"me") |
| `appfoundry_post_comment` | Chatter-comment met markdown |
| `appfoundry_update_item` | Velden aanpassen (name, description, ...) |
| `appfoundry_link_blocked_by` | Dependency vastleggen (of weghalen) |
| `appfoundry_create_item` | Nieuw item aanmaken |

### Veelvoorkomende workflows

**"Pick up a story"**:
```
"What's open on my plate in MSA?"
→ appfoundry_list_my_items({"project_code":"MSA"})

"Open MSA-42 in detail"
→ appfoundry_get_item({"item":"MSA-42"})
```

**"Status updaten aan einde van sessie"**:
```
"Move MSA-42 to In Review and add a comment with the commit msg"
→ appfoundry_set_stage({"item":"MSA-42","stage":"In Review"})
→ appfoundry_post_comment({"item":"MSA-42",
    "body":"Implemented in commit abc123. Awaiting review."})
```

**"Sprint-overzicht"**:
```
"What's in our active sprint?"
→ appfoundry_list_active_sprints({"include_items":true})
```

**"Nieuwe bug-melding"**:
```
"Create a bug in MSA about the login form crashing"
→ appfoundry_create_item({
    "project":"MSA","item_type":"bug",
    "name":"Login form crashes on empty submit",
    "description":"Reproduceer: ...","priority":"2",
    "assign_to_me":true})
```

**Markdown in description/comment**: `**bold**`, `*italic*`,
`` `code` ``, bullet-lijsten met `-` of `*`, lege regel = nieuwe
paragraaf.

## Beheer (admin)

**Settings → Technical → MCP Server Settings**:

- **Rate-limit (calls)** + **Rate-limit-venster (sec)**: maximaal
  aantal MCP-calls per gebruiker per venster. Default 60/60s. Niet
  voor security — om runaway-loops in AI-clients te dempen.
- **AppFoundry provider** (toggle): verberg alle `appfoundry_*` tools
  tijdelijk zonder de module te uninstalleren. Handig bij debuggen.

Wijzigingen zijn direct effectief — geen restart nodig.

## Audit-trail

Elke MCP-tool-call schrijft een sys_event met `source='MCP'`:

- **MCP-CALL** — succesvolle tool-aanroep, met tool-naam + arg-summary
- **MCP-ERROR** — gefaalde call

Zichtbaar via **Operations → Systeemevents → Alle events** (filter op
`source = MCP`).

Daarnaast: elke `appfoundry_set_stage`, `_assign`, `_post_comment`,
`_update_item`, `_create_item` triggert de standaard Odoo chatter-
en tracking-entries — zichtbaar op het item zelf onder de naam van de
gebruiker wiens API-key gebruikt werd.

## Troubleshooting

**401 Unauthorized op tools/call**:
- Header `X-API-Key` correct verstuurd? (let op spaties/quotes)
- Key niet vervallen? (expiration_date)
- Key gemaakt met scope `rpc`? Andere scopes worden niet geaccepteerd.
- Probeer alternatief: `Authorization: Bearer <key>` header.

**403 Forbidden op een specifieke tool**:
- Gebruiker zit niet in `myschool_mcp.group_mcp_user` (poortwachter)
  of niet in de tool-specifieke groep (AppFoundry User/Manager).

**404 Method not found op tools/call**:
- Tool-naam fout gespeld. Vraag eerst `tools/list` op om de exacte
  namen te zien.
- Of de provider staat in Settings uitgevinkt.

**429-achtige error (`-32002`)**:
- Rate-limit bereikt. Wacht het venster uit, of verhoog de limiet in
  Settings.

**Tool retourneert "Validation error"**:
- Argumenten kloppen niet met de tool-schema. Controleer `tools/list`
  voor de exacte input-schema (Claude Code toont deze automatisch).

**Tool retourneert "Access error"**:
- Odoo `ir.model.access` of `ir.rule` blokkeert. Tools praten met
  de Odoo ORM in de naam van de gebruiker; alle standaard access-
  checks gelden. Geef de gebruiker de juiste AppFoundry-groep.

**Server-logs raadplegen**:
```bash
tail -f /var/log/odoo/odoo-server.log | grep -i mcp
```

## Security overwegingen

- **API-keys zijn als wachtwoorden**: bewaar ze in een password
  manager, niet in plain config-bestanden gecommit naar git.
- **Per-user**: elke ontwikkelaar maakt zijn eigen key. Geen gedeelde
  "bot"-account.
- **Expiration**: voor productie aanrader 1 jaar; vernieuw rond
  performance-reviews.
- **Revoke**: gebruiker verlaat team → Preferences → Account Security
  → Delete API Key. Effect direct.
- **TLS**: stel het endpoint nooit zonder HTTPS open op het internet.
- **Rate-limit**: standaard 60/min volstaat voor interactieve flows;
  voorkomt dat een runaway-AI je server beklimt.
- **Audit**: sys_event + chatter geven volledig spoor van wie wat
  wanneer deed.
