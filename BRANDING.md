# Branding — MySchool → Surtia

> Werkdocument. **Surtia = VOORLOPIGE WERKNAAM (vastgelegd 2026-06-12).**
> Definitief pas na groene registercheck (BOIP/EUIPO klassen 9/41/42) + WHOIS + hardop-test.
> Registercheck-resultaten: zie sectie "Registercheck — uitvoering" onderaan.

## Naam
**Surtia** — vervangt "MySchool" (dat botst met bestaande schooladministratie-software
en dicht bij Smartschool ligt).

- Uitspraak: **SUR-tia** — eenduidig voor Vlamingen, foutloos spelbaar.
- Internationaal leesbaar (NL/EN/FR/DE/ES/IT), geen valse vrienden.
- Naamveld: geen software-/EdTech-/Benelux-bezetter gevonden (enkel een lege ES-
  consumentensite + plaatsnaam in India).
- Alternatief in reserve: **Yveda** (schoner naamveld, maar Y-start geeft
  blind-spelling-twijfel).

## Betekenis / positionering
Bewust een **betekenis-vrij kunstwoord** — gekozen op gevoel, niet op letterlijke
betekenis. Na zes naamrondes bleek elk betekenisvol "licht/helderheid/inzicht"-veld in
software/EdTech verzadigd (Lumen, Clarix, Sagax, … allemaal bezet). Surtia straalt uit:
**cool, modern, efficiënt, organisatie/structuur, "graag leren"** — professioneel genoeg
voor IT/bedrijfsvoering, sympathiek genoeg voor een onderwijscontext. Cruciaal: er zit
géén "school" in de naam, waardoor ze de hele scope dekt (niet enkel onderwijs) — precies
de val waarin "MySchool" trapte.

## Merk-architectuur — branded house met endorsed sub-brand
Eén koepelnaam, twee pijlers:

```
                       SURTIA
        (koepel = platform = organisatie/merkfamilie)
        ├── Surtia Core / Process / ITSM / Inventory …      ← Pijler 1  (prefix surtia_*)
        └── “<warme naam>”  ·  powered by Surtia            ← Pijler 2  (LearningAssistant)
```

- **Surtia = koepel + platform + organisatienaam** in één. Geen aparte bedrijfsnaam
  erboven voor nu; later optilbaar als er écht commercieel naar buiten wordt getreden.
- **Pijler 1 — operationeel platform** (de Odoo-basis): organisatie efficiënter maken op
  **personen / rollen / processen / taken / toegang**, met uitbreidingen: procesmaker,
  appmaker, organisatie-eigen toepassingen, ITSM, inventaris. Doelgroep: directie,
  secretariaat, ICT. = de huidige `myschool_*`-modulesuite, wordt `surtia_*`.
- **Pijler 2 — LearningAssistant** (toekomst): helpt **leerlingen én leerkrachten**.
  Pedagogisch/warm, andere doelgroep en emotie dan pijler 1. Opvolger van de bestaande
  MySchoolAssistant (Next.js + FastAPI). Krijgt een **eigen, warme, leerling-vriendelijke
  naam** met endorsement *"powered by Surtia"* — aparte naamzoektocht met eigen criteria.
  Sluit technisch aan op de Surtia-kern (personen/rollen/toegang), eigen prefix
  (bv. `surtia_learn`).

Waarom dit model: de twee pijlers verschillen wezenlijk in publiek én toon (zakelijk vs
pedagogisch). Één gedeelde koepel geeft synergie, één huisstijl en laag kosten; de
assistent krijgt z'n eigen gezicht zonder de koepel los te laten.

## Huisstijl
Teal **#004850** blijft het kleuranker; logo/woordmerk wijzigt mee met de naam.

## Impact van de hernoeming (bewustwording, geen plan)
Raakt veel: `myschool_*`-prefix op 24 modules, de `myschool.*`-model-namespace
(DB-migratie — **gefaseerd**, geen big-bang), repo (`odoo-myschool` / `MySchool_addons`),
Semaphore-playbooks, MCP-namespace + remote `myschool-ict.olvp.be`, mail-templates en
interne communicatie. Aanpak: eerst branding + nieuwe modules hernoemen, de bestaande
`myschool.*`-modellen via een aparte gefaseerde migratie verhuizen.

## Koepelnaam-afweging (3 kandidaten, vergeleken 2026-06-12)
Drie koepelkandidaten naast elkaar gecleard (web-search, geen juridische zekerheid):

| Criterium | Surtia | Organos | Orkestra |
|---|---|---|---|
| Betekenis | betekenis-vrij | organon+organisatie+OS-grap | orkestratie/samenspel |
| VL-uitspraak | SUR-tia ✓ | klemtoon-twijfel | or-KES-tra ✓ |
| Valse vrienden | geen | ES/PT/IT órganos=organen/bestuursorganen | "orkest"-ruis |
| SW/EdTech-collision | vrijwel leeg ✓ | Orgos.io + Organon (sw+farma) | stampvol: Orkes $60M, getorchestra, Kestra, Orkestra SCS/Energy, Training Orchestra, QuickSchools "Orchestra" |
| Domein .com | plausibel vrij | bezet | vrijwel zeker bezet |
| Merkenrisico 9/41/42 | laag | verhoogd (Organon ®) | hoog |
| Warmte | neutraal | klinisch | warmst |

**Rangschikking: 1. Surtia (winnaar — enige met schoon naamveld + eenduidige uitspraak + laag merkenrisico) · 2. Orkestra (mooiste betekenis, maar drukste niche denkbaar → afgeraden) · 3. Organos (afvaller: Orgos.io + Organon + órganos-valse vriend).**

**Ook geëvalueerd en afgewezen (2026-06-12): Kordia** — 🔴 botst met Kordia Group NZ (staats-cybersecurity/cloud/managed-IT, klassen 9/42 = jouw zwaartepunt) + cor-familie bezet (Cordia/Cordis/Concordia); bovendien klopt de "cor/cordis=hart"-rationale etymologisch niet (Kordia ← concordia=harmonie). Surtia blijft sterker. Alternatieven met hart-lading indien ooit gewenst: Corvia / Cordian (nog te clearen).
Organos en Orkestra enkel reactiveren als Surtia onverwacht sneuvelt op de echte registercheck. **Surtia blijft de werknaam-kandidaat.**

## Merk-rationale Melira — het bijenkorf-verhaal

**Naam.** *Melira* is afgeleid van **Melissa**, het Griekse woord voor *bij* (μέλισσα).
De bij en haar korf zijn sinds de oudheid het symbool van **georganiseerde, collectieve
wijsheid**: duizenden individuen die — elk met een eigen rol — samen iets bouwen dat
geen van hen alleen zou kunnen.

**Waarom de korf.** Een bijenkorf is geen chaos en geen bevel-van-bovenaf; het is een
**zelforganiserend systeem**. Iedere bij kent haar rol, taken stromen naar waar ze nodig
zijn, het werk is verdeeld, de toegang geregeld, en het geheel past zich aan zonder dat
iemand de hele zwerm hoeft te micromanagen. Dat is precies wat Melira voor een organisatie
wil zijn: het stille raamwerk waarin **mensen, rollen, processen, taken en toegang** vanzelf
op hun plaats vallen, zodat de organisatie als geheel soepel en doelgericht functioneert.

**De brug naar het platform.** Waar de korf zes hoekige cellen tot één sterke structuur
verbindt, verbindt Melira losse modules — beheer, ITSM, inventaris, processen, projecten —
tot één samenhangend geheel. De honingraat is het beeld: eenvoudige, herhaalbare bouwstenen
die samen een veerkrachtig bouwwerk vormen.

**Waarden die de naam draagt.**
- *Samenwerking* — de korf werkt alleen omdat het geheel meer is dan de som der delen.
- *Orde zonder dwang* — structuur die ontstaat uit goede afspraken, niet uit controle.
- *Vlijt & efficiëntie* — "bezig als een bij"; werk dat zin heeft en vooruitgaat.
- *Wijsheid & groei* — honing als vrucht van collectief leren; de natuurlijke brug naar de
  tweede pijler, de leerassistent, die leerlingen en leerkrachten helpt groeien.

**Toon & uitspraak.** *me-LEE-ra* — zacht, warm, uitnodigend. Professioneel genoeg voor
bestuur en IT, sympathiek genoeg voor een school. Geen "school" in de naam: Melira draagt
de hele organisatie, niet enkel het klaslokaal.

**Visueel anker (suggestie).** Honingraat-hexagoon als beeldmerk, in het bestaande teal
(#004850); de zeshoek als modulair grid sluit naadloos aan bij de module-architectuur.

> Eén regel: **Melira — waar mensen, rollen en processen samenkomen als in een korf.**

### Kosten merkdepot (officiële taksen, 10 jaar geldig, verlengbaar) — voor onze klassen 9·41·42
| Register | 1e klasse | 2e klasse | 3e klasse | **Totaal 3 klassen** | Dekking |
|---|---|---|---|---|---|
| **BOIP** (Benelux: BE/NL/LU) | €244 | +€27 | +€81 | **≈ €352** | België + Nederland + Luxemburg |
| **EUIPO** (hele EU-27) | €850 | +€50 | +€150 | **≈ €1.050** | volledige EU (incl. Benelux), EU-breed oppositierecht |

- **Intern/Benelux-platform nu** → BOIP (~€352) volstaat; later uitbreidbaar naar EU-merk.
- **Bij commerciële/internationale ambitie** → EUIPO (~€1.050) ineens.
- Dit zijn de **kale taksen** (zelf indienbaar via de portals). Een **merkengemachtigde** (aangeraden voor
  verwarringsgevaar-bevestiging + correcte klasse-omschrijving) kost ~**€300–900+** extra.
- **Domeinen** melira.be/.eu/.io: samen ~**€50–80/jaar** — kleine maar tijdsgevoelige stap (nu nog vrij).

---

## Clearance-checklist Surtia (zelf afwerken vóór definitieve keuze)
Alle "lijkt vrij"-uitspraken hierboven zijn web-search-inschattingen, géén registerwaarheid.
Werk onderstaande vier checks af (±20 min) vóór je de naam vastklikt. Relevante Nice-klassen:
**9** (software), **41** (onderwijs/opleiding), **42** (SaaS/IT-diensten).

### 1. Merkenregister — Benelux (primair; OLVP-thuismarkt)
- Ga naar **BOIP trademark register**: https://www.boip.int/en/trademarks-register
- Zoek op **"Surtia"** (woordmerk) → daarna fonetische varianten: **Surtya, Soortia, Surtia + spatie**.
- Filter/lees treffers in klassen **9, 41, 42**. Geen treffer in die klassen = groen voor Benelux.

### 2. Merkenregister — EU-breed
- **EUIPO eSearch**: https://www.euipo.europa.eu/en/search-ip  ·  of **TMview** (BOIP+EUIPO+nationaal): https://www.tmdn.org/tmview/
- Zelfde zoekopdracht ("Surtia" + varianten) in klassen 9/41/42.
- Let op identieke én "verwarringwekkend gelijkende" oudere merken. Bij twijfel: kort advies van een merkengemachtigde.

### 3. Handelsnaam / onderneming (België)
- **KBO/BCE publieke databank**: https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html → zoek op naam "Surtia".
- Doel: bestaande Belgische onderneming/handelsnaam uitsluiten.

### 4. Domeinen (WHOIS)
- `.be` via **DNS Belgium**: https://www.dnsbelgium.be/nl/whois  → check **surtia.be**
- `.com/.eu/.app` via https://www.whois.com/whois/ of https://lookup.icann.org/  → **surtia.com, surtia.eu, surtia.app**
- Bij groen: registreer **surtia.be + .com + .eu** meteen defensief.

### 5. Uitspraak-realiteitstest (parallel)
- Laat 5-10 Vlaamse collega's/leerlingen **"Surtia"** koud voorlezen én na enkel horen blind opschrijven.
- Verwacht: ~foutloze "SUR-tia". Meet eventuele spellingsvarianten.

**Beslisregel:** alle vier groen + uitspraaktest oké → Surtia vastleggen, domeinen + BOIP-depot (kl. 9/41/42)
regelen, dan pas de gefaseerde rename starten. Eén harde collision in kl. 9/41/42 → terugval op
Orkestra/Organos heroverwegen (zie afweging hierboven).

## Registercheck — uitvoering (2026-06-12)
Uitgevoerd voor zover automatiseerbaar (RDAP/DNS + web search). Merkenregisters zijn
JS-apps / API-beveiligd → autoritatieve merkcheck blijft een handmatige stap.

**Domeinen — geverifieerd (RDAP + Google DNS):**
| Domein | Status | Bron |
|---|---|---|
| surtia.be | ✅ **VRIJ** (NXDOMAIN, geen DNS) | RDAP 404 + DoH NS=NXDOMAIN |
| surtia.eu | ✅ **VRIJ** (NXDOMAIN) | RDAP 404 + DoH NS=NXDOMAIN |
| surtia.app | ✅ **VRIJ** (NXDOMAIN) | RDAP 404 + DoH NS=NXDOMAIN |
| surtia.com | ⚠️ bezet, maar **te koop** — nameservers = BrandBucket (domein-marktplaats), géén operationeel bedrijf | RDAP: registratie 2020-12-30; NS=ns1/2.brandbucket.com |

→ Voor een Benelux-first product is dit gunstig: .be/.eu/.app vrij; .com is een
premium-koopdomein zonder onderneming erachter (niet kritiek, evt. later koopbaar).

**Bedrijf/handelsnaam — web search (soft signal, niet autoritatief):**
Geen software-/EdTech-/Benelux-onderneming "Surtia". Enkel: dode ES-webshop
(surtia.company.site), FF14-personage, SoundCloud/Twitch-handles, dorp Surtia (India,
Haryana). → Geen botsende onderneming gevonden.

**Merkenregister BOIP/EUIPO/TMview — ✅ HANDMATIG NAGEKEKEN DOOR USER (2026-06-12): GEEN CONFLICT.**
Enige nabije treffers: **"Surtiarra"** (sector bloemen, Uruguay/Peru/Zuid-Amerika) en
**"surtiapp"** (Zuid-Amerika). Andere sector, andere regio, andere klassen → **geen overlap**
met "Surtia" in kl. 9/41/42, geen verwarringsgevaar in Benelux/EU.

**Uitspraaktest:** optioneel, nog te doen (checklist stap 5) — geen blocker meer.

**CORRECTIE (2026-06-12): surtia.io = LIVE same-sector naamgenoot.**
surtia.io is GEEN dode webshop maar een **actieve Spaanstalige SaaS "Surtia — Inventory
Intelligence" (inventarisbeheer-software)** — exact onze sector (kl. 9/42), overlapt met de
inventaris-module. Spaanstalige markt (LatAm/ES), domein live (A-record). Hoort bij het
Spaanse *surtir*-cluster (Surtia/Surtiapp/Surtiarra).
- Juridisch (Benelux/EU): user-merkencheck vond **geen EU/Benelux-merk** → blokkeert jouw
  gebruik/registratie in Benelux (nog) niet.
- Maar: naamveld is **niet meer "vrijwel leeg"** — één live gelijknamige speler in dezelfde
  sector. Toegevoegde risico's: SEO/vindbaarheid (zij komen mee boven), EU-merk-frictie als
  één van beiden ooit EUTM kl. 9/42 indient, en ".io weg" verzwakt het "naam-bezit"-verhaal.

**EINDSTAND: 🟡 SURTIA — GEPARKEERD (2026-06-12).** Domeinen .be/.eu/.app vrij, geen
Benelux/EU-merkconflict, MAAR live LatAm same-sector naamgenoot surtia.io. User parkeert
Surtia als werknaam en start een **nieuwe naamronde**. Surtia blijft terugvaloptie als de
nieuwe ronde niets beters oplevert.

**NIEUWE RONDE — richtlijn (2026-06-12):**
- **Vlaamse/NL-insteek laten vallen** → internationaal/neutraal kunstwoord.
- **Strengere lat (les van Surtia):** géén LIVE software/SaaS-naamgenoot. Per finalist expliciet
  de exact-match domeinen (.com/.io/.ai) + web search checken op een bestaand same-sector bedrijf.
- Behoud: eenduidige uitspraak (ook voor Vlamingen), kort, prefix-geschikt, geen valse vriend,
  kl. 9/41/42 plausibel vrij, professioneel/modern (koepel = zakelijk; warmte zit in de aparte
  assistent-naam).

**Nieuwe-ronde-resultaat (2026-06-12):** strenge live-naamgenoot-check sneuvelde >50% van de
munten (o.a. Velnar→velnir.com = AI-automation = Surtia-herhaling). Geclearde overlevers:
- **Nessvar** ⭐ (NESS-var) — schoonste veld van alle rondes; geen SW-naamgenoot; nessvar.com vrij.
- **Krevan** (KREH/KREE-van) — krachtig; .com geparkeerd → start .io/.eu.
- **Orvend** — schoon, maar "vend/vendor"-bijklank EN; .com te koop.
- Pruvio (reserve) — pruvio.com in gebruik (coaching-LLC, niet-SW).
Tradeoff: schoon veld maar KOUD/betekenisloos (prijs voor het laten vallen van betekenis+Vlaams).
Surtia blijft terugvaloptie (eleganter, maar LatAm-naamgenoot). Beslissing user openstaand.
- **Hemex** (gecheckt 2026-06-12): 🔴 afgewezen — hemex.be én hemex.eu BEZET (resolveren),
  gefinancierde medtech-naamgenoot "Hemex Health" met cloud/AI (Gazelle), + "hem-"=bloed-connotatie.
- **Felix**: 🔴 zwaar bezet (DreamWorks "Felix the Cat" merk in kl.9 + kattenvoer + telecom; alle domeinen bezet incl. .be/.eu).

**ACRONIEM-AANPAK (2026-06-12, user-idee): kunstwoord uit beginletters van een slogan.**
Beste vondst: **TASORA** ⭐ — slogan **T**aken·**A**ccess·**S**tructuur·**O**rganisatie·**R**ollen·**A**utomatisering
(werkt ook EN: Tasks·Access·Structure·Organisation·Roles·Automation). Uitspraak ta-SO-ra.
**SCHOON:** geen software-naamgenoot, geen merkhit; tasora.com = persoonlijke redirect (geen bedrijf);
**tasora.be/.eu/.io VRIJ**. Warm + brandbaar (zachte -a, zoals Surtia) maar zónder Surtia's LatAm-naamgenoot,
én met ingebouwd betekenis-verhaal. = sterkste kandidaat tot nu toe. Nog te doen: formele BOIP/EUIPO
(kl.9/41/42) + valse-vrienden-check.
(Ook gecheckt, afgewezen: Vestra=bezet+meerdere SW-bedrijven; Kortas=.com/.eu bezet+veelvoorkomende achternaam.)
**2-lettergreep-ronde (P erbij voor person/process):** **TARPO** ⭐ (TAR-po) = Taken·Access·Rollen·Processen·Organisatie —
schoon (geen SW-naamgenoot; tarpo.com=Keniaans tentenbedrijf; .io/.be/.eu vrij); kanttekening: "tarp"(dekzeil)-echo in EN.
Afgewezen: Parso (IoT/SaaS CR), Torsa (Torsa Global tech ES), Protas (ProTAS travel-SaaS), Parsa (alle domeinen bezet).
→ Schone acroniem-kandidaten: **Tasora** (3 syll, warmst, smetloos) en **Tarpo** (2 syll, "tarp"-echo).
**Tech-stack-ronde (Linux/Odoo/opensource als termen erbij):** **LARTO** ⭐ (LAR-to) = **L**inux·**A**ccess·**R**ollen·**T**aken·**O**doo —
tech-stack ingebakken; geen SW-naamgenoot (Larto's bestaan in e-commerce/logistiek, andere sector); larto.com=Sedo-koopdomein;
larto.io/.be/.eu VRIJ. Kanttekening: IT "l'arto"=ledemaat (mild); naam niet uniek buiten software.
Afgewezen: Lotas (🔴 Lotas.ai YC + LOTAS GmbH DE), Solta (Solta Medical, alles bezet), Prola (PROLA=physics-archief + .com/.eu bezet), Rolas (.com/.eu bezet).
→ DRIE schone acroniem-finalisten: **Tasora · Tarpo · Larto**.
**Symbool-wortel-coinage-ronde (2026-06-12):** wijsheidssymbool als wortel → coined naam.
Godennamen + klassieke symbool-woorden (Athena=AWS, Minerva=EdTech, Metis/Sophos/Munin/Hugin=SW, Otus/Glaux/Olea/Melis=bezet) allemaal bezet.
Coinage-winnaar: **MELIRA** ⭐ (me-LEE-ra) — van Melissa=Grieks "bij"; bijenkorf=georganiseerde collectieve wijsheid (dubbele fit). Zachte klank (geen harde t/r),
geen software-naamgenoot, **.io/.be/.eu vrij** (.com=Franse PE-firma, andere sector). = betekenis + schoon veld + zacht.
Ook ok: Olvana (zwakke olijf-link + US-Army-fictieland-bijvangst). Afgewezen: Apivo (Appivo/Apivio-cluster).

**MELIRA — DEEP CLEAR (2026-06-12): 🟢 zeer schoon.**
- Domeinen: melira.io/.be/.eu/.ai **alle VRIJ** (RDAP 404); .com bezet sinds 2012 = Franse PE-firma "Melira".
- Geen software/SaaS/EdTech-naamgenoot (gerichte sweep education/app/AI/SaaS/Belgium = niets); geen merk gevonden.
- Enige naamgenoot = Franse private-equity "Melira" (sector financiën, kl.36 ≠ onze 9/41/42) → coëxistentie ruim haalbaar.
- Materieel schoner dan Surtia (die had same-sector SaaS surtia.io; Melira's naamgenoot zit in niet-conflicterende klasse).
- Klank me-LEE-ra (zacht), verhaal=bij/korf.

**EUIPO-CHECK (user, 2026-06-12): bestaand EU-merk MELIRA gevonden — MAAR in onverwante klassen → gunstig.**
- EUTM 013971718, *figuratief* (logo), individueel, geregistreerd 13/08/2015, exp. 2035. Eigenaar: Panagiotis Alexiou (natuurlijke persoon, Griekenland) — producten-merk.
- Nice-klassen: **3** (cosmetica/zeep/oliën), **5** (farma/supplementen), **29+30** (voeding: jam/tahini/gebak/repen/sauzen/halva).
- ONZE klassen = **9** (software), **41** (onderwijs), **42** (SaaS/IT) → totaal andere goederen/markt/consument.
- Specialiteitsbeginsel: merken met dezelfde naam coëxisteren in niet-verwante klassen → **blokkeert Melira NIET**; woordmerk MELIRA in 9/41/42 vrijwel zeker registreerbaar (extra ruimte want bestaand merk is figuratief).
- EUTM dekt óók Benelux → beantwoordt meteen de BOIP-vraag (enig EU-MELIRA zit in onverwante klassen).
- ⚠️ Vóór eigen depot: merkengemachtigde laten bevestigen dat er geen verwarringsgevaar is (standaard due diligence; klasse-afstand sterk gunstig).
→ **MELIRA ≈ GROEN** (merkencheck in essentie rond). Nieuwe koploper naast Tasora/Larto; Surtia=terugval. Nog: eigen woordmerk-depot kl.9/41/42 + domeinen registreren + (optioneel) uitspraaktest.

## Status / openstaand
- [x] Domeincheck (.be/.eu/.app vrij; .com = BrandBucket-koopdomein) — 2026-06-12.
- [x] Onderneming/web-presence-check (geen botsende speler) — 2026-06-12.
- [x] **Autoritatieve merkenzoek BOIP + EUIPO/TMview** (kl. 9/41/42) — user 2026-06-12: enkel Surtiarra/surtiapp (ZA, bloemen/andere sector) → **geen conflict**.
- [ ] Uitspraaktest in de lerarenkamer (optioneel, geen blocker).
- [ ] Domeinen .be/.eu/.app defensief registreren.
- [ ] Gefaseerde rename plannen (`myschool_*` → `surtia_*`; model-namespace via aparte migratie).
- [ ] Pas na groen licht: Surtia vastleggen, domeinen + merkdepot, dan gefaseerd renamen.
- [ ] **LearningAssistant-naam (pijler 2): PRINCIPE AKKOORD** — eigen warme naam, *"powered by Surtia"*,
      géén "Surtia Assistant". Concrete zoektocht **uitgesteld** ("bij gelegenheid"). Geparkeerde
      kandidaten: Dodoens (schoonste veld) / Tycho / Verla + bredere Vlaamse-geleerden-hoek.
