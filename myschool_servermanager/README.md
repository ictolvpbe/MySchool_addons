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
| SRVMGR-5 | Enrollment o.b.v. rol | ✅ klaar (zie Enrollment) |
| SRVMGR-6 | Provisioning base-data + default user | ✅ klaar (zie Provisioning) |
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

## Enrollment (SRVMGR-5)

Servermanager past de standaard-instellingen van de **rol** idempotent toe op een
remote instance via de **Odoo externe API** (`/jsonrpc`).

- **Credentials** staan per server (manager-only): `login`, `api_key`, +
  `use_https`/poort/`api_endpoint` voor de URL. **Test Connection** controleert de
  authenticatie en zet `connection_state`.
- **Wat wordt toegepast** (afgeleid van de rol):
  - *Taal* — `role.enroll_lang` (bv. `nl_BE`): wordt geactiveerd indien aanwezig.
  - *Modules* — de unie van `property.module_names` over de eigenschappen van de rol
    (`role.enroll_module_names`). Enkel modules die nog niet geïnstalleerd zijn worden
    geïnstalleerd → **opnieuw draaien is veilig**.
  - *Admin-wachtwoord* — optioneel veld `target_admin_password` (set-once): wordt
    gezet en daarna gewist.
- Resultaat: `enrollment_state` (pending/done/error), `last_enrolled` en een
  `enrollment_log`; elke run logt ook naar de chatter.
- Alle netwerk-IO loopt door één methode `_jsonrpc` → in tests volledig gemockt
  (geen echte remote nodig).

> **Security-afweging:** `api_key`/`target_admin_password` zijn velden met
> `groups=`-restrictie (manager-only) + password-widget. Een echte secrets-vault is
> een latere verbetering.

## Provisioning (SRVMGR-6)

Naast enrollment voorziet servermanager een (verse) instance van **base-data** en
**default-gebruikers** — idempotent en via dezelfde `_jsonrpc`-laag. Knop
**Provision** op de server-form.

- **Companies** — een **company-boom** per server (`provision_company_ids`): één
  knoop kan `is_main` zijn (hernoemt de bestaande hoofd-company van de remote, géén
  nieuwe), de overige knopen zijn **sub-companies** die via `parent_id` naar een
  andere knoop verwijzen. Bij provisioning worden parents vóór kinderen verwerkt en
  wordt op naam gematcht: bestaat een company al, dan wordt ze overgeslagen → opnieuw
  draaien is veilig. (Constraints: max. één hoofd-company per server, geen lus,
  parent bij dezelfde server.)
- **Default users** — een sjabloon op de **rol** (`provision_user_ids`): per
  gebruiker `name`/`login`/`email`/`lang`/`password` (set-once, manager-only) +
  `is_admin`. Per login gematcht op de remote: bestaat de login al, dan wordt de
  gebruiker **overgeslagen** (geen duplicaten, geen wachtwoord-overschrijving).
  Nieuwe gebruikers krijgen `base.group_user`, admins ook `base.group_system`.
- Resultaat: `provision_state` (pending/done/error), `last_provisioned` en een
  `provision_log`; elke run logt naar de chatter.

> **Scope-afbakening:** de MySchool **org/structuur**-masterdata (org-boom) wordt
> *niet* hier gekopieerd — dat is master→slave-replicatie en hoort bij
> `myschool_sync` (SRVMGR-7), aansluitend op de data-locatie-keuze (SRVMGR-4).
> SRVMGR-6 voorziet de instance-identiteit (company) + toegang (default users).

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

33 unit-tests (eigenschap-overerving + propagatie, unieke codes/FQDN,
poort-validatie, data-locatie-constraints, tellers, de enrollment-laag met
gemockte JSON-RPC: connectie, idempotente module-install, taal, admin-pw, en de
provisioning-laag: hoofd-company-rename/idempotentie, sub-company-boom incl.
diepe hiërarchie parents-eerst, skip bij bestaande company, default-user-creatie
+ groepen, skip bij bestaande login, herhaalbaarheid).

> Lokaal draait de dev-server op poort 8069; gebruik voor een test-run een vrije
> poort, bv. `--http-port=8971 --gevent-port=8972`.

## Roadmap

- **SRVMGR-7 — Sync verhuizen.** `myschool_sync`-beheer migreren vanuit
  `myschool_admin` naar deze app, gekoppeld aan het server-register; databehoud.
  Brengt ook de org/structuur-masterdata-replicatie (de "structuur" uit de
  userstory) onder, aansluitend op de data-locatie-keuze (SRVMGR-4).
