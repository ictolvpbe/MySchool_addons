# MySchool Theme — OLVP

OLVP-gebrande **calm-tech** backend-look voor Odoo 19, gebouwd naar het
design-handoff `design_handoff/calm tech olvp/`. Brengt de
merk-neutrale `myschool_theme_calm` terug naar de **echte OLVP-merkkleur**:
petrol/teal **#007E8C** primair, op warm ivoor, met salie secundair, klei als
waarschuwing en lila strikt voor AI.

## Laagstructuur (overlay-op-overlay)

```
myschool_theme            basis · teal-tokens + alle structurele SCSS/JS/XML
  └── myschool_theme_calm calm-tech vorm · merk-neutraal (salie/crème/lila)
        └── myschool_theme_olvp    ← DEZE · zelfde vorm, OLVP-petrol palet
```

- **Installeren** → calm-tech in OLVP-petrol.
- **Verwijderen** → merk-neutrale calm (salie) komt terug; nog een laag eraf → teal-basis.

`myschool_theme_olvp` is een **token-overlay**: het herdefinieert enkel de
design-tokens (`--myschool-*` / `--ms-*`) naar de exacte handoff-hexes en flipt
de paar interactie-regels die calm in salie hardcodeerde (knop-hover, focus-
ringen, facet-tekst) naar petrol. Alle layout/gedrag erft van calm + basis.

## Token-mapping (handoff §6 → hier)

| Rol | Hex | Token |
|---|---|---|
| Primair (logo) | `#007E8C` | `--myschool-brand-1`, `$o-brand-primary` |
| Primair hover | `#006A77` | `--myschool-brand-2` |
| Achtergrond (ivoor) | `#FBFAF6` | `--myschool-bg` / `--ms-surface-base` |
| Warm vlak | `#F4EFE6` | `--ms-surface-2` |
| Kaart-oppervlak | `#FFFFFF` | `--myschool-bg-card` / `--ms-surface-1` |
| Kaartrand | `#ECE6DA` | `--myschool-border` |
| Tekst (leisteen) | `#3B454B` | `--myschool-text` |
| Accent salie (secundair/succes) | `#6F8E69` | `--ms-success` |
| Accent klei (waarschuwing) | `#9A7B66` | `--ms-warning` |
| AI (gereserveerd) | `#8E7CC3` | `--ms-accent-ai` |

Typografie (Inter + Plus Jakarta Sans, self-hosted), radii (14/18px) en zachte
schaduwen komen ongewijzigd uit `myschool_theme_calm`.

## Logo

`static/src/img/olvp_logo_petrol.svg` (knockout — letters tonen de achtergrond;
plaats op licht/wit, **nooit** op teal/groen). Niet auto-gewired; stel in via de
bedrijfsinstellingen of een header-template waar gewenst.

## Testen

```bash
./odoo-bin -d <db> -u myschool_theme_olvp --dev=assets
```

Daarna in Odoo de backend-UI controleren tegen het handoff-ontwerp. Verfijn de
tokens in `static/src/scss/olvp.scss` tot het overeenkomt.
