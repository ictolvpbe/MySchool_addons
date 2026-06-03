# myschool_sync

Master-slave data-replicatie tussen MySchool Odoo-instances. Synchroniseert data van een centraal master-instance naar slave-instances (test, dev, externe scholen).

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `myschool_core`, `myschool_admin` |

## Doel

Gebruikssituaties:

- **Prod → test**: snapshot van productiedata naar test-omgeving voor user-acceptance-testing
- **Master → samenwerkingsscholen**: data delen tussen meerdere schoolinstanties van dezelfde overkoepelende organisatie
- **Selective sync**: niet alle records, configureerbaar per entity

## Architectuur

Vermoedelijk:

- Master-instance exposeert `sync`-endpoint
- Slave-instances pullen via cron of webhook
- Sync-state per record (last_synced_at, source_master_id)

(Exacte details TBD — geen in-module README aanwezig)

## Verschil met DB-restore

`myschool_sync` werkt op record-niveau (geselecteerde entities), terwijl DB-restore (zie [`../operations/backup-restore.md`](../operations/backup-restore.md)) een volledige DB-snapshot is. Sync is geschikt voor periodiek partial-refresh; restore voor full-restore na data-loss.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_core`](myschool_core.md) — fundament
- [`myschool_admin`](myschool_admin.md) — depends op deze
