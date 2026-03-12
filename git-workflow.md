# Git Branch Workflow voor Extra-Addons

## Overzicht

```
master          ●────────●─────────────────●──────────● (stabiel, productie-klaar)
                          \               /
dev             ●──●───●───●──●───●──●───● (integratie-branch)
                    \     /       \     /
feature/...          ●──●         ●──●   (per app/feature)
```

## Branches

| Branch | Doel | Wie pusht |
|--------|------|-----------|
| `master` | Stabiele, geteste code. Alleen merges vanuit `dev`. | Nooit direct — alleen via merge |
| `dev` | Integratie-branch. Hier komen alle feature-branches samen. | Merge vanuit feature-branches |
| `feature/<app>-<beschrijving>` | Werk aan één specifieke app of feature. | Jij, tijdens ontwikkeling |

## Git Commando's in het Kort

| Commando | Wat doet het |
|----------|-------------|
| `git checkout <branch>` | Wissel naar een andere branch. Je werkbestanden veranderen mee naar de staat van die branch. |
| `git checkout -b <naam>` | Maak een nieuwe branch aan én wissel er meteen naartoe. De nieuwe branch start vanaf waar je nu staat. |
| `git pull origin <branch>` | Haal de nieuwste wijzigingen op van GitHub en voeg ze samen met je lokale branch. Combinatie van `fetch` + `merge`. |
| `git merge <branch>` | Voeg de wijzigingen van een andere branch samen in je huidige branch. Bij conflicten moet je die handmatig oplossen. |
| `git push origin <branch>` | Stuur je lokale commits naar GitHub zodat anderen ze ook hebben. |
| `git add <bestanden>` | Markeer bestanden voor de volgende commit (staging). |
| `git commit -m "bericht"` | Sla de gestage wijzigingen op als een snapshot met een beschrijving. |
| `git clone <url>` | Download een volledige repository van GitHub naar je lokale machine. Eenmalig per server. |
| `git branch -d <naam>` | Verwijder een lokale branch (alleen als deze al gemerged is). |

> **Wat is `origin`?** `origin` is niet je lokale branch — het is de standaardnaam voor de **remote** (= je repository op GitHub). Je ziet de URL met `git remote -v`. Voorbeeld: `git push origin dev` = "stuur mijn lokale `dev`-commits naar GitHub".

## Dagelijks Werken aan Eén App

### 1. Start een feature-branch vanuit `dev`

```bash
git checkout dev
git pull origin dev
git checkout -b feature/myschool-sync-initial
```

> Naamgeving: `feature/<app-naam>-<korte-beschrijving>`
> Voorbeelden: `feature/myschool-sync-initial`, `feature/process-mapper-svg-fix`, `feature/admin-persongroups`

### 2. Werk op je feature-branch

Commit regelmatig met duidelijke berichten:

```bash
git add myschool_sync/models/sync_target.py myschool_sync/models/sync_log.py
git commit -m "sync_target en sync_log modellen toegevoegd"
```

**Tips:**
- Commit per logische eenheid (niet alles in één grote commit)
- Stage specifieke bestanden, niet `git add .` (voorkomt dat je per ongeluk `.env` of grote bestanden meeneemt)
- Werk alleen aan bestanden van de app waar je mee bezig bent

### 3. Tussendoor: haal wijzigingen op van `dev`

Als `dev` ondertussen veranderd is (bv. door werk aan een andere app):

```bash
git checkout feature/myschool-sync-initial
git merge dev
```

Los eventuele merge-conflicten op en commit.

### 4. Feature klaar → merge naar `dev`

```bash
git checkout dev
git pull origin dev
git merge feature/myschool-sync-initial
git push origin dev
```

Test of alles nog werkt op `dev` (installeer/upgrade modules, start Odoo).

### 5. `dev` is stabiel → merge naar `master`

Wanneer `dev` getest is en klaar voor productie:

```bash
git checkout master
git pull origin master
git merge dev
git push origin master
```

### 6. Opruimen

Na een succesvolle merge kun je de feature-branch verwijderen:

```bash
git branch -d feature/myschool-sync-initial
```

## In PyCharm

### Branch wisselen
- Rechtsonder in de statusbalk staat de huidige branch → klik om te wisselen
- Of: **Git → Branches...** (Ctrl+Shift+`)

### Nieuwe branch aanmaken
1. **Git → Branches... → + New Branch**
2. Zorg dat je op `dev` staat voordat je de nieuwe branch aanmaakt
3. Vink "Checkout branch" aan

### Merge uitvoeren
1. Checkout de doel-branch (bv. `dev`)
2. **Git → Merge... → kies de bron-branch** (bv. `feature/myschool-sync-initial`)
3. Bij conflicten opent PyCharm automatisch de merge-tool (3-panel view)

### Commit & Push
- **Ctrl+K** → commit-venster (selecteer bestanden, schrijf bericht)
- **Ctrl+Shift+K** → push naar remote

## Vuistregels

1. **Nooit direct op `master` werken** — altijd via `dev` → `master` merge
2. **Eén feature-branch per app/taak** — voorkomt dat onaf werk andere apps blokkeert
3. **Kleine, frequente commits** — makkelijker te reviewen en terug te draaien
4. **Test op `dev` voordat je naar `master` merget** — start Odoo, upgrade modules, controleer logs
5. **Feature-branch leeft kort** — merge zodra de feature werkt, laat geen weken-oude branches rondslingeren

## Deployen naar Test- en Productieserver

```
GitHub repo
    │
    ├── dev branch ────── git pull ────── TESTSERVER  (extra-addons/)
    │
    └── master branch ─── git pull ────── PRODUCTIESERVER (extra-addons/)
```

### Eerste keer: repository clonen

**Testserver** (gebruikt `dev` branch):

```bash
cd /opt/odoo
git clone -b dev https://github.com/<user>/extra-addons.git extra-addons
```

**Productieserver** (gebruikt `master` branch):

```bash
cd /opt/odoo
git clone -b master https://github.com/<user>/extra-addons.git extra-addons
```

> `-b dev` of `-b master` zorgt dat meteen de juiste branch wordt uitgecheckt.
> Pas het pad (`/opt/odoo`) aan naar de locatie van je Odoo-installatie.

### Updaten: nieuwe code ophalen

Wanneer er wijzigingen zijn gepusht naar GitHub:

**Testserver:**

```bash
cd /opt/odoo/extra-addons
git pull origin dev
sudo systemctl restart odoo    # of je eigen herstart-commando
```

**Productieserver:**

```bash
cd /opt/odoo/extra-addons
git pull origin master
sudo systemctl restart odoo
```

### Na het updaten: modules upgraden in Odoo

Als er modelwijzigingen zijn (nieuwe velden, views, security), moet je de module ook upgraden in Odoo:

```bash
# Via commandline
odoo -u myschool_sync -d <databasenaam> --stop-after-init

# Of via de Odoo UI: Apps → zoek de module → Upgrade
```

### SSH-toegang voor private repositories

Als de repository privé is, gebruik dan SSH in plaats van HTTPS:

```bash
# Clone via SSH (vereist SSH-key op de server + in GitHub)
git clone -b dev git@github.com:<user>/extra-addons.git extra-addons
```

## Versies van Apps (Odoo Module Versioning)

### Hoe werkt het

Elke Odoo-module heeft een versienummer in `__manifest__.py`. Dit nummer bepaalt of Odoo een upgrade nodig acht.

```python
# myschool_sync/__manifest__.py
{
    'name': 'MySchool Sync',
    'version': '0.1',     # ← dit is het versienummer
    ...
}
```

### Versienummer-schema

Gebruik **major.minor** (of **major.minor.patch**):

| Versie | Wanneer ophogen | Voorbeeld |
|--------|----------------|-----------|
| **major** (1.x → 2.0) | Grote wijzigingen, breaking changes, nieuwe architectuur | Volledige herwerking van sync protocol |
| **minor** (0.1 → 0.2) | Nieuwe features, extra velden, nieuwe views | School-filter toegevoegd aan sync |
| **patch** (0.2.0 → 0.2.1) | Bugfixes, kleine aanpassingen | Fout in serializer opgelost |

### Concreet: versie ophogen

Bij elke release naar `dev` (of `master`), pas het versienummer aan in `__manifest__.py`:

```python
# Was:
'version': '0.1',

# Wordt (na toevoegen school-filter feature):
'version': '0.2',
```

Commit deze wijziging samen met de feature:

```bash
git add myschool_sync/__manifest__.py
git commit -m "bump myschool_sync naar 0.2 — school-filter toegevoegd"
```

### Git tags voor releases (optioneel)

Je kunt versies ook markeren met git tags. Handig om later snel terug te vinden welke code bij welke versie hoort.

```bash
# Tag aanmaken na merge naar master
git checkout master
git tag -a myschool_sync-v0.2 -m "myschool_sync 0.2: school-filter"
git push origin myschool_sync-v0.2
```

Alle tags bekijken:

```bash
git tag -l "myschool_sync-*"
# myschool_sync-v0.1
# myschool_sync-v0.2
```

Code van een specifieke versie bekijken:

```bash
git show myschool_sync-v0.2
```

### Meerdere apps, onafhankelijke versies

Elke app in `extra-addons/` heeft zijn eigen versienummer:

```
extra-addons/
├── myschool_core/       __manifest__.py → version: '0.5'
├── myschool_admin/      __manifest__.py → version: '0.3'
├── myschool_sync/       __manifest__.py → version: '0.1'
└── process_mapper/      __manifest__.py → version: '0.2'
```

Ze leven in dezelfde git repository maar de versies zijn onafhankelijk. Bij een release hoef je alleen de versie op te hogen van de app(s) die gewijzigd zijn.

## Voorbeeld: Werken aan myschool_sync

```bash
# Start
git checkout dev && git pull origin dev
git checkout -b feature/myschool-sync-initial

# Werk...
git add myschool_sync/
git commit -m "module skeleton en manifest"
# ... meer werk en commits ...

# Versie ophogen
# → pas version aan in __manifest__.py
git add myschool_sync/__manifest__.py
git commit -m "bump myschool_sync naar 0.1"

# Klaar, merge naar dev
git checkout dev && git pull origin dev
git merge feature/myschool-sync-initial
git push origin dev

# → Test op testserver: ssh testserver, cd extra-addons, git pull origin dev

# Alles getest, merge naar master
git checkout master && git pull origin master
git merge dev
git push origin master
git tag -a myschool_sync-v0.1 -m "myschool_sync 0.1: eerste release"
git push origin myschool_sync-v0.1

# → Update productieserver: ssh prodserver, cd extra-addons, git pull origin master

# Opruimen
git branch -d feature/myschool-sync-initial
```
