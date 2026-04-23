# Account Lifecycle Process

Dit document beschrijft het volledige account-lifecycle proces in MySchool.
Elk account doorloopt dezelfde stappen, ongeacht of het via SAP sync of manueel wordt beheerd.

---

## Overzicht

```
               SAP Sync (automatisch)              Object Manager (manueel)
               ────────────────────                ────────────────────────
               Informat API → cron                 Admin UI → wizard
                       │                                    │
                       ▼                                    ▼
                  DB betask                           MANUAL betask
                       │                                    │
                       └────────────┬───────────────────────┘
                                    ▼
                            Betask Processor
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              PERSON-TREE     Odoo Account     Groepssync
              (tree-positie)  (user+employee)  (Odoo+LDAP+persongroups)
```

Alle bewerkingen lopen via de betask-pipeline en produceren dezelfde downstream-effecten.

---

## 1. Account Aanmaken

### Trigger

| Pad | Trigger | Betask |
|-----|---------|--------|
| SAP Sync | Informat API levert nieuwe employee | `DB/EMPLOYEE/ADD` |
| Object Manager | Admin maakt persoon aan via CreatePersonWizard | `MANUAL/PERSON/ADD` |

### Processtappen

```
1. PERSON RECORD
   ├── Maak myschool.person record aan
   ├── Velden: name, first_name, email_cloud, email_private, person_type_id
   └── SAP sync vult ook: sap_ref, sap_person_uuid, person_details

2. PPSBR PROPRELATION (indien van toepassing)
   ├── Koppelt Person ↔ Role ↔ Org (classgroup/school) ↔ Period
   ├── SAP sync: automatisch via DB/PROPRELATION/ADD
   └── Manueel: via ManagePersonRolesWizard → MANUAL/PROPRELATION/ADD

3. TREE-POSITIE BEPALEN → _update_person_tree_position(person)
   ├── Zoek alle actieve PPSBR voor de persoon
   ├── Selecteer PPSBR: is_master=True wint, anders hoogste rol-prioriteit
   ├── Zoek target OU via BRSO (BackendRole→SchoolOrg mapping)
   ├── Fallback: id_org uit PPSBR (bv. classgroup voor studenten)
   ├── Resolve administratieve orgs → niet-admin parent
   ├── Maak/update PERSON-TREE proprelation (person → target OU)
   └── Resultaat: persoon staat op de juiste plek in de org-tree

4. ACCOUNT-VELDEN POPULEREN → _populate_person_account_fields(person, target_org)
   ├── email_cloud = {voornaam}.{achternaam}@{domain_external}
   ├── person_fqdn_internal = cn={email_account},{target_org.ou_fqdn_internal}
   └── person_fqdn_external = cn={email_account},{target_org.ou_fqdn_external}

5. ODOO ACCOUNT AANMAKEN → ODOO/PERSON/ADD betask
   ├── Voorwaarde: persoon heeft actieve assignments
   ├── Maak res.users record (login = email_cloud)
   ├── Maak hr.employee record (alleen voor EMPLOYEE type)
   ├── Koppel aan person: odoo_user_id, odoo_employee_id
   └── Hergebruik bestaande/gearchiveerde user indien login al bestaat

6. GROEPSLIDMAATSCHAP SYNCHRONISEREN
   ├── _sync_person_group_memberships(person):
   │   ├── Verzamel actieve PPSBR → rollen met has_odoo_group=True
   │   ├── Vergelijk met huidige user.group_ids (enkel managed groups)
   │   ├── ODOO/GROUPMEMBER/ADD voor ontbrekende groepen
   │   └── ODOO/GROUPMEMBER/REMOVE voor overbodige groepen
   │
   └── _sync_persongroup_memberships(person):
       ├── Org-based: als PERSON-TREE org has_comgroup → sync PG-P leden
       └── Role-based: voor elke rol met has_group → sync rol-persongroups
```

### Wat bepaalt waar iemand in de tree terechtkomt?

```
PPSBR (Person-Period-School-BackendRole)
   │
   ├── id_role → rol met hoogste prioriteit wordt geselecteerd
   │              (laagste getal = hoogste prioriteit, is_master=True overrulet alles)
   │
   └── via BRSO (BackendRole-SchoolOrg):
       ├── id_role + id_org_parent (school) → zoek BRSO
       └── BRSO.id_org = target OU (waar de persoon in de tree komt)

Voorbeeld:
  PPSBR: person=Jan, role=ICT, school=BAWA
  BRSO:  role=ICT, org=int.olvp.bawa.ict, school=BAWA
  → PERSON-TREE: Jan → int.olvp.bawa.ict
  → FQDN: cn=jan.janssens,ou=ict,ou=bawa,dc=olvp,dc=int
```

---

## 2. Account Updaten

### 2a. Persoonsvelden wijzigen

| Pad | Trigger | Betask |
|-----|---------|--------|
| SAP Sync | Gewijzigde employee data | `DB/EMPLOYEE/UPD` |
| Object Manager | Admin wijzigt velden | `MANUAL/PERSON/UPD` (vals-modus) |

```
1. Update person-velden (naam, email, etc.)
2. Herbereken PPSBR (_ensure_ppsbr_exists_for_employee) [alleen SAP sync]
3. Herbereken tree-positie (_update_person_tree_position) [alleen SAP sync]
4. Herbereken account-velden (FQDN) [alleen SAP sync]
```

### 2b. Persoon verplaatsen naar andere org

| Pad | Trigger | Betask |
|-----|---------|--------|
| Object Manager | Admin verplaatst via MovePersonWizard | `MANUAL/PERSON/UPD` (move-modus) |

```
1. Deactiveer oude PERSON-TREE proprelatie
2. Maak nieuwe PERSON-TREE proprelatie naar nieuwe org
3. Herbereken account-velden (FQDN) → _populate_person_account_fields
4. Synchroniseer groepslidmaatschap → _sync_person_group_memberships + _sync_persongroup_memberships
```

### 2c. Wachtwoord wijzigen

| Pad | Trigger | Betask |
|-----|---------|--------|
| Object Manager | Admin wijzigt via PasswordWizard | `MANUAL/PERSON/UPD` (vals-modus) |

```
1. person.write({'password': new_password})
   (wachtwoord opgeslagen op person, gebruikt bij account-creatie)
```

---

## 3. Rolwijziging

Een rolwijziging is de meest impactvolle bewerking: het wijzigt de tree-positie,
groepslidmaatschap en potentieel de FQDN van het account.

### Rol toevoegen

| Pad | Trigger | Betask |
|-----|---------|--------|
| SAP Sync | Nieuwe assignment | `DB/PROPRELATION/ADD` (PPSBR) |
| Object Manager | Admin via ManagePersonRolesWizard | `MANUAL/PROPRELATION/ADD` (PPSBR) |

```
1. Maak PPSBR proprelation (person ↔ role ↔ school ↔ period)
2. Herbereken tree-positie → _update_person_tree_position(person)
   ├── Als nieuwe rol hogere prioriteit heeft → persoon verhuist in tree
   └── FQDN wijzigt mee
3. Sync Odoo groepen → _sync_person_group_memberships(person)
   └── Toevoegen aan groep van nieuwe rol (als has_odoo_group=True)
4. Sync persongroups → _sync_persongroup_memberships(person)
   └── Toevoegen aan persongroups van nieuwe org/rol
```

### Rol verwijderen

| Pad | Trigger | Betask |
|-----|---------|--------|
| SAP Sync | Assignment vervalt | `DB/PROPRELATION/DEACT` (PPSBR) |
| Object Manager | Admin via ManagePersonRolesWizard | `MANUAL/PROPRELATION/DEACT` |

```
1. Deactiveer PPSBR proprelation
2. Herbereken tree-positie → _update_person_tree_position(person)
   ├── Volgende hoogste-prioriteit rol neemt over
   ├── Als geen rollen meer → deactiveer PERSON-TREE
   └── FQDN wijzigt mee
3. Sync Odoo groepen → _sync_person_group_memberships(person)
   └── Verwijderen uit groep van oude rol
4. Sync persongroups → _sync_persongroup_memberships(person)
   └── Verwijderen uit persongroups van oude org/rol
```

### Voorbeeld rolwijziging: TEACHER → ICT

```
VOOR:
  PPSBR: person=Jan, role=TEACHER, school=BAWA
  BRSO:  role=TEACHER → org=int.olvp.bawa.pers
  PERSON-TREE: Jan → int.olvp.bawa.pers
  Odoo groep: group_myschool_teacher
  FQDN: cn=jan.janssens,ou=pers,ou=bawa,dc=olvp,dc=int

ACTIE: deactiveer TEACHER PPSBR, activeer ICT PPSBR

NA:
  PPSBR: person=Jan, role=ICT, school=BAWA
  BRSO:  role=ICT → org=int.olvp.bawa.ict
  PERSON-TREE: Jan → int.olvp.bawa.ict            ← VERHUISD
  Odoo groep: group_myschool_ict                   ← GEWIJZIGD
  FQDN: cn=jan.janssens,ou=ict,ou=bawa,dc=olvp,dc=int  ← GEWIJZIGD
```

---

## 4. Rol koppelen aan Org (BRSO)

Een BRSO bepaalt welke features beschikbaar zijn voor een rol bij een school.
Dit beheert groepen, accounts en persongroups.

### BRSO aanmaken met flags

| Pad | Trigger | Betask |
|-----|---------|--------|
| Object Manager | Admin via ManageOrgRolesWizard | `MANUAL/PROPRELATION/ADD` (BRSO) |

```
1. Maak BRSO proprelation (role ↔ target_org ↔ school)
2. Voor elke actieve flag:
   ├── has_accounts=True:
   │   ├── Queue LDAP/USER/ADD voor alle leden
   │   ├── Queue ODOO/PERSON/ADD voor alle leden
   │   └── Update PERSON-TREE posities (_update_tree_positions_for_brso)
   │
   ├── has_ldap_com_group=True:
   │   ├── Queue LDAP/GROUP/ADD (communicatiegroep)
   │   ├── Maak persongroup org onder OuForGroups
   │   └── Sync PG-P leden
   │
   ├── has_ldap_sec_group=True:
   │   ├── Queue LDAP/GROUP/ADD (beveiligingsgroep)
   │   ├── Maak persongroup org onder OuForGroups
   │   └── Sync PG-P leden
   │
   └── has_odoo_group=True:
       ├── Maak res.groups record
       ├── Maak persongroup org onder OuForGroups
       └── Sync PG-P leden + voeg users toe aan Odoo groep
3. Update org feature flags (org.update_org_flags)
```

### BRSO flag wijzigen (via OrgRoleLine.write in role_lines.py)

```
Flag-transitie detectie:
  ├── False → True (enabled):  → _process_brso_groups(rel, enabled_flags)
  │   └── Maak groepen + sync leden (zie hierboven)
  │
  └── True → False (disabled): → _remove_brso_groups(rel, disabled_flags)
      ├── has_ldap_com_group uitgeschakeld:
      │   ├── Queue LDAP/GROUP/DEL
      │   └── Deactiveer persongroup + PG-P leden
      ├── has_ldap_sec_group uitgeschakeld:
      │   ├── Queue LDAP/GROUP/DEL
      │   └── Deactiveer persongroup + PG-P leden
      └── has_odoo_group uitgeschakeld:
          ├── Verwijder users uit Odoo groep
          ├── Verwijder res.groups record
          └── Deactiveer persongroup
```

### BRSO verwijderen (via OrgRoleLine.action_remove in role_lines.py)

```
1. Verzamel alle actieve has_* flags op de BRSO
2. _remove_brso_groups(proprelation, active_flags) → verwijder alle groepen
3. MANUAL/PROPRELATION/DEACT → deactiveer de BRSO zelf
4. org.update_org_flags() → herbereken org flags
```

### Groepsnaam-algoritme

Eén autoritatief algoritme (ORG-TREE walk) in zowel `org.py` als `manual_task_processor.py`:

```
1. Start met org.name_short (lowercase)
2. Loop ORG-TREE proprelaties omhoog
3. Skip is_administrative=True en org_type=SCHOOLBOARD
4. Voeg name_short van elke org toe
5. Join met '-'
6. Prefix: 'grp-' (COM) of 'bgrp-' (SEC)

Voorbeeld: school(baple) → pers → adm
  COM: grp-adm-pers-baple
  SEC: bgrp-adm-pers-baple
```

### FQDN-constructie

Groepen leven onder OuForGroups van de school:

```
com_group_fqdn = cn={group_name},ou={OuForGroups},{school.ou_fqdn}

Voorbeeld: cn=grp-adm-pers-baple,ou=groups,ou=baple,dc=olvp,dc=int
```

### Ledenbepalings-strategie

De ledenbepaling hangt af van `brso.has_accounts`:

```
has_accounts=True:
  → OU-scoped: personen IN de OU (PERSON-TREE) ∩ personen MET de rol (PPSBR)
  → Alleen personen die fysiek in deze OU geplaatst zijn

has_accounts=False:
  → School-scoped: alle personen met de rol bij de school (PPSBR)
  → Breder: alle rolhouders, ongeacht hun OU-plaatsing
```

---

## 5. Account Deactiveren

### Automatisch (dagelijkse cron)

**Methode**: `cron_employee_account_lifecycle()` in `betask_processor.py`

```
Fase 0: DETECTIE (dagelijks)
  ├── Scan actieve employees zonder deactivation_date
  ├── Check person_details voor actieve assignments
  ├── Geen assignments meer:
  │   ├── Set deactivation_date = vandaag
  │   └── Deactiveer alle proprelations onmiddellijk
  └── automatic_sync=False personen worden geskipt

Fase 1: ACCOUNT DEACTIVATIE (na EmployeeAccountDeactivationDays, default 30 dagen)
  ├── person.write({'is_active': False})
  ├── Dit triggert _on_deactivate() cascade:
  │   ├── Odoo user deactiveren (user.active = False)
  │   ├── HR employee deactiveren (employee.active = False)
  │   └── Alle proprelations deactiveren
  └── Persoon verdwijnt uit actieve tree

Fase 2: ACCOUNT VERWIJDERING (na EmployeeAccountRemovalDays, default 90 dagen)
  ├── HR employee record verwijderen (unlink)
  ├── Odoo user record verwijderen (unlink)
  └── Person record BLIJFT bestaan (inactief, voor audit)
```

### Manueel via Object Manager

| Trigger | Betask |
|---------|--------|
| Admin klikt "Deactivate Person" | `MANUAL/PERSON/DEACT` |

```
1. _remove_user_from_all_role_groups(user)
   └── Verwijder uit alle door rollen beheerde Odoo groepen
2. person.write({'is_active': False, 'automatic_sync': False})
   ├── automatic_sync=False voorkomt re-activatie door SAP sync
   └── Triggert _on_deactivate() cascade:
       ├── Odoo user deactiveren
       ├── HR employee deactiveren
       └── Alle proprelations deactiveren
```

### Cascade: _on_deactivate() (person.py)

```python
def _on_deactivate(self):
    # 1. Deactiveer Odoo user
    if self.odoo_user_id:
        self.odoo_user_id.write({'active': False})

    # 2. Deactiveer HR employee
    if self.odoo_employee_id:
        self.odoo_employee_id.write({'active': False})

    # 3. Deactiveer alle proprelations
    self._deactivate_proprelations()
```

---

## 6. Account Verwijderen

| Pad | Trigger | Betask |
|-----|---------|--------|
| Automatisch | Fase 2 van lifecycle cron (na 90d) | Geen betask (directe write) |
| Object Manager | Admin klikt "Delete Person" | `MANUAL/PERSON/DEL` |

### Manueel verwijderen (MANUAL/PERSON/DEL)

```
1. ACCOUNT CLEANUP (voorkom orphaned records)
   ├── _remove_user_from_all_role_groups(user)
   ├── Verwijder HR employee record (unlink)
   └── Verwijder Odoo user record (unlink)

2. PROPRELATIONS OPRUIMEN
   └── Verwijder alle proprelations waar persoon betrokken is (unlink)

3. PERSON VERWIJDEREN
   └── person.unlink()
```

### Automatisch verwijderen (Fase 2 lifecycle cron)

```
1. Verwijder HR employee (person.odoo_employee_id → unlink)
2. Verwijder Odoo user (person.odoo_user_id → unlink)
3. Person record BLIJFT bestaan (inactief)
   └── Verschil met manueel: person wordt NIET verwijderd
```

---

## 7. Configuratie

### Systeemparameters (ir.config_parameter)

| Parameter | Default | Doel |
|-----------|---------|------|
| `myschool.manual_task_mode` | `'immediate'` | Verwerkingsmodus: `'immediate'` of `'queued'` |

### Config Items (myschool.config.item)

| Naam | Scope | Doel |
|------|-------|------|
| `EmployeeAccountDeactivationDays` | Globaal | Dagen na deactivation_date tot account-deactivatie (default 30) |
| `EmployeeAccountRemovalDays` | Globaal | Dagen na deactivation_date tot account-verwijdering (default 90) |
| `OuForGroups` | Per school | Naam van de OU waaronder persongroups worden aangemaakt |

### Cron Jobs

| Job | Interval | Methode |
|-----|----------|---------|
| Backend Task Processor | 15 min | `cron_process_tasks()` |
| Employee Account Lifecycle | Dagelijks | `cron_employee_account_lifecycle()` |
| Task Cleanup | Dagelijks | Archiveer completed tasks ouder dan 30 dagen |

---

## 8. Bronbestanden

| Bestand | Verantwoordelijkheid |
|---------|---------------------|
| `myschool_core/models/person.py` | Person model, `_on_deactivate`/`_on_reactivate` cascade |
| `myschool_core/models/org.py` | Org model, `update_org_flags`, `_compute_and_write_group_fields` |
| `myschool_core/models/role.py` | Role model, `has_odoo_group` koppeling |
| `myschool_core/models/proprelation.py` | PropRelation model, BRSO flags |
| `myschool_core/models/betask_processor.py` | Hoofd-processor: tree-positie, groepssync, account lifecycle |
| `myschool_core/models/manual_task_processor.py` | MANUAL handlers met cascade-effecten |
| `myschool_core/models/manual_task_service.py` | Service: `create_manual_task()` |
| `myschool_admin/models/role_lines.py` | OrgRoleLine: flag-transitie detectie → groep create/delete |
| `myschool_admin/models/wizards.py` | UI wizards die MANUAL betasks aanmaken |
| `myschool_admin/models/object_browser.py` | Object Manager backend |
