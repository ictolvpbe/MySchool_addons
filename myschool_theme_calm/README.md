# MySchool Theme — Calm Tech

Calm-tech re-skin van de Odoo-backend, als **aparte overlay-module** bovenop
`myschool_theme`. De bestaande teal-theme blijft volledig ongemoeid.

> Bron: het calm-tech design-handoff (`../design_handoff_melira/`) — warm crème /
> salie / lila-AI, Plus Jakarta Sans + Inter. Dit is een **visuele exploratie**
> op het echte product, geen productie-rebrand. De technische namespace blijft
> **merk-neutraal**: alle tokens dragen de `--ms-*`-prefix, geen productnaam.

## Hoe het werkt (overlay)

`myschool_theme_calm` *depend* op `myschool_theme` en laadt **ná** dat module.
Het herschrijft enkel de **design-tokens**; alle structurele SCSS/JS/XML
(navbar-, sidebar-, apps-menu-, chatter-gedrag) wordt hergebruikt.

| Laag | Bestand | Bundel |
|---|---|---|
| SCSS primary-vars (`$o-brand-*`) | `static/src/scss/colors.scss` | `web._assets_primary_variables` (after teal) |
| Webfonts (self-hosted woff2) | `static/src/scss/fonts.scss` | `web.assets_backend` |
| Tokens + selector-overrides | `static/src/scss/calm.scss` | `web.assets_backend` (after teal) |

### Token-lagen

- **`--myschool-*`** (basis `myschool_theme/layout.scss`) drijft de standaard
  Odoo-schermen (navbar, sidebar, lijsten, formulieren).
- **`--ms-*`** (eveneens in `myschool_theme/layout.scss`) is de canonieke
  token-API die de OWL-apps consumeren; brand/text/bg/border zijn afgeleid van
  `--myschool-*`, de rest (surfaces/semantic/typografie/radii/schaduw/AI-accent)
  heeft daar een teal-default.

Deze overlay overschrijft **beide lagen** met calm-tech-waarden. Omdat de
overlay op `myschool_theme` *depend*, laadt ze gegarandeerd ná de basis en wint
ze betrouwbaar — ongeacht bron-volgorde t.o.v. andere modules.

- **Installeren** → calm-tech actief.
- **Verwijderen** → teal `myschool_theme` komt onveranderd terug.

## Installeren / testen

```bash
# op de instance (verse asset-build)
odoo -d <db> -u myschool_theme_calm --stop-after-init
# of via de Apps-UI: "MySchool Theme — Calm Tech" installeren.
```

Hard-refresh de browser (assets-cache) na (de-)installatie.

## Palet (calm-tech tokens)

| Rol | Hex |
|---|---|
| Canvas (crème) | `#F2EEE5` |
| Kaart-oppervlak | `#FBFAF6` · alt `#F7F4EC` |
| Salie (primair) | `#7E9B79` · diep `#5E7A55` · soft `#E7EEE2` |
| Lila (AI-accent, `--ms-accent-ai`) | `#7C68B8` · soft `#EFEBF8` |
| Klei/amber (warm/urgent) | `#9A7B66` · soft `#F1E7DF` |
| Ink-tekst | `#33403C` · muted `#8A918C` |
| Navbar (diep salie-charcoal) | `#3F4A43` |

Fonts: **Inter** (body, 400/500/600) + **Plus Jakarta Sans** (headings, 600/700),
latin-subset woff2, lokaal geserveerd → **geen externe Google-call** (GDPR-proof).
Geïnjecteerd via de `--ms-font-body` / `--ms-font-head` tokens.

## Bewuste keuzes (en alternatieven)

- **Navbar = diepe salie-charcoal** (`#3F4A43`), niet de mid-salie, omdat de
  bestaande navbar witte tekst/iconen gebruikt en mid-salie te weinig contrast
  geeft (~3:1). Wil je een **lichte** navbar (zoals het prototype)? Dat vereist
  het overschrijven van álle systray-icoon/tekst-kleuren naar ink — bewust niet
  in deze eerste versie om legibility-randgevallen te vermijden.
- **Sidebar = licht** met salie active-bar. De tekstkleuren van `myschool_theme`
  waren wit-op-donker en zijn hier expliciet naar ink-op-licht overschreven.

## Grens van "1-1"

Deze module brengt de **vormtaal** (palet, fonts, radii, schaduwen, calm-tech-
sfeer) op de standaard Odoo-schermen én — via de `--ms-*`-tokens — op de OWL-apps;
realistisch ~85-90% van het calm-tech-gevoel. De **specifieke dashboardlayout**
(zwevende hover-nav, metric-grid, uitschuifbaar AI-paneel) is géén theme maar
custom OWL-development; valt buiten deze overlay.

## Fonts verversen / uitbreiden

```bash
# extra gewicht ophalen (latin-subset)
UA="Mozilla/5.0 ... Chrome/120 Safari/537.36"
css=$(curl -s -A "$UA" "https://fonts.googleapis.com/css2?family=Inter:wght@700&display=swap")
url=$(printf '%s\n' "$css" | grep -o 'https://[^)]*\.woff2' | tail -1)   # latin = laatste blok
curl -s -A "$UA" "$url" -o static/src/fonts/inter-700.woff2
# daarna een @font-face toevoegen in fonts.scss
```
