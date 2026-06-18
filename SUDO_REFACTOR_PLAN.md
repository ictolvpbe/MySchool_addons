# SUDO_REFACTOR_PLAN — `.sudo()`-opschoning extra-addons

> **Status: NIET GESTART** — inventaris afgerond 2026-06-09, repo op `Dev`
> tip `59837e7`. Dit document is zelfstandig oppikbaar: het bevat de volledige
> telling, alle te-versmallen call-sites met voorstel, en de werkpakket-volgorde.
>
> **Code-stijlregel** (zie ook [CLAUDE.md](CLAUDE.md)): sudo zo smal mogelijk —
> rond één statement, niet rond hele flows.

## Methodiek

- Grep: `grep -rn "\.sudo()" extra-addons --include="*.py"` → **206 call-sites**.
  Er zijn geen `.sudo(user)`-varianten met argument in de repo.
- Criteria "te versmallen":
  1. een gesudo'de recordset/env die voor meerdere opeenvolgende operaties
     hergebruikt wordt;
  2. sudo aan het begin van een methode terwijl maar één regel het nodig heeft;
  3. sudo in een controller/compute op data die daarna integraal naar de
     client gaat.
- "Al smal" = één gerichte read/write van `ir.config_parameter` (~70 sites),
  `ir.sequence`, `ir.logging`, mail-server-counts, api-key-reads op
  config-records, password-writes op person, migrations en tests. Die blijven
  ongemoeid.

⚠️ Regelnummers hieronder gelden voor `Dev` tip `59837e7` (2026-06-09).
Bij oppikken eerst opnieuw greppen; de functienamen staan erbij als anker.

## 1. Tellingstabel per module

| Module | Totaal | Al smal | Te versmallen |
|---|---|---|---|
| myschool_core | 41 | 39 | 2 |
| myschool_activiteiten | 24 | 23 | 1 |
| myschool_sync | 23 | 15 | 8 |
| myschool_drukwerk | 23 | 21 | 2 |
| myschool_professionalisering | 21 | 15 | 6 |
| myschool_admin | 17 | 14 | 3 |
| myschool_mcp | 11 | 11 | 0 |
| myschool_theme | 10 | 7 | 3 |
| myschool_lessenrooster | 9 | 6 | 3 |
| myschool_dashboard | 9 | 7 | 2 |
| myschool_kosten_dashboard | 4 | 1 | 3 |
| myschool_planner | 3 | 3 | 0 |
| myschool_knowledge_builder | 3 | 2 | 1 |
| myschool_itsm | 3 | 3 | 0 |
| myschool_appfoundry | 3 | 2 | 1 |
| myschool_directie_dashboard | 2 | 2 | 0 |
| **Totaal** | **206** | **171** | **35** |

## 2. Te-versmallen-lijst (22 vindingen, 35 sites)

### A. Wizard-exports/imports die een hele flow sudo'en (criterium i/ii)

- [ ] **A1. `myschool_admin/models/data_exchange.py:545`** — `action_import`:
  `sudo_self = self.sudo()` waarna ~15 `_import_*`-methodes (creates/writes op
  org/person/role/proprelation/betask) onder sudo draaien.
  **Voorstel**: expliciete admin-groepscheck bovenaan + sudo per `_import_*`-call
  laten vallen; als sync-record-rules echt blokkeren: sudo enkel in de ene
  create/write die erop botst, met comment welke rule.
- [ ] **A2. `myschool_admin/models/data_exchange.py:131`** — `action_export`:
  `self.sudo()._build_export_data()` — volledige export (alle orgs/persons/
  betasks, alle velden) onder sudo. Comment zegt: ACL is al admin-only.
  **Voorstel**: expliciete groepscheck + gewone env; sudo enkel op de query die
  door de `automatic_sync`-record-rule geblokkeerd wordt.
- [ ] **A3. `myschool_activiteiten/wizard/export_wizard.py:50`** —
  `action_export`: `Act = ...record'].sudo()` → search + Excel-opbouw die
  tientallen velden van álle activiteiten leest; resultaat integraal naar de
  gebruiker. **Voorstel**: groepscheck (directie/aankoop) + gewone env; of sudo
  alleen op de `search` en velden via `read()` met expliciete lijst.
- [ ] **A4. `myschool_professionalisering/wizard/export_wizard.py:54`** —
  `action_export`: identiek patroon als A3 voor prof-records.
  **Voorstel**: zelfde remedie als A3.
- [ ] **A5. `myschool_drukwerk/wizard/count_e_export_wizard.py:86`** —
  `action_export`: `Drukwerk = ...sudo()` → hele CSV-export incl.
  `record.student_ids` en `student.sap_ref/name` onder sudo.
  **Voorstel**: wizard is boekhouding/admin → groepscheck + gewone env; sudo
  hooguit op één `search_read` met veldlijst (`kleur`, `aantal_paginas`,
  `student_ids.sap_ref`).
- [ ] **A6. `myschool_professionalisering/wizard/import_intranet_wizard.py:108-111`**
  (4 sites) — `_import_records`: vier sudo-modelhandles (`Prof`, `Employee`,
  `Vak`, `Address`) voor de hele importloop.
  **Voorstel**: alleen de `Employee`-lookup heeft sudo nodig (hr-ACL); de drie
  eigen modellen via gewone env + admin-ACL op de wizard. (Regel 359 in
  dezelfde file is een losse smalle search — laten staan.)

### B. Sudo'de recordsets/envs hergebruikt over meerdere operaties (criterium i)

- [ ] **B1. `myschool_core/models/org.py:1310`** — company-sync-methode:
  `Company = self.env['res.company'].sudo()` bovenaan; daarna search + create +
  write + archive over honderden regels.
  **Voorstel**: sudo per statement op precies de mutatieplekken
  (`company.sudo().write(...)`, `Company.sudo().create(...)`); searches via
  gewone env (cron draait al als sync-user). Regel 1327 (`Country`-lookup) is
  smal en blijft.
- [ ] **B2. `myschool_core/models/manual_task_processor.py:1670`** —
  domain-rename-flow: `ResUsers = ...users'].sudo()` → search alle users +
  login-writes in loop.
  **Voorstel**: sudo enkel op de write (`u.sudo().write({'login': ...})`);
  search met gewone env of `search_read([...], ['login'])`.
- [ ] **B3. `myschool_admin/models/ad_takeover.py:2926`** — index-bouw:
  `Users = ...sudo().with_context(active_test=False)` → `search([])` + alle
  logins inlezen. **Voorstel**: één `search_read([], ['login'])` onder sudo;
  geen herbruikbare sudo-handle.
- [ ] **B4. `myschool_theme/models/icon_manager.py:157,160,180`** (3 sites) —
  `_restore_standard_icons` / `_regenerate_all_icons`: sudo'd menu-recordsets
  hergebruikt voor reads (`get_external_id`, `web_icon`) én writes.
  **Voorstel**: searches via gewone env; sudo enkel rond
  `menu.sudo().write({'web_icon_data': ...})`.
- [ ] **B5. `myschool_appfoundry/models/project.py:322`** — icoon-toepassing:
  `ir.ui.menu` sudo-search, daarna `menu.write(...)` (impliciet sudo) in loop.
  **Voorstel**: search normaal, `menu.sudo().write({'web_icon_data': icon_b64})`.
- [ ] **B6. `myschool_dashboard/models/dashboard.py:848`** —
  `_setup_optional_apps`: sudo'd `children`-search waarna
  `to_deactivate.write(...)` / `to_activate.write(...)` op de sudo-set draaien.
  Bovendien: alles loopt al in `_register_hook` (superuser-context).
  **Voorstel**: sudo hier schrappen of per write-statement zetten.
- [ ] **B7. `myschool_dashboard/models/dashboard.py:568`** —
  `action_open_prof_import`: `import.wizard'].sudo().create({})` — wizard wordt
  sudo-gecreëerd en daarna door de user bediend.
  **Voorstel**: doelgroep create-ACL geven op het wizard-model, sudo weg.

### C. Sync-pipeline: sudo als impliciete service-identiteit (criterium i + iii)

> Samenhangend cluster — beste moment om dit op te lossen is **SRVMGR-7**
> (sync verhuizen naar servermanager). Kernbeslissing: technische sync-user
> i.p.v. sudo.

- [ ] **C1. `myschool_sync/controllers/sync_receiver.py:95-96`** (2 sites) —
  `receive()`-endpoint (`auth='public'`): `resolver = ...sudo()` +
  `sync_log = ...sudo()`; de héle inbound apply-flow (creates/writes op
  person/org/role/proprelation) draait sudo na enkel een API-key-check.
  **Voorstel**: na key-check switchen naar technische sync-user
  (`request.env(user=sync_user.id)`) zodat ACL + audit-trail gelden; sudo
  alleen voor de config-parameter-reads (regels 33/42 — die zijn al smal).
- [ ] **C2. `myschool_sync/models/sync_resolver.py:30`** — `resolve_natural_key`
  retourneert een sudo'd recordset die in `apply_payload` hergebruikt wordt
  voor change-detection én `write()` (regel 112, impliciet sudo).
  **Voorstel**: lookup via gewone (sync-user-)env; sudo enkel op de ene
  write/create indien echt nodig. (Regels 49 en 129 zijn losse smalle ops.)
- [ ] **C3. `myschool_sync/models/sync_target.py:122`** — `action_full_sync`:
  `Model = ...sudo().with_context(...)` → `search([])` + serialisatie van álle
  velden van álle records per registry-entry.
  **Voorstel**: admin-knop → groepscheck + gewone env; of sudo beperken tot de
  `search`, serializer met expliciete veldlijst.
- [ ] **C4. `myschool_sync/models/sync_emitter.py:132,145,154,161`** (4 sites) —
  vier sudo-modelhandles (Person/Org/PropRelation/Role) waarvan alle velden
  geserialiseerd en naar buiten gestuurd worden.
  **Voorstel**: zelfde keuze als C1 — technische sync-user i.p.v. sudo; dan
  vervallen deze vier in één klap.

### D. Data onder sudo integraal naar de client (criterium iii)

- [ ] **D1. `myschool_kosten_dashboard/models/kosten_dashboard_main.py:30,48` +
  `kosten_dashboard.py:42`** (3 sites) — `_compute_kpis` /
  `_compute_top_spenders` / `_compute_detail_html`: `search_read` onder sudo op
  kosten-per-medewerker/kosten-detail; resultaat (namen + bedragen van álle
  medewerkers) gaat integraal als HTML naar de client.
  **Voorstel**: expliciete groepscheck (directie-groep) + gewone env met
  ACL/record rule op de SQL-view-modellen; sudo volledig weg. Grootste
  PII-winst van het hele plan.
- [ ] **D2. `myschool_lessenrooster/models/inhaal_view.py:53,73,95`** (3 sites) —
  `_absence_dates_for` (aangeroepen vanuit OWL-RPC): sudo-searches op
  activiteiten/prof-records; titels van andermans records gaan naar de client.
  **Voorstel**: `search_read` onder sudo met expliciete veldlijst (`datetime`,
  `datetime_end`, `titel`, `name`, `start_date`, `end_date`) en alleen die dict
  doorsturen. NB: de create-flow op regels 264-368 is al per statement
  gesudo'd en gedocumenteerd (self-service) — laten staan.
- [ ] **D3. `myschool_drukwerk/models/drukwerk.py:837`** — `action_view_students`:
  sudo-search op alle leerlingen van de klassen, daarna per student velden
  gelezen voor wizard-lines.
  **Voorstel**: `search_read([...], ['tree_org_id'])` onder sudo; rest via ids.
- [ ] **D4. `myschool_professionalisering/models/professionalisering.py:273`** —
  `hr.employee.name_search`-override: `self.sudo().name_search(...)` zodra de
  context-vlag `professionalisering_directie_search` gezet is; alle
  werknemersnamen naar de client-picker.
  **Voorstel**: expliciete check
  `has_group('myschool_professionalisering.group_professionalisering_directie')`
  vóór de sudo-tak; anders gewoon `super()`.
- [ ] **D5. `myschool_knowledge_builder/models/knowledge_object.py:274`** —
  `get_shared_data`: sudo-search op share-token + hergebruik van het
  sudo-object voor alle veld- en step-reads, integraal naar een publieke
  pagina. **Nuance**: bewust token-share-patroon; output is al een expliciete
  whitelist (`title/details/knowledge_type/steps`). **Laagste prioriteit** —
  vooral een comment toevoegen dat de whitelist het beveiligingscontract is.
  (De controller `controllers/share.py:11` delegeert enkel — smal.)

## 3. Werkpakketten (aanbevolen volgorde)

| # | Pakket | Vindingen | Sites | Risico/baat |
|---|---|---|---|---|
| 1 | Quick wins, puur mechanisch | B2, B3, B4, B5, B6, B7 | 8 | Laag risico, zelfde gedrag; sudo verplaatsen naar het write-statement |
| 2 | Exports/imports → groepscheck | A1–A6 | 11 | ACL-controle per wizard nodig; functioneel testbaar via bestaande flows |
| 3 | Client-facing reads → veldlijst/groepscheck | D1–D5 | 9 | Echte PII-winst; sluit aan bij geplande PII-classificatie (arch-split) |
| 4 | Sync-pipeline → technische sync-user | C1–C4 + B1 | 9 | Grootste ontwerpbeslissing; **meenemen in SRVMGR-7** (sync verhuizen) |

### Aandachtspunten pakket 4

- De receiver draait op `auth='public'` → zonder technische user is er
  letterlijk geen user-context; dát is waarom sudo daar nu overal zit.
- Een technische sync-user heeft ACL's nodig op alle core-modellen
  (person/org/role/proprelation) plus een uitzondering op de
  betask-pipeline-regel: sync-writes lopen nu al via de resolver, niet via
  `manual_task_service` — dat blijft zo.
- Positief referentievoorbeeld in de repo: `myschool_mcp/controllers/mcp.py`
  — `_env_for()` bouwt `request.env(user=user_id, su=False)` na
  apikey-check; sudo enkel voor apikey-validatie, config-reads en
  sys-event-logging.

### Grijze gevallen — bewust NIET in scope (gedocumenteerde afweging)

- `myschool_core/models/asset.py:204` + `access_policy.py:76` — compute moet
  álle policies/assets zien ongeacht de user; één search, intern gebruik.
- `myschool_core/models/hr_employee_display_name.py:38` — één search,
  beperkt veldgebruik (first_name/name/login) voor display_name.
- `myschool_directie_dashboard/models/dashboard.py:268,278` — gerichte
  `read_group`-aggregaties (counts), geen record-data naar client.
- `myschool_drukwerk/models/drukwerk.py:341,356-358,403` en
  `myschool_planner/models/planner.py:105,281` — cross-module computes die
  enkel ids/datums gebruiken.
- `myschool_activiteiten/models/activiteiten.py:305-310` — bus-lines
  create/unlink: per statement gesudo'd, met comment waarom (leerkracht heeft
  geen rechten op bus-model).
- `myschool_lessenrooster/models/inhaal_view.py:264-368` — self-service
  create-flow, per statement gesudo'd en gedocumenteerd in docstring.
- `myschool_core/models/letter_template.py:496` — `mail.mail` sudo
  create+send: standaard Odoo-mailpatroon.

## 4. Definition of done

- [ ] Pakket 1 t/m 4 afgewerkt (checkboxes hierboven).
- [ ] Hergrep `\.sudo()` toont geen modelhandle-patroon meer
  (`= self.env[...].sudo()` aan methode-start gevolgd door flow).
- [ ] Tests groen per module na elk pakket (zie pre-prod test coverage-doel).
- [ ] CLAUDE.md sudo-regels blijven het normatieve referentiepunt.
