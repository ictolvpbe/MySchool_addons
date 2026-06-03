# Claude — Agent context voor MySchool_addons

Deze file wordt automatisch ingelezen door Claude Code (CLI) bij sessies in deze repo. Bevat conventies, structuur en hot-paths zodat de agent direct productief is.

## Wat is dit repo

`MySchool_addons` = de Odoo-extra-addons-repo voor OLVP (Onze-Lieve-Vrouwepresentatie). Bevat ~18 modules die het school-administratie-platform bouwen bovenop Odoo 19.0. Wordt via Semaphore-pipeline gepulled naar de Odoo-VMs (`SRVV-ODOO-01`, `SRVV-TST-ODOO-01`, `SRVV-TST-ODOO-02`, `SRVV-ACC-01`).

## Structuur

```
MySchool_addons/
├── README.md            ← repo-overzicht
├── CONTRIBUTING.md      ← dev-onboarding (PyCharm, branch-naming, commit-style)
├── CLAUDE.md            ← dit bestand (agent-context)
├── docs/                ← centrale documentatie (zie docs/README.md)
│   ├── architecture/
│   ├── modules/         ← per-module overzicht + crosslinks
│   ├── guides/
│   ├── operations/
│   ├── reference/
│   ├── prompts/
│   └── decisions/       ← ADRs (0000-template, 0001-mcp-as-module, 0002-branch-strategy, ...)
├── myschool_core/       ← Odoo-module (fundament)
├── myschool_admin/      ← school-org admin-laag
├── myschool_mcp/        ← MCP-server voor Claude-integratie
├── myschool_appfoundry/ ← dev-project management
├── ... (~14 andere modules)
└── (legacy top-level *.md files → te verplaatsen naar docs/guides/ of docs/prompts/)
```

## Conventies

### Branches
- `master` = productie (myschool, myschool-ict, id, myschool-acc)
- `Dev` = test + dev environments (case-sensitive — Dev met hoofdletter)
- `Dev-<Topic>` = feature-branches (bv. `Dev-MCP`, `Dev-Admin-and-Core`)

Zie [`docs/decisions/0002-branch-strategy.md`](docs/decisions/0002-branch-strategy.md) voor volledige conventie.

### Modules
- Per module `__manifest__.py` met `name`, `summary`, `depends`, `data`, etc.
- Naming: `myschool_<topic>` voor MySchool-specifieke modules. Ook generieke `activiteiten`, `planner`, `process_mapper` zonder prefix bestaan (legacy).
- Tests in `<module>/tests/test_*.py`, runnen via `odoo -d <db> -i <module> --test-tags <module> --stop-after-init`.

### Documentation
- Cross-cutting docs → `docs/<category>/<topic>.md`
- Per-module docs (USER_MANUAL, DEVELOPER) blijven IN de module-dir voor IDE-context
- ADRs in `docs/decisions/NNNN-titel.md` (zie template `0000-template.md`)

### Commits
- Nederlandse commit-messages (consistent met platform-ansible/handbook conventie)
- Imperatief: "voeg X toe", "fix Y", "refactor Z"
- Eerste regel ≤ 72 chars, optionele body met motivatie ("why")

## Verwante repo's

Zie `platform-handbook` voor infrastructuur-documentatie:
- HAProxy + Caddy + step-ca reverse-proxy chain
- Semaphore pipeline die deze repo deployt naar Odoo-VMs
- Ansible-playbooks (`platform-ansible`)

## Hot-paths voor agents

Veelgevraagde acties:
- **Nieuw addon aanmaken** → kopieer skeleton van `myschool_core/` of `myschool_mcp/`, pas `__manifest__.py` aan, voeg toe aan `docs/modules/README.md` index
- **Module-install op live VM** → via Semaphore "Odoo extra-addons Update" + Odoo CLI `-i <module>` (zie `docs/operations/deploy-via-semaphore.md`)
- **MCP-tool uitbreiden** → nieuw bestand in `myschool_mcp/providers/`, registreer via `@McpRegistry.tool(...)`, import in `providers/__init__.py`
- **ADR schrijven** → kopieer `docs/decisions/0000-template.md`, increment het nummer
- **Lokaal testen** → PyCharm Run-config voor Odoo, dev-DB `odoo-dev` op localhost:5432

## Niet doen

- ❌ Geen rechtstreekse commits op `master` zonder gemerged PR / review
- ❌ Geen `git push --force` op shared branches (`master`, `Dev`)
- ❌ Geen automatische module-install op productie zonder eerst niveau-1 (lokaal) + niveau-2 (test) validatie
- ❌ Geen secrets in code/docs — gebruik KeePassXC + ansible-vault (vault-flow zie platform-ansible)
- ❌ Geen lower-case `dev` branch — case-sensitivity ruïneert deploys (zie ADR 0002)

## Memory

Persistent memory voor Claude Code zit in `~/.claude/projects/-home-demm-PyCharm-odoo-myschool/memory/` (workstation-lokaal). Cross-project context: zie de OLVP platform-handbook memory voor infra-overlap.
