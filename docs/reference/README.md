# Reference

Naslagdocumentatie: branches, environments, instances, git-workflow.

## Inhoud

| Bestand | Doel | Status |
|---|---|---|
| [`branches.md`](branches.md) | Lijst + status van huidige branches, naming-conventie | done (2026-06-03) |
| [`environments.md`](environments.md) | prod/test/dev mapping per FQDN, multi-env-VM-pattern, cert-strategie | done (2026-06-03) |
| [`git-workflow.md`](git-workflow.md) | Git-workflow van repo (commits, merges, releases) | verplaatst van repo-root; inhouds-review pending |

(`instances.md` als aparte file is niet meer nodig — FQDN-mapping zit nu compleet in `environments.md` en in deze README-inleiding hieronder.)

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
