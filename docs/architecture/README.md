# Architecture

Overall ontwerp van de MySchool-stack: module-relaties, data-model, MCP-architectuur, integratiepatronen.

## Inhoud

- `overview.md` — TODO: high-level platform-overview (Odoo + extra-addons + MCP + integraties)
- `module-graph.md` — TODO: Mermaid-graph van alle module-dependencies
- `data-model.md` — TODO: kernentiteiten (Organization, Person, Role, Period) en hun relaties over modules
- `mcp-architecture.md` — TODO: hoe `myschool_mcp` provider-pattern werkt, request-flow JSON-RPC ↔ Odoo-records

## Cross-link met platform-handbook

Voor hosting, netwerk, certificaten en de HAProxy → Caddy → Odoo chain die deze addons serveert: zie [`platform-handbook/hosting/`](https://github.com/ictolvpbe/platform-handbook/tree/main/hosting).
