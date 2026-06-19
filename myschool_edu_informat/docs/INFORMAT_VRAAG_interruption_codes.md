# Vraag aan Informat — Personeel WEB API: interruption-codes & verlofomvang

**Van:** OLVP ICT (ict@olvp.be)
**Betreft:** Personeel WEB API V2.14 — endpoint `/employees/interruptions`
**Doel:** geautomatiseerde account-provisioning op basis van verlofstelsels

---

Beste Informat-team,

Wij integreren de Personeel WEB API (V2.14) en willen op basis van de
**`/employees/interruptions`**-endpoint bepalen of een personeelslid zijn
account/toegang moet behouden, beperken of verliezen tijdens een verlofstelsel.
Daarvoor hebben we van jullie de volgende verduidelijkingen nodig.

## 1. Volledige codetabel
De implementatiegids geeft bij `code` enkel een lijst "at this moment"
(1, 45, 90, 144, 197, 200, 203, 206, 209). Graag de **volledige, autoritatieve
lijst** van alle mogelijke `code`-waarden + `omschrijving`, met name:
- de **deeltijdse** zorgkrediet-varianten (de gidslijst toont enkel "Voltijds …");
- **terbeschikkingstelling (TBS)** in al haar vormen;
- **verlof voor verminderde prestaties (VVP)** / deeltijds verlof;
- loopbaanonderbreking algemeen.

## 2. Voltijds vs. deeltijds — hoe te bepalen?
Onze businesslogica: **voltijds verlof → account deactiveren; deeltijds → behouden.**
- Is "voltijds vs. deeltijds" **uitsluitend** af te leiden uit de `code` (zoals de
  omschrijving "Voltijds zorgkrediet …" suggereert), of bestaat er ook een
  expliciet **percentage- of uren-veld** op het interruption-record?
- Het interruption-record bevat (volgens de gids) géén algemeen uren-veld behalve
  `stakingUren`. Hoe bepalen we de **omvang** van een niet-staking-verlof
  (volledig vs. gedeeltelijk t.o.v. de opdracht)?

## 3. Relatie interruption ↔ opdracht (assignment)
In de assignment-data zien we per opdracht een `vervangingen`-lijst met een
**`doId`** dat overeenkomt met het `doId` van een interruption.
- Is dat de **bedoelde koppeling** tussen een interruption en de opdracht(en) die
  ze (deels) onderbreekt?
- Kan één interruption meerdere opdrachten betreffen, en kan één opdracht meerdere
  gelijktijdige interruptions hebben?
- Hoe weten we welk **deel** van een opdracht door de interruption wordt gedekt
  (bij deeltijds verlof)?

## 4. Periode & status
- Bevestig dat `begindatum`/`einddatum` de **effectieve verlofperiode** zijn (om
  te bepalen of het verlof *vandaag* loopt).
- Wat betekent `soort` (RL-code) precies, en `verstuurdAgODi`?

Alvast bedankt voor de toelichting.

Met vriendelijke groet,
OLVP ICT
