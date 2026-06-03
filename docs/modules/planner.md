# planner

Inhaalplannen voor klassen die afwezig waren door activiteiten. Plannings-laag bovenop `activiteiten` + `afwezigen` voor het inplannen van vervangmomenten.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `mail`, `myschool_admin`, `activiteiten` |

## Kern-entiteiten

(Op basis van `models/`-folder en `views/`)

| Entity | Doel |
|---|---|
| `Planner` | Hoofd-entiteit — een planning voor een afwezige les |
| `VervangingLine` | Concrete vervanging (welke leerkracht voor welke les) |
| `AfwezigeLeerkracht` | Per-leerkracht afwezigheidsplanning |
| `Tijdslot` | Tijdsloten waar les ingehaald kan worden |

## Functionaliteit

- **Free-slot-wizard**: zoekt vrije tijdsloten waarop een klas + vervangende leerkracht beide beschikbaar zijn
- **Sequence + view's** voor vervangings-overzicht per dag/week
- **Mail-templates** voor notificaties naar leerkrachten

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`activiteiten`](activiteiten.md) — bron van afwezigheden (depends op deze)
- [`afwezigen`](afwezigen.md) — overzicht afwezigen
- [`myschool_admin`](myschool_admin.md) — depends op deze
