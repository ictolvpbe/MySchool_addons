# MySchool_addons

Odoo-extra-addons voor het OLVP MySchool-platform. Bevat ~18 modules die het school-administratie-platform vormen bovenop Odoo 19.0.

## Structuur

Cross-cutting documentatie staat in [`docs/`](docs/). Per-module documentatie (README, USER_MANUAL, DEVELOPER) blijft binnen elke module-dir voor IDE-zoekbaarheid.

### Belangrijkste startpunten

- [`docs/`](docs/) — centrale documentatie-index
- [`docs/modules/README.md`](docs/modules/README.md) — alle modules met 1-line summary + categorieën
- [`docs/architecture/`](docs/architecture/) — module-graph, data-model
- [`docs/operations/`](docs/operations/) — deploy via Semaphore, module-install, branch-promote
- [`docs/decisions/`](docs/decisions/) — Architecture Decision Records (ADRs)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev-onboarding (PyCharm, branches, commits)
- [`CLAUDE.md`](CLAUDE.md) — agent-context voor Claude Code

## Branches

- `master` = productie (myschool, myschool-ict, id, myschool-acc) — case-sensitive
- `Dev` = test + dev environments (myschool-test, myschool-dev, ...)
- `Dev-<Topic>` = feature-branches (bv. `Dev-MCP`, `Dev-Admin-and-Core`)

Volledige conventie: [`docs/decisions/0002-branch-strategy.md`](docs/decisions/0002-branch-strategy.md).

## Deploy

Wordt automatisch gepulled door [Semaphore](https://semaphoreui.com/) template "Odoo extra-addons Update" naar de Odoo-VMs in OLVP-netwerk. Survey-vars (`target_env`, `addons_branch_override`, `target_limit`) sturen welke env/branch/VMs gepulled worden.

Details + cross-links naar infrastructuur-docs: [`docs/operations/`](docs/operations/) en [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md).

## Verwante repo's

- [`platform-handbook`](https://github.com/ictolvpbe/platform-handbook) — OLVP infrastructuur-docs (HAProxy, Caddy, Semaphore, ansible)
- [`platform-ansible`](https://github.com/ictolvpbe/platform-ansible) — Ansible-playbooks (Semaphore + bare-metal config)
