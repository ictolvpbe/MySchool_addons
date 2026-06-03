# 0002 — Branch-strategie: master/Dev/Dev-* feature-branches

- **Status**: accepted
- **Datum**: 2026-06-02 (bevestigd tijdens Semaphore-setup)
- **Beslisser**: ict@olvp.be

## Context

Bij het opzetten van Semaphore's "Odoo extra-addons Update" pipeline (zie [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md)) moest een formele branch-strategie bevestigd worden voor de `MySchool_addons` repo. Dit ADR documenteert de gehanteerde conventie zodat toekomstige contributors weten welke branch waarvoor dient.

Constraints:
- Multi-environment deploy: prod (myschool, myschool-ict, id, myschool-acc) + test (myschool-test, myschool-acc-test) + dev (id-test, myschool-dev, myschool-dev2)
- Semaphore Survey-var `target_env` filtert per env welke Odoo-instances geüpdate worden
- Branch-naam per env wordt via `addons_branch` per-instance in `platform-ansible/vars/instances.yml` vastgelegd
- Git branches zijn **case-sensitive** — verschillende spelling = andere branch

## Opties overwogen

### Optie A: master + dev (lowercase, GitFlow-light)

- Voor: industriestandaard (master/main + dev)
- Tegen: huidige repo heeft `master` + `Dev` (hoofdletter), zou een rename vereisen die andere developers stoort

### Optie B: master + Dev + Dev-<topic> (huidige praktijk)

- Voor:
  - Reflecteert de bestaande situatie in de repo
  - Feature-branches (Dev-Aanvragen, Dev-Bus_Seater, Dev-MCP, etc.) zijn gegroeid topic-gewijs en blijven leesbaar
  - Geen rename-disruptie
- Tegen:
  - `Dev` met hoofdletter is on-Englishly atypisch
  - 14+ feature-branches op origin — sommige al stale

### Optie C: trunk-based (alleen master + short-lived branches)

- Voor: snelle iteratie, eenvoudig
- Tegen: te disruptief voor huidige collega's gewend aan feature-branches; verlies van isolatie tussen experimenten

## Beslissing

**Optie B — master + Dev + Dev-<topic>**, met expliciete documentatie hier zodat conventie duidelijk is.

Branch-rollen:
- **`master`** — productie. Wordt gepulled door Semaphore voor `target_env=prod` (= alle myschool-ict en zusters op SRVV-ODOO-01)
- **`Dev`** — gedeelde test/dev-omgeving. Wordt gepulled voor `target_env=test` (= myschool-test) en `target_env=dev` (= id-test, myschool-dev, myschool-dev2)
- **`Dev-<Topic>`** — feature-branches per ontwikkelaar/onderwerp (bv. `Dev-MCP`, `Dev-Admin-and-Core`, `Dev-Docs-structure`). Niet auto-pulled door Semaphore. Te testen via Survey-override (`addons_branch_override=Dev-Topic`) op een single-instance.

**Case-sensitivity**: branches matchen exact. Gebruik altijd `Dev` (hoofdletter D) — niet `dev`, niet `DEV`.

**Lifecycle**: feature-branch → werk afronden → merge naar `Dev` (test-omgeving valideert) → merge naar `master` (prod-deploy) → branch deleten of laten staan voor referentie.

## Gevolgen

- **Positief**:
  - Werkende workflow zonder rename
  - Per-env deployment via Semaphore zonder branch-rename-overhead
  - Feature-isolatie is duidelijk via branch-naamgeving
- **Negatief**:
  - Inconsistente conventie t.o.v. andere repo's (platform-ansible gebruikt enkel `main`)
  - Stale feature-branches stapelen op origin (cleanup ooit te plannen)
- **Open punten**:
  - Stale-branch-cleanup: na 90 dagen inactief + gemerged kan branch verwijderd worden — proces TBD
  - Bij ooit-cutover naar trunk-based: separate ADR met motivatie

## Referenties

- [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md) — Semaphore pipeline-conventies
- `platform-handbook` memory `project_odoo_addons_repo.md` — branch-conventie samenvatting
- `platform-ansible/vars/instances.yml` — per-instance `addons_branch` field
- [`../reference/branches.md`](../reference/branches.md) — branch-lijst + status (TODO)
