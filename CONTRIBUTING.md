# Bijdragen aan MySchool_addons

Voor developers die aan de MySchool Odoo-modules werken.

## Werkstation-setup

### 1. Repo clonen + branch

```bash
git clone git@github.com:ictolvpbe/MySchool_addons.git
cd MySchool_addons
git checkout Dev    # of een Dev-<Topic> feature-branch
```

### 2. Lokale Odoo

PyCharm is de standaard-IDE. Setup:

1. Open `/home/demm/PyCharm/odoo-myschool/` als project (gebruik path die voor jou geldt)
2. Python-interpreter: "Python 3.13 (PyCharm)" (PyCharm-managed venv met Odoo + deps geïnstalleerd)
3. Run-config voor Odoo: bestaat al in `.idea/runConfigurations/` (legacy lokale config)
4. DB-keuze: `odoo-dev` is de standaard dev-DB op localhost:5432 (user `myschool`, pw in `config/odoo.conf`)

### 3. Module installen lokaal

In Odoo UI (na inloggen als admin):
- **Apps** → **Update Apps List** (Developer mode aan!)
- Zoek module-naam → **Install**

Via CLI (alternatief):
```bash
odoo -c config/odoo.conf -d odoo-dev -i <module> --stop-after-init
```

### 4. Tests draaien

Per module:
```bash
odoo -c config/odoo.conf -d <testdb> -i <module> --test-tags <module> --stop-after-init
```

`<testdb>` bestaat liefst niet vooraf (test-runner maakt/dropt). Voor herhaald gebruik: zorg dat `<testdb>` niet productiedata bevat.

> **Pre-productie-vereiste:** vóór een productie-release moeten **alle apps** automatische tests hebben (TransactionCase/HttpCase), niet enkel `myschool_projects`. De meeste modules zijn nu enkel handmatig getest. Welke apps + welke scope = nog te bepalen.

## App-architectuur — hoe de modules zijn opgebouwd

De ~18 modules volgen een beperkt aantal patronen. Diepere uitwerking: [`docs/architecture/`](docs/architecture/) (module-graph, data-model, MCP) en [`docs/modules/`](docs/modules/) (per-module overzicht).

| Patroon | Voorbeelden | Kenmerk |
|---|---|---|
| **Core data-laag** | `myschool_core` | Álle gedeelde datamodellen met `myschool.*`-prefix (org, person, role, period, process, asset, …). Mutaties op org/person/role/proprelation lopen verplicht via de **betask-pipeline** (`myschool.manual.task.service.create_manual_task`), niet via directe `create/write`. |
| **Frontend-only UI-app** | `myschool_tasks`, `myschool_processcomposer` | Geen eigen modellen — die wonen in `myschool_core`. De module levert enkel views/menu's/OWL-componenten en `depends` op core. |
| **Self-contained app** | `myschool_appfoundry`, `myschool_projects` | Bezit **eigen modellen** in de module zelf (`appfoundry.*`, `myschool.project.*`), met views/security samen. `application=True`. Geen betask-pipeline nodig (geldt enkel voor de core-4). |
| **OWL2 client-action** | `myschool_admin` (object_browser), `myschool_dashboard`, `myschool_projects` (workspace) | Custom frontend-scherm via `registry.category("actions").add("<tag>", Component)` + een `ir.actions.client`-record. Assets in `static/src/{js,xml,css}`. |
| **MCP-server** | `myschool_mcp` | JSON-RPC 2.0 over `POST /mcp` (X-API-Key auth). Tools per domein in `providers/<naam>.py`, geregistreerd via `@McpRegistry.tool(...)`. Zie [`docs/architecture/mcp-architecture.md`](docs/architecture/mcp-architecture.md). |

**Module-skelet** (typisch):
```
<module>/
├── __manifest__.py          # name, depends, data, assets, application
├── models/                  # (self-contained/core) Python-modellen
├── views/                   # XML: list/form/kanban/search + menu's
├── security/                # res.groups (implied_ids) + ir.model.access.csv
├── static/src/{js,xml,css}/ # (OWL) client-action componenten
└── tests/                   # TransactionCase/HttpCase (test_*.py)
```

Odoo-19-conventies waar nieuwe code zich aan houdt: `<list>` i.p.v. `<tree>`; `widget="badge"` (geen `label_selection`); geen `<group>` in `<search>`; `res.users` heeft `group_ids` (niet `groups_id`); `ir.actions.act_window.target` kent geen `inline` meer; HTTP-routes met `auth='none'` zijn standaard read-only → zet `readonly=False` voor write-endpoints. OWL: component-prop-strings moeten binnen-quotes (`title="'X'"`).

## Apps lokaal draaien & testen (CLI)

Gebruik de project-venv-python: `/home/demm/PyCharm/.venv/bin/python` (zie [`docs/reference/`](docs/reference/) en `odoo-bin` onder `odoo/`). De DB-credentials staan in `config/odoo.conf` (user `myschool`).

```bash
# Verse install op een (wegwerp-)DB — valideert dat de module + deps schoon laden
odoo-bin -c config/odoo.conf -d <db> -i <module> --stop-after-init

# Module bijwerken na codewijziging (op een bestaande DB)
odoo-bin -c config/odoo.conf -d <db> -u <module> --stop-after-init

# Tests draaien (verse DB aangeraden)
odoo-bin -c config/odoo.conf -d <db> -i <module> --test-enable --test-tags <module> --stop-after-init

# Snelle model-/registry-check zonder UI
echo "print(env['myschool.project'].search_count([]))" | odoo-bin shell -c config/odoo.conf -d <db> --no-http
```

**Naast een draaiende dev-server** (poort 8069 bezet): geef de wegwerp-run een vrije poort mee, anders botst `HttpCase`/de webserver:
```bash
odoo-bin ... --http-port 8070 --gevent-port 8073
```

**Frontend (OWL) wijzigingen:**
- Na `-u <module>` worden de asset-bundles herbouwd → in de browser **hard refresh** (Ctrl+Shift+R), anders zie je de oude bundle.
- Een verse install/upgrade valideert XML/Python/asset-bundling, **maar OWL-templates compileren pas in de browser** — template-compile-fouten zie je dus enkel runtime. Test OWL-schermen altijd in de browser.

**Verse-install-smoke als veiligheidsnet:** vóór een merge naar `Dev` een module (of de geraakte set) op een wegwerp-DB installeren vangt grove laadfouten (ontbrekende databestanden, kapotte view-arch, verkeerde xmlid-volgorde) die een upgrade op een bestaande DB zou maskeren.

## Branch-strategie

| Branch | Doel |
|---|---|
| `master` | Productie (myschool, myschool-ict, id, myschool-acc) |
| `Dev` | Test + dev-omgevingen (myschool-test, myschool-dev, ...) |
| `Dev-<Topic>` | Feature-branch per ontwikkelaar/onderwerp |

**Case-sensitive**: `Dev` met hoofdletter D. Niet `dev`, niet `DEV`.

**Workflow**:
1. Vanuit `master`: `git checkout -b Dev-<Topic>`
2. Werk + commit (kleine, gefocuste commits)
3. Push naar GitHub: `git push -u origin Dev-<Topic>`
4. (Optioneel) Test op myschool-test via Semaphore Survey-override `addons_branch_override=Dev-<Topic>`
5. Merge naar `Dev` voor brede test-validatie
6. Merge naar `master` voor productie-deploy

Volledige conventie: [`docs/decisions/0002-branch-strategy.md`](docs/decisions/0002-branch-strategy.md).

## Commit-stijl

- **Taal**: Nederlands (consistent met platform-ansible + platform-handbook)
- **Imperatief**: "voeg X toe", "fix Y bug", "refactor Z module"
- **Lengte**: eerste regel ≤ 72 chars; optionele body met motivatie ("why", niet "what")
- **Body**: leeg laten als titel volstaat. Anders: één lege regel + body. Body legt context uit (Wat was het probleem? Welke aanpak overwogen?).

Voorbeelden (uit recente commits):

```
myschool_mcp : start
```

```
appfoundry: fix sprint-velocity calc bij mid-sprint join

Bug: items die mid-sprint toegevoegd werden telden niet in velocity-baseline.
Fix: gebruik sprint.start_date als ijkpunt, niet item.create_date. Sluit
aan op de Scrum-conventie "scope-creep telt niet voor velocity-meting".
```

## Code-conventies (samenvatting)

- Python: PEP 8 + Odoo's eigen Odoo Guidelines (zie `styleguide.md` — wordt verplaatst naar `docs/guides/styleguide.md`)
- XML-views: 4-space indent, alphabetic attribute order voor consistency
- Markdown-docstrings in module-README's

## ADRs schrijven

Wanneer je een belangrijke architectuur- of design-beslissing neemt:
1. Kopieer [`docs/decisions/0000-template.md`](docs/decisions/0000-template.md) naar nieuwe file
2. Increment het nummer (kijk eerst welke hoogste is)
3. Vul Context / Opties / Beslissing / Gevolgen in
4. Voeg toe aan [`docs/decisions/README.md`](docs/decisions/README.md) index
5. Commit met message `adr: NNNN — <korte titel>`

## Hulp

- **Architectuur-vragen**: zie [`docs/architecture/`](docs/architecture/) of de bestaande ADRs in [`docs/decisions/`](docs/decisions/)
- **Operations-vragen** (deploy/upgrade/backup): zie [`docs/operations/`](docs/operations/)
- **Infrastructuur-vragen** (HAProxy, Caddy, Ansible, Semaphore): zie verwante repo [`platform-handbook`](https://github.com/ictolvpbe/platform-handbook)
- **Claude-context**: zie [`CLAUDE.md`](CLAUDE.md) in repo-root
