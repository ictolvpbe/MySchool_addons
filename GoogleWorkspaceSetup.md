# Google Workspace — Configuratie & Connectie Test

Stap-voor-stap handleiding om een Google Workspace tenant aan MySchool te
koppelen via de `CLOUD/*` betask-pipeline.

> **Doelgroep:** systeembeheerder met super-admin toegang tot zowel
> Google Cloud Console als de Workspace Admin Console.

---

## 1. Voorwaarden

| Vereiste | Toelichting |
|---|---|
| GCP-project | Eén apart project per Workspace-tenant. Mag bestaand zijn. |
| Workspace super-admin account | Voor domain-wide delegation grants. Zelfde account wordt later het "impersonation subject". |
| Primary domain | Het hoofd-domein van je tenant (bv. `olvp.be`). |
| Python deps op Odoo-host | `google-api-python-client` en `google-auth` (zie §5). |
| MySchool module | `myschool_core` ≥ versie waarin Google Workspace modellen aanwezig zijn. |

---

## 2. Service Account aanmaken in GCP

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com) → kies/maak je project.
2. **APIs & Services → Library** → enable de volgende API's
   (alleen die welke je gaat gebruiken — meer kan altijd later):
   - Admin SDK API
   - Google Drive API *(optioneel — voor shared-drives)*
   - Google Classroom API *(optioneel)*
   - Enterprise License Manager API *(optioneel — voor licenties)*
3. **IAM & Admin → Service Accounts → Create Service Account**.
   - Name: `myschool-workspace-sync` (of vergelijkbaar)
   - Description: `Service account for MySchool ↔ Workspace betask sync`
4. Klaar — sla "Grant access" en "Grant users" stappen over (niet nodig).
5. Open de aangemaakte service account → tab **Details** → noteer
   het veld **Unique ID** (de "Client ID", een lang nummer). Heb je
   dadelijk nodig voor §4.
6. Tab **Keys → Add Key → Create new key → JSON** → download.
   Bewaar dit bestand veilig op de Odoo-host (bv.
   `/home/odoo/secrets/workspace-sync.json`, mode `0600`, eigenaar
   van het Odoo-proces).

---

## 3. Domain-Wide Delegation grant in Workspace

Het service account moet expliciet toestemming krijgen om gebruikers
in jouw tenant te mogen impersoneren.

1. Open [admin.google.com](https://admin.google.com) als super-admin.
2. **Security → Access and data control → API Controls → Manage
   Domain Wide Delegation** → `Add new`.
3. **Client ID** = het Unique ID uit §2 stap 5.
4. **OAuth scopes** = comma-separated lijst van wat je nodig hebt.
   Minimumset voor user/group/OU/device beheer:

   ```
   https://www.googleapis.com/auth/admin.directory.user,
   https://www.googleapis.com/auth/admin.directory.group,
   https://www.googleapis.com/auth/admin.directory.group.member,
   https://www.googleapis.com/auth/admin.directory.orgunit,
   https://www.googleapis.com/auth/admin.directory.device.chromeos
   ```

   Optionele extra's (alleen toevoegen indien nodig):

   ```
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/classroom.courses
   https://www.googleapis.com/auth/classroom.rosters
   https://www.googleapis.com/auth/apps.licensing
   ```

   > De scopes die je hier grant **moeten exact overeenkomen** met de
   > scopes die je in §6 in de MySchool-config aanvinkt. Een ontbrekende
   > grant veroorzaakt `403 unauthorized_client` bij de eerste call.

5. **Authorize**.
6. Wijzigingen kunnen tot 24u duren om volledig te propageren — maar
   in praktijk werkt het binnen enkele minuten.

---

## 4. Impersonation subject kiezen

Het service-account zelf kan geen API-calls doen — het delegeert naar
een gebruiker. Voor admin-scope calls moet die gebruiker een **super-
admin** zijn van het Workspace tenant.

Aanbeveling: maak één dedicated automation-account aan
(`automation@<jouw-domein>`) met super-admin role, in plaats van
een persoonlijke admin te gebruiken. Voordelen:
- Scheidt audit-logs van menselijke admin-acties
- Overleeft personeelswisselingen
- Kan strakkere groep- en password-policies hebben

Noteer het email-adres — dat wordt het `subject_email` veld in §6.

---

## 5. Python dependencies op de Odoo-host

In de venv die Odoo gebruikt:

```bash
# Pas het pad aan naar jouw venv
~/PyCharm/odoo-myschool/.venv/bin/pip install \
    google-api-python-client google-auth
```

Verifieer:

```bash
~/PyCharm/odoo-myschool/.venv/bin/python -c "
from google.oauth2 import service_account
from googleapiclient.discovery import build
print('OK')
"
```

> **Niet zeker welke venv Odoo gebruikt?** Start Odoo en check
> `ps -ef | grep odoo-bin` — de gebruikte python-binary staat als
> eerste argument.

---

## 6. MySchool module installeren / upgraden

### 6.1 Eerste install

```bash
~/PyCharm/odoo-myschool/.venv/bin/python \
    ~/PyCharm/odoo-myschool/odoo/odoo-bin \
    -c ~/PyCharm/odoo-myschool/config/odoo.conf \
    -d odoo-dev \
    -i myschool_core \
    --stop-after-init
```

### 6.2 Bestaande install upgraden

```bash
~/PyCharm/odoo-myschool/.venv/bin/python \
    ~/PyCharm/odoo-myschool/odoo/odoo-bin \
    -c ~/PyCharm/odoo-myschool/config/odoo.conf \
    -d odoo-dev \
    -u myschool_core \
    --stop-after-init
```

Verifieer dat de nieuwe tabel bestaat:

```bash
PGPASSWORD=<jouw-pw> psql -h localhost -U myschool -d odoo-dev -tAc "
SELECT count(*) FROM myschool_google_workspace_config;
"
# Moet 0 (of meer) returnen — niet meer 'relation does not exist'.
```

---

## 7. Workspace Config record aanmaken

### 7.1 Via de UI (aanbevolen)

1. Start Odoo, log in als admin.
2. Ga naar de Settings (volgens jouw menu-structuur). De form view
   bevat alle nodige velden.

   > Tip: als er nog geen menu-ingang is, navigeer rechtstreeks naar
   > `/odoo/action-myschool_core.action_google_workspace_config` —
   > of voeg de menu-entry toe in `myschool_admin/views/menu_views.xml`.

3. Vul in:
   - **Name**: bv. `OLVP Workspace`
   - **Primary Domain**: `olvp.be`
   - **Customer ID**: laat `my_customer` staan (correct voor
     single-tenant setups)
   - **Impersonation Subject**: `automation@olvp.be` (uit §4)
   - **Service Account JSON Path**: `/home/odoo/secrets/workspace-sync.json`
     (uit §2 stap 6)
   - **Sequence**: 10
   - **Active**: aan

4. Tab **Scopes** — vink aan wat je in §3 stap 4 hebt gegrant.
   Minimumset: alle 4 onder *Directory API*.

5. Tab **Organizations** — laat eerst leeg. De `get_server_for_org`
   resolver valt terug op de single active config wanneer geen
   expliciete koppeling bestaat. Pas wanneer je meerdere tenants hebt
   (bv. één per koepel) wijs je orgs expliciet toe.

6. **Save**.

### 7.2 Via SQL (alleen voor scripted setups)

Niet aanbevolen — gebruikt geen scope-validatie en mist de
single-active constraint. Gebruik de UI of de Odoo shell.

---

## 8. Connectie testen

In de form view: knop **Test Connection** (boven in de header).

Wat de knop doet (zie `google_directory_service.py:test_connection`):
1. Bouwt credentials uit het JSON-bestand
2. Past delegated `subject_email` toe
3. Activeert de geselecteerde scopes
4. Doet één call: `users.list(customer='my_customer', maxResults=1)`

### 8.1 Mogelijke uitkomsten

| Resultaat | Betekenis |
|---|---|
| `Bind OK — listed 1 user(s) on customer=my_customer` | Volledig OK. |
| `Bind OK — listed 0 user(s) ...` | Werkt, maar tenant is leeg. Niet abnormaal voor test-tenants. |
| `Service-account key file not found: /…` | Pad fout, of permissies te strak voor de odoo-user. Check `ls -l` en `chown`. |
| `Workspace config "X" has no scopes enabled` | Geen enkele scope aangevinkt in tab Scopes. |
| `HTTP 401 / unauthorized_client` | Domain-Wide Delegation niet (correct) gegrant in §3. Vaakste oorzaak: Client ID matcht niet, of scopes ontbreken. |
| `HTTP 403 / Not Authorized to access this resource` | Subject is geen super-admin (of OU-admin zonder de juiste rechten). |
| `HTTP 403 / accessDenied` op een specifieke API | API niet enabled in GCP project (§2 stap 2). |
| `HTTP 400 / invalid_grant: account not found` | `subject_email` typfout, of subject is in een suspended/deleted state. |

### 8.2 Diagnostiek

De config-record zelf onthoudt het laatste resultaat:

```sql
SELECT name, last_test_date, last_test_result, last_test_message
FROM myschool_google_workspace_config
ORDER BY id DESC LIMIT 1;
```

Voor diepere diagnostiek: zet `log_level = debug` in `odoo.conf`,
herhaal de test, en bekijk de Odoo-log. De service logt de exacte
`HttpError.content` wanneer Google een fout teruggeeft.

---

## 9. Eerste echte calls — manueel testen

Nadat *Test Connection* groen is, kan je de pipeline testen door
manueel een betask te queuen:

### 9.1 Dry-run user-create

In de Odoo shell:

```python
person = env['myschool.person'].browse(<id>)
org = env['myschool.org'].browse(<id>)  # PERSON-TREE org
cfg = env['myschool.google.workspace.config'].search([('active', '=', True)], limit=1)
svc = env['myschool.google.directory.service']
svc.create_user(cfg, person, org, dry_run=True)
# → toont gegenereerde primaryEmail + ouPath + (geredacteerd) password
```

### 9.2 Echte create via de betask-pipeline

```python
env['myschool.betask.service'].create_task('CLOUD', 'USER', 'ADD', data={
    'person_id': <person_id>,
    'dry_run': False,
})
env.cr.commit()
# Wacht op de cron of run direct:
env['myschool.betask.processor'].cron_process_tasks()
```

Controleer daarna in `myschool_betask` (kolom `changes`) wat er is
gebeurd.

### 9.3 Apparaat-move test

```python
env['myschool.betask.service'].create_task('CLOUD', 'DEVICE', 'MOVE', data={
    'target_org_id': <doel_org_id>,
    'device_ids': ['<google-device-id>'],
    'dry_run': True,  # eerst droogtrekken
})
```

---

## 10. Cron-activering

| Cron | Default | Wanneer activeren |
|---|---|---|
| `Cloud: Sync ChromeOS Inventory` | **Inactief** | Pas wanneer minstens één `myschool.asset` rij `serial_number` heeft. Anders draait de cron alleen om "no match" te loggen. Activeer via **Settings → Technical → Scheduled Actions**. |
| `Employee Account Lifecycle` | Actief | Doet automatisch `CLOUD/USER/DEACT` (suspend bij EmployeeSuspendPeriod-elapse) en `CLOUD/USER/DEL` (na EmployeeDeletePeriod). Kan nu draaien met de nieuwe handlers. |
| `Backend Tasks: Process Pending` | Actief | Verwerkt elke 15 min de queue, inclusief `CLOUD/*` types. |

---

## 11. Wat er automatisch cascadet (na §7+8)

Wanneer er een actieve Workspace-config staat, **én** de school
LDAP-flag-aan heeft (`has_ou`), dan queuet MySchool automatisch:

| Trigger | LDAP betask | CLOUD betask |
|---|---|---|
| Nieuwe PPSBR (sync of manual) | `LDAP/USER/ADD` | `CLOUD/USER/ADD` |
| Persongroep-membership | `LDAP/GROUPMEMBER/ADD` | `CLOUD/GROUPMEMBER/ADD` *(alleen COM-kant + persoon heeft `email_cloud`)* |
| Nieuwe persongroep org | `LDAP/ORG/ADD` (= AD group) | `CLOUD/GROUP/ADD` |
| Nieuwe gewone org | `LDAP/ORG/ADD` (= OU) | `CLOUD/ORG/ADD` |
| Lifecycle Phase 1 (suspend) | `LDAP/USER/DEL` | `CLOUD/USER/DEACT` |
| Lifecycle Phase 2 (delete) | — | `CLOUD/USER/DEL` |

De cascade is **additief** — als geen Workspace-config bestaat,
wordt geen enkele CLOUD-task gequeued en blijft de bestaande
LDAP-flow ongewijzigd.

---

## 12. Wachtwoord-synchronisatie tussen AD en Google

`process_cloud_user_add` en `process_cloud_user_pwd` lezen
`myschool.person.password` (plaintext, hetzelfde veld als LDAP) en
sturen het als SHA-1 hex naar Google met `hashFunction='SHA-1'`.

Wanneer het veld leeg is, of niet voldoet aan AD-complexiteit,
wordt een nieuw wachtwoord gegenereerd via
`ldap_service._generate_ad_complex_password()` en teruggeschreven —
zodat AD en Google dezelfde plaintext gebruiken.

> Dit kan alleen werken **vóór** AD het wachtwoord rota. Als een AD-
> reset extern gebeurt (gebruiker zelf, of GPO-policy) dan loopt
> Google uit sync. Voor een "ene reset triggert beide" workflow:
> queue zowel `LDAP/USER/UPD` (met nieuw `person.password`) als
> `CLOUD/USER/PWD` met dezelfde `person_id`.

---

## 13. Veelvoorkomende valkuilen

| Symptoom | Oorzaak | Fix |
|---|---|---|
| Test Connection werkt, maar `CLOUD/USER/ADD` faalt met `Cannot resolve primaryEmail` | `org.domain_internal` is niet gezet op enige ancestor | Vul `domain_internal` op de SCHOOL of zet `domain` in de Workspace config als fallback |
| `403 Not Authorized` op één specifieke API | Scope niet aangevinkt in MySchool config tab Scopes | Vink aan + save (geen restart nodig) |
| `409 entityExists` bij re-run van USER/ADD | Geen — handler is idempotent en logt "already exists" | Gewenst gedrag, geen actie nodig |
| OU wordt aangemaakt onder `/olvp/olvp/...` ipv `/olvp/...` | `name_tree` heeft de domain-head als prefix | Service heeft een `domain_head` strip in `org_to_google_path`. Controleer dat config.domain begint met de juiste head. |
| Suspended user kan na een `CLOUD/USER/UPD` weer inloggen | `users.patch` overschrijft `suspended` niet als je hem niet meegeeft, maar bepaalde body-keys reactiveren impliciet | Gebruik altijd een aparte `CLOUD/USER/DEACT` om de suspend-flag te zetten — niet smokkelen via UPD |

---

## 14. Rollback / verwijderen

Om een config-koppeling te verwijderen zonder data-verlies:

1. Zet de config-record op `Active = False` (via UI). De
   `_cloud_provisioning_enabled()` guard schakelt dan elke nieuwe
   CLOUD-task uit.
2. Pending CLOUD/* betasks blijven bestaan — zet ze handmatig op
   `error` of laat ze draaien (ze faalt netjes als geen actieve
   config).
3. Als je het tenant écht wil ontkoppelen: revoke de Domain-Wide
   Delegation in §3, of disable/delete het service-account in §2.
   De JSON-key wordt daarmee waardeloos.

---

## 15. Snelle checklist

- [ ] §2 GCP service account aangemaakt + Unique ID genoteerd
- [ ] §2 stap 6 JSON-key gedownload + veilig opgeslagen
- [ ] §2 stap 2 Admin SDK API enabled (+ optionele extra's)
- [ ] §3 Domain-Wide Delegation grant met juiste scopes
- [ ] §4 Impersonation subject (super-admin) gekozen
- [ ] §5 `google-api-python-client` + `google-auth` in venv
- [ ] §6 `myschool_core` upgrade uitgevoerd
- [ ] §7 Workspace config record aangemaakt + active
- [ ] §8 Test Connection groen
- [ ] §9 Dry-run `CLOUD/USER/ADD` succesvol
- [ ] §9 Echte `CLOUD/USER/ADD` succesvol
- [ ] §10 Cron-status nagekeken (lifecycle aan, ChromeOS-sync optioneel)
