# Melira — Doelarchitectuur (greenfield rebranding + product-lijn)

> Status: **ONTWERP, vastgesteld 2026-06-12.** Opvolger van `BRANDING.md` (naamtraject).
> Dit document is de hand-off voor de MITRAS-werf "Rebranding → Melira (greenfield)".
> Naam **Melira** is gekozen maar nog niet juridisch gecleard (BOIP-woordmerk kl. 9/41/42 loopt) —
> begin geen externe publicatie/registratie vóór clearing-bevestiging. Zie `BRANDING.md`.
> **De technische namespace is merk-neutraal `ml_`/`ml.` — een latere merkwijziging raakt de code niet** (§5).

---

## 1. Uitgangspunten (beslist)

| # | Beslissing | Gevolg |
|---|---|---|
| 1 | **MySchool is niet in productie**; de `test`-instance wordt binnen ~2 weken gedecommissioneerd. | **Geen datamigratie.** De rename is een source-transform naar verse repo(s) + verse provisioning. |
| 2 | **Geen migratiepad** — modules worden onder verse naam (her)geschreven. | De ~132 modellen en ~1.344 XML-IDs worden gewoon mét nieuwe naam aangemaakt; nul migratierisico. |
| 3 | **Nieuwe repo(s)**, niet `odoo-myschool` hernoemen. | Schone git-historie, geen legacy-refs. GitHub-account nog te kiezen. |
| 4 | **3-tier product-lijn**: (1) platform = kernel + gedeelde apps, (2) business, (3) education. | Zie §3. |
| 5 | **Business-editie concreet** bouwen (niet enkel structureel voorzien). | `ml_business`-bundle wordt nu aangemaakt (platform + nog zonder biz-verticals). |
| 6 | **Tier-prefix in technische modulenamen** (`ml_edu_*`, `ml_biz_*`), **niet** in zichtbare app-namen. | Eindgebruiker ziet "Lessenrooster", niet "Edu Lessenrooster". |
| 7 | **MCP-namespace mee-renamen** (`mcp__myschool__*` → `mcp__melira__*`). | Her-registratie Claude Code + her-deploy + DNS-host (§8). |
| 8 | **3 repo's: `melira-platform` (core+common), `melira-business`, `melira-education` — symmetrische editie-repo's.** | Editie-specifieke admin-extensies + connectors (bv. Informat/Smartschool → edu) zitten in hún editie-repo, als plugins op de generieke admin. Dependency éénrichting (editie → platform). |
| 9 | **Per-klant maatwerk mag in een aparte overlay-repo.** | Klant-/school-specifieke apps als additieve laag bovenop een editie (§2.2). |
| 10 | **Integratie met het Odoo-ecosysteem is een doorlopend ontwerpprincipe.** | Bouwen náást/op standaard Odoo + OCA, niet ertegenin (§9). |
| 11 | **Technische namespace merk-neutraal `ml_`/`ml.`** (modules, modellen, tabellen, XML-IDs, velden); "Melira" enkel in de merklaag. | Een latere gedwongen merkwijziging (bv. Melira→Melirax wegens merkenschending) raakt **enkel** manifest-`name`, repo-namen, DNS en docs — **nul impact op code/data** (§5). |

---

## 2. Repo-topologie

### 2.1 Drie repo's — één platform + symmetrische editie-repo's

De afhankelijkheid loopt **strikt één kant op**: een editie hangt af van het platform, nooit
omgekeerd. Geverifieerd uit de huidige dependency-graph — geen enkele platform-module verwijst naar
een business- of education-module. **Core en common reizen altijd samen** (elke instance laadt
beide), dus ze delen één repo; biz en edu zijn **symmetrische** editie-repo's die elk hun eigen
admin-extensies + connectors dragen.

```
┌──────────────────────────────────────────────────────────────┐
│ REPO 1 — melira-platform   (account: TBD; kandidaat publiek)   │
│                                                                │
│  TIER 1 · PLATFORM                                             │
│    Kernel (core)  ml_core · ml_theme · ml_admin(basic) ·      │
│                   ml_oidc · ml_sync · ml_servermanager        │
│    Common (apps)  ml_projects · ml_appfoundry · ml_itsm ·     │
│                   ml_assets · ml_knowledge · ml_tasks ·       │
│                   ml_processcomposer · ml_mcp · ml_dashboard  │
└──────────────────────────────────────────────────────────────┘
              ▲                                   ▲
              │  depends (éénrichting)            │
┌─────────────┴───────────────┐   ┌───────────────┴──────────────┐
│ REPO 2 — melira-business     │   │ REPO 3 — melira-education     │
│  (privé)                     │   │  (privé aanbevolen)           │
│                              │   │                               │
│  TIER 2 · BUSINESS           │   │  TIER 3 · EDUCATION           │
│   Verticals  ml_biz_*        │   │   Verticals  ml_edu_*         │
│   Admin-ext  ml_biz_admin    │   │   Admin-ext  ml_edu_admin     │
│   Persoon    ml_biz_person   │   │              (BRSO/SRBR)      │
│   Connectors (later)         │   │   Persoon    ml_edu_person    │
│   Bundle     ml_business     │   │   Connectors ml_edu_informat ·│
│                              │   │              ml_edu_smartschool│
│                              │   │   Bundle     ml_education      │
└──────────────────────────────┘   └───────────────────────────────┘
```

> Repo-namen dragen wél het merk (`melira-…`) — dat is de merklaag (§5) en een repo hernoemen is
> triviaal (GitHub-rename + `git remote set-url`), zonder code-impact.

**Waarom dit werkt.** Een Odoo-instance laadt meerdere repo's op zijn `addons_path` (zoals OCA).
- **Business-instance**: repo 1 **+** repo 2 → installeert `ml_business`.
- **Education-instance**: repo 1 **+** repo 3 → installeert `ml_education`.

De editie-repo haakt op de **generieke admin** via plugins (zie §6): `ml_edu_informat` declareert
`depends=['ml_admin']` en injecteert zijn config/connector zonder de kern te raken. Zo zit de
Informat-/Smartschool-integratie (en de bijhorende secrets/PII) in edu, nooit in core of biz.

**Waarom common bij core en niet apart.** Core en common worden nooit los gedeployed; een aparte
repo zou in de greenfield-fase (hoogste churn) elke "app heeft net een nieuwe core-hook nodig"-wijziging
in twee PR's + een versie-pin splitsen. Common blijft binnen repo 1 wél een **strikt
éénrichtings-module-groep** (common → core, nooit omgekeerd), zodat ze later met `git filter-repo`
mét historie naar een eigen 4e repo te promoveren is zodra daar een concrete reden voor is
(apps open-sourcen of externe contributors los van de PII-kern).

**Waarom education privé.** Repo 3 bevat de Belgische onderwijs-integraties (Smartschool/Informat)
en de school-PII-extensies (INSZ, stamboeknummer, gezinsdump). Gevoeliger en specifieker dan het
generieke platform; scheidt ook wat ooit open/commercieel kan versus wat schoolgebonden blijft.

### 2.2 Per-klant overlay-repo's (toekomst)

Als later **meerdere scholen of bedrijven** eigen apps nodig hebben, krijgt elke klant een **aparte
overlay-repo** — géén product-tier, maar een deployment-laag bovenop een editie:

```
   melira-platform  ──►  melira-education  ──►  melira-cust-<school-X>
     (repo 1)              (repo 3)               (overlay, privé)
```

- Naampatroon: repo `melira-cust-<klant>` (merklaag) met modules `ml_<klantprefix>_<naam>`.
- **Strikt additief**: enkel `_inherit`, nieuwe modellen, nieuwe views — **nooit** upstream-code
  forken of monkey-patchen. Zo blijft het platform/vertical-onderhoud single-source.
- `addons_path` van die klant-instance = platform (+ editie) + de overlay-repo.
- Generiek maatwerk dat meerdere klanten willen → promoveren naar de vertical of het platform;
  écht klant-specifiek blijft in de overlay. (Periodiek terug-promoveren voorkomt drift.)

Dit is exact het Odoo-partnermodel voor klant-customisaties en houdt de product-repo's schoon.

### 2.3 Repo-indeling & `addons_path`

`addons_path` is een lijst van mappen waarvan Odoo de **directe submappen** als modules inleest —
Odoo **recurseert niet**. De natuurlijke eenheid is dus: **één repo = één addons-root op het pad**.
Modulenaam ≠ mapnaam: de repo-map zélf is de addons-root; de modules erin heten gewoon `ml_core`,
`ml_projects`, … (OCA-conventie: modules plat in de repo-root; wie de root wil vrijhouden voor
CI/docs zet ze onder één `addons/`-submap — één van beide, consistent).

```
melira-platform/          ← staat op addons_path (core én common samen, geen aparte map)
├── ml_core/  ml_theme/  ml_admin/  ml_oidc/  ml_sync/  ml_servermanager/
└── ml_projects/  ml_appfoundry/  ml_itsm/  ml_assets/  ml_knowledge/  …
```

Een instance laadt **platform + zijn eigen editie** (2 roots), niet alle drie:

```ini
# odoo.conf — EDUCATION-instance
addons_path = /opt/odoo/odoo/addons, /opt/melira/melira-platform, /opt/melira/melira-education

# odoo.conf — BUSINESS-instance
addons_path = /opt/odoo/odoo/addons, /opt/melira/melira-platform, /opt/melira/melira-business

# odoo.conf — klant met overlay (§2.2)
addons_path = /opt/odoo/odoo/addons, /opt/melira/melira-platform, /opt/melira/melira-education, /opt/melira/melira-cust-schoolX
```

**Anti-patroon:** géén aparte addons-map per tier/module (bv. `ml_core_addons`/`ml_edu_addons`) —
dat verwart container met modulenaam. En géén mapsplitsing core-vs-common binnen `melira-platform`:
die grens (common → core) dwing je af via manifest-`depends`, niet via mappen. Wil je common ooit naar
een eigen 4e repo promoveren (§2.1), leg ze dán pas in submappen `kernel/` + `common/` (= 2
path-entries) zodat de `git filter-repo`-knip schoon is; tot dan plat houden.

---

## 3. Het 3-tier-model

| Tier | Repo | Inhoud | Regel |
|---|---|---|---|
| **1 · Platform** | `melira-platform` | **Kernel/core** (`ml_core` + identiteit org/person/role/proprelation, proces, betask, toegang, sys.event, settings, sync-framework, generieke connectors LDAP/Google/SAP, generieke admin) **+ common/gedeelde apps** (projects, appfoundry, itsm, assets, knowledge, tasks, processcomposer, mcp, dashboard). | Domein-agnostisch, bruikbaar in elke editie. Common = single-source, geen fork; éénrichting common → core. |
| **2 · Business** | `melira-business` | `ml_biz_*`-verticals + `ml_biz_admin`/`ml_biz_person`-extensies + bundle `ml_business`. | Hangt af van platform. Nu greenfield. |
| **3 · Education** | `melira-education` | `ml_edu_*`-verticals + `ml_edu_admin` (BRSO/SRBR) + `ml_edu_person` + connectors `ml_edu_informat`/`ml_edu_smartschool` + bundle `ml_education`. | Hangt af van platform. Editie-extensies = plugins op de generieke admin (§6). |

**Editie-bundel** = dun meta-module per vertical-tier (alleen `depends=[...]` + branding). Bepaalt
welke apps de editie krijgt.

**Kernprincipe — thin platform-kernel.** Hou de kernel minimaal; gedeelde apps en verticals zijn
opt-in via de bundle. Een vette kernel duwt domein-gewicht op elke install. (Bewust het tegendeel
van "core uitbreiden".)

---

## 4. Volledige module-mapping

> Technische modulenaam = merk-neutraal `ml_`. Tier-prefix (`edu_`/`biz_`) zit alleen in de
> technische naam, nooit in de zichtbare naam. Zichtbare naam (`name`) = merklaag → "Melira …";
> functie-only namen blijven (bv. "Lessenrooster", "Afdrukcentrum").

### Tier 1 · Platform — Kernel/core  ·  repo `melira-platform`

| Huidige module | → Nieuwe module | Zichtbare naam | Opmerking |
|---|---|---|---|
| `myschool_core` | `ml_core` | Melira Core | **Afslanken**: school-PII + Smartschool/Informat eruit (§6). |
| `myschool_theme` | `ml_theme` | Melira Theme | |
| `myschool_admin` | `ml_admin` | Melira Admin | **Generiek/basic** — biedt extensiepunten (§6); BRSO/SRBR → `ml_edu_admin`. |
| `myschool_oidc` | `ml_oidc` | Melira OIDC (Keycloak) | |
| `myschool_sync` | `ml_sync` | Melira Sync | |
| `myschool_servermanager` | `ml_servermanager` | Melira Server Manager | |

### Tier 1 · Platform — Common/gedeelde apps  ·  repo `melira-platform`

| Huidige module | → Nieuwe module | Zichtbare naam | Opmerking |
|---|---|---|---|
| `myschool_projects` | `ml_projects` | Melira Projects | Hangt nu al schoon enkel aan core. |
| `myschool_appfoundry` | `ml_appfoundry` | AppFoundry | |
| `myschool_itsm` | `ml_itsm` | Melira IT Service Management | |
| `myschool_assets` | `ml_assets` | Asset- en Inventarisbeheer | |
| `myschool_knowledge_builder` | `ml_knowledge_builder` | Knowledge Builder | Hangt zelfs niet aan core → volledig generiek. |
| `myschool_tasks` | `ml_tasks` | Melira Takenbord | |
| `myschool_processcomposer` | `ml_processcomposer` | Melira Process Composer | |
| `myschool_mcp` | `ml_mcp` | Melira MCP Server | Namespace-rename, zie §8. |
| `myschool_dashboard` | `ml_dashboard` | Mijn Dashboard | Generiek dashboard-framework. |

### Tier 2 · Business  ·  repo `melira-business`  ·  prefix `ml_biz_`

Nog geen modules — greenfield. Eerste biz-vertical `_inherit`t `ml.person` voor business-velden (§6)
en hangt aan het platform. Editie-extensies symmetrisch met edu: `ml_biz_admin` (plugin op de
generieke admin), `ml_biz_person`, en later eventuele biz-connectors. Bundle: `ml_business`
(zichtbaar "Melira for Business").

### Tier 3 · Education  ·  repo `melira-education`  ·  prefix `ml_edu_`

| Huidige module | → Nieuwe module | Zichtbare naam | Opmerking |
|---|---|---|---|
| `myschool_lessenrooster` | `ml_edu_lessenrooster` | Lessenrooster | |
| `myschool_activiteiten` | `ml_edu_activiteiten` | Activiteiten | |
| `myschool_drukwerk` | `ml_edu_drukwerk` | Afdrukcentrum | |
| `myschool_professionalisering` | `ml_edu_professionalisering` | Professionalisering | |
| `myschool_planner` | `ml_edu_planner` | Planner | |
| `myschool_directie_dashboard` | `ml_edu_directie_dashboard` | Directie Dashboard | |
| `myschool_kosten_dashboard` | `ml_edu_kosten_dashboard` | Kosten Dashboard | ⚠ Kandidaat voor **platform** i.p.v. edu — verifiëren (§7). |
| *(nieuw, uit core)* | `ml_edu_informat` | Informat-koppeling | Connector-plugin op `ml_admin` (§6). Eigen config + secret. |
| *(nieuw, uit core)* | `ml_edu_smartschool` | Smartschool-koppeling | Connector-plugin op `ml_admin` (§6). Eigen config + secret. |
| *(nieuw, uit admin)* | `ml_edu_admin` | Onderwijs-admin (BRSO/SRBR) | Admin-plugin: BRSO/SRBR-wizards + onderwijs-rolconcepten. |
| *(nieuw, uit core)* | `ml_edu_person` | Onderwijs-persoonsgegevens | Extractie INSZ/`person.details` uit core (§6). |

> De twee connectors mogen ook samen in één `ml_edu_connect` als de config gedeeld blijkt; per-connector
> modules (hierboven) geven schonere aan/uit-controle en gescheiden secrets per koppeling.

Bundle: `ml_education` (zichtbaar "Melira for Education"), repo `melira-education`.

---

## 5. Naamgeving — twee lagen (merk-ontkoppeling)

De technische identifiers zijn **merk-neutraal** en veranderen nóóit; "Melira" leeft alleen in de
zichtbare/merklaag. Zo blijft een eventuele gedwongen merkwijziging (bv. wegens merkenschending →
"Melirax") puur cosmetisch.

**A. Technische laag — prefix `ml_` / `ml.` (verandert nooit):**
- **Modulenaam**: `ml_<naam>` (platform), `ml_edu_<naam>` / `ml_biz_<naam>` (verticals),
  `ml_<klantprefix>_<naam>` (overlay). Geldige Python-identifier → **underscore**, geen streep.
- **Modelnaam (`_name`)**: **plat** `ml.<...>`, géén tier in de namespace. Odoo-modellen leven in één
  globale namespace los van de module (vgl. module `sale` → model `sale.order`). Dus
  `ml_edu_lessenrooster` bevat modellen `ml.lessenrooster.*`.
- **Tabelnaam**: door Odoo afgeleid uit `_name` → `ml_lessenrooster_line` enz.
- **XML-ID-module (`ir_model_data.module`)**: volgt de modulenaam → `ml_*` (mét tier-prefix).
- **Veldnamen** die nu `myschool_*` heten (bv. `myschool_sync_api_key`) → `ml_*`.

**B. Merklaag — "Melira" (mag wijzigen zonder code-impact):**
- Zichtbare app-naam (manifest `name`, bv. "Melira Core"), repo-namen (`melira-platform`),
  DNS/hosts, MCP-registratienaam, documentatie en branding-assets.

**Blast-radius van een merkwijziging** = enkel laag B: find/replace in `name`-strings, repo-rename,
DNS en docs. Modellen, tabellen, modules, XML-IDs, velden, data en code blijven ongemoeid. Dít is de
reden om `ml_` te kiezen i.p.v. `melira_` voluit.

---

## 6. Datamodel-naden + extensiepunt-patroon (de echte herstructurering)

Drie naden waarlangs de kernel wordt afgeslankt — méér dan rename: de domein-splitsing die de
4-instance-split en PII-classificatie tóch al vroegen (§10). Elke naad wordt een **expliciet
extensiepunt** in de generieke kern/admin, waar editie-modules als **plugin** op haken.

1. **`person`-naad.** Kernel definieert generiek `ml.person(person_type)`. Onderwijs-velden (`insz`,
   `stamboeknummer`, `person.details`-dump = INSZ/bankrekening/gezinssamenstelling) verhuizen uit
   `core/models/person.py` + `person_details.py` naar **`ml_edu_person`** (dat `ml.person` `_inherit`t;
   model `ml.person.details`). Business `_inherit`t later voor eigen velden. → Kernel draagt geen
   domein-PII meer. *(Integratie-noot §9: weeg of `ml.person` koppelt aan `res.partner`/`hr.employee`
   i.p.v. parallel datamodel.)*
2. **Connector-naad — niet uniform (empirisch bijgesteld, zie §6.2).** Connectors verschillen sterk
   in verwevenheid; behandel ze niet als één klasse:
   - **Smartschool = leaf** → schoon te extraheren naar **`ml_edu_smartschool`** (✓ bewezen, §6.2).
   - **Informat = géén leaf, maar ingestie-backbone** → structureel in de kern (org-sync-actie,
     SAP-pijplijn, res_config, betask-mappers). Extractie = **herontwerp**, geen move (§6.2).
   - **SAP-sync is NIET los van Informat**: de SAP-sync ís de Informat-analyse/review-pijplijn — één
     gekoppelde pijplijn in de kern. (Corrigeert de eerdere aanname "SAP blijft kernel, Informat→edu".)
   - LDAP/Google: nog te bekijken; vermoedelijk eerder backbone dan leaf.
3. **Admin-naad.** BRSO/SRBR-wizards in `ml_admin` zijn onderwijs-rolconcepten → naar **`ml_edu_admin`**
   (admin-plugin). `ml_admin` blijft generieke identiteits-/betask-UI én levert de extensiepunten.

### 6.1 Extensiepunt-patroon (plugin op de generieke admin)

**Éénrichtingsregel.** De generieke admin/kern noemt **nooit** een editie-begrip (geen `if person.insz`,
geen `informat` in core). Hij biedt extensiepunten; de plugin vult ze in. Afhankelijkheid loopt
`ml_edu_*` → `ml_admin`, **nooit** omgekeerd — dezelfde regel als de repo-grens, één niveau dieper.
Uitsluitend `_inherit`/view-inheritance/menu-extensie; **geen monkey-patch** (§9).

**Connector-interface (abstract-model-registry).** De kern definieert een domein-neutrale interface;
elke connector-plugin implementeert ze, en de betask-processor roept ze generiek aan zonder één naam
te kennen:

```python
# melira-platform — het extensiepunt
class MlDirectoryConnector(models.AbstractModel):
    _name = "ml.directory.connector"
    def sync_person(self, person): return          # default no-op
    def on_person_created(self, person): return

# melira-education/ml_edu_smartschool — de plugin (leaf-connector, ✓ bewezen §6.2)
class MlSmartschoolConnector(models.Model):
    _name = "ml.connector.smartschool"
    _inherit = "ml.directory.connector"            # implementeert de interface
    def sync_person(self, person):
        ...                                         # Smartschool-push
```

De processor dispatcht over alle modellen die de interface implementeren. Config + secret van de
connector zitten in de plugin-module (edu), nooit in de kern — meteen goed voor de PII/security-scheiding.

> Variant: i.p.v. de abstract-model-registry kan een data-gedreven `ml.connector.provider`-model
> (één record per actieve connector → wijst naar het implementerende model) handiger zijn voor
> aan/uit-per-instance via config. Voor pure code-koppeling volstaat de abstract-model-registry.

### 6.2 Empirisch — connector-naad geprototyped (myschool-codebase, 2026-06)

De connector-naad is op de huidige `myschool`-codebase geprototyped (branch `Dev-core-seams`), onder
de huidige namen (de `ml_`-rename komt later, §11). Twee bevindingen die de architectuur bijsturen:

**Smartschool = leaf, schoon extraheerbaar (✓ gedaan).** Een keystone-extensiepunt op de
betask-processor (`_get_connector_betask_handlers` + drie no-op cascade-hooks) liet toe álle
Smartschool-handlers + cascade-emitters + modellen + config/service naar een aparte plugin te
verhuizen die `_inherit`t op de processor. De kern bevat daarna nul Smartschool-referenties; getest:
plugin-loze install + plugin-install + admin-zonder-plugin + admin+plugin, plus de volledige
testsuite identiek aan baseline (0 regressie). Dit ís het §6.1-patroon, bewezen werkbaar.

**Informat = ingestie-backbone, géén leaf — daarom GEFASEERD afgesplitst.** Anders dan Smartschool zit
Informat structureel in de kern. De afsplitsing is daarom in twee stukken gedaan:

**Stage-1 (✓ gedaan, Dev `91676a0`, 2026-06-14) — `myschool_edu_informat` (depends core+admin).** De
service/config/dto + admin-UI (wizard, config-view, test-runner-stappen) zijn verhuisd en de drie
echte core→Informat-module-naden geknipt:
- *org-sync-actie*: `action_sync_this_school` (knop + methode) → plugin (`_inherit myschool.org` +
  view-xpath). Core-`org` noemt geen Informat meer.
- *safeguard-config*: de drempel-velden bleken functioneel **SAP-sync**, niet Informat. Ze zijn naar
  een neutraal kernel-model `myschool.sap.sync.config` verhuisd (met data-migratie); `sap_sync_service`
  leest daaruit. De `res.config.settings`-reuse + het settings-blok verhuizen mee naar de plugin.
- *cron*: `ir_cron_sap_sync_auto` (reft het Informat-model) → plugin; de neutrale cleanup-cron blijft.
- Geverifieerd: 4 install-configs (core-Informat-vrij / plugin / admin-zonder / admin+plugin) + de
  migratie-upgrade + de volledige testsuite identiek aan baseline (0 regressie). Recon-correctie:
  **sync re-emit géén DB-betasks** (serialiseert het neutrale record naar `('API',*,'SYNC')`) → een
  slave raakt de Informat-handlers nooit, de plugin hoeft enkel op de master.

**Stage-2 (uitgesteld → PII-werf §10).** Wat in de kern blíjft is de eigenlijke ingestie: de
JSON→`person`/`person.details`/`org`-mappers + `_create/_update_person_from_*`-helpers, aangeroepen
vanuit de **generieke** `('DB',EMPLOYEE/STUDENT/…)`-betask-handlers (manuele edits lopen via aparte
`('MANUAL',…)`-handlers — de DB-ingestie is dus feitelijk Informat-only). Dit verhuizen via het
keystone-extensiepunt (`_get_connector_betask_handlers`) raakt **exact de PII-velden** (`insz`,
`reg_*`, het volledige JSON-archief) en hoort daarom bij de PII-/retentie-werf, samen met de
person-naad. Na Stage-1 is dit nog enkel **data-vorm-koppeling**, geen module-koppeling meer.

**person-naad idem uitgesteld.** `person.details`/`insz` zijn verweven met generieke admin-tooling
(een algemene rollback/cleanup-wizard rolt person.details-versies terug) en vergen de
PII-/retentiebeslissingen van §10 vooraf. Niet nu; bij de PII-werf.

---

## 7. Te verifiëren door MITRAS (open naden)

- **SAP-sync + Informat**: de connector-laag is afgesplitst (§6.2 Stage-1, `myschool_edu_informat`);
  de **safeguard-drempels** zijn neutraal geworden (`myschool.sap.sync.config`). Wat resteert is de
  Informat-JSON→record-ingestie in de generieke DB-betask-handlers (Stage-2) — koppelen aan de
  PII-/4-instance-werf (§10), want het raakt de PII-velden.
- **`kosten_dashboard`**: edu of platform? (hangt enkel aan core+dashboard → mogelijk platform)
- **`admin` BRSO/SRBR**: bestemming = `ml_edu_admin` (beslist); exacte omvang onderwijs-staart verifiëren.
- **`dashboard`-familie** (dashboard/directie/kosten): consolideren? (open vraag platform-review).
- **`processcomposer` vs `tasks`**: twee BPMN-families (`process.map.*` vs `ml.process.*`) —
  greenfield = hét moment om er één te deprecaten.

---

## 8. MCP-namespace rename

| Touchpoint | Van | Naar |
|---|---|---|
| Module (technisch) | `myschool_mcp` | `ml_mcp` |
| Claude Code server-registratie (naam, merklaag) | `myschool` | `melira` |
| Tool-namespace (client) | `mcp__myschool__*` | `mcp__melira__*` |
| Remote host (infra/DNS — olvp-ict werf) | `myschool-ict.olvp.be` | `melira-*.olvp.be` (TBD) |
| `db_user`, DB-naam, `odoo.conf` | `myschool` | `melira` |

Provider-prefixen (`appfoundry_*`, `projects_*`) blijven — die dragen geen merknaam. De
registratienaam/host zit in de merklaag (triviaal herregistreerbaar). Na rename: nieuwe RPC-key op de
verse instance + `claude mcp remove myschool` / `claude mcp add ... melira ...`. Zie
[[project-myschool-mcp]] voor het key-beheer-recept.

---

## 9. Odoo-ecosysteem-integratie (doorlopend principe)

Melira draait ín Odoo en moet **náást/op** de standaard-suite + OCA leven, niet ertegenin. Bewaak
dit gedurende het hele project — vooral de business-editie zal Odoo's zakelijke apps willen.

- **Niet heruitvinden wat standaard bestaat.** Waar een Odoo-standaardmodel past, leun erop of brug
  ernaartoe i.p.v. een parallel model. Concreet aandachtspunt: `ml.person`/`ml.org` versus
  `res.partner`/`hr.employee` (kernel hangt al aan `hr`). Overweeg een dunne brug- of
  delegatie-relatie zodat standaard Odoo (Contacten/HR) blijft werken.
- **Co-existentie i.p.v. vervanging (business).** `ml_business` moet **naast** Odoo Accounting/CRM/
  Sales/Inventory/Project kunnen draaien. Vermijd harde botsingen op die domeinen.
- **Geen monkey-patching van Odoo-core.** Uitsluitend `_inherit`/`_inherits`; respecteer de
  upgrade-baarheid naar volgende Odoo-versies.
- **Integratie-bruggen optioneel en dun.** Koppelingen naar standaard/OCA-modules als aparte,
  optionele modules (bv. `ml_hr_bridge`, `ml_project_bridge`) zodat een klant ze à la carte kan
  toevoegen — niet hard in de kernel bedraden.
- **Dependencies expliciet.** `external_dependencies` (python/bin) en Odoo/OCA-module-deps netjes in
  de manifests; per editie/overlay duidelijk welke standaard-apps vereist zijn.
- **Per-klant overlays** (§2.2) kunnen gericht specifieke Odoo/OCA-modules als dependency toevoegen
  zonder het platform te belasten.

> MITRAS-actie: bij elke tier-beslissing toetsen "bestaat hier al een Odoo/OCA-standaard voor, en
> botsen we ermee?" — en de `ml.person`/`ml.org` ↔ `res.partner`/`hr.employee`-brug expliciet
> ontwerpen.

---

## 10. Convergentie — één greenfield-beweging lost meerdere dossiers op

- **Security-review HOOG #4** (`person.details` te breed leesbaar) → opgelost zodra school-PII in
  `ml_edu_person` met strikte groep zit. Zie [[project_security_review_2026_06]].
- **Platform-review "core afslanken"** (connectors → aparte modules; 4-instance-split) → ís de
  kernel/`ml_edu_connect`-splitsing. Zie [[project_platform_review_2026_06]].
- **PII-datadomein** (kern-identiteit vs account/directory vs app-slaves) → valt samen met de
  tier-grens kernel ↔ `ml_edu_person`. Zie [[project_arch_split_admin_apps]].

→ Rebranding + domein-tiering + PII-classificatie + connector-extractie = één keer goed, nul
migratierisico.

---

## 11. Greenfield transform-aanpak (geen migratie)

Tweefasige, deterministische transform van de huidige `extra-addons/` naar de verse repo's. Géén
DB-migratie — alles wordt mét nieuwe naam geschreven en daarna vers geprovisioneerd. **Let op de twee
verschillende vervangingen:**
- **Technische identifiers**: `myschool` → `ml` (mapnamen `myschool_`→`ml_`, model `myschool.`→`ml.`,
  XML-IDs + `ref=` + security-CSV `model_myschool_*`→`model_ml_*`, veldnamen, JS-registry/action-tags,
  MCP-module).
- **Zichtbare/merk-strings**: "MySchool"/"Myschool" → "Melira" (manifest `name`, UI-labels,
  mailteksten, docs).

**Fase A — vlakke rename** over de hele boom (beide vervangingen hierboven).

**Fase B — tier-prefix + repo-split + datamodel-naden**: onderwijs-modules → `ml_edu_*` (dir +
manifest + XML-ID-module; cross-refs bijwerken); extractie §6 (person-PII, connectors als plugins,
BRSO/SRBR → `ml_edu_admin`) uit core; extensiepunten in `ml_admin` definiëren; bundels `ml_business`
(repo `melira-business`) + `ml_education` (repo `melira-education`); modellen blijven plat `ml.*`;
de drie repo's splitsen + `addons_path`-profielen per editie.

**Verificatie** (per editie, verse DB): `-i ml_business` (platform + business) en `-i ml_education`
(platform + education) op lege DB → install + bestaande test-suites groen. Geen upgrade-pad; faalt
iets, dan broncode-fout, geen dataverlies.

---

## 12. Werkvolgorde voor MITRAS

1. **Repo's + accounts** vastleggen (3 repo's: `melira-platform`/`-business`/`-education`, GitHub TBD),
   `addons_path`-profielen, CI per repo.
2. **Transform-script** (fase A, beide vervangingen §11) + dry-run-diff reviewen.
3. **Platform** (kernel/core + common) naar `melira-platform`; extensiepunten in `ml_admin` (§6.1);
   `ml_business`-bundle + `ml_biz_admin` naar `melira-business`; verse install groen.
4. **Datamodel-naden** (§6): core afslanken. **Niet uniform — zie §6.2:** `ml_edu_smartschool` is een
   schone move (bewezen); **`ml_edu_informat` + SAP + de person-naad (`ml_edu_person`) vergen eerst een
   herontwerp** (ingestie-backbone achter extensiepunten + PII-/retentiebeslissingen) → eigen
   ontwerp-stap gekoppeld aan de PII-werf (§10), niet zomaar meenemen. `ml_edu_admin` (BRSO/SRBR) los
   te onderzoeken. `ml.person`↔`res.partner`/`hr.employee`-brug ontwerpen (§9).
5. **Education** naar `melira-education`; `ml_education`-bundle; verse install (platform+education) groen.
6. **MCP-rename** (§8) + her-registratie + infra/DNS-ticket (olvp-ict werf).
7. **Provisioning**: verse business- en education-instances via `ml_servermanager`.
8. **Decommissioning** oude `test`-instance + repo `odoo-myschool` archiveren.
9. **(Later)** overlay-repo-template `melira-cust-*` voor de eerste klant met eigen apps (§2.2).

Pre-conditie: naam **Melira** juridisch bevestigd (BOIP) vóór externe publicatie/DNS. Interne
greenfield-bouw kan vooruit; externe namen als laatste. Dankzij de `ml_`-ontkoppeling (§5) blijft een
late merkwijziging sowieso buiten de code.

---

## 13. Frontend-strategie — headless-posture (beslist 2026-06-13)

**Keuze: Odoo blijft, de presentatielaag wordt ontkoppeld. Géén platformmigratie naar
Django + Vue.** De pijnpunten (views-als-data is star; native install lastig) zitten in de
*presentatie* en *deploy*, niet in wat Odoo gratis geeft (ORM, ACL/record rules, betask-pipeline,
connectors, sync, multi-company, MCP). Een volledige rewrite gooit die dure helft weg (~1-2 jaar om op
feature-pariteit te komen) om het minst-erge probleem op te lossen.

```
   ┌─────────────── presentatie (vervangbaar) ───────────────┐
   │  Learning Assistant   admin-SPA        leerling-portaal   │
   │  (Vue ✓)              (Vue/OWL)        (later)            │
   └───────────────┬──────────────┬───────────────┬───────────┘
                   │  JSON-RPC / REST / MCP  (versioneerd contract)
   ┌───────────────┴──────────────────────────────────────────┐
   │  Odoo = system-of-record + business-logica + auth         │
   │  betask · connectors · sync · ACL · multi-company         │
   └───────────────────────────────────────────────────────────┘
```

**Bewijs van haalbaarheid.** De Learning Assistant is al **herwerkt van Next.js naar Vue.js in een
halve dag** — bewuste keuze tégen een big-tech-frontend. Dat toont dat de frontend tegen een stabiel
API-contract een weekendklus is om te wisselen, geen migratie.

**Toepassing (greenfield = goedkoopste moment om in te bakken):**
- `ml_core` **headless-vriendelijk**: alle logica in models/services, niets cruciaals dat enkel via
  een Odoo-view bereikbaar is (betask dwingt dit al grotendeels af).
- Eigen UX = OWL-workspace of externe **Vue-SPA**; Odoo's XML-views blijven voor ICT-admin-CRUD, waar
  starheid net een voordeel is (snel, gratis, onderhoudsarm).
- **JSON-RPC/MCP als versioneerd publiek API-contract** behandelen → frontend vervangen wordt
  additief, geen rewrite. Sluit aan op de API-first 4-instance-split (§10, [[project-arch-split-admin-apps]]).

**Heroverweeg een volledige overstap pas als ≥2 van 3 waar zijn:** (1) de frontend wórdt het
product/differentiator; (2) Odoo's breaking-change-last (`<tree>`→`<list>`, `category_id`/`name_get`
weg) weegt structureel zwaarder dan wat de ORM bespaart; (3) je wil weg van de AGPL/Odoo-SA-binding om
commerciële redenen.
