# Scope — Informat Student API (push) — GEPARKEERD

> Status: **scoping, niet ingepland.** Opgesteld 2026-06-16 n.a.v. de ontdekking van de nieuwe
> Informat push-API. Géén breaking change voor de huidige (lees-)koppeling — dit is een
> *nieuwe capability*. Hervatten = lees dit document + `student-api-public.yaml`.

## 1. Waarom / use-case
Vandaag is onze Informat-koppeling **eenrichting (inbound, read-only)**: we lezen
inschrijvingen, leerlingen en personeel uit Informat. De nieuwe **Student API (Public)** laat
toe om **terug te schrijven** richting Informat:

- **`POST /enrollments/create`** — een inschrijving in een SO-administratieve groep aanmaken.
- **`PUT /enrollments/{enrollmentId}/link-class`** — een klas aan een inschrijving koppelen.
- **`PUT /students/{studentId}/absences`** — een afwezigheid registreren/bijwerken.

**Prime use-case voor OLVP**: (voor)inschrijvingen die elders ontstaan (bv. Smartschool-
aanmeldingen, of de toekomstige SRVMGR/onboarding-flow) **automatisch naar het Informat-
acceptatiescherm pushen**, i.p.v. manuele her-invoer. Afwezigheden-push is secundair
(enkel relevant als we ooit afwezigheden in het platform beheren).

## 2. API-feiten (uit `student-api-public.yaml`, v1.0.0)
- **Host (nieuw!)**: `https://studentapi.informatsoftware.be/api/v1` — **andere host** dan
  `leerlingenapi`/`personeelsapi`.
- **Auth**: identiek model als nu → Bearer JWT van identityserver, header `instituteNo`,
  scope `api_informat_sas_leerlingen.leerlingen.{instituteNo}`. **We hebben dit al.**
  ⚠️ Te bevestigen: of onze API-client **schrijfrechten** heeft op deze API (mogelijk moet
  Informat dit per school activeren — zie ook de dagboeken-/activatie-logica bij andere API's).
- **Foutmodel**: **RFC 7807 ProblemDetails** met `validationErrors[]` + foutcodes
  (`BR0xx` validatie, `DNF0xx` not-found, `MNA0xx` conflict). ⚠️ Dit is een **ander
  foutformaat** dan onze lees-API's (die werken met result-codes 200/400/404/500/999) →
  aparte error-handling nodig.
- **Concurrency**: afwezigheden gebruiken optimistic concurrency via `timestamp`
  (409 `MNA007` als er een nieuwere registratie bestaat).

## 3. Datamapping (create enrollment)
`CreateEnrollmentRequest` verplichte velden → onze bron:
| Informat-veld | Vorm / regel | Onze bron | Open? |
|---|---|---|---|
| `schoolYear` | `yyyy-yy` (bv. `2025-26`) | `CurrentSchoolYear` (settings) — **formaat omzetten** | formaat-check |
| `mainStructure` | enkel `"311"` (SO) | constante | ok |
| `personId` | student-UUID | `myschool.person.sap_person_uuid` | ✅ hebben we uit read-sync |
| `admgrpNo` | **exact 6 tekens**, niet `043905`/`006246`/`006247` | administratieve-groep-nr | ⚠️ **resolven we dit?** te checken |
| `startDate` | binnen schooljaar; geen weekend tenzij 1 sep | bron-inschrijving | ok |
| `nameExternalProvider` | ≤50 tekens | constante (bv. `"Melira"` / `"OLVP"`) | ok |
| `classCode` (opt.) | 1 unieke klas in dept-jaar | `reg_group_code` | optioneel |
| `religionCode` (opt.) | enum | — | meestal weglaten (auto) |
| `locationIdDiscimus` (opt.) | int | location-ID per school | zie helpdesk "location ID" |

**Grootste open vraag**: kunnen we voor een persoon de juiste **`admgrpNo`** (6-cijferige
administratieve groep) afleiden? We kennen `inst_nr` en klascodes, maar `admgrpNo` is de
DAGO-administratieve-groep — mogelijk te halen uit de registrations-read (`klasCode`/`afdeling`)
of via een lookup. Dit bepaalt de haalbaarheid van enrollment-push.

## 4. Architectuur-inpassing
- Hoort thuis in **`myschool_edu_informat`** (de connector-plugin na slice 3), als **outbound**-
  tegenhanger van de bestaande inbound-service. Niet in `myschool_core` (eenrichting platform→editie).
- Twee opties voor de trigger:
  1. **Via de betask-keystone** — een nieuwe connector-betask (bv. `('CONNECTOR','ENROLLMENT','PUSH')`)
     die de plugin afhandelt. Consistent met het bestaande emit/handler-patroon
     (`_get_connector_betask_handlers()` / `_emit_connector_*`). **Voorkeur** — past in de pipeline-discipline.
  2. Een directe push-service met expliciete actieknop/cron. Sneller, maar buiten de betask-discipline.
- **Nieuw config-veld** voor de push-host (`studentapi.informatsoftware.be/api/v1`) +
  `nameExternalProvider`-waarde. Hergebruik bestaande token/credentials.

## 5. Buiten scope (nu)
- Afwezigheden-push (`PUT /absences`) — enkel zinvol als afwezigheidsbeheer in het platform komt.
- `link-class` afzonderlijk — meenemen ná dat enrollment-create werkt.
- Bulk/historische migratie van inschrijvingen.

## 6. Eerste stappen wanneer we hervatten
1. **Haalbaarheid `admgrpNo`** uitklaren (de blocker — zie §3). Zonder betrouwbare admgrpNo
   geen enrollment-create.
2. Bij Informat **schrijfrechten + location-ID** bevestigen voor de OLVP-instnr's.
3. Klein: token + `instituteNo`-header hergebruiken, 1 test-enrollment tegen acceptatie-omgeving
   (let op: er is in de yaml enkel een Production-server vermeld → voorzichtig testen).
4. Error-handling op ProblemDetails/`validationErrors` (apart van de read-result-codes).
5. Pas dan: betask-handler + mapping + config in `myschool_edu_informat`.

## 7. Inschatting
Klein-tot-middelgroot **mits** §6.1 (admgrpNo) en §6.2 (rechten) groen zijn. De auth/transport-
laag is hergebruik; het echte werk zit in de mapping + foutafhandeling + de betask-integratie.
Als admgrpNo niet betrouwbaar af te leiden is, vervalt de business-case grotendeels.
