# myschool_servermanager — Server Manager

App om de MySchool Odoo-instances/servers te beheren: een centraal register,
samenstelbare rollen, en een data-locatie/privacy-matrix. Latere fasen voegen
enrollment en provisioning toe.

## Status

| Story | Onderwerp | Status |
|---|---|---|
| SRVMGR-2 | Server/Instance-register | ✅ klaar (commit `88e2186`) |
| SRVMGR-3 | Rollen samengesteld uit eigenschappen | ✅ klaar (commit `88e2186`) |
| SRVMGR-4 | Data-locatie & privacy | ✅ klaar (commit `671498a`) |
| SRVMGR-5 | Enrollment o.b.v. rol | ⏳ volgende (zie Roadmap) |
| SRVMGR-6 | Provisioning base-data + default user | 🔜 backlog |
| SRVMGR-7 | myschool_sync verhuizen uit myschool_admin | 🔜 backlog |

Backlog + tracking: AppFoundry-app **SRVMGR** (remote `myschool-ict.olvp.be`).

## Datamodel

```
myschool.server                 een Odoo-instance / server
 ├─ fqdn (uniek), ip_address, ssh_port, http_port, api_endpoint
 ├─ environment (prod/test/dev), db_name, instance_id, code (uniek)
 ├─ role_id            ──► myschool.server.role
 ├─ property_ids       (effectief, geërfd van de rol — computed)
 └─ data_location_ids  ──► myschool.server.data.location

myschool.server.role            typeert een server (account-server, webapps, …)
 └─ property_ids       ──► myschool.server.property   (m2m, samenstelbaar)

myschool.server.property        herbruikbare capability (host webapps, biedt API, …)
 └─ code (uniek), category, color

myschool.data.domain            categorie data (PII, bedrijven, org-structuur, …)
 └─ code (uniek), is_pii

myschool.server.data.location   lijn server × data-domein
 ├─ location           local | remote (via API)
 ├─ source_server_id   (verplicht & ≠ self bij remote)
 └─ endpoint           (optionele override)
 └─ uniek per (server, domein)
```

**Kerngedachte (SRVMGR-3):** een rol is *samengesteld uit eigenschappen*, geen
vaste enum. Wijzig je een eigenschap, dan erven alle rollen — en de servers met
die rol — de wijziging automatisch (gedeelde m2m + computed effective properties).

**Privacy (SRVMGR-4):** per server bepaal je per data-domein of de data lokaal
leeft of via API bij een bronserver opgehaald wordt. De `is_pii`-vlag maakt de
privacy-afweging expliciet en sluit aan op de geplande PII-classificatie.

## Menu's

- **Server Manager → Servers** — kanban (per environment) / list / form.
- **Server Manager → Data & Privacy** — de volledige locatie-matrix, gegroepeerd
  per server.
- **Configuration** (manager-only) → **Roles**, **Properties**, **Data Domains**.

## Security

Eén privilege-dropdown "Server access" (Odoo 19 `res.groups.privilege`):

- `group_servermanager_user` — leesrechten.
- `group_servermanager_manager` — volledige rechten.
- `myschool_core.group_myschool_core_admin` impliceert manager.

## Tests

```
odoo -d <testdb> -u myschool_servermanager \
     --test-enable --test-tags myschool_servermanager --stop-after-init
```

14 unit-tests (eigenschap-overerving + propagatie, unieke codes/FQDN,
poort-validatie, data-locatie-constraints, tellers).

> Lokaal draait de dev-server op poort 8069; gebruik voor een test-run een vrije
> poort, bv. `--http-port=8971 --gevent-port=8972`.

## Roadmap

- **SRVMGR-5 — Enrollment.** Standaard-instellingen per rol toepassen (taal,
  admin-password, apps). **Besloten uitvoeringsstrategie: Odoo JSON-RPC** —
  servermanager praat rechtstreeks met de remote instance. Vereist nog: veilige
  opslag van connectie-credentials per server + idempotente enroll-actie.
  Mogelijk: enrollment-settings koppelen aan rol-eigenschappen.
- **SRVMGR-6 — Provisioning.** Base-data (bedrijven/org/structuur) + default user
  seeden bij enrollment; herhaalbaar zonder duplicaten.
- **SRVMGR-7 — Sync verhuizen.** `myschool_sync`-beheer migreren vanuit
  `myschool_admin` naar deze app, gekoppeld aan het server-register; databehoud.
