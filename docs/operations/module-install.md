# Module install + upgrade

Hoe je een MySchool-addon installeert of upgrade op een Odoo-instance. Voor automatische deploy van addon-code naar de VMs zelf: zie [`deploy-via-semaphore.md`](deploy-via-semaphore.md). Deze runbook gaat over de Odoo-zijde: code is op de VM, maar Odoo moet de module nog kennen.

## Pre-conditions

- Module-code staat in `/opt/odoo-multi-instance/addonsN/` op de Odoo-VM (Semaphore-pipeline heeft gepulled)
- Container `odoo_instance_N` draait en is op de juiste addons-dir bind-mounted
- Module-dependencies (uit `__manifest__.py` `depends`) zijn al geïnstalleerd

## Methode 1 — Odoo UI (eenvoudig, interactief)

Aanbevolen voor eerste install van een nieuwe module.

1. **Login**: open `https://<fqdn>/web/login` als admin (of een gebruiker met `group_system`)
2. **Developer mode aan**: ga naar Settings → "Activate the developer mode" onderaan, of voeg `?debug=1` toe aan URL
3. **Update Apps List**: Apps → linksboven 3-stippen-menu → **Update Apps List** → **Update**
   - Odoo scant `addons_path` voor nieuwe `__manifest__.py` files
4. **Module zoeken**: in de Apps-zoekbalk filter `Modules → Not Installed` weghalen of zoeken op naam (bv. "MCP")
5. **Install**: klik op de module-card → **Install**
   - Odoo voert post-install hooks uit, data-files laden, security-rules creëren

## Methode 2 — Odoo CLI in container (reproduceerbaar, automatisch)

Aanbevolen voor Ansible/Semaphore-driven upgrades.

```bash
ssh ansible@<VM-IP>

# Install (eerste keer)
sudo podman exec odoo_instance_N \
  odoo -d <db> -i <module> --stop-after-init --no-http

# Upgrade (na addons-update via Semaphore)
sudo podman exec odoo_instance_N \
  odoo -d <db> -u <module> --stop-after-init --no-http

# Multiple modules tegelijk
sudo podman exec odoo_instance_N \
  odoo -d <db> -u myschool_core,myschool_mcp --stop-after-init --no-http

# Restart Odoo zodat nieuwe code wordt geladen
sudo systemctl restart odoo_instance_N.service
```

Parameters:
- `-d <db>` — DB-naam (afhankelijk van instance). DB-naam staat in `odoo.conf` of `instances.yml` (`db_name` field)
- `-i <module>` — install (fresh)
- `-u <module>` — upgrade (run `migrations/` als die er zijn)
- `--stop-after-init` — process exit na install, geen web-server start
- `--no-http` — vermijdt poort-conflict (instance draait al op de HTTP-poort via Quadlet)

## Methode 3 — `-u all` (volledige upgrade van alle modules)

Bij grote refactors of major Odoo-upgrade:

```bash
sudo podman exec odoo_instance_N odoo -d <db> -u all --stop-after-init --no-http
```

⚠️ Duurt lang (5-30min afhankelijk van DB-grootte) en blokkeert de instance tijdens upgrade. Doe dit in maintenance-window.

## Verificatie na install

```bash
# Module is "installed" in DB?
ssh ansible@<VM-IP> 'sudo podman exec postgres_odoo_N \
  psql -U odoo -d <db> -tAc "SELECT state FROM ir_module_module WHERE name='\''<module>'\''"'
# Verwacht: "installed"

# Web-endpoint reageert?
curl -kI https://<fqdn>/<endpoint>
# Voor myschool_mcp: curl -X POST https://<fqdn>/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' -H 'Content-Type: application/json'
```

## Module uninstall

⚠️ Uninstall verwijdert data van de module (alle records uit module's tabellen, niet alle Odoo-tabellen!).

```bash
sudo podman exec odoo_instance_N odoo -d <db> --uninstall <module> --stop-after-init --no-http
```

Of via UI: Apps → module-card → **Uninstall**.

**Voor productie**: nooit uninstall doen zonder DB-backup vooraf. Liever module disablen via custom config of `installable=False` in manifest.

## Common gotchas

- **Odoo cached `ir.model.data`**: na install ziet de UI nieuwe modellen pas na restart. Gebruik altijd `systemctl restart` na CLI-install.
- **`base` module-dependency conflict**: als een nieuwe module deps heeft die nog niet installed zijn, Odoo installeert ze automatisch tijdens de install. Maar als deps zelf falen (bv. syntax-fout in een dep-module's xml), faalt de hele install.
- **Migrations**: bij `-u` runt Odoo `migrations/<version>/pre-migrate.py`, `post-migrate.py`. Check deze files in de module voor side-effects.
- **Multi-DB op één instance**: als `db_filter` niet ingesteld is, kan een `-i` per ongeluk in de verkeerde DB landen. Gebruik altijd expliciete `-d <db>`.
- **No-HTTP-flag**: zonder `--no-http` probeert Odoo de web-server op 8069 te starten, maar die poort is al door de Quadlet-container in gebruik → port-conflict-error. Vandaar de `--no-http`-flag bij alle install-commando's binnen container.

## Per-FQDN voorbeelden

| FQDN | VM | Instance | DB-naam (typisch) |
|---|---|---|---|
| `myschool.olvp.be` | SRVV-ODOO-01 | `odoo_instance_1` | TBD (check instances.yml) |
| `myschool-ict.olvp.be` | SRVV-ODOO-01 | `odoo_instance_2` | TBD |
| `id.olvp.be` | SRVV-ODOO-01 | `odoo_instance_3` | TBD |
| `myschool-test.olvp.be` | SRVV-TST-ODOO-01 | `odoo_instance_1` | `myschool-test` |
| `myschool-dev.olvp.be` | SRVV-TST-ODOO-01 | `odoo_instance_3` | TBD |
| `myschool-acc.olvp.int` | SRVV-ACC-01 | `odoo_instance_1` | `myschool_acc` |
| `myschool-acc-test.olvp.int` | SRVV-ACC-01 | `odoo_instance_2` | `myschool_acc_test` |

## Volgende

- Voor branche-promote-flow (feature → Dev → master): zie [`branch-promote.md`](branch-promote.md)
- Voor backup vóór risky upgrades: zie [`backup-restore.md`](backup-restore.md) (TODO)
