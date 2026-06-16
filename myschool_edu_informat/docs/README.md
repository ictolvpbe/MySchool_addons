# Informat REST API — bronnen & status

Dit mapje bewaart de officiële Informat-API-documentatie waartegen onze connector is
gebouwd, plus de bevindingen van de impact-analyse van **16 juni 2026** (n.a.v. een
gemelde API-aanpassing bij Informat).

> Connector-code: `myschool_edu_informat/models/informat_service.py` (+ `informat_dto.py`,
> `informat_service_config.py`). De DB-ingestie-mappers staan nog in
> `myschool_core/models/betask_processor.py` (`_map_*_json_to_*_vals`, `_clean_informat_string`,
> `*_FIELD_MAP`) — die verhuizen pas in slice 3 **Stage-2** (gepland voor de PII-werf).

## Bestanden
| Bestand | Wat |
|---|---|
| `Leerlingen-WEB-API-Implementation-Guide-V1.24.pdf` | Lees-API leerlingen/inschrijvingen (release 12 mei 2026) |
| `Personeel-WEB-API-Implementation-Guide-V2.14.pdf` | Lees-API personeel (release 8 juni 2026) |
| `student-api-public.yaml` | **Nieuwe** Student API (Public) — push van inschrijvingen + afwezigheden (OpenAPI 3.0.3) |
| `PUSH_API_SCOPE.md` | Scope/voorstel voor het push-spoor (geparkeerd voor later) |

Bron: <https://helpdesk.informat.be/hc/nl/articles/20664337172114> (downloadbaar onderaan dat artikel).

## Wat wij vandaag gebruiken (alles READ)
| Onze call | Versie-anker | Auth |
|---|---|---|
| `identityserver.be/connect/token` | OAuth2 client-credentials | scope `api_informat_sas_leerlingen.leerlingen.{inst_nr}` |
| `leerlingenapi.../1/registrations` + `/1/students` | URL-pad `/1/` (major v1) | Bearer + `InstituteNo`-header |
| `personeelsapi.../employees` + `/employees/assignments` | header `Api-Version: 2` | Bearer + `InstituteNo`-header |

## Verdict impact-analyse (2026-06-16)
**Geen breaking change. Onze sync blijft ongewijzigd werken.**

- **Leerlingen**: doc-versie nu **V1.24**, wij coderen tegen v1.23. Major-versie blijft `1`
  (URL `/1/`). Alle wijzigingen 1.16→1.24 zijn **additief** (nieuwe response-velden /
  nieuwe calls die wij niet aanroepen). Niets verwijderd of hernoemd.
- **Personeel**: doc-versie nu **V2.14**, wij sturen `Api-Version: 2` (geen v3). Alle
  wijzigingen die `GET /employees` + `/assignments` raken zijn **additief**
  (`effectiefInDienst`, `aantalKinderen`, `vakRubriek`, unieke keys `pAdres`/`pEmail`/`pOpdracht`…).
  2.13/2.14 gaan over RL-documenten/digitaal tekenen — niet door ons gebruikt.
- De échte "aanpassing" = een **nieuwe, aparte push-API** (`studentapi.informatsoftware.be/api/v1`).
  Raakt onze lees-koppeling niet; is een opportuniteit → zie `PUSH_API_SCOPE.md`.

### Watch-items (geen actie vereist, wel goed te weten)
1. **Leerlingen 1.23** wijzigde `refdate`-filtergedrag op `/students` ("filtert enkel als een
   datum wordt meegegeven"). Wij sturen `refdate` mee (`myschool_edu_informat/models/informat_service.py`,
   regels ~59 + ~872) → we zitten in het gefilterde geval, geen verrassing.
2. **Personeel 2.6** filtert `personeelsgroepen` op `GET /employees` nu op `instituteNo`
   (+ optionele `structure`). We syncen per `inst_nr`, dus impact verwacht nihil — quick-check
   waard als ergens de volledige groepenlijst werd verondersteld.

### Optionele "bijtrek"-kansen (niet nodig, puur nuttig)
- `effectiefInDienst` (Personeel 2.10) als netter actief-signaal dan `isActive`.
- Stabiele sub-record-keys (`pInschr`, `pInschrKlas`, `comnrId`, `emailId`, `pOpdracht`)
  i.p.v. matching op samengestelde velden.
- `klassenleraars` / `GroepType` (OLOD) / `Afdeling` / `afdelingsjaarOptie` op registrations.
