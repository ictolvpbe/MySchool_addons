# Verlofstelsels via de Informat Personeels-API — integratie-analyse

**Status:** analyse / scoping (2026-06-19) · hoort bij MS-PREPROD #211
**Aanleiding:** personeel in een verlofstelsel (bv. Charlotte Van Gysel) wordt nu
volwaardig geprovisioneerd (rol + account + groepen) omdat de sync het verlof niet
ziet. De huidige connector haalt enkel `/employees` + `/employees/assignments` op.

---

## 1. Kan de Informat-API verlofstelsel-info leveren? — Ja

De **Personeel WEB API V2.14** (`docs/Personeel-WEB-API-Implementation-Guide-V2.14.pdf`,
p. 31-41) heeft een dedicated resource **Interruptions** (= *dienstonderbrekingen*),
het overkoepelende begrip dat verlofstelsels omvat:

| Methode | Pad | Doel |
|---|---|---|
| GET | `/employees/interruptions?schoolyear={jaar}&structure={structuur}` | alle onderbrekingen voor school/jaar (InstituteNo via header) |
| GET | `/employees/{personId}/interruptions?schoolyear={jaar}` | onderbrekingen per persoon |
| PUT | `/employees/{personId}/interruptions/{interruptionId}` | toevoegen / wijzigen |
| DELETE | `/employees/interruptions/{interruptionId}` | verwijderen |

Dus **lezen én schrijven**. Header `Api-Version` is version-neutral (1 of 2 = zelfde
resultaat).

### Velden per interruption-record
`pOnderbreking` (int id), `doId` (Guid), `personId` (Guid), `hfd` (structuur),
`begindatum`, `einddatum`, **`code` + `omschrijving`** (het type), `soort` (RL-code),
`verstuurdAgODi`, `opmSecretariaat`, `opmPersoneelslid`, `staking` / `stakingUren`,
`ziekteverlofZonderBezoldiging`.

### `code`-waarden (doc: "at this moment" — NIET exhaustief)
| code | omschrijving | verlofstelsel? |
|---|---|---|
| 1 | Ziekteverlof | nee (ziekte) |
| 45 | Staking | nee |
| 90 | Omstandigheidsverlof | nee |
| 144 | Verlof wegens overmacht | nee |
| 197 | Voltijds zorgkrediet kinderen ≤12j | **ja** (loopbaanonderbreking) |
| 200 | Voltijds zorgkrediet medische bijstand | **ja** |
| 203 | Voltijds zorgkrediet palliatieve zorg | **ja** |
| 206 | Voltijds zorgkrediet kind met handicap | **ja** |
| 209 | Voltijds zorgkrediet opleiding | **ja** |
| 19 | Verlof tijdelijk ander ambt/opdracht | grijs |
| 002 | Te laat toegekomen | nee |

⚠️ **Open vraag aan Informat:** de volledige, autoritatieve codetabel — incl.
**deeltijdse** zorgkrediet-varianten, **TBS** (terbeschikkingstelling) en **VVP**
(verlof verminderde prestaties). De doc-lijst is expliciet "at this moment".

---

## 2. Twee gegevenslagen: detectie vs. classificatie

Cruciaal inzicht uit de **echte data** (Charlotte, person 8699):
haar assignment-velden geven **geen** verlof-signaal op opdracht-niveau
(`urenTbsOB=0`, `reaffWedertew=""`, `afstandWachtgeld=0`, `isTao=false`,
`aanstellingscode=0`, `ato="4"`). Tóch is haar verlof **detecteerbaar**:

```
assignment.vervangingen = [{ "opdrachtId": "...", "doId": "6187563b-1ba9-4ac5-..." }]
```

Het `doId` in `vervangingen` is **exact het `doId`-veld van een interruption**. Dus:
haar opdracht wordt **vervangen wegens een dienstonderbreking** → ze is (deels) afwezig.

| Laag | Bron | Wat het geeft | Al opgehaald? |
|---|---|---|---|
| **Detectie** | assignment `vervangingen[].doId` (+ `urenTbsOB`, `reaffWedertew`, `afstandWachtgeld`, `isTao`) | "deze persoon heeft een onderbreking" | ✅ ja (zit in `/assignments`) |
| **Classificatie** | `/employees/interruptions` → match op `doId` | **wélk** verlofstelsel (`code`/periode) | ❌ nee (endpoint niet aangeroepen) |

➡️ We kunnen **nu al** detecteren dat iemand een onderbreking heeft, zónder nieuwe
API-call. Het **type** (verlofstelsel-code) vergt de interruptions-endpoint.

---

## 3. Integratiepad

### Quick wins (geen nieuwe endpoint nodig)
1. **Verlof-signaal afleiden uit de reeds-opgeslagen assignment-data** en zichtbaar
   maken op de persoon: `vervangingen[].doId` aanwezig, of `urenTbsOB > 0`, of
   `reaffWedertew` ∈ {R,W,VT}, of `isTao`, of `afstandWachtgeld > 0`.
   → maakt Charlotte's status meteen inspecteerbaar.
2. **(later) provisioning-guard koppelen** aan dat signaal (geen account / suspend /
   beperkte groepen), analoog aan de Phase-0 feed-gap guard.

### Volwaardig (nieuwe endpoint)
3. **`/employees/interruptions` consumeren** in de sync: nieuw `myschool.interruption`-
   model + mapper + fetch (analoog aan de assignments-fetch). Match interruptions op
   `personId`/`doId`, gebruik `code` + `begindatum`/`einddatum` voor de exacte
   verlofstelsel-bepaling.
4. **Codetabel → beleid**: mapping `code` → {volledig weg / deeltijds / negeren} →
   provisioning-beslissing. Vereist de volledige codetabel (open vraag §1).
5. **(optioneel) schrijven**: PUT/DELETE interruptions — enkel als het platform
   verlof-beheer gaat doen; voorlopig out-of-scope.

### Aandachtspunten
- Voltijds vs. deeltijds zorgkrediet bepaalt het gedrag (volledig weg vs. beperkt
  actief). Periode (`begindatum`/`einddatum`) bepaalt of het verlof *nu* loopt.
- Dev-data: de huidige dev-snapshot bevat **geen** interruptions-bestanden; voor een
  echte classificatie-test is een prod-API-call of een interruptions-snapshot nodig.
  De **detectie** (vervangingen.doId) werkt wél op de bestaande dev-data.

---

## 4. Charlotte als testcase
- person 8699, school baple (107839), ambt 00000237 (administratief medewerker).
- Assignment: actieve admin-opdracht 11/36, géén TBS-velden ingevuld.
- **Wél** `vervangingen[].doId = 6187563b-1ba9-4ac5-a0ad-8e1cb5006c2a` → onderbreking
  gedetecteerd; het tÝpe (welk verlofstelsel) komt uit de interruptions-endpoint.
