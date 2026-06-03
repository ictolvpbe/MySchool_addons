# Backup + restore

Backup-strategie voor MySchool Odoo-instances. Twee componenten moeten samen geback-upt worden: **Postgres-DB** + **filestore** (binary attachments).

## Wat moet geback-upt

| Onderdeel | Locatie | Inhoud |
|---|---|---|
| Postgres-DB | Postgres-container per instance | Alle records, configuratie, modules-state |
| Filestore | `/opt/odoo-multi-instance/odoo<N>-data/filestore/<db>/` | Binary attachments (PDFs, images, ...) |
| Odoo.conf | `/opt/odoo-multi-instance/config<N>/odoo.conf` | DB-conn-string, admin_passwd hash, settings |
| Custom addons | `/opt/odoo-multi-instance/addons<N>/` | Code (al in git → niet kritisch backup-doel) |

**Belangrijk**: DB-only backup zonder filestore = onbruikbaar voor restore (attachments raken stuk). Altijd beide samen.

## Backup-strategie (huidig)

**Status 2026-06-03**: handmatige backup-procedure per instance. **Geautomatiseerde Bacula-deploy is gepland** maar nog niet operationeel (zie [`platform-handbook/management-tools/bacula.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/bacula.md)).

### Handmatige backup (proces nu)

Per instance, op de VM:

```bash
ssh ansible@<VM-IP>

# Parameters
INSTANCE=N                          # 1, 2, of 3
DB=<db-naam>                        # uit instances.yml of odoo.conf
TS=$(date +%Y%m%d-%H%M%S)
BACKUPDIR=/opt/odoo-multi-instance/backups
mkdir -p "$BACKUPDIR"

# 1. Postgres-dump (consistent: pg_dump locks niet, gebruikt MVCC-snapshot)
sudo podman exec postgres_odoo_$INSTANCE \
  pg_dump -U odoo -d "$DB" -Fc --no-owner --no-privileges \
  > "$BACKUPDIR/${DB}-${TS}.dump"

# 2. Filestore-tarball
sudo tar -czf "$BACKUPDIR/${DB}-filestore-${TS}.tar.gz" \
  -C /opt/odoo-multi-instance/odoo${INSTANCE}-data/filestore \
  "$DB"

# 3. Config-snapshot (klein, handig voor disaster-recovery)
sudo cp /opt/odoo-multi-instance/config${INSTANCE}/odoo.conf \
  "$BACKUPDIR/${DB}-odoo.conf-${TS}"

# 4. Verifie + manifest
ls -lh "$BACKUPDIR/" | grep "$TS"
echo "Backup gemaakt op $(date) voor DB=$DB instance=$INSTANCE" \
  >> "$BACKUPDIR/manifest.log"
```

### Off-site kopie

De `/opt/odoo-multi-instance/backups/` map staat op de VM-zelf — bij hardware-failure ben je deze kwijt. Off-site-kopie naar mgmt-VM of NAS:

```bash
# Op werkstation of mgmt-host
rsync -av --delete \
  ansible@<VM-IP>:/opt/odoo-multi-instance/backups/ \
  /mnt/backup-storage/myschool/<vm-naam>/
```

Of via Bacula zodra die deployed is (toekomst).

## Restore-procedures

### Scenario 1: Restore op zelfde instance (rollback)

Uitgangspunt: Odoo-instance draait nog, maar je wil een oudere state terug.

⚠️ **Voorlopig stop schrijven door alle users** voor restore.

```bash
ssh ansible@<VM-IP>

INSTANCE=N
DB=<db-naam>
RESTORE_DUMP=/opt/odoo-multi-instance/backups/${DB}-<datum>-<tijd>.dump
RESTORE_FS=/opt/odoo-multi-instance/backups/${DB}-filestore-<datum>-<tijd>.tar.gz

# 1. Stop Odoo (filestore mag niet gewijzigd worden tijdens restore)
sudo systemctl stop odoo_instance_$INSTANCE.service

# 2. Drop bestaande DB + recreate
sudo podman exec postgres_odoo_$INSTANCE psql -U odoo -d postgres -c \
  "DROP DATABASE \"$DB\" WITH (FORCE);"
sudo podman exec postgres_odoo_$INSTANCE psql -U odoo -d postgres -c \
  "CREATE DATABASE \"$DB\" OWNER odoo;"

# 3. Restore DB
sudo podman exec -i postgres_odoo_$INSTANCE \
  pg_restore -U odoo -d "$DB" --no-owner --no-privileges \
  < "$RESTORE_DUMP"

# 4. Restore filestore
sudo rm -rf /opt/odoo-multi-instance/odoo${INSTANCE}-data/filestore/$DB
sudo tar -xzf "$RESTORE_FS" \
  -C /opt/odoo-multi-instance/odoo${INSTANCE}-data/filestore/

# 5. Fix ownership van filestore (Odoo user binnen container is uid 100)
sudo chown -R 100:101 /opt/odoo-multi-instance/odoo${INSTANCE}-data/filestore/$DB

# 6. Start Odoo
sudo systemctl start odoo_instance_$INSTANCE.service

# 7. Verifie via curl + login
curl -kI https://<fqdn>/web/login
```

### Scenario 2: Restore op nieuwe VM (disaster recovery)

Uitgangspunt: oorspronkelijke VM weg, nieuwe Tier 1 baseline-VM gereed (gekloond uit SRVV-ODOO-TEMPLATE).

1. **Ansible-deploy** met juiste hostname/IP — zie [`platform-ansible/odoo-podman.yml`](https://github.com/ictolvpbe/platform-ansible/blob/main/odoo-podman.yml)
2. **DB-init overslaan**: bij eerste run produceert de role een lege Odoo-DB. Drop die direct na deploy.
3. **Restore-procedure** zoals scenario 1 toepassen
4. **DNS-A-record bijwerken** (one.com of AD-DNS, afhankelijk van publiek vs intern)

### Scenario 3: Single-module restore

Soms wil je niet alle data terug, maar één module opnieuw initialiseren (bv. corrupted module-state):

```bash
# Drop module-tabellen en re-install
sudo podman exec odoo_instance_$INSTANCE odoo -d $DB \
  --no-http --stop-after-init \
  --without-demo=all -u <module>
```

⚠️ Dit verliest alle data van die module (records, attachments gerelateerd). Alleen doen na backup.

## Backup-frequentie (aanbeveling)

| Environment | Frequentie | Retentie |
|---|---|---|
| **prod** (myschool, myschool-ict, id, myschool-acc) | dagelijks + uurly tijdens werkuren | 30d dagelijks + 12m maandelijks |
| **test** (myschool-test, myschool-acc-test) | dagelijks | 7d |
| **dev** (id-test, myschool-dev, myschool-dev2) | wekelijks of bij belangrijke milestones | 14d |

## Bacula-doelplaatje (TODO)

Bacula deploys nog niet uitgerold. Doelarchitectuur:

```
SRVV-BACULA-01 (director + storage)
   │
   ├── ansible@srvv-odoo-01    : daily backup om 02:00 (pre/post-script wrapt pg_dump + tar)
   ├── ansible@srvv-tst-odoo-01: daily 03:00
   ├── ansible@srvv-acc-01     : daily 04:00
   └── off-site sync naar NAS  : weekly
```

Pre/post-script-template voor Bacula:
```bash
# pre-backup: snapshot DB + filestore in /opt/.../backups/
# post-backup: cleanup oude lokale snapshots (Bacula heeft kopieën)
```

Volledige Bacula-architectuur + setup-procedure: zie [`platform-handbook/management-tools/bacula.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/bacula.md) (TODO bij Bacula-deploy).

## Testen van backup-integriteit

Backup zonder restore-test is geen backup. Maandelijks/per-quarter:

1. Pak een willekeurige backup-set (DB + filestore)
2. Restore in een test-DB op een dev-VM (bv. myschool-dev2)
3. Login, check een paar willekeurige records
4. Compare aantal records voor enkele tabellen (`ir.attachment`, hoofd-entiteiten) met productie

Logboek bijhouden: wie restoreerde wanneer welke backup-set, en wat de uitkomst was.

## Backup-secrets

- `db_password` zit in `odoo.conf` (oudere setup) of als Podman-secret `odoo-db-passwd` (nieuwere setup met `roles/odoo-podman/`)
- Voor restore op nieuwe VM: zorg dat het secret/odoo.conf met juist pw aanwezig is **vóór** restore
- Master `admin_passwd` (Odoo's super-admin voor DB-manager) staat hashed in odoo.conf — kan via ansible-vault opnieuw uitgerold worden

## Verwante docs

- [`platform-handbook/management-tools/bacula.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/bacula.md) — Bacula-architectuur (TBD)
- [`module-install.md`](module-install.md) — single-module install/upgrade
- `platform-ansible/roles/odoo-podman/` — Ansible-role voor Odoo-deploy (incl. DB-init)
