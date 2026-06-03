# Branches

Huidige branches in `MySchool_addons` (stand 2026-06-03). Branch-conventie zie [`../decisions/0002-branch-strategy.md`](../decisions/0002-branch-strategy.md).

## Stabiele branches

| Branch | Rol | Auto-pulled door Semaphore | Wie merget |
|---|---|---|---|
| `master` | Productie | `target_env=prod` | Code-eigenaar na groen op Dev |
| `Dev` | Test + dev | `target_env=test` / `target_env=dev` | Code-eigenaar na groen op feature-branch |

## Feature-branches (Dev-*)

Lijst per 2026-06-03 (snapshot uit `git branch -a`). Status-classificatie is indicatief — een review-rondje is gepland voor housekeeping.

| Branch | Onderwerp | Indicatieve status |
|---|---|---|
| `Dev-MCP` | myschool_mcp deploy-spoor (gecherry-pickt uit Dev-Admin-and-Core) | actief (Werf A) |
| `Dev-Docs-structure` | Docs-restructuur (`docs/`-submap) | actief (Werf B) |
| `Dev-Admin-and-Core` | Activiteiten/Admin/Core grote refactor | actief, lang openstaand |
| `Dev-Aanvragen` | Aanvragen-workflow | review pending |
| `Dev-Aciviteiten` (sic, typo) | Activiteiten-uitbreidingen | review pending |
| `Dev-Bus_Seater` | Bus-stoel-allocatie | mogelijk gemerged of obsolete |
| `Dev-Drukwerk` | Drukwerk-aanvragen | review pending |
| `Dev-MuSchoolAdmin-Christophe` (sic, typo) | Persoonlijke feature-branch Christophe | review pending |
| `Dev-MySchoolAdmin-Christophe-Lessenroster` | Lessenrooster-koppeling | review pending |
| `Dev-Nascholing` | Nascholing-module | review pending |
| `Dev-Planner` | Planner-uitbreidingen | review pending |
| `Dev-Test-christophe` | Test-branch | mogelijk weg |
| `Dev-proffecionalisering` (sic, typo) | Professionalisering | mogelijk gemerged |

## Housekeeping-todo

- **Typo-branches**: `Dev-Aciviteiten`, `Dev-MuSchoolAdmin-Christophe`, `Dev-proffecionalisering` — bij gelegenheid rename of close
- **Lang openstaande feature-branches**: `Dev-Admin-and-Core` is 195 commits ahead van master (per 2026-06-03). Plannen om die in chunks te mergen of de werkzaamheden over te zetten naar nieuwe focused branches
- **Persoonlijke branches**: `Dev-Test-christophe` lijkt experimentele scratch — kandidaat voor delete na review

## Werkprocedure: nieuwe branch starten

```bash
git checkout master
git pull origin master
git checkout -b Dev-<Topic>
# werk + commits
git push -u origin Dev-<Topic>
```

Naming-convention:
- Prefix `Dev-`
- Korte topic-naam in CamelCase of met streepjes (geen spaties of underscores in branch-naam)
- Vermijd persoons-namen tenzij echt experimenteel; gebruik liever onderwerp-naam

Verwante: [`../decisions/0002-branch-strategy.md`](../decisions/0002-branch-strategy.md), [`../operations/branch-promote.md`](../operations/branch-promote.md).
