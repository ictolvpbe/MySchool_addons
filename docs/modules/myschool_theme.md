# myschool_theme

Teal-based backend-theme voor MySchool. Visuele aanpassing van Odoo's backend (web-UI) met OLVP/MySchool huisstijl (kleuren, logo's, branding).

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `muk_web_theme` (community-addon — separate install nodig) |

## Doel

- **Branding**: MySchool/OLVP-kleuren (teal-gebaseerd), logo's
- **Bouwt op** `muk_web_theme` (community-addon van Muk-IT met theme-framework)
- **Geen functionele wijzigingen** — puur visueel

## Install-volgorde

1. `muk_web_theme` (uit `/mnt/extra-addons` of community-OCA-pakket)
2. `myschool_theme` (uit MySchool_addons repo)

Voor lokale dev: zorg dat `muk_web_theme` in addons_path zit.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- `muk_web_theme` (extern, community-addon)
- [`myschool_admin`](myschool_admin.md) — gebruikt theme voor admin-views
