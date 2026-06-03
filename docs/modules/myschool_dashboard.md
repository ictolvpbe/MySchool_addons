# myschool_dashboard

Persoonlijk dashboard met overzicht van alle taken voor de ingelogde gebruiker. Aggregeert taken uit verschillende MySchool-modules (activiteiten, professionalisering, evt. ITSM, devhub) in één view.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `myschool_core`, `professionalisering`, `activiteiten` |

## Doel

Verschillende modules creëren taken/uitstaande items per gebruiker. Zonder dashboard zou je elke module apart moeten openen om "wat staat er voor mij open?" te beantwoorden.

Dashboard aggregeert:

- **Activiteiten** — waar je organizer/verantwoordelijke bent
- **Professionalisering** — openstaande aanvragen, deadlines
- **Toekomst**: ITSM-tickets, devhub-items, etc.

## Categorie-fit

Verschilt van `myschool_directie_dashboard` (een ander dashboard voor schoolleiding) — focus hier is per individu, niet rapportage-overzicht.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`activiteiten`](activiteiten.md) — bron-data
- [`professionalisering`](professionalisering.md) — bron-data
- [`myschool_core`](myschool_core.md) — Person/Role fundament
