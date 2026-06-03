# 0001 — MCP-server als Odoo-module i.p.v. extern proces

- **Status**: accepted
- **Datum**: 2026-05-17 (initiële implementatie); 2026-06-03 (ADR opgesteld retroactief)
- **Beslisser**: ict@olvp.be

## Context

Voor Project G (Claude-integratie) moet MySchool-data en -acties beschikbaar zijn voor Claude via het Model Context Protocol (MCP). Twee implementatie-modellen waren mogelijk:

1. **In-process** — MCP-server als Odoo-module met een HTTP-controller die JSON-RPC 2.0 op `/mcp` exposeert
2. **Extern proces** — Aparte FastAPI/aiohttp-service die XML-RPC/JSON-RPC tegen Odoo doet en MCP-protocol naar Claude

Beide kunnen technisch werken. De keuze beïnvloedt deploy-complexity, auth-model, data-consistency en onderhoudsbelasting.

## Opties overwogen

### Optie A: MCP als Odoo-module (in-process)

- **Voor**:
  - Hergebruik van Odoo's auth-infrastructuur (`res.users.apikeys`, scopes, group-checks)
  - Direct toegang tot env (recordsets, ORM, multi-company, sudo-context) — geen serialize/deserialize-overhead
  - Acties verschijnen onder de echte user in chatter (multi-user audit-trail werkt automatisch)
  - Eén deploy-eenheid: Semaphore addons-update pull + Odoo restart, klaar
  - Audit-logging via bestaande `sys_event` integratie
  - Geen aparte network-pad / firewall-rule nodig
- **Tegen**:
  - Odoo workers worden belast met MCP-requests (in-process)
  - Niet onafhankelijk schaalbaar (alle Odoo workers serveren MCP)
  - Bij Odoo-upgrade moet de module mee-getest worden

### Optie B: Externe MCP-service

- **Voor**:
  - Onafhankelijk schaalbaar (eigen process, eigen scaling)
  - Niet gekoppeld aan Odoo-upgrade-cycle
  - Eventueel naar andere data-bronnen uit te breiden (niet alleen Odoo)
- **Tegen**:
  - Aparte auth-laag bouwen (eigen tokens of OAuth-broker tegen id.olvp.be)
  - XML-RPC/JSON-RPC overhead tussen MCP-service en Odoo
  - Acties moeten "as user X" gedaan worden — vereist user-impersonation via Odoo-API-key
  - Aparte deploy + Quadlet + monitoring
  - Extra firewall-rules (Caddy → MCP-service → Odoo)
  - Dubbele audit-logging (MCP-service log + Odoo chatter)

## Beslissing

**Gekozen: Optie A — MCP als Odoo-module (`myschool_mcp`)**.

Doorslaggevend was de **multi-user audit-trail** in chatter: acties moeten zichtbaar zijn als gedaan door de echte gebruiker (Claude representeert de gebruiker, geen system-account). In-process toegang tot het Odoo env maakt dat triviaal; externe services vereisen impersonation-trucs die complexer worden bij rate-limiting, error-paths en sudo-context-switches.

De schaalbaarheid-trade-off (Odoo workers serveren MCP) is voor onze schaal (handvol concurrent Claude-sessies) niet relevant. Bij meer load kan dit later geherzien worden — een externe service-laag toevoegen is technisch nog steeds mogelijk.

## Gevolgen

- **Positief**:
  - Snelle implementatie en deploy (één addon, geen aparte infra)
  - Auth-model hergebruikt Odoo's native API-keys — gebruikers beheren hun eigen credentials
  - Audit-trail werkt automatisch (Odoo `mail.thread`, `sys_event`)
  - Rate-limit + provider-toggle als settings-tab in Odoo (admin-UI)
- **Negatief**:
  - Single point of failure: Odoo down = MCP down
  - Rate-limit is per-Python-worker (in-memory) — niet shared bij multi-worker scaling
  - Module-code moet mee bij elke Odoo-upgrade getest worden
- **Open punten**:
  - Bij multi-worker scaling: vervang in-memory rate-limit door Redis-counter of `ir.config_parameter`
  - Bij groei naar non-Odoo-data-bronnen: heroverweeg externe service (zie [[project-mcp-and-itsm]] memory voor langtermijn)

## Referenties

- [`myschool_mcp/README.md`](../../myschool_mcp/README.md) — module-overzicht
- [`myschool_mcp/DEVELOPER.md`](../../myschool_mcp/DEVELOPER.md) — registry-API + provider-pattern
- [`myschool_mcp/NEXT_STEPS.md`](../../myschool_mcp/NEXT_STEPS.md) — v2-roadmap, bekende issues
- `platform-handbook` memory `project_mcp_and_itsm.md` — lange-termijn vision
- [MCP-spec](https://modelcontextprotocol.io/) — protocol-referentie
