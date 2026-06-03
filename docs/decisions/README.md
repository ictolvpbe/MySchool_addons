# Architecture Decision Records (ADRs)

Belangrijke architectuur- en design-beslissingen voor MySchool. Eén bestand per beslissing, genummerd `NNNN-titel.md`. Volgt het [MADR-format](https://adr.github.io/madr/) lichtjes aangepast.

## Inhoud

- [`0000-template.md`](0000-template.md) — Template voor nieuwe ADRs
- [`0001-mcp-as-odoo-module.md`](0001-mcp-as-odoo-module.md) — MCP-server als Odoo-module i.p.v. extern proces
- [`0002-branch-strategy.md`](0002-branch-strategy.md) — Branch-strategie master/Dev/Dev-* feature-branches
- TODO: `0003-project-management-addon.md` — Odoo `project` vs eigen `myschool_projectmanager` (Werf D, in evaluatie)

## ADR-conventie

Status-waarden: `proposed` / `accepted` / `deprecated` / `superseded by NNNN`. Status enkel wijzigen via nieuwe commit met motivatie. Een geaccepteerd ADR niet meer wijzigen — een nieuw ADR schrijven dat het oude superseded.
