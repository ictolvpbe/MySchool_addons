# Reference

Naslagdocumentatie: branches, environments, instances, git-workflow.

## Inhoud

- `branches.md` — TODO: branch-strategie (master/Dev/Dev-* feature-branches)
- `environments.md` — TODO: prod/test/dev environment-mapping en welke FQDN bij welke instance hoort
- `instances.md` — TODO: FQDN → VM:port mapping (myschool/myschool-ict/id/myschool-test/myschool-dev/id-test)
- `git-workflow.md` — TODO: git-workflow.md (top-level) verplaatsen + bijwerken

## Branch-conventie (kort)

Bevestigd 2026-06-02 bij Semaphore-setup:
- `master` → productie (myschool, myschool-ict, id, myschool-acc)
- `Dev` → test + dev environments
- `Dev-<Topic>` → feature-branches (bv. `Dev-Admin-and-Core`, `Dev-MCP`, `Dev-Docs-structure`, `Dev-Planner`, ...)

**Case-sensitive** — Git branches matchen exact. `Dev` met hoofdletter D (zoals de repo het spelt).

Volledige details + Semaphore Survey-vars: [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md).

## Instance-FQDN-mapping (samenvatting, zie platform-handbook voor volledige inventory)

| FQDN | Env | VM | Port | Branch |
|---|---|---|---|---|
| `myschool.olvp.be` | prod | SRVV-ODOO-01 | 8069 | master |
| `myschool-ict.olvp.be` | prod | SRVV-ODOO-01 | 8070 | master |
| `id.olvp.be` | prod | SRVV-ODOO-01 | 8071 | master |
| `myschool-acc.olvp.int` (intern) | prod | SRVV-ACC-01 | 8069 | master |
| `myschool-acc-test.olvp.int` (intern) | test | SRVV-ACC-01 | 8070 | Dev |
| `myschool-test.olvp.be` | test | SRVV-TST-ODOO-01 | 8069 | Dev |
| `id-test.olvp.be` | dev | SRVV-TST-ODOO-01 | 8070 | Dev |
| `myschool-dev.olvp.be` | dev | SRVV-TST-ODOO-01 | 8071 | Dev |
| `myschool-dev2.olvp.be` | dev | SRVV-TST-ODOO-02 | 8069 | Dev |
