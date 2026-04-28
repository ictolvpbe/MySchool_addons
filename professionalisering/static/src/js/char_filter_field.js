/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * char_filter — een Char-veld dat de record bijwerkt op elke toetsaanslag
 * (in plaats van enkel bij blur of Enter). Bedoeld voor live-filtering.
 */
export class CharFilterField extends Component {
    static template = "professionalisering.CharFilterField";
    static props = { ...standardFieldProps, placeholder: { type: String, optional: true } };

    onInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }
}

export const charFilterField = {
    component: CharFilterField,
    extractProps: ({ attrs }) => ({
        placeholder: attrs.placeholder || "",
    }),
    supportedTypes: ["char"],
};

registry.category("fields").add("char_filter", charFilterField);
