# MySchool Design System — Style Guide

> Reference for styling all MySchool Odoo 19 modules.
> Based on OLVP brand identity, HTML mockups (01–06), and `myschool_theme.css`.

---

## 1. Brand Color Palette

| Name         | Variable         | Hex       | Usage                                              |
|--------------|-----------------|-----------|-----------------------------------------------------|
| Hoofdblauw   | `--ms-brand-1`  | `#007d8c` | Topbar, primary buttons, active tabs, stat numbers  |
| 2e blauw     | `--ms-brand-2`  | `#0094A4` | Hover accents, links, focus rings, toggle on-state  |
| 3e blauw     | `--ms-brand-3`  | `#00ACBF` | Tertiary accents, gradient stops                    |
| 4e blauw     | `--ms-brand-4`  | `#00C4D9` | Highlights, annotation accents, active underlines   |
| Zwart        | `--ms-black`    | `#252525` | Headings, card titles                               |
| Grijs        | `--ms-gray`     | `#9B9B9B` | Group titles, stat labels, muted text               |
| Text         | `--ms-text`     | `#003333` | Primary body text, field values                     |
| Text muted   | `--ms-text-muted` | `#5a7a7a` | Field labels, subtitles, secondary text           |

### Surface Colors

| Name           | Variable / Hex      | Usage                                              |
|----------------|--------------------|----------------------------------------------------|
| Page bg        | `--ms-bg` `#f0f5f5`      | Page background, content area                |
| Card bg        | `--ms-bg-card` `#ffffff`  | Form sheets, table containers, cards         |
| Border         | `--ms-border` `#d6e4e4`   | Standard borders, separators                 |
| Border light   | `--ms-border-light` `#e8f0f0` | Subtle dividers, group title underlines  |
| Surface        | `#f5fafa`                 | Readonly fields, status bars, table headers  |
| Hover bg       | `#e6f7f8`                 | Button/card hover                            |
| Row hover      | `#f0f8f8`                 | Table row hover                              |
| Selection bg   | `#d9f2f4`                 | Selected rows, facet chips, icon tints       |

### Semantic Colors

| Meaning  | Foreground (`--ms-*`) | Background (`--ms-*-bg`) | Odoo decoration | Usage                     |
|----------|-----------------------|--------------------------|------------------|--------------------------|
| Success  | `#0d9488`             | `#ccfbf1`                | `decoration-success` | Active, completed, STUDENT |
| Error    | `#dc2626`             | `#fee2e2`                | `decoration-danger`  | Failures, inactive ribbon  |
| Warning  | `#d97706`             | `#fef3c7`                | `decoration-warning` | Caution, BRSO, PERSONGROUP |
| Info     | `#0284c7`             | `#e0f2fe`                | `decoration-info`    | EMPLOYEE, PPSBR, SCHOOL    |

---

## 2. CSS Custom Properties

Copy into any module's root CSS:

```css
:root {
  --ms-brand-1: #007d8c;  --ms-brand-2: #0094A4;
  --ms-brand-3: #00ACBF;  --ms-brand-4: #00C4D9;
  --ms-black: #252525;    --ms-gray: #9B9B9B;
  --ms-text: #003333;     --ms-text-muted: #5a7a7a;
  --ms-bg: #f0f5f5;       --ms-bg-card: #ffffff;
  --ms-border: #d6e4e4;   --ms-border-light: #e8f0f0;
  --ms-success: #0d9488;  --ms-success-bg: #ccfbf1;
  --ms-error: #dc2626;    --ms-error-bg: #fee2e2;
  --ms-warning: #d97706;  --ms-warning-bg: #fef3c7;
  --ms-info: #0284c7;     --ms-info-bg: #e0f2fe;
}
```

---

## 3. Typography

| Level           | Size   | Weight | Color           | Usage                               |
|-----------------|--------|--------|-----------------|-------------------------------------|
| Form title (h1) | 20px   | 700    | `--ms-black`    | `oe_title h1` — record name        |
| Subtitle (h3)   | 13px   | 400    | `--ms-text-muted` | `oe_title h3` — type, ref, tree  |
| Group title     | 11px   | 600    | `--ms-gray`     | Uppercase, letter-spacing 0.8px     |
| Stat number     | 22px   | 700    | `--ms-brand-1`  | `oe_stat_button .o_stat_value`      |
| Stat label      | 11px   | 600    | `--ms-gray`     | Uppercase, letter-spacing 0.5px     |
| Field label     | 13px   | 400    | `--ms-text-muted` | Form field labels                 |
| Field value     | 13px   | 400    | `--ms-text`     | Form field inputs                   |
| Table header    | 11px   | 600    | `--ms-gray`     | Uppercase, letter-spacing 0.6px     |
| Table body      | 13px   | 400    | `--ms-text`     | Table cells                         |
| Badge           | 11px   | 600    | varies          | Type/status badges                  |
| Monospace       | 12px   | 400    | `--ms-text`     | FQDNs, DNs — `ms-field-mono` class |

### Monospace font stack

```css
font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace;
```

---

## 4. Spacing & Borders

| Token | Value | Radius | Shadow |
|-------|-------|--------|--------|
| Form sheet | — | 12px | `0 1px 4px rgba(0,60,60,.07)` + `1px solid --ms-border-light` |
| List table | — | 10px | `0 1px 3px rgba(0,60,60,.06)` + `1px solid --ms-border-light` |
| Buttons | — | 6px | — |
| Badges | — | 12px (pill) | — |
| Search facets | — | 16px (pill) | — |
| Modals | — | 12px | — |
| Inputs | — | 6px | Focus: `0 0 0 3px rgba(0,125,140,.1)` |

---

## 5. Form View — Odoo-to-Mockup Mapping

This section maps each mockup element to the Odoo component and CSS selector that styles it.

### 5.1 Form Card (`.o_form_sheet`)

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `form-card` container | `<sheet>` | `.o_form_view .o_form_sheet` | radius 12px, shadow, border |
| Page background | Sheet bg | `.o_form_view .o_form_sheet_bg` | `--ms-bg` (#f0f5f5) |

### 5.2 Form Header & Title

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `form-header h1` | `oe_title h1` | `.o_form_view .oe_title h1` | 20px, bold, `--ms-black` |
| `form-header .subtitle` | `oe_title h3` | `.o_form_view .oe_title h3` | 13px, `--ms-text-muted` |
| `form-header-actions` | `<header>` buttons | `.o_form_view .o_form_statusbar .btn` | 6px radius, 13px |
| `form-avatar` | Not available in standard Odoo | — | Requires custom OWL widget |

**XML pattern:**
```xml
<div class="oe_title">
    <h1><field name="name"/></h1>
    <h3 class="text-muted">
        <field name="type_id" class="oe_inline" options="{'no_create': True}"/> |
        <field name="ref_field" class="oe_inline"/>
    </h3>
</div>
```

### 5.3 Status Bar

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `status-bar` | `<header>` | `.o_form_view .o_form_statusbar` | bg `#f5fafa`, border bottom |
| `status-dot.active` | Not standard in Odoo | — | Use `widget="boolean_toggle"` for is_active |
| `badge-type` | `widget="badge"` on type field | `.badge.text-bg-*` | Pill badges with semantic colors |

### 5.4 Stat Buttons

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `stat-btn` | `oe_stat_button` | `.oe_stat_button` | border `--ms-border-light`, hover `#e6f7f8` |
| `stat-number` | `widget="statinfo"` value | `.oe_stat_button .o_stat_value` | 22px, bold, `--ms-brand-1` |
| `stat-label` | `widget="statinfo"` label | `.oe_stat_button .o_stat_text` | 11px, uppercase, `--ms-gray` |

**XML pattern:**
```xml
<div class="oe_button_box" name="button_box">
    <button name="action_view_relations" type="object"
            class="oe_stat_button" icon="fa-link">
        <field name="relation_count" widget="statinfo" string="Relations"/>
    </button>
</div>
```

### 5.5 Tabs

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `.tab` | `nav-link` | `.o_form_view .o_notebook .nav-link` | 13px, `--ms-text-muted` |
| `.tab.active` | `nav-link.active` | `.o_form_view .o_notebook .nav-link.active` | `--ms-brand-1`, 2px bottom border |
| `.tab:hover` | `nav-link:hover` | `.o_form_view .o_notebook .nav-link:hover` | bg `#f5fafa` |

### 5.6 Field Groups

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `field-group-title` | `<group string="Title">` | `.o_form_view .o_inner_group .o_group_header` | 11px, uppercase, `--ms-gray`, bottom border `--ms-border-light` |
| `field-grid` (2-col) | `<group><group>...<group>` | `.o_form_view .o_group` | Built-in two-column |
| `field-label` | Form label | `.o_form_view .o_form_label` | 13px, `--ms-text-muted` |
| `field-value` | Input field | `.o_form_view .o_field_widget .o_input` | 13px, border `--ms-border`, radius 6px |
| `field-value.readonly` | Readonly field | `.o_form_view .o_field_widget.o_readonly_modifier` | bg `#f5fafa`, border `--ms-border-light`, color `--ms-text-muted` |
| `field-value.mono` | `class="ms-field-mono"` | `.ms-field-mono` | Monospace 12px |

### 5.7 Inactive Ribbon

| Mockup element | Odoo element | CSS |
|----------------|-------------|-----|
| Danger ribbon  | `web_ribbon` | `bg_color="text-bg-danger"`, bg `--ms-error` |

**XML pattern:**
```xml
<widget name="web_ribbon" title="Inactive" bg_color="text-bg-danger" invisible="is_active"/>
```

### 5.8 Boolean Toggles

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| Teal toggle (on) | `widget="boolean_toggle"` | `.form-check-input:checked` | bg/border `--ms-brand-2` |

---

## 6. List View — Odoo-to-Mockup Mapping

### 6.1 Table Container

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `table-card` | List renderer | `.o_list_view .o_list_renderer` | bg white, radius 10px, shadow, border |
| `table` | List table | `.o_list_view .o_list_table` | font-size 13px, radius 10px |

### 6.2 Table Header

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `thead th` | Table header cells | `.o_list_view .o_list_table thead th` | 11px, uppercase, letter-spacing 0.6px, `--ms-gray`, bg `#f5fafa`, padding 12px 14px |

### 6.3 Table Rows

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `tbody td` | Data cells | `.o_list_view .o_list_table tbody td` | padding 11px 14px, border `--ms-border-light` |
| Row hover | Hover state | `.o_data_row:hover > td` | bg `#f0f8f8` |
| Selected row | Selection | `.o_data_row_selected > td` | bg `#d9f2f4` |
| Inactive row | `decoration-muted` | `.o_data_row.text-muted td` | opacity 0.5 |

### 6.4 Badges in Lists

| Mockup badge | Odoo widget | CSS selector | Styling |
|-------------|-------------|--------------|---------|
| `badge-employee` (blue) | `decoration-info` | `.o_field_badge .badge.text-bg-info` | bg `--ms-info-bg`, color `--ms-info` |
| `badge-student` (green) | `decoration-success` | `.o_field_badge .badge.text-bg-success` | bg `--ms-success-bg`, color `--ms-success` |
| `badge-warning` (amber) | `decoration-warning` | `.o_field_badge .badge.text-bg-warning` | bg `--ms-warning-bg`, color `--ms-warning` |

All badges: `padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;`

### 6.5 Search & Filters

| Mockup element | Odoo element | CSS selector | Styling |
|----------------|-------------|--------------|---------|
| `search-box` | Search view | `.o_control_panel .o_searchview` | border `--ms-border`, radius 8px, focus ring teal |
| `chip.active` | Facet chip | `.o_searchview_facet` | bg `#d9f2f4`, border `--ms-brand-2`, radius 16px |

---

## 7. Odoo XML View Patterns

### 7.1 List View

```xml
<list decoration-muted="not is_active"
      default_order="name">
    <field name="name" string="Person"/>
    <!-- Type badges with color decorations -->
    <field name="person_type_id" widget="badge"
           decoration-info="person_type_id.name == 'EMPLOYEE'"
           decoration-success="person_type_id.name == 'STUDENT'"/>
    <field name="sap_ref" optional="show"/>
    <field name="tree_org_id" string="Organization" optional="show"/>
    <field name="email_cloud" optional="show"/>
    <field name="is_active" widget="boolean"/>
</list>
```

**Checklist:**
- [ ] `decoration-muted="not is_active"` on `<list>`
- [ ] `widget="badge"` with `decoration-*` on type/category fields
- [ ] `widget="boolean"` on boolean columns
- [ ] `optional="show"` / `optional="hide"` on secondary columns
- [ ] `default_order` for logical sorting

### 7.2 Form View

```xml
<form string="Title">
    <header>
        <button name="action_..." string="Action" type="object"
                class="btn-secondary" icon="fa-refresh"/>
    </header>
    <sheet>
        <div class="oe_button_box" name="button_box">
            <button name="action_view_..." type="object"
                    class="oe_stat_button" icon="fa-link">
                <field name="count_field" widget="statinfo" string="Label"/>
            </button>
        </div>

        <widget name="web_ribbon" title="Inactive"
                bg_color="text-bg-danger" invisible="is_active"/>

        <div class="oe_title">
            <h1><field name="name"/></h1>
            <h3 class="text-muted">
                <field name="type_id" class="oe_inline"
                       options="{'no_create': True}"/>
            </h3>
        </div>

        <group>
            <group string="Status &amp; Type">
                <field name="type_id"/>
                <field name="is_active" widget="boolean_toggle"/>
            </group>
            <group string="References">
                <field name="ref_field"/>
            </group>
        </group>

        <notebook>
            <page string="Overview" name="overview">
                <group>
                    <group string="Identity">
                        <field name="name"/>
                    </group>
                    <group string="References">
                        <field name="sap_ref"/>
                    </group>
                </group>
            </page>
            <page string="FQDN" name="fqdn">
                <field name="fqdn_field" class="ms-field-mono"/>
            </page>
            <page string="Relations" name="relations">
                <field name="relation_ids" readonly="1">
                    <list decoration-muted="not is_active">
                        <field name="name"/>
                        <field name="type_id" widget="badge"
                               decoration-info="type_id.name == 'PPSBR'"
                               decoration-success="type_id.name == 'PERSON-TREE'"
                               decoration-warning="type_id.name == 'BRSO'"/>
                        <field name="is_active" widget="boolean"/>
                    </list>
                </field>
            </page>
        </notebook>
    </sheet>
</form>
```

**Checklist:**
- [ ] `<header>` with action buttons (icon + class)
- [ ] `<div class="oe_button_box">` with stat buttons
- [ ] `<widget name="web_ribbon" ... bg_color="text-bg-danger" invisible="is_active"/>`
- [ ] `<div class="oe_title"><h1>` + optional `<h3 class="text-muted">`
- [ ] `widget="boolean_toggle"` on `is_active`
- [ ] `class="ms-field-mono"` on FQDN/DN fields
- [ ] Group titles in English: `<group string="Identity">`
- [ ] Icons on header buttons: `icon="fa-refresh"`
- [ ] Relations tab with embedded `<list>` using badges and decoration-muted

### 7.3 Search View

```xml
<search string="Search">
    <field name="name" string="Name / SAP / Email"
           filter_domain="['|','|',
               ('name', 'ilike', self),
               ('sap_ref', 'ilike', self),
               ('email_cloud', 'ilike', self)]"/>
    <field name="type_id"/>
    <separator/>
    <filter string="Active" name="active"
            domain="[('is_active', '=', True)]"/>
    <filter string="Inactive" name="inactive"
            domain="[('is_active', '=', False)]"/>
    <separator/>
    <filter string="Type A" name="type_a"
            domain="[('type_id.name', '=', 'TYPE_A')]"/>
</search>
```

**Checklist:**
- [ ] Combined `filter_domain` on primary search field
- [ ] Active/Inactive filter pair
- [ ] `<separator/>` between filter groups
- [ ] No `<group>` elements (Odoo 19 bug)

### 7.4 Actions

```xml
<record id="action_entity" model="ir.actions.act_window">
    <field name="name">Entities</field>
    <field name="res_model">myschool.entity</field>
    <field name="view_mode">list,form</field>
    <field name="context">{'search_default_active': 1}</field>
</record>
```

- Always `list,form` (NOT `tree,form`)
- Always `{'search_default_active': 1}` to auto-filter active records

---

## 8. Entity Color Coding

| Entity / Type    | `decoration-*`    | Badge style (list)          |
|-----------------|-------------------|-----------------------------|
| EMPLOYEE        | `decoration-info` | bg `#e0f2fe`, text `#0284c7` |
| STUDENT         | `decoration-success` | bg `#ccfbf1`, text `#0d9488` |
| PPSBR           | `decoration-info` | bg `#d9f2f4`, text `#007d8c` |
| PERSON-TREE     | `decoration-success` | bg `#ccfbf1`, text `#0d9488` |
| BRSO            | `decoration-warning` | bg `#fef3c7`, text `#d97706` |
| SCHOOL          | `decoration-info` | bg `#e0f2fe`, text `#0284c7` |
| CLASSGROUP      | `decoration-success` | bg `#ccfbf1`, text `#0d9488` |
| PERSONGROUP     | `decoration-warning` | bg `#fef3c7`, text `#d97706` |
| SCHOOLJAAR      | `decoration-info` | bg `#e0f2fe`, text `#0284c7` |
| Error status    | `decoration-danger` | bg `#fee2e2`, text `#dc2626` |
| Completed       | `decoration-success` | bg `#ccfbf1`, text `#0d9488` |

**Badge XML pattern:**
```xml
<field name="type_field" widget="badge"
       decoration-info="type_field.name == 'TYPE_A'"
       decoration-success="type_field.name == 'TYPE_B'"
       decoration-warning="type_field.name == 'TYPE_C'"/>
```

---

## 9. Utility CSS Classes

Defined in `myschool_admin/static/src/css/myschool_theme.css`:

| Class            | Effect                                        | Usage                    |
|------------------|-----------------------------------------------|--------------------------|
| `ms-field-mono`  | Monospace font, 12px, tight letter-spacing    | FQDN, DN, OU path fields |

```xml
<field name="person_fqdn_internal" class="ms-field-mono"/>
<field name="ou_fqdn_internal" class="ms-field-mono"/>
```

---

## 10. CSS File Reference

All styles live in `myschool_admin/static/src/css/myschool_theme.css`.

| Section | What it styles | Key selectors |
|---------|---------------|---------------|
| 1. Navbar | Topbar bg, brand, menu items | `.o_main_navbar` |
| 2. Buttons | Primary/secondary/stat buttons | `.btn-primary`, `.oe_stat_button` |
| 3. Form view | Sheet, statusbar, groups, labels, fields, title | `.o_form_view .o_form_sheet`, `.oe_title`, `.o_inner_group` |
| 4. Tabs | Notebook nav links | `.o_notebook .nav-link` |
| 5. List view | Table container, headers, cells, rows | `.o_list_view .o_list_table`, `thead th`, `tbody td` |
| 6. Kanban | Card backgrounds, hover | `.o_kanban_view .o_kanban_record` |
| 7. Control panel | Breadcrumbs, search, facets, pager | `.o_control_panel .o_searchview` |
| 8. Badges | Color overrides for all badge types | `.badge.text-bg-*`, `.o_field_badge .badge` |
| 9. Links & misc | Form links, checkbox accent, selection | `a:not(.btn)`, `input:checked` |
| 10. Chatter | Message bubbles | `.o-mail-Chatter` |
| 11. Modals | Header/footer borders, radius | `.modal-content` |
| 12. Scrollbar | Thin teal scrollbars | `::-webkit-scrollbar` |
| 13. Utility | `ms-field-mono` | `.ms-field-mono` |
| 14. Toggles | Boolean toggle brand color | `.form-check-input:checked` |
| 15. Dropdowns | Filter/group-by menus | `.dropdown-menu .dropdown-item` |

---

## 11. Interactive States

| State    | CSS Pattern                                                              |
|----------|-------------------------------------------------------------------------|
| Hover    | `background: #e6f7f8;` or `#f0f8f8;`, `border-color: var(--ms-brand-2);` |
| Active   | `background: var(--ms-brand-1); color: #fff;` or `background: #d9f2f4;` |
| Focus    | `border-color: var(--ms-brand-2); box-shadow: 0 0 0 3px rgba(0,125,140,.1);` |
| Disabled | `opacity: .5;` or `background: #f5fafa; color: var(--ms-text-muted);` |
| Readonly | `background: #f5fafa; border-color: var(--ms-border-light); color: var(--ms-text-muted);` |

---

## 12. Do's and Don'ts

**Do:**
- Use CSS custom properties (`--ms-*`) for all colors
- Use `!important` on CSS overrides (Odoo defaults are high-specificity)
- Use `widget="badge"` with `decoration-*` for type fields in lists
- Use `widget="boolean_toggle"` for editable booleans in forms
- Use `widget="boolean"` for read-only boolean columns in lists
- Use `class="ms-field-mono"` on FQDN/DN/technical text fields
- Use `bg_color="text-bg-danger"` on `web_ribbon`
- Use `<list>` tag, `list,form` view_mode (Odoo 19)
- Use `<separator/>` between filter groups in search views
- Use `{'search_default_active': 1}` on actions

**Don't:**
- Use Odoo's default purple (`#714B67`) — replaced by `--ms-brand-1`
- Use `bg_color="danger"` on web_ribbon — use `bg_color="text-bg-danger"`
- Use `<tree>` tag — use `<list>` (Odoo 19)
- Use `tree,form` in view_mode — use `list,form`
- Use `<group>` inside `<search>` views (causes Odoo 19 error)
- Use pure black (`#000`) — use `--ms-black` (`#252525`)
- Use generic gray borders (`#ddd`) — use `--ms-border` / `--ms-border-light`
- Use `widget="label_selection"` — deprecated, use `widget="badge"` instead
