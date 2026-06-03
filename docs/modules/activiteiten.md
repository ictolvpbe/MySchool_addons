# activiteiten

Aanvragen voor interne en externe schoolactiviteiten — beheer van workflow van aanvraag tot afsluiting (deelnemers, kosten, bus-allocatie, vervangingen).

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `mail`, `myschool_core`, `myschool_admin` |
| Wordt gebruikt door | `afwezigen`, `planner`, `myschool_dashboard` |

## Kern-entiteiten

(Op basis van `models/`-folder)

| Entity | Doel |
|---|---|
| `Activiteit` | Hoofd-entiteit — een geplande activiteit |
| `ActiviteitenAction` | Workflow-acties (goedkeuring, annulering) |
| `ActiviteitenConfig` | Per-organisatie configuratie |
| `ActiviteitenInvite` | Uitnodigingen voor deelnemers |
| `BusAssignment` | Bus-stoel-allocatie per deelnemer |
| `KostenLine` | Kostenposten per activiteit (transport, locatie, materialen) |
| `OrgStudents` | Snapshot van leerlingen per organisatie op moment van aanvraag |
| `SnapshotLine` | Historische snapshot-lijnen |

## Functionaliteit

- **Aanvraag-workflow**: draft → submitted → approved → executed → closed
- **Mail-templates** voor uitnodigingen + reminders + afsluiting
- **Migratie 1.9** beschikbaar (`migrations/1.9/post-migrate.py`) — schema-evolutie pre-1.9 → 1.9

## In-module docs

Geen aparte README/USER_MANUAL in deze module (TODO).

## Gerelateerde modules

- [`afwezigen`](afwezigen.md) — overzicht van afwezige medewerkers door activiteiten (depends op deze)
- [`planner`](planner.md) — inhaalplannen voor klassen door activiteiten (depends op deze + admin)
- [`myschool_dashboard`](myschool_dashboard.md) — toont activiteiten-status per gebruiker
