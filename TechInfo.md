# MySchool Account Workflow — Technical Reference

## 1. Account Lifecycle Overview

Accounts worden beheerd via twee paden die beide door de **betask-pipeline** lopen:

| Pad | Trigger | Betask Target | Processor |
|-----|---------|---------------|-----------|
| SAP Sync (automatisch) | Cron / Informat API | `DB` | `betask_processor.py` |
| Object Manager (manueel) | Admin UI / wizard | `MANUAL` | `manual_task_processor.py` |

Beide paden produceren dezelfde downstream-effecten: tree-positie, groepslidmaatschap, en accountcreatie.

---

## 2. Betask Pipeline Architectuur

### Kernbestanden

| Bestand | Doel |
|---------|------|
| `myschool_core/models/betask.py` | BeTask model (status, data, retry) |
| `myschool_core/models/betask_type.py` | BeTaskType (target × object × action) |
| `myschool_core/models/betask_service.py` | Service layer (find, create) |
| `myschool_core/models/betask_processor.py` | Hoofdprocessor (~5700 regels) |
| `myschool_core/models/manual_task_service.py` | Service voor MANUAL betasks |
| `myschool_core/models/manual_task_processor.py` | Processor voor MANUAL betasks |

### BeTaskType dimensies

- **target**: `DB`, `ODOO`, `LDAP`, `AD`, `CLOUD`, `API`, `EMAIL`, `ALL`, `MANUAL`
- **object**: `ORG`, `PERSON`, `GROUPMEMBER`, `STUDENT`, `EMPLOYEE`, `ROLE`, `PERIOD`, `PROPRELATION`, `RELATION`, `COM_EMAIL`, `COM_ADDRESS`, `COM_PHONE`, `USER`, `GROUP`, `CONFIG`
- **action**: `ADD`, `UPD`, `DEL`, `REMOVE`, `DEACT`, `ARC`, `SYNC`

### Betask statussen

`new` → `processing` → `completed_ok` | `error`

### Cron jobs

- **Processor**: elke 15 min → `cron_process_tasks()`
- **Cleanup**: dagelijks → archiveer completed tasks ouder dan 30 dagen
- **Account lifecycle**: dagelijks → `cron_employee_account_lifecycle()`

---

## 2b. Groepsnaam & FQDN Constructie (geünificeerd)

### Groepsnaam-algoritme (autoritatief)

Eén algoritme voor zowel `org.py:_compute_and_write_group_fields` als `manual_task_processor.py:_build_org_tree_group_names`:

```
1. Start met org.name_short (lowercase)
2. Loop ORG-TREE proprelaties omhoog naar root
3. Skip administratieve orgs (is_administrative=True)
4. Skip SCHOOLBOARD org types
5. Voeg name_short van elke niet-geskipte org toe
6. Join met '-', prefix met 'grp-' (COM) of 'bgrp-' (SEC)
```

**Voorbeeld**: `school(baple) → pers → adm` → `grp-adm-pers-baple` / `bgrp-adm-pers-baple`

### FQDN-constructie voor groepen

Groepen leven onder OuForGroups van de **school** (niet de directe parent):

```
com_group_fqdn = cn={group_name},ou={OuForGroups},{school.ou_fqdn}
```

**Voorbeeld**: `cn=grp-adm-pers-baple,ou=groups,ou=baple,dc=olvp,dc=int`

Consistent in:
- `org.py:_compute_and_write_group_fields` — schrijft naar org record
- `betask_processor.py:_find_or_create_persongroup` — schrijft naar persongroup record

---

## 3. PropRelation Types (scharnierpunten)

| Type | Doel | Sleutelvelden |
|------|------|---------------|
| `PPSBR` | Person-Period-School-BackendRole | id_person, id_role, id_org (classgroup), id_org_parent (school), id_period |
| `BRSO` | BackendRole-SchoolOrg mapping | id_role, id_org (target OU), id_org_parent (school) + has_accounts, has_ldap_com_group, has_ldap_sec_group, has_odoo_group |
| `PERSON-TREE` | Persoon → Org positie in tree | id_person, id_org, id_role |
| `ORG-TREE` | Org → Parent org hiërarchie | id_org, id_org_parent |
| `SR-BR` | SapRole → BackendRole mapping | id_role_child (sap), id_role_parent (backend) |
| `PG-P` | Persongroup-Person membership | id_org (persongroup), id_person |

### BRSO als scharnierpunt

```
BRSO: role=ICT, org=int.olvp.bawa.ict, school=BAWA
  ├── has_accounts=True    → bepaalt PERSON-TREE locatie (target OU)
  ├── has_ldap_com_group   → LDAP communicatiegroep
  ├── has_ldap_sec_group   → LDAP beveiligingsgroep
  └── has_odoo_group       → Odoo security group
```

---

## 4. Tree-positie bepaling (`_update_person_tree_position`)

**Locatie**: `betask_processor.py`, methode `_update_person_tree_position(person)`

### Algoritme

1. Zoek alle actieve PPSBR voor de persoon
2. Als een PPSBR `is_master=True` → gebruik die direct
3. Anders: groepeer per rol, selecteer hoogste prioriteit (laagste getal)
4. Zoek BRSO voor geselecteerde rol + school → `id_org` is de target OU
5. Fallback: gebruik `id_org` uit PPSBR zelf (bv. classgroup voor studenten)
6. Resolve administratieve orgs naar niet-admin parent
7. Maak/update PERSON-TREE proprelation
8. Vul account-velden aan (`_populate_person_account_fields`)

### Account-velden

```python
email_cloud = f"{clean_first}.{clean_last}@{domain_external}"
person_fqdn_internal = f"cn={email_account},{target_org.ou_fqdn_internal}"
person_fqdn_external = f"cn={email_account},{target_org.ou_fqdn_external}"
```

---

## 5. Groepssynchronisatie

### Odoo groepen (`_sync_person_group_memberships`)

**Locatie**: `betask_processor.py`, lijn ~4691

1. Verzamel alle actieve PPSBR → rollen met `has_odoo_group=True`
2. Vergelijk met huidige `user.group_ids` (enkel managed groups)
3. `ODOO/GROUPMEMBER/ADD` voor ontbrekende groepen
4. `ODOO/GROUPMEMBER/REMOVE` voor overbodige groepen

### Persongroepen (`_sync_persongroup_memberships`)

**Locatie**: `betask_processor.py`, lijn ~5551

1. Org-based: als PERSON-TREE org `has_comgroup=True` → sync die org's persongroup
2. Role-based: voor elke actieve rol met `has_group=True` → sync rol-persongroups

### Groepsverwijdering (`_remove_user_from_all_role_groups`)

**Locatie**: `betask_processor.py`, lijn ~4791

Verwijdert user uit alle groepen die door rollen beheerd worden. Wordt aangeroepen bij deactivatie/verwijdering.

---

## 6. Account Lifecycle (dagelijkse cron)

**Methode**: `cron_employee_account_lifecycle()` in `betask_processor.py`

### 3-fasen model

| Fase | Timing | Actie |
|------|--------|-------|
| Fase 0 | Direct | Scan actieve employees zonder deactivation_date; als geen actieve assignments → set deactivation_date + deactiveer proprelations |
| Fase 1 | Na `EmployeeAccountDeactivationDays` (default 30d) | `person.is_active = False` → cascade: Odoo user + HR employee + proprelations |
| Fase 2 | Na `EmployeeAccountRemovalDays` (default 90d) | Verwijder HR employee + Odoo user records (person blijft) |

### Cascade bij deactivatie

`person.write({'is_active': False})` triggert `_on_deactivate()` in `person.py`:
- Deactiveert `odoo_user_id` (res.users)
- Deactiveert `odoo_employee_id` (hr.employee)
- Deactiveert alle proprelations via `_deactivate_proprelations()`

---

## 7. MANUAL Betask Handlers (manual_task_processor.py)

### Beschikbare handlers

| Handler | Betask | Downstream effecten |
|---------|--------|---------------------|
| `process_manual_person_add` | MANUAL/PERSON/ADD | Maak person + PERSON-TREE + groepssync |
| `process_manual_person_upd` | MANUAL/PERSON/UPD | Update velden OF verplaats (PERSON-TREE + FQDN + groepssync) |
| `process_manual_person_deact` | MANUAL/PERSON/DEACT | Groepsverwijdering → `_on_deactivate()` cascade |
| `process_manual_person_del` | MANUAL/PERSON/DEL | Account cleanup (user+employee) → proprelations → person delete |
| `process_manual_org_add` | MANUAL/ORG/ADD | Org + ORG-TREE + persongroup sync |
| `process_manual_org_upd` | MANUAL/ORG/UPD | Verplaats (ORG-TREE + FQDN + name_tree) |
| `process_manual_org_del` | MANUAL/ORG/DEL | Proprelations → tree_org_id cleanup → org delete |
| `process_manual_proprelation_add` | MANUAL/PROPRELATION/ADD | Maak proprelation + voor PPSBR: tree-herberekening + groepssync |
| `process_manual_proprelation_upd` | MANUAL/PROPRELATION/UPD | Update velden |
| `process_manual_proprelation_deact` | MANUAL/PROPRELATION/DEACT | Deactiveer + voor PPSBR: tree-herberekening + groepssync |

### Aanroepen vanuit admin UI

```python
# Via manual_task_service
service = self.env['myschool.manual.task.service']
service.create_manual_task('PERSON', 'ADD', {
    'first_name': 'Jan',
    'name': 'Janssens',
    'org_id': org.id,
    'person_type_name': 'EMPLOYEE',
    'create_user': True,
    'user_login': 'jan.janssens@school.be',
    'create_employee': True,
})
```

### Processing modes

Gestuurd door `ir.config_parameter` → `myschool.manual_task_mode`:
- `'immediate'` (default): verwerkt in dezelfde request
- `'queued'`: wacht op batch-verwerking

---

## 8. Rolwijziging Flow

Bij rolwijziging (bv. TEACHER → ICT) via PPSBR add/deact:

```
1. PPSBR wijziging
   ↓
2. _update_person_tree_position(person)
   ├── Herbereken hoogste-prioriteit PPSBR
   ├── Zoek BRSO voor nieuwe rol → nieuwe target OU
   ├── Update PERSON-TREE (persoon verhuist in tree)
   └── Herbereken FQDN (cn=... wijzigt)
   ↓
3. _sync_person_group_memberships(person)
   ├── REMOVE uit oude rol-groep (bv. group_myschool_teacher)
   └── ADD aan nieuwe rol-groep (bv. group_myschool_ict)
   ↓
4. _sync_persongroup_memberships(person)
   ├── Verwijder uit persongroups van oude org/rol
   └── Voeg toe aan persongroups van nieuwe org/rol
```

---

## 9. Odoo Security Groups

**Definitie**: `myschool_core/security/myschool_security.xml`

| Groep | Implied |
|-------|---------|
| `group_myschool_core_user` | base.group_user |
| `group_myschool_core_admin` | group_myschool_core_user |
| `group_myschool_employee` | group_myschool_core_user |
| `group_myschool_teacher` | group_myschool_employee |
| `group_myschool_ict` | group_myschool_employee |
| `group_myschool_accounting` | group_myschool_employee |
| `group_myschool_student` | base.group_user |
| `group_myschool_relation` | base.group_user |

Rol-koppeling via `myschool.role`:
- `has_odoo_group=True` + `odoo_group_id` → employees met deze rol worden automatisch aan de groep toegevoegd

---

## 10. SAP Sync Flow (automatisch pad)

**Entry point**: `informat_service.execute_sync()` (cron of manueel)

```
Informat API → Fetch employees/students/roles/classes
  ↓
DB_EMPLOYEE_ADD / DB_STUDENT_ADD / DB_ROLE_ADD betasks
  ↓
betask_processor.py verwerkt:
  1. Person record aanmaken/updaten
  2. PPSBR proprelation aanmaken
  3. _update_person_tree_position() → PERSON-TREE + FQDN
  4. ODOO_PERSON_ADD betask (als actieve assignments)
  5. _sync_person_group_memberships() + _sync_persongroup_memberships()
  ↓
(optioneel) myschool_sync → API_*_SYNC betasks → slave instances
```

---

## 11. Master-Slave Sync (myschool_sync)

**Architectuur**: Eenrichtingsreplicatie master → slave via JSON-RPC.

### Gesynchroniseerde modellen (prioriteitsvolgorde)

| Prio | Model | Natural Key |
|------|-------|-------------|
| 10 | org.type, person.type, role.type, period.type, proprelation.type | name |
| 20 | myschool.period | name |
| 30 | myschool.org | sync_uuid |
| 30 | myschool.role | shortname |
| 40 | myschool.person | sap_person_uuid |
| 50 | myschool.proprelation | name |

### Sync flow

```
DB/MANUAL task completed
  → SyncEmitter._maybe_emit_sync_task()
  → API_*_SYNC betask aangemaakt
  → SyncProcessor verwerkt
  → SyncSerializer serialiseert record
  → SyncDispatcher POST naar /myschool_sync/receive
  → SyncResolver op slave: resolve natural key → create/update/skip
```

### Configuratie

- `ir.config_parameter` → `myschool.sync_role`: 'disabled' | 'master' | 'slave' | 'both'
- `ir.config_parameter` → `myschool.sync_api_key`: gedeeld geheim
- `sync.target` model: per-model toggles, school filter, status tracking

---

## 12. Kernmodellen Quick Reference

### myschool.person

| Veld | Type | Doel |
|------|------|------|
| name | Char | Achternaam (of "Achternaam, Voornaam") |
| first_name | Char | Voornaam |
| email_cloud | Char | Cloud e-mail (account@domain) |
| email_private | Char | Privé e-mail |
| odoo_user_id | M2O → res.users | Gekoppeld Odoo account |
| odoo_employee_id | M2O → hr.employee | Gekoppeld HR record |
| has_odoo_account | Computed Boolean | Heeft Odoo account |
| is_active | Boolean | Actief (write triggert _on_deactivate/_on_reactivate) |
| deactivation_date | Date | Datum waarop alle actieve assignments eindigden |
| person_fqdn_internal | Char | LDAP DN intern |
| person_fqdn_external | Char | LDAP DN extern |
| tree_org_id | Computed M2O → myschool.org | Huidige positie in tree |
| automatic_sync | Boolean | Beheerd door SAP sync |

### myschool.role

| Veld | Type | Doel |
|------|------|------|
| name | Char | Systeemnaam (EMPLOYEE, TEACHER, ICT, etc.) |
| priority | Integer | Bepaalt tree-positie (laagste getal = hoogste prioriteit) |
| has_accounts | Boolean | Vereist account-creatie in AD |
| has_group | Boolean | Vereist persongroup per school |
| has_odoo_group | Boolean | Koppelt aan Odoo security group |
| odoo_group_id | M2O → res.groups | Gekoppelde Odoo groep |
| has_ui_access | Boolean | Geeft UI toegang |

### myschool.org

| Veld | Type | Doel |
|------|------|------|
| name / name_short | Char | Volledige en korte naam |
| name_tree | Char | Volledig pad (bv. int.olvp.bawa.pers) |
| ou_fqdn_internal/external | Char | LDAP OU distinguished name |
| has_accounts | Boolean | Flag vanuit BRSO |
| has_comgroup / has_secgroup | Boolean | Persongroup flags |
| com_group_name / sec_group_name | Char | Groepsnamen |
| is_administrative | Boolean | Admin org (wordt geresolvet naar parent) |
| domain_internal / domain_external | Char | AD domeinen |

### myschool.proprelation

| Veld | Type | Doel |
|------|------|------|
| proprelation_type_id | M2O | Type (PPSBR, BRSO, PERSON-TREE, etc.) |
| name | Char | Gestandaardiseerd: "TYPE:Ro=X,Or=Y,Pn=Z" |
| id_person, id_org, id_role, id_period | M2O | Entiteitverwijzingen |
| id_*_parent, id_*_child | M2O | Hiërarchische verwijzingen |
| is_master | Boolean | Override voor tree-positie |
| has_accounts, has_ldap_com_group, has_ldap_sec_group, has_odoo_group | Boolean | Feature flags (BRSO) |
| is_active | Boolean | Actief/gedeactiveerd |
| automatic_sync | Boolean | Beheerd door sync |

---

## 13. Object Browser (myschool_admin)

**Backend**: `myschool_admin/models/object_browser.py` (~12000 regels)
**Frontend**: `myschool_admin/static/src/js/object_browser.js` (~1500 regels)
**Wizards**: `myschool_admin/models/wizards.py` (~3200 regels)

### Context menu acties → betask mapping

| UI Actie | Wizard | Betask |
|----------|--------|--------|
| Create Person | CreatePersonWizard | MANUAL/PERSON/ADD |
| Move Person | MovePersonWizard | MANUAL/PERSON/UPD |
| Deactivate Person | (direct) | MANUAL/PERSON/DEACT |
| Delete Person | (direct) | MANUAL/PERSON/DEL |
| Add Sub-Org | AddChildOrgWizard | MANUAL/ORG/ADD |
| Move Org | MoveOrgWizard | MANUAL/ORG/UPD |
| Delete Org | (direct) | MANUAL/ORG/DEL |
| Manage Person Roles | ManagePersonRolesWizard | MANUAL/PROPRELATION/ADD + DEACT |
| Manage Org Roles | ManageOrgRolesWizard | MANUAL/PROPRELATION/ADD + DEACT |
| Password | PasswordWizard | MANUAL/PERSON/UPD |
