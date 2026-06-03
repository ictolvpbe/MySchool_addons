# security_phishing

Interne phishing-bewustwordingscampagnes. Stelt school-administrators in staat om gecontroleerde phishing-simulaties uit te voeren voor security-awareness-training van personeel.

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `base`, `mail` |
| Standalone | Geen `myschool_core`-dep — kan in andere Odoo-instances |

## Doel

Voor het OLVP security-testing-programma (zie [[project-security-testing]] memory in platform-handbook):

- **Campagne-templates**: voorgeprogrammeerde phishing-mails (kleurmotief, urgentie, fake-link-structuur)
- **Targeting**: per groep of organisatie-eenheid
- **Tracking**: wie klikt, wie meldt, klik-percentage per groep
- **Bewustwordings-flow**: na klikken krijgt slachtoffer een educatieve pagina met uitleg over phishing-tekens

## Strategische context

OLVP-plan voor security-testing was eerst GoPhish (open-source phishing-tool), maar wordt nu **vervangen door Microsoft Defender Attack Simulator** (komt met M365 A5-licentie). Reden: één tool minder beheren, fully integrated met M365-mail.

Status van deze module na deze beslissing: **mogelijk obsolete** of complementair voor interne campagnes die NIET via M365 lopen.

## In-module docs

Geen aparte README (TODO).

## Open punten

- Heroverweeg of module nog actief ontwikkeld moet worden gezien Defender-keuze
- Indien actief: documenteer interplay met M365 Defender (welke campagnes via welk tool)

## Gerelateerde

- `platform-handbook` memory `project_security_testing.md` — strategie voor security-testing
- Microsoft Defender Attack Simulator (extern)
