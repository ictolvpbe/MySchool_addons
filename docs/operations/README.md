# Operations

Deploy-, upgrade- en beheer-procedures voor MySchool addons.

## Inhoud

- `deploy-via-semaphore.md` — TODO: hoe addons gepulled worden naar Odoo-VMs via Semaphore "Odoo extra-addons Update" template (cross-link naar [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md))
- `module-install.md` — TODO: install + upgrade procedure (Odoo UI vs CLI `-i` / `-u`)
- `backup-restore.md` — TODO: DB-backup, filestore-backup, restore-procedure
- `branch-promote.md` — TODO: feature-branch → Dev → master promote-pad, link met Semaphore env-filter
- `tech-info.md` — TODO: TechInfo.md verplaatsen + reviewen

## Semaphore-pipeline (huidig)

Repo `MySchool_addons` wordt gepulled via Semaphore template "Odoo extra-addons Update" op de OLVP Odoo-VMs:
- **target_env=prod** → branch `master` → instances op SRVV-ODOO-01 (myschool/myschool-ict/id)
- **target_env=test** → branch `Dev` → instance `myschool-test` op SRVV-TST-ODOO-01:8069
- **target_env=dev** → branch `Dev` → instances op TST-ODOO-01:8070+8071 + TST-ODOO-02:8069
- **addons_branch_override=...** → één-shot override, bv. `Dev-MCP` voor feature-branch-test

Volledige details: zie cross-link met [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md).
