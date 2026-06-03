# professionalisering

Beheer van professionaliseringsaanvragen voor leerkrachten. Workflow van bijscholing-aanvraag tot goedkeuring tot afronding, inclusief budget-tracking en HR-koppeling.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `mail`, `hr`, `myschool_core` |
| Wordt gebruikt door | `myschool_dashboard` (toont openstaande aanvragen) |

## Doel

Vlaamse onderwijs-contexten vereisen tracking van professionaliseringsuren per leerkracht. Deze module:

- **Aanvragen-workflow**: draft → submitted → directie-goedkeuring → ingepland → afgerond
- **Budget-tracking**: per persoon / per organisatie / per periode
- **HR-koppeling** via Odoo's `hr.employee`-model voor cumulatief overzicht per medewerker

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_core`](myschool_core.md) — fundament (depends op deze)
- [`myschool_dashboard`](myschool_dashboard.md) — toont aanvragen per gebruiker
- Odoo's standaard `hr`-module (depends op deze)
