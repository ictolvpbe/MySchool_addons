# Branch-promote: feature → Dev → master

Hoe een feature-branch z'n weg vindt door de test/dev → productie-omgevingen, en welke Semaphore-runs daarvoor nodig zijn.

## Het pad in één plaatje

```
Dev-<Topic>  ──merge──▶  Dev  ──merge──▶  master
   │                       │                  │
   │                       │                  │
   ▼                       ▼                  ▼
Semaphore run         Semaphore run     Semaphore run
target_env=dev        target_env=test   target_env=prod
addons_branch_        (geen override —  (geen override —
 override=Dev-<T>     pulled Dev auto)  pulled master auto)
single VM             alle test-VMs     alle prod-VMs
       │
       ▼
Module-install:
podman exec ...
  odoo -d <db> -i <module>
       │
       ▼
Verifie + smoke-test
```

## Stap 1 — Feature-branch testen op één test-VM

```bash
# Lokaal
git checkout Dev-<Topic>
git push origin Dev-<Topic>
```

**Semaphore**:
- Template `Odoo extra-addons Update` → Run
- Survey:
  - `target_env=dev` (of `test` als feature een gebruikers-feature is)
  - `addons_branch_override=Dev-<Topic>`
  - `target_limit=tst-odoo-01` (single VM voor isolatie)

**Op de VM**: module-install + restart (zie [`module-install.md`](module-install.md)).

**Validatie**:
- Smoke-test via curl of UI
- Geen errors in Odoo-log (`sudo podman logs --tail 100 odoo_instance_N`)
- Tests draaien indien aanwezig: `odoo -d <db> -i <module> --test-tags <module> --stop-after-init --no-http`

**Wanneer er problemen zijn**: fix lokaal, force-push naar `Dev-<Topic>`, re-run Semaphore. **Niet** mergen voor je groen bent.

## Stap 2 — Merge naar Dev voor brede test-validatie

```bash
git checkout Dev
git pull origin Dev
git merge --no-ff Dev-<Topic>
git push origin Dev
```

**`--no-ff`** behoudt de merge-commit zodat het zichtbaar is dat een feature gemerged is — handig voor latere revert.

**Semaphore**: Run met `target_env=test` (alle test-instances) + `target_env=dev` (alle dev-instances). Of één run zonder target_env-filter (= alles met env=test of dev).

**Validatie**: alle test/dev-instances werken nog. Module-install + restart per VM. Smoke-test myschool-test (gebruikers-test-omgeving).

## Stap 3 — Merge naar master voor productie

⚠️ Doe dit in maintenance-window of na confirmation dat de wijziging veilig is voor live gebruikers.

```bash
git checkout master
git pull origin master
git merge --no-ff Dev
git push origin master
```

**Semaphore**: Run met `target_env=prod`, optioneel `target_limit=srvv-odoo-01` voor één VM-tegelijk.

**Op de prod-VM**:
```bash
ssh ansible@10.36.0.40
sudo podman exec odoo_instance_2 odoo -d <db> -u <module> --stop-after-init --no-http
sudo systemctl restart odoo_instance_2.service
```

**Validatie**:
- Smoke-test op `https://myschool-ict.olvp.be/` (of welke prod-FQDN relevant is)
- Monitor Odoo-log eerste 15min voor onverwachte errors
- HAProxy backend-status moet `UP` blijven (geen 502)

## Rollback-scenarios

### Rollback Stap 3 (master)

Als productie kapot is na deploy:

```bash
# Lokaal — revert de merge-commit (let op: --no-ff merge in stap 3 maakt dit mogelijk!)
git checkout master
git revert -m 1 <merge-commit-hash>
git push origin master
```

**Semaphore** opnieuw runnen → master-versie zonder feature wordt teruggepulled.

**Op de prod-VM**:
```bash
sudo podman exec odoo_instance_N odoo -d <db> -u <module> --stop-after-init --no-http
sudo systemctl restart odoo_instance_N.service
```

⚠️ Als de feature-branch DB-schema wijzigingen deed (nieuwe velden, models, migrations), is een schema-rollback complexer dan code-rollback. Heroverweeg DB-backup-restore in dat geval.

### Rollback Stap 2 (Dev)

Idem als boven maar op `Dev`-branch. Geen impact op productie omdat master niet aangepast was.

## Branch-housekeeping

Na een geslaagde merge naar `master` (en stabiele werking op prod):

```bash
# Lokaal
git branch -d Dev-<Topic>

# Op GitHub (handmatig of via gh cli)
gh api -X DELETE /repos/ictolvpbe/MySchool_addons/git/refs/heads/Dev-<Topic>
```

Vermijdt stale branches op origin (geconstateerd 2026-06-02 dat er 14+ Dev-* branches openstaan, meestal verzameling van oude features).

## Common situations

### Een instance per omgeving testen?

Use `target_limit` op één VM. Bv. test alleen `srvv-tst-odoo-01` (myschool-test):
```
target_env=test
target_limit=tst-odoo-01
```

### Twee features tegelijk testen?

Maak een combinatie-branch:
```bash
git checkout -b Dev-Combo-A-and-B
git merge Dev-Feature-A
git merge Dev-Feature-B
git push origin Dev-Combo-A-and-B
```
Test deze als één feature. Bij groen → merge component-branches afzonderlijk naar Dev (eerst A, dan B; vermijd merge-conflicts).

### Hotfix direct naar master?

Als bug-fix urgent is en je niet door Dev wil:
```bash
git checkout master
git checkout -b Dev-Hotfix-<beschrijving>
# fix + commit
git push origin Dev-Hotfix-<beschrijving>
# test via Semaphore: target_env=prod target_limit=<één-vm> addons_branch_override=Dev-Hotfix-...
# Bij groen → merge naar master + back-merge naar Dev (zodat Dev niet achter loopt)
git checkout master && git merge --no-ff Dev-Hotfix-<beschrijving> && git push
git checkout Dev    && git merge --no-ff master && git push
```

## Verwante docs

- [`deploy-via-semaphore.md`](deploy-via-semaphore.md) — Semaphore-Survey-vars en pipeline-details
- [`module-install.md`](module-install.md) — Odoo-zijde install/upgrade procedures
- [`../decisions/0002-branch-strategy.md`](../decisions/0002-branch-strategy.md) — waarom master/Dev/Dev-* (niet GitFlow of trunk-based)
