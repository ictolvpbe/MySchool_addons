# `myschool_mcp` — Developer Guide

> Hoe je nieuwe MCP-tools toevoegt aan deze module of aan een andere
> MySchool-module die zijn eigen tools wil exposeren.

## Architectuur in 60 seconden

```
HTTP-request   →  controllers/mcp.py   →  models/mcp_registry.py
                  (JSON-RPC dispatch +     (singleton +
                   auth + audit)            tool-dispatch)
                                                  │
                                                  ▼
                                      providers/<naam>.py
                                      (decorators registreren
                                       handlers bij de registry)
```

- **Eén tool = één Python-functie**, gedecoreerd met
  `@McpRegistry.tool(...)`.
- De eerste parameter is altijd `env` (Odoo Environment van de
  authentiek gebruiker).
- De overige parameters komen 1-op-1 uit `arguments` van de
  JSON-RPC call.
- Return-waarde wordt door de controller naar de MCP `content[]`-
  structuur ge-wrapped — wat jij teruggeeft moet **JSON-serialiseerbaar**
  zijn (dicts, lijsten, primitives, datetimes).

## Een tool toevoegen in deze module

Open of maak `providers/<jouw-provider>.py`:

```python
from ..models.mcp_registry import McpRegistry, McpToolError
from . import base


@McpRegistry.tool(
    name='betask_list_errors',           # ← unieke globale naam, met prefix
    description='List backend tasks in state=error',
    input_schema={
        'type': 'object',
        'properties': {
            'object_type': {'type': 'string',
                            'description': 'Filter op object (ORG, PERSON, ...)'},
            'limit': {'type': 'integer', 'default': 50, 'maximum': 500},
        },
    },
    required_group='myschool_core.group_myschool_core_admin',
)
def list_errors(env, object_type=None, limit=50):
    domain = [('status', '=', 'error')]
    if object_type:
        domain.append(('object_type', '=', object_type))
    tasks = env['myschool.betask'].search(
        domain, limit=min(int(limit or 50), 500))
    return [{
        'id': t.id,
        'name': t.name,
        'target': t.target,
        'object_type': t.object_type,
        'action': t.action,
        'error': t.error_description or '',
    } for t in tasks]
```

Voeg `from . import betask` toe in `providers/__init__.py` zodat de
decorator runt bij module-laad.

Klaar — geen wijzigingen aan controller, registry of manifest. Restart
Odoo, de tool verschijnt automatisch in `tools/list`.

## Convenanten

### Toolnamen

- **Altijd geprefixt** met je provider-naam: `appfoundry_*`,
  `betask_*`, `sysevent_*`, ...
- snake_case.
- Werkwoord-eerst: `list_*`, `get_*`, `set_*`, `create_*`, `delete_*`.

### Input-schema

JSON-Schema (subset):

- Top-level moet `{'type': 'object', ...}` zijn.
- Voor verplichte velden: `'required': ['x', 'y']`.
- `'default'` op een property → registry vult automatisch in als de
  AI-client het veld niet meestuurt.
- Voor "id of string-code" parameters: `'oneOf': [{'type':'integer'},{'type':'string'}]`.

We doen géén full JSON-Schema validatie in v1 — alleen type-check op
de top-level dict + default-injectie. Validatie gebeurt in de Python-
handler zelf (TypeError → wordt netjes naar JSON-RPC error gemapt).

### Required groups

- `required_group=None` → enkel `group_mcp_user` (de poortwachter).
- Read-tools: gebruik de "user"-groep van je domein (bv.
  `myschool_appfoundry.group_appfoundry_user`).
- Write/create tools: de "manager"-groep
  (`myschool_appfoundry.group_appfoundry_manager`).

### Error handling

Gooi `McpToolError(msg, code=-3200X)` voor expliciete fouten. Codes:

- `-32602` Invalid arguments / validation
- `-32004` Not found / validation error
- `-32003` Forbidden (access denied)
- `-32000..-32099` reserved voor toepassings-fouten

Voor standaard-Odoo-uitzonderingen (AccessError, UserError,
ValidationError, TypeError) doet de registry automatisch de mapping
naar JSON-RPC errors — gewoon laten gooien.

### Output

- Return een dict of een lijst van dicts.
- **Geen recordsets**: de JSON-encoder kan ze niet aan. Gebruik
  serializer-helpers uit `providers/base.py` of map zelf naar dicts.
- **Geen Markup-objecten**: de JSON-encoder serialiseert ze als
  string maar Markup gaat verloren bij de AI-client — gebruik
  `_html_to_text` als je platte tekst wil, of leg de HTML expliciet
  in een `*_html` key.
- Datetimes: laat ze gerust — de controller heeft een fallback
  `default=` die `.isoformat()` aanroept.

### Helpers uit `providers/base.py`

Hergebruik waar mogelijk:

- `resolve_item(env, ref)` — int id of "MSA-42" → record
- `resolve_project(env, ref)` — id of code → record
- `resolve_stage(env, project, name_or_id)` — case-insensitive lookup
- `resolve_user(env, ref)` — id, login, of "me"
- `resolve_or_create_tags(env, names)` — tag-namen → ids (autocreate)
- `render_markdown_to_html(text)` — lichte markdown → HTML voor chatter
- `_html_to_text(html)` — strip HTML voor tekst-output

## Een nieuwe provider toevoegen in een **andere** myschool-module

Stel je wil `myschool_core` zijn eigen betask-tools laten exposeren.
Twee opties:

### Optie 1 (aanbevolen voor v1) — centraal in myschool_mcp/providers/

Voordeel: één plek om te zoeken, eenvoudige imports.
Nadeel: import van core-tools zit fysiek in mcp-module.

Maak `myschool_mcp/providers/betask.py` met `@McpRegistry.tool(...)`
decorators, voeg `from . import betask` toe in `providers/__init__.py`.

### Optie 2 (voor v2+) — gedistribueerd via een entry-point pattern

Wanneer providers in hun eigen modules gaan leven:

1. Module declareert dependency op `myschool_mcp`.
2. In de eigen `__init__.py`: `from . import mcp_tools` (een nieuw
   bestand met de decorators).
3. Bovenaan dat bestand:
   ```python
   from odoo.addons.myschool_mcp.models.mcp_registry import McpRegistry
   ```
4. Registratie gebeurt bij module-laad.

Risico: als `myschool_mcp` later geüpdatet wordt en de registry resets,
moet de provider-module opnieuw geïmporteerd worden. Voor productie
nog niet aan beginnen — eerst kijken of v1 stabiel is.

## Tests

`tests/test_mcp_appfoundry.py` toont het patroon:

```python
from odoo.tests.common import HttpCase, tagged

@tagged('post_install', '-at_install', 'myschool_mcp')
class TestMcpAppfoundry(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Maak test-user + API-key via _generate
        cls.api_key_value = cls.env['res.users.apikeys'].with_user(
            cls.test_user).sudo()._generate(
                scope='rpc', name='Test', expiration_date=False)

    def _call_tool(self, name, args):
        resp = self.url_open('/mcp', data=json.dumps({
            'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name': name, 'arguments': args}}).encode(),
            headers={'X-API-Key': self.api_key_value,
                     'Content-Type':'application/json'})
        return json.loads(resp.json()['result']['content'][0]['text'])
```

Run: `odoo -d <testdb> -i myschool_mcp --test-tags myschool_mcp --stop-after-init`

## Beperkingen / nog te doen (v2)

Wat **nog niet** in v1 zit, met de aanbevolen aanpak voor later:

- **SSE-stream** voor server→client notifications. Nodig voor
  langlopende tools die progress willen rapporteren of voor chatter-
  pushes. Implementeer een tweede route `GET /mcp` die een SSE-stream
  opent en push-events stuurt; deel state via een per-session id.
- **MCP Resources** (`resources/list`, `resources/read`). Hiermee kan
  Claude een item als "context-bron" trekken zonder explicit tool-call
  — bv. een item-resource met URI `myschool://appfoundry/item/42`.
- **MCP Prompts** — herbruikbare prompt-templates ("review this story",
  "implement this bug fix").
- **OAuth** ipv API-key voor SSO-integratie met externe AI-tools.
- **Cache** per request-id (idempotency-key) zodat dezelfde call binnen
  een venster hetzelfde antwoord geeft.
- **Tool-resultaten als gestructureerde objects** ipv text-content
  (MCP 2025-06-18 ondersteunt structured outputs — wij geven nu nog
  een JSON-string in `content[0].text` terug voor maximale
  compatibility).
- **Pagineren** voor lijst-tools die boven `limit=500` kunnen lopen.
  Voeg `cursor`/`next_cursor` toe aan het schema en de implementatie.

## Patterns die we **niet** willen

- ❌ Tool die het hele model rauw teruggeeft (lekt interne velden).
  Bouw altijd een expliciete serializer.
- ❌ Tool die `env['some.model'].sudo()` doet zonder gegronde reden.
  De controller heeft expliciet env gemaakt onder de authentiek
  gebruiker — gebruik sudo() alleen voor read-only audit-acties of
  systeem-config-reads.
- ❌ Tool die zelf de auth-header leest. Auth is centraal in de
  controller; tools krijgen al een geautoriseerde env.
- ❌ Bypass van de betask-pipeline voor data-mutaties op core
  modellen. Volg `CLAUDE.md`-regels — alle wijzigingen op org/person/
  role/proprelation gaan via `myschool.manual.task.service`. Voor
  appfoundry-models geldt deze regel niet (geen betask-flow nodig).
