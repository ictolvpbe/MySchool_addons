# myschool_core

Fundament van het MySchool-platform. Definieert school-organisaties, personen, rollen, periodes en de gedeelde service-laag (LDAP, BeTask, Informat-sync). Alle andere `myschool_*` modules depend hierop.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `mail`, `hr` (Odoo standaard) |
| Productie-instances | myschool, myschool-ict, id, myschool-acc + alle test/dev |
| Documentatie in-module | `docs/employee_deactivation_flowchart.md` (deelflow) |

## Kern-entiteiten

(Op basis van models/-folder; volledig data-model TODO in [`../architecture/data-model.md`](../architecture/data-model.md))

| Entity | Doel |
|---|---|
| `Organization` | School-organisatie (top-level entiteit) |
| `OrgType` | Type school-organisatie |
| `Period` | Schooljaar / trimester / periode |
| `Person` | Persoon (uitgebreid op `res.partner`) |
| `Role` | Rol van persoon binnen org (leerkracht, leerling, ouder, admin, ...) |
| `BeTask` | Background-task framework (async processing) |
| `BeTaskType` | Type background-task |
| `ConfigItem` + `CIRelation` | CMDB-achtige config-tracking |
| `LdapServerConfig` + `LdapService` | LDAP-koppeling naar AD voor user-sync |
| `InformatService` + `InformatServiceConfig` + `InformatDto` | Sync met Informat (extern school-administratie-systeem) |
| `ManualTaskService` + `ManualTaskProcessor` | Manuele taken voor school-admins |
| `Process` + flow-chart entiteiten | Process-mapping infrastructuur (gebruikt door `process_mapper`) |

## Functionaliteit

### LDAP-bind tegen AD
- `LdapServerConfig`: stelt AD-DC + bind-credentials in
- `LdapService`: voert sync uit naar `Person`-records
- Verbinding via `ldap3` Python-package (external_dep in manifest)
- Cert-trust: CA-cert van AD wordt in container's CA-store geplaatst tijdens image-build

### Informat-sync
- Externe school-administratie-systeem (Informat) is bron-van-waarheid voor leerlingen + leerkrachten
- `InformatService` haalt periodiek nieuwe data op via XML-API
- Mapping naar `Person`/`Organization`/`Role` in Odoo

### BeTask-framework
- Long-running achtergrond-jobs (rapporten, syncs, bulk-operaties)
- Decouple van HTTP-requests; runs in cron of triggered
- Status-tracking + retry-policy + audit-log
- Wordt gebruikt door andere modules voor schaal-veilige operaties

## Configuratie

**Settings → Technical → MySchool Core**:
- LDAP-server-config (host, port, bind-DN, sync-frequentie)
- Informat-API-credentials
- BeTask-cron-instellingen

Per-organisatie config in `Organization`-form.

## Veelvoorkomende issues

- **LDAP-bind faalt** → check certs in container (`/etc/ssl/certs/`), check AD-DC bereikbaar (firewall VLAN → AD), check bind-DN+pw in `LdapServerConfig`
- **Informat-sync timeout** → BeTask-retry kicks in; check `BeTask` records met state=`failed`
- **Person-deduplicate** → er is `core/docs/employee_deactivation_flowchart.md` voor de deactivatie-flow; deduplicatie zelf is manueel via merge in UI

## Gerelateerde modules

- [`myschool_admin`](myschool_admin.md) — admin-UI bovenop core (TODO doc)
- [`myschool_sync`](myschool_sync.md) — master-slave-replicatie tussen MySchool-instances (TODO doc)
- [`myschool_appfoundry`](myschool_appfoundry.md) — project-management (TODO doc)
- [`myschool_dashboard`](myschool_dashboard.md) — taken-dashboard per gebruiker (TODO doc)

## Diepere docs

- [`../../myschool_core/docs/employee_deactivation_flowchart.md`](../../myschool_core/docs/employee_deactivation_flowchart.md) — deactivatie-flow voor werknemers
- (TODO: in-module README/USER_MANUAL/DEVELOPER nog niet geschreven; module heeft alleen partial doc)
