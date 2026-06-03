# myschool_itsm

ITIL 4 compliant IT Service Management voor school-omgevingen. Tickets/incidents, knowledge-base, change-management workflow, asset/CMDB-koppeling en risk-register.

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `myschool_core`, `myschool_asset`, `mail` |
| Strategisch | Toekomstige single-source-of-truth voor IT-governance (zie [[project-mcp-and-itsm]] memory) |

## Aanwezig (uit memory)

- **Tickets/Incidents** + knowledge-base
- **Change-management** workflow
- **Asset-management/CMDB** + risk-register (via `myschool_asset`)

## Nog niet aanwezig

- **SLA-tracking + reporting** — mogelijk apart te bouwen
- Volledige incident-RCA (root-cause-analysis) workflow

## Strategische rol

Project H in OLVP programma-structuur. Doel: tracking van risk-register, incident-log, change-log, tasks/projecten verhuist van git/Sheets naar Odoo. Architectuur-docs blijven in git.

Voorwaarden voor migratie:
- SLA-tracking + reporting beschikbaar
- MCP-koppeling getest (zodat Claude updates kan doen via myschool_mcp)
- Wazuh + monitoring-events naar ITSM-tickets gerouteerd (Fase 3)

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_asset`](myschool_asset.md) — CMDB-laag (depends op deze)
- [`myschool_core`](myschool_core.md) — fundament
- [`knowledge_builder`](knowledge_builder.md) — mogelijke knowledge-base-integratie
- [`myschool_mcp`](myschool_mcp.md) — toekomstige ITSM-provider voor Claude-toegang
