# knowledge_builder

Visual knowledge-object builder met step-editor. Stelt eindgebruikers in staat om gestructureerde kennis-objecten (procedures, instructies, FAQ) op te bouwen via een visuele step-by-step interface.

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `base`, `web`, `mail` |
| Standalone | Geen dep op `myschool_core` — kan ook in andere Odoo-instances |

## Doel

Naast tekstuele FAQ en handleidingen zorgt deze module voor:

- **Visuele opbouw** van procedures via een step-canvas
- **Knowledge-objects** met meerdere stappen, branches, conditions
- **Embedding** in andere modules (bv. ITSM-knowledge-base, school-procedures)

## Verwante modules

- [`process_mapper`](process_mapper.md) — BPMN-process-mapping (vergelijkbaar concept, andere abstractie-laag)
- [`myschool_itsm`](myschool_itsm.md) — ITIL knowledge-base kan deze module gebruiken voor procedures

## In-module docs

Geen aparte README (TODO).
