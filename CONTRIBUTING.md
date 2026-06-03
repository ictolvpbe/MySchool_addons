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
