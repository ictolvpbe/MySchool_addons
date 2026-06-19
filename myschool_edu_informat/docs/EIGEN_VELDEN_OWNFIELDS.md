# Eigen velden (own fields) uit Informat — `ActiefOpSchool`

**Status:** gebouwd, gated achter SI `ActiefOpSchoolEnforce` (default uit) · MS-PREPROD #211-familie

## Endpoint (Personeel WEB API V2.14, p. 49-52)
- `GET /employees/ownfields?schoolyear={jaar}&structure={struct}` — alle eigen velden (InstituteNo via header)
- `GET /employees/{personId}/ownfields?schoolyear={jaar}` — per persoon
- **Read-only.** Je beheert het veld in Informat; wij lezen het.

## Veldstructuur per eigen veld
`personId` (Guid) · `vvId` (Guid, uniek id) · **`naam`** (veldnaam) · **`waarde`** (waarde) ·
`dataType` (Tekst/datum/getal — **géén boolean**) · `rubriek` (1=Personalia, 2=Tewerkstelling).

## Gebruik: `ActiefOpSchool`
- Maak in Informat een eigen veld **`ActiefOpSchool`** (Tekst, waarde `"Ja"`/`"Neen"`), gekoppeld aan de school → per-school.
- De connector leest `waarde` (tolerant: neen/nee/no/false/onwaar/0 = inactief).
- **Beleid (gated achter SI `ActiefOpSchoolEnforce`, default uit):**
  - **Nieuwe** werknemer met `ActiefOpSchool=Neen` → **geen account aanmaken** (creatie overgeslagen in Phase 1b).
  - **Bestaande** actieve werknemer met `ActiefOpSchool=Neen` → **deactiveren** (volledige suspend-cascade via `_suspend_person_fully`, reviewbaar in de SAP-review, Phase 1c).

## Opslag / zichtbaarheid
De geïmporteerde eigen-velden-JSON wordt per persoon bewaard op `person.details.ownfields`
(zoals assignments/interruptions) en getoond in de tab **"Eigen velden"** in de details-view.
Opslag gebeurt altijd (ook als enforce uit staat), scope-veilig (alleen in-scope scholen).

## Implementatie
- `EMPLOYEE_OWNFIELDS_API_URL` + `_get_employee_ownfields_from_informat(dev_mode)` (mirror van assignments/interruptions; dev-bestand `dev-ownfields-{instNr}.json`).
- `_ownfields_says_inactive(ownfields)` — checkt `naam=ActiefOpSchool` + waarde.
- Phase 1a haalt ownfields op; Phase 1b skipt creatie; Phase 1c bewaart + deactiveert.
