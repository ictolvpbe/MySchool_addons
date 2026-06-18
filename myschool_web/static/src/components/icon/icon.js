/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Icon — monochroom lijn-icoon (Lucide/Feather-stijl) als inline-SVG.
 *
 * Calm-tech: `stroke-width 1.6`, `currentColor`, rounded caps/joins. Omdat de
 * SVG `currentColor` erft, is het icoon monochroom én theme-volgend (light/dark)
 * zonder extra styling — geef gewoon een tekstkleur op de ouder.
 *
 * NB: dit vervangt Font Awesome enkel in ONZE eigen OWL-componenten. Odoo's
 * native chrome (formulier-/lijst-/kanban-controls) blijft Font Awesome.
 *
 * Props:
 *   - name:        string  — icoonnaam (zie de set in icon.xml; volgt de FA-namen
 *                            die we al gebruikten, bv. "users", "sitemap", "bell")
 *   - size:        number  — px (default 18)
 *   - strokeWidth: number  — default 1.6
 *
 * Een `class`-attribuut op <Icon .../> wordt door OWL automatisch op de root-svg
 * doorgezet.
 *
 * Gebruik:
 *   import { Icon } from "@myschool_web/components/icon/icon";
 *   static components = { Icon };
 *   <Icon name="users" size="20"/>
 */
export class Icon extends Component {
    static template = "myschool_web.Icon";
    static props = {
        name: { type: String },
        size: { type: [Number, String], optional: true },
        strokeWidth: { type: [Number, String], optional: true },
    };
    static defaultProps = {
        size: 18,
        strokeWidth: 1.6,
    };
}
