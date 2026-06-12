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
| 8 | **Repo-split: platform+business in repo A, education in repo B.** | Kan, want dependency-richting loopt al éénrichting (vertical → platform, nooit omgekeerd). |
| 9 | **Per-klant maatwerk mag in een aparte overlay-repo.** | Klant-/school-specifieke apps als additieve laag bovenop een editie (§2.2). |
| 10 | **Integratie met het Odoo-ecosysteem is een doorlopend ontwerpprincipe.** | Bouwen náást/op standaard Odoo + OCA, niet ertegenin (§9). |
| 11 | **Technische namespace merk-neutraal `ml_`/`ml.`** (modules, modellen, tabellen, XML-IDs, velden); "Melira" enkel in de merklaag. | Een latere gedwongen merkwijziging (bv. Melira→Melirax wegens merkenschending) raakt **enkel** manifest-`name`, repo-namen, DNS en docs — **nul impact op code/data** (§5). |

---

## 2. Repo-topologie

### 2.1 Twee product-repo's

De afhankelijkheid loopt **strikt één kant op**: een vertical hangt af van het platform, nooit
omgekeerd. Geverifieerd uit de huidige dependency-graph — geen enkele platform-module verwijst naar
een business- of education-module.

```
┌──────────────────────────────────────────────────────────────┐
│ REPO A — melira-platform   (account: TBD; kandidaat publiek)   │
│                                                                │
│  TIER 1 · PLATFORM                                             │
│    Kernel        ml_core · ml_theme · ml_admin · ml_oidc ·     │
│                  ml_sync · ml_servermanager                    │
│    Gedeelde apps ml_projects · ml_appfoundry · ml_itsm ·       │
│                  ml_assets · ml_knowledge · ml_tasks ·         │
│                  ml_processcomposer · ml_mcp · ml_dashboard    │
│                                                                │
│  TIER 2 · BUSINESS                                             │
│    Verticals     ml_biz_*  (greenfield, leeg)                 │
│    Bundle        ml_business                                   │
└──────────────────────────────────────────────────────────────┘
                          ▲  depends (éénrichting)
                          │
┌──────────────────────────────────────────────────────────────┐
│ REPO B — melira-education  (account: TBD; privé aanbevolen)     │
│                                                                │
│  TIER 3 · EDUCATION                                           │
│    Verticals     ml_edu_lessenrooster · ml_edu_activiteiten ·  │
│                  ml_edu_drukwerk · ml_edu_professionalisering ·│
│                  ml_edu_planner · ml_edu_directie_dashboard ·  │
│                  ml_edu_kosten_dashboard ·                     │
│                  ml_edu_connect · ml_edu_person                │
│    Bundle        ml_education                                   │
└──────────────────────────────────────────────────────────────┘
```

> Repo-namen dragen wél het merk (`melira-…`) — dat is de merklaag (§5) en een repo hernoemen is
> triviaal (GitHub-rename + `git remote set-url`), zonder code-impact.

**Waarom dit werkt.** Een Odoo-instance laadt meerdere repo's op zijn `addons_path` (zoals OCA).
- **Business-instance**: repo A → installeert `ml_business`.
- **Education-instance**: repo A **+** repo B → installeert `ml_education`.

**Waarom education privé.** Repo B bevat de Belgische onderwijs-integraties (Smartschool/Informat)
en de school-PII-extensies (INSZ, stamboeknummer, gezinsdump). Gevoeliger en specifieker dan het
generieke platform; scheidt ook wat ooit open/commercieel kan versus wat schoolgebonden blijft.

### 2.2 Per-klant overlay-repo's (toekomst)

Als later **meerdere scholen of bedrijven** eigen apps nodig hebben, krijgt elke klant een **aparte
overlay-repo** — géén product-tier, maar een deployment-laag bovenop een editie:

```
   melira-platform  ──►  melira-education  ──►  melira-cust-<school-X>
        (A)                    (B)                  (overlay, privé)
```

- Naampatroon: repo `melira-cust-<klant>` (merklaag) met modules `ml_<klantprefix>_<naam>`.
- **Strikt additief**: enkel `_inherit`, nieuwe modellen, nieuwe views — **nooit** upstream-code
  forken of monkey-patchen. Zo blijft het platform/vertical-onderhoud single-source.
- `addons_path` van die klant-instance = platform (+ editie) + de overlay-repo.
- Generiek maatwerk dat meerdere klanten willen → promoveren naar de vertical of het platform;
  écht klant-specifiek blijft in de overlay. (Periodiek terug-promoveren voorkomt drift.)

Dit is exact het Odoo-partnermodel voor klant-customisaties en houdt de product-repo's schoon.

---

## 3. Het 3-tier-model

| Tier | Repo | Inhoud | Regel |
|---|---|---|---|
| **1 · Platform** | A | **Kernel** (`ml_core` + identiteit org/person/role/proprelation, proces, betask, toegang, sys.event, settings, sync-framework, generieke connectors LDAP/Google/SAP) **+ gedeelde apps** (projects, appfoundry, itsm, assets, knowledge, tasks, processcomposer, mcp, dashboard). | Domein-agnostisch, bruikbaar in elke editie. Gedeelde apps = single-source, geen fork. |
| **2 · Business** | A | `ml_biz_*`-verticals + bundle `ml_business`. | Hangt af van platform. Nu greenfield. |
| **3 · Education** | B | `ml_edu_*`-verticals + bundle `ml_education`. | Hangt af van platform. |

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

### Tier 1 · Platform — Kernel  ·  repo A

| Huidige module | → Nieuwe module | Zichtbare naam | Opmerking |
|---|---|---|---|
| `myschool_core` | `ml_core` | Melira Core | **Afslanken**: school-PII + Smartschool/Informat eruit (§6). |
| `myschool_theme` | `ml_theme` | Melira Theme | |
| `myschool_admin` | `ml_admin` | Melira Admin | ⚠ BRSO/SRBR-wizards zijn onderwijs-specifiek → naar edu (§7). |
| `myschool_oidc` | `ml_oidc` | Melira OIDC (Keycloak) | |
| `myschool_sync` | `ml_sync` | Melira Sync | |
| `myschool_servermanager` | `ml_servermanager` | Melira Server Manager | |

### Tier 1 · Platform — Gedeelde apps  ·  repo A

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

### Tier 2 · Business  ·  repo A  ·  prefix `ml_biz_`

Nog geen modules — greenfield. Eerste biz-vertical `_inherit`t `ml.person` voor business-velden (§6)
en hangt aan het platform. Bundle: `ml_business` (zichtbaar "Melira for Business").

### Tier 3 · Education  ·  repo B  ·  prefix `ml_edu_`

| Huidige module | → Nieuwe module | Zichtbare naam | Opmerking |
|---|---|---|---|
| `myschool_lessenrooster` | `ml_edu_lessenrooster` | Lessenrooster | |
| `myschool_activiteiten` | `ml_edu_activiteiten` | Activiteiten | |
| `myschool_drukwerk` | `ml_edu_drukwerk` | Afdrukcentrum | |
| `myschool_professionalisering` | `ml_edu_professionalisering` | Professionalisering | |
| `myschool_planner` | `ml_edu_planner` | Planner | |
| `myschool_directie_dashboard` | `ml_edu_directie_dashboard` | Directie Dashboard | |
| `myschool_kosten_dashboard` | `ml_edu_kosten_dashboard` | Kosten Dashboard | ⚠ Kandidaat voor **platform** i.p.v. edu — verifiëren (§7). |
| *(nieuw, uit core)* | `ml_edu_connect` | Smartschool/Informat-koppeling | Extractie connectors uit core (§6). |
| *(nieuw, uit core)* | `ml_edu_person` | Onderwijs-persoonsgegevens | Extractie INSZ/`person.details` uit core (§6). |

Bundle: `ml_education` (zichtbaar "Melira for Education"), repo B.

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

## 6. Datamodel-naden (de echte herstructurering)

Drie naden waarlangs de kernel wordt afgeslankt — méér dan rename: de domein-splitsing die de
4-instance-split en PII-classificatie tóch al vroegen (§10).

1. **`person`-naad.** Kernel definieert generiek `ml.person(person_type)`. Onderwijs-velden (`insz`,
   `stamboeknummer`, `person.details`-dump = INSZ/bankrekening/gezinssamenstelling) verhuizen uit
   `core/models/person.py` + `person_details.py` naar **`ml_edu_person`** (dat `ml.person` `_inherit`t;
   model `ml.person.details`). Business `_inherit`t later voor eigen velden. → Kernel draagt geen
   domein-PII meer. *(Integratie-noot §9: weeg of `ml.person` koppelt aan `res.partner`/`hr.employee`
   i.p.v. parallel datamodel.)*
2. **Connector-naad.** `smartschool_*`, `informat_*` (DTO + service + config) verhuizen uit core naar
   **`ml_edu_connect`**. **SAP-sync** = generiek-enterprise → blijft kernel (verifiëren). LDAP/Google
   blijven kernel.
3. **Admin-naad.** BRSO/SRBR-wizards in `ml_admin` zijn onderwijs-rolconcepten → naar edu (bv.
   `ml_edu_person` of `ml_edu_admin`). `ml_admin` blijft generieke identiteits-/betask-UI.

---

## 7. Te verifiëren door MITRAS (open naden)

- **SAP-sync**: kernel-generiek of toch edu/biz? (§6.2)
- **`kosten_dashboard`**: edu of platform? (hangt enkel aan core+dashboard → mogelijk platform)
- **`admin` BRSO/SRBR**: exacte omvang onderwijs-staart; waarheen.
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
manifest + XML-ID-module; cross-refs bijwerken); extractie §6 (person-PII, connectors, BRSO/SRBR) uit
core; bundels `ml_business` (A) + `ml_education` (B); modellen blijven plat `ml.*`; repo A/B splitsen
+ `addons_path`-profielen per editie.

**Verificatie** (per repo, verse DB): `-i ml_business` (A alleen) en `-i ml_education` (A+B) op lege
DB → install + bestaande test-suites groen. Geen upgrade-pad; faalt iets, dan broncode-fout, geen
dataverlies.

---

## 12. Werkvolgorde voor MITRAS

1. **Repo's + accounts** vastleggen (GitHub TBD), `addons_path`-profielen, CI per repo.
2. **Transform-script** (fase A, beide vervangingen §11) + dry-run-diff reviewen.
3. **Platform** (kernel + gedeelde apps) naar repo A; `ml_business`-bundle; verse install groen.
4. **Datamodel-naden** (§6): core afslanken, `ml_edu_person`/`ml_edu_connect`; `ml.person`↔
   `res.partner`/`hr.employee`-brug ontwerpen (§9).
5. **Education** naar repo B; `ml_education`-bundle; verse install (A+B) groen.
6. **MCP-rename** (§8) + her-registratie + infra/DNS-ticket (olvp-ict werf).
7. **Provisioning**: verse business- en education-instances via `ml_servermanager`.
8. **Decommissioning** oude `test`-instance + repo `odoo-myschool` archiveren.
9. **(Later)** overlay-repo-template `melira-cust-*` voor de eerste klant met eigen apps (§2.2).

Pre-conditie: naam **Melira** juridisch bevestigd (BOIP) vóór externe publicatie/DNS. Interne
greenfield-bouw kan vooruit; externe namen als laatste. Dankzij de `ml_`-ontkoppeling (§5) blijft een
late merkwijziging sowieso buiten de code.
