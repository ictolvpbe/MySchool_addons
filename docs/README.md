# MySchool Documentation

Centrale documentatie voor de OLVP MySchool Odoo-addons-repo (`MySchool_addons`). Per-module README's blijven in de module-dir zelf (voor IDE-context); deze `docs/`-submap bundelt cross-cutting documentatie, ADRs, runbooks en procedures.

Geïnspireerd op de structuur van `platform-handbook` (zie verwante repo's onderaan).

## Indeling

- [`architecture/`](architecture/) — overall ontwerp: module-graph, data-model, MCP-architectuur
- [`modules/`](modules/) — index van alle modules met 1-line summary + crosslinks naar in-module docs
- [`guides/`](guides/) — gebruikers-handleidingen (account-lifecycle, Google Workspace setup, process-mapper, styleguide, QC-checklist)
- [`operations/`](operations/) — deploy-procedures (Semaphore-pipeline, module-install via Odoo UI/CLI, upgrade, backup-restore)
- [`reference/`](reference/) — naslag: branches, environments, instance-mapping, git-workflow
- [`prompts/`](prompts/) — AI prompt-templates (BPMN-improvement, kennisbank-plan, code-improvement)
- [`decisions/`](decisions/) — ADRs (Architecture Decision Records), genummerd `0001-...md`

## Conventies

- Markdown met GitHub-flavored extensies (Mermaid voor diagrammen).
- Per module 1 file in `docs/modules/<module>.md` met:
  - 1-paragraph beschrijving
  - dependencies
  - status (alpha/beta/stable)
  - link naar in-module README (zoals `myschool_mcp/README.md`)
- ADRs incrementeel genummerd. Eén ADR per beslissing. Voor het format: zie `decisions/0000-template.md`.
- Per-module USER_MANUAL/DEVELOPER docs blijven in module-dir voor IDE-zoekbaarheid. Hier in `docs/modules/<module>.md` enkel kort overzicht + crosslinks.

## Verwante repo's

- [`platform-handbook`](https://github.com/ictolvpbe/platform-handbook) — OLVP infrastructuur-documentatie (HAProxy, Caddy, step-ca, Ansible, Semaphore)
- [`platform-ansible`](https://github.com/ictolvpbe/platform-ansible) — Ansible-playbooks voor OLVP-stack (incl. Semaphore-pipeline die deze repo naar Odoo-VMs pullt)

## Voor nieuwe contributors

Zie [`../CONTRIBUTING.md`](../CONTRIBUTING.md) (in repo-root) voor PyCharm-setup, branch-naming, commit-conventies.
