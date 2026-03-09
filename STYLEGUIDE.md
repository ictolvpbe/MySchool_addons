# MySchool Design System — Style Guide

> Reference document for styling all MySchool Odoo modules.
> Based on the OLVP brand identity and modern UI best practices.

---

## 1. Brand Color Palette

| Name         | Variable     | Hex       | Usage                                              |
|--------------|-------------|-----------|-----------------------------------------------------|
| Hoofdblauw   | `--ms-brand-1` | `#007d8c` | Topbar, primary buttons, active tabs, main accents  |
| 2e blauw     | `--ms-brand-2` | `#0094A4` | Hover accents, links, focus rings, secondary icons  |
| 3e blauw     | `--ms-brand-3` | `#00ACBF` | Tertiary accents, gradient stops                    |
| 4e blauw     | `--ms-brand-4` | `#00C4D9` | Highlights, annotation accents, active underlines   |
| Zwart        | `--ms-black`   | `#252525` | Headings, card titles, dark backgrounds             |
| Grijs        | `--ms-gray`    | `#9B9B9B` | Labels, captions, muted text, counts                |
| Text kleur   | `--ms-text`    | `#003333` | Primary body text                                   |

### Derived Colors

| Name           | Variable           | Hex         | Usage                                    |
|----------------|--------------------|------------|-------------------------------------------|
| Text muted     | `--ms-text-muted`  | `#5a7a7a`  | Secondary text, field labels              |
| Background     | `--ms-bg`          | `#f0f5f5`  | Page background                           |
| Card bg        | `--ms-bg-card`     | `#ffffff`  | Card/panel surfaces                       |
| Border         | `--ms-border`      | `#d6e4e4`  | Standard borders                          |
| Border light   | `--ms-border-light`| `#e8f0f0`  | Subtle borders, dividers                  |
| Tint 1         | —                  | `#d9f2f4`  | Icon backgrounds (c1), active tree nodes  |
| Tint 2         | —                  | `#d1f0f3`  | Icon backgrounds (c2)                     |
| Tint 3         | —                  | `#c9eef2`  | Icon backgrounds (c3)                     |
| Tint 4         | —                  | `#c1ecf0`  | Icon backgrounds (c4)                     |
| Hover bg       | —                  | `#e6f7f8`  | Button/card hover backgrounds             |
| Row hover      | —                  | `#f0f8f8`  | Table row / tree node hover               |
| Surface        | —                  | `#f5fafa`  | Readonly fields, panel headers, status bars|

### Semantic Colors

| Meaning  | Foreground  | Background  | Usage                                    |
|----------|------------|------------|-------------------------------------------|
| Success  | `#0d9488`  | `#ccfbf1`  | Active status, completed, students        |
| Error    | `#dc2626`  | `#fee2e2`  | Failures, danger zones, delete actions    |
| Warning  | `#d97706`  | `#fef3c7`  | Destructive ops, caution, tree badges     |
| Info     | `#0284c7`  | `#e0f2fe`  | Employees, informational badges           |

### Brand Gradient

```css
background: linear-gradient(135deg, var(--ms-brand-1) 0%, var(--ms-brand-2) 50%, var(--ms-brand-3) 100%);
```

Use for hero sections, promotional banners, and dashboard highlights.

---

## 2. CSS Custom Properties Block

Copy this into any module's root CSS to get the full palette:

```css
:root {
  /* Brand */
  --ms-brand-1: #007d8c;
  --ms-brand-2: #0094A4;
  --ms-brand-3: #00ACBF;
  --ms-brand-4: #00C4D9;

  /* Neutrals */
  --ms-black: #252525;
  --ms-gray: #9B9B9B;
  --ms-text: #003333;
  --ms-text-muted: #5a7a7a;

  /* Surfaces */
  --ms-bg: #f0f5f5;
  --ms-bg-card: #ffffff;
  --ms-border: #d6e4e4;
  --ms-border-light: #e8f0f0;

  /* Semantic */
  --ms-success: #0d9488;
  --ms-success-bg: #ccfbf1;
  --ms-error: #dc2626;
  --ms-error-bg: #fee2e2;
  --ms-warning: #d97706;
  --ms-warning-bg: #fef3c7;
  --ms-info: #0284c7;
  --ms-info-bg: #e0f2fe;
}
```

---

## 3. Typography

### Font Stack

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

Monospace (for FQDNs, code, technical values):

```css
font-family: 'SF Mono', 'Fira Code', monospace;
```

### Scale

| Level           | Size   | Weight | Color           | Usage                         |
|-----------------|--------|--------|-----------------|-------------------------------|
| Page title      | 22px   | 700    | `--ms-black`    | Top-level headings            |
| Card/form title | 20px   | 700    | `--ms-black`    | Form headers, card titles     |
| Section header  | 16px   | 600    | `--ms-black`    | Panel titles, section names   |
| Body large      | 14px   | 400    | `--ms-text`     | Descriptions, main content    |
| Body standard   | 13px   | 400    | `--ms-text`     | Default text, table cells     |
| Body small      | 12px   | 400    | `--ms-text`     | Metadata, secondary info      |
| Label           | 11px   | 600    | `--ms-gray`     | Uppercase labels, badge text  |
| Mini            | 10px   | 600    | varies          | Tiny badges, tree badges      |

### Labels (uppercase)

```css
font-size: 11px;
text-transform: uppercase;
letter-spacing: 0.8px;
color: var(--ms-gray);
font-weight: 600;
```

---

## 4. Spacing

Base unit: **4px**. Use multiples for consistency.

| Token   | Value  | Usage                                    |
|---------|--------|------------------------------------------|
| xs      | 4px    | Tight internal gaps                      |
| sm      | 8px    | Badge padding, small gaps                |
| md      | 12px   | Card internal padding, field spacing     |
| lg      | 16px   | Grid gaps, section margins               |
| xl      | 20px   | Panel padding, major spacing             |
| 2xl     | 24px   | Page padding, form body padding          |
| 3xl     | 28px   | Form body horizontal padding             |
| 4xl     | 32px   | Section bottom margins                   |

### Common Patterns

- **Page container**: `max-width: 1100px; margin: 0 auto; padding: 24px;`
- **Card padding**: `padding: 20px 28px;` (header) or `padding: 24px 28px;` (body)
- **Field row**: `margin-bottom: 10px;`
- **Field group**: `margin-bottom: 24px;`
- **Section gap**: `margin-bottom: 32px;`
- **Grid column gap**: `40px` (form two-column layout)

---

## 5. Borders & Shadows

### Border Radius

| Size     | Value  | Usage                            |
|----------|--------|----------------------------------|
| Small    | 6px    | Buttons, inputs, badges          |
| Medium   | 8px    | Info cards, search boxes         |
| Large    | 10px   | Cards, panels                    |
| XL       | 12px   | Form cards, icon containers      |
| Pill     | 16px   | Chips, filter pills              |
| Circle   | 50%    | Avatars, status dots             |

### Shadows

| Name      | Value                                  | Usage                     |
|-----------|----------------------------------------|---------------------------|
| Subtle    | `0 1px 3px rgba(0,60,60,.06)`         | Standard cards            |
| Card      | `0 1px 4px rgba(0,60,60,.07)`         | Form cards                |
| Hover     | `0 2px 8px rgba(0,125,140,.08)`       | Card hover states         |
| Elevated  | `0 4px 20px rgba(0,125,140,.2)`       | Hero sections, dropdowns  |
| Button    | `0 4px 12px rgba(0,0,0,.15)`          | Prominent button hover    |

### Border Colors

- Default: `var(--ms-border)` — `#d6e4e4`
- Light: `var(--ms-border-light)` — `#e8f0f0`
- Hover: `var(--ms-brand-2)` — `#0094A4`
- Danger: `#fca5a5`
- Warning: `#fbbf24`

---

## 6. Component Patterns

### Buttons

**Default button:**
```css
padding: 8px 16px;
border-radius: 6px;
border: 1px solid var(--ms-border);
background: #fff;
font-size: 13px;
font-weight: 500;
cursor: pointer;
transition: .15s;
color: var(--ms-text);
display: flex; align-items: center; gap: 6px;
```

**Hover:** `background: #e6f7f8; border-color: var(--ms-brand-2);`

**Primary variant:** `background: var(--ms-brand-1); color: #fff; border-color: var(--ms-brand-1);`
**Primary hover:** `background: #006b78;`

**Danger variant:** `color: var(--ms-error); border-color: #fca5a5;`
**Danger hover:** `background: #fff5f5;`

### Cards

```css
background: var(--ms-bg-card);
border: 1px solid var(--ms-border-light);
border-radius: 10px;
box-shadow: 0 1px 3px rgba(0,60,60,.06);
```

**Hover (interactive cards):** `border-color: var(--ms-brand-2); box-shadow: 0 2px 8px rgba(0,125,140,.08);`

### Badges

```css
padding: 2px 10px;
border-radius: 12px;
font-size: 11px;
font-weight: 600;
```

Variant backgrounds: use semantic color pairs (e.g., `background: var(--ms-success-bg); color: var(--ms-success);`).

### Chips (filter pills)

```css
padding: 5px 14px;
border-radius: 16px;
font-size: 12px;
font-weight: 500;
border: 1px solid var(--ms-border);
background: #fff;
color: var(--ms-text-muted);
```

**Active:** `background: var(--ms-brand-1); color: #fff; border-color: var(--ms-brand-1);`

### Tabs

```css
/* Container */
display: flex; gap: 0;
padding: 0 28px;
border-bottom: 1px solid var(--ms-border);

/* Tab item */
padding: 12px 20px;
font-size: 13px;
color: var(--ms-gray);
border-bottom: 2px solid transparent;
font-weight: 500;
```

**Active tab:** `color: var(--ms-brand-1); border-bottom-color: var(--ms-brand-1); font-weight: 600;`

### Tables

```css
/* Header cells */
padding: 12px 14px;
font-size: 11px;
text-transform: uppercase;
letter-spacing: .6px;
color: var(--ms-gray);
background: #f5fafa;
font-weight: 600;
border-bottom: 1px solid var(--ms-border);

/* Body cells */
padding: 11px 14px;
border-bottom: 1px solid var(--ms-border-light);

/* Row hover */
background: #f0f8f8;
```

### Search Inputs

```css
display: flex; align-items: center; gap: 8px;
padding: 7px 14px;
border: 1px solid var(--ms-border);
border-radius: 8px;
background: #fff;
```

**Focus:** `border-color: var(--ms-brand-2); box-shadow: 0 0 0 3px rgba(0,125,140,.1);`

### Avatars

| Size  | Dimensions | Font | Usage        |
|-------|-----------|------|--------------|
| Large | 56×56px   | 20px | Form headers |
| Medium| 32×32px   | 11px | Member lists |
| Small | 30×30px   | 11px | Table rows   |
| Tiny  | 28×28px   | 12px | Topbar       |

All: `border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600;`

### Icon Containers

```css
/* Standard */
width: 40px; height: 40px;
border-radius: 10px;
display: flex; align-items: center; justify-content: center;
font-size: 18px;

/* Background tints (c1–c4 gradient): */
.c1 { background: #d9f2f4; color: var(--ms-brand-1); }
.c2 { background: #d1f0f3; color: var(--ms-brand-2); }
.c3 { background: #c9eef2; color: var(--ms-brand-3); }
.c4 { background: #c1ecf0; color: var(--ms-brand-4); }
```

### Toggle Switches

```css
width: 36px; height: 20px;
border-radius: 10px;
background: var(--ms-brand-2);
position: relative; cursor: pointer;
```
Thumb: `::after` pseudo-element, 16×16px white circle.

### Status Dots

```css
width: 8px; height: 8px;
border-radius: 50%;
display: inline-block;
```

Active: `background: var(--ms-success);`
Inactive: `background: var(--ms-border);`

---

## 7. Interactive States

| State    | Pattern                                                      |
|----------|--------------------------------------------------------------|
| Hover    | `background: #e6f7f8;` or `#f0f8f8;`, `border-color: var(--ms-brand-2);` |
| Active   | `background: var(--ms-brand-1); color: #fff;` or `background: #d9f2f4; color: var(--ms-brand-1);` |
| Focus    | `border-color: var(--ms-brand-2); box-shadow: 0 0 0 3px rgba(0,125,140,.1);` |
| Disabled | `opacity: .5;` or `background: #f5fafa; color: var(--ms-text-muted);` |
| Readonly | `background: #f5fafa; border-color: var(--ms-border-light); color: var(--ms-text-muted);` |

---

## 8. Layout Patterns

### Grids

| Name          | Template                     | Gap    | Usage                    |
|---------------|------------------------------|--------|--------------------------|
| KPI row       | `repeat(4, 1fr)`             | 16px   | Dashboard stat cards     |
| 2-column      | `repeat(2, 1fr)` or `1fr 1fr`| 14px   | Action cards, form fields|
| 3-column      | `repeat(3, 1fr)`             | 14px   | Entity type cards        |
| Dashboard     | `2fr 1fr`                    | 20px   | Main + sidebar           |
| Form fields   | `1fr 1fr`                    | `0 40px`| Two-column form layout  |

### 3-Panel Layout (Object Browser)

```
┌──────────────────────────────────────────────────────┐
│  Toolbar (search, actions)                           │
├──────────┬──────────────┬────────────────────────────┤
│  Tree    │  Members     │  Details                   │
│  320px   │  400px       │  flex: 1                   │
│  fixed   │  fixed       │  bg: #f5fafa              │
└──────────┴──────────────┴────────────────────────────┘
```

### Page Container

```css
max-width: 1100px;  /* or 1280px for wide pages */
margin: 0 auto;
padding: 24px;
```

---

## 9. Entity Color Coding

Consistent colors per entity type across all views:

| Entity       | Icon bg   | Badge bg             | Badge text           |
|-------------|-----------|----------------------|----------------------|
| Organization | `#d9f2f4` | `#d9f2f4`            | `var(--ms-brand-1)`  |
| Employee     | `#e0f2fe` | `var(--ms-info-bg)`  | `var(--ms-info)`     |
| Student      | `#ccfbf1` | `var(--ms-success-bg)`| `var(--ms-success)` |
| Role         | `#d9f2f4` | `#d9f2f4`            | `var(--ms-brand-1)`  |
| Period       | `#c1ecf0` | `#c1ecf0`            | `var(--ms-brand-4)`  |

---

## 10. Do's and Don'ts

**Do:**
- Use CSS custom properties (`--ms-*`) for all colors
- Use the brand gradient for hero/promotional sections
- Use teal tint backgrounds (`#e6f7f8`, `#f0f8f8`, `#d9f2f4`) for hover/active states
- Use monospace font for FQDNs, technical identifiers, code values
- Use uppercase + letter-spacing for section labels
- Use consistent border-radius (6px buttons, 10px cards, 12px form cards)
- Keep shadows subtle — use `rgba(0,60,60,...)` for teal-tinted shadows

**Don't:**
- Use Odoo's default purple (`#714B67`) — replace with `--ms-brand-1`
- Use pure black (`#000`) — use `--ms-black` (`#252525`)
- Use generic gray borders (`#ddd`, `#e0e0e0`) — use `--ms-border` / `--ms-border-light`
- Use `#f8f9fa` for backgrounds — use `#f5fafa` (teal-tinted) or `var(--ms-bg)`
- Mix blue hover states — use teal palette exclusively
- Add heavy shadows — keep the UI light and clean
