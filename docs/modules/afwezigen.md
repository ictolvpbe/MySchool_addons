# afwezigen

Overzicht van afwezige medewerkers door activiteiten. Aggregeert per dag/periode wie afwezig is en welke vervanging er gepland is.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `activiteiten` |
| Wordt gebruikt door | `planner` (impliciet, voor inhaal-planning) |

## Doel

Wanneer een leerkracht een activiteit doet, is hij/zij niet beschikbaar voor reguliere lessen. Deze module geeft beheerders zicht op wie wanneer afwezig is, zodat:

- Vervangingen kunnen worden gepland (zie [`planner`](planner.md))
- Lesroosters tijdelijk aangepast kunnen worden
- HR-overzicht (afwezigheid per leerkracht over de tijd) beschikbaar is

## Architectuur

Geen eigen entiteiten (bouwt op `activiteiten`-records). Pure aggregatie + views.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`activiteiten`](activiteiten.md) — bron-data (depends op deze)
- [`planner`](planner.md) — inhaalplannen
