/** @odoo-module **/

import { Component, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { usePopover } from "@web/core/popover/popover_hook";

/**
 * Curated palette + icon set for myschool type configuration.
 *
 * Palette is short on purpose — admins should pick from a coherent set
 * unless they really need a custom hex. Custom hex remains available
 * via the inline text input.
 */
const PALETTE = [
    "#0d9488", // teal (brand)
    "#0094a4", // brand-2
    "#0284c7", // blue
    "#7c3aed", // purple
    "#9333ea", // violet
    "#d97706", // amber
    "#ea580c", // orange
    "#dc2626", // red
    "#65a30d", // lime
    "#16a34a", // green
    "#0891b2", // cyan
    "#db2777", // pink
    "#475569", // slate
    "#1f2937", // gray-900
];

/**
 * Curated Font-Awesome 4 set. Grouped by context but flattened so the
 * picker shows them in one grid. Keep this list reasonably small — if
 * an admin needs something exotic, the inline text input still accepts
 * any "fa fa-xxx" string.
 */
const ICONS = [
    // Education / org
    "fa fa-university", "fa fa-graduation-cap", "fa fa-book", "fa fa-school",
    "fa fa-building", "fa fa-building-o", "fa fa-sitemap", "fa fa-bank",
    "fa fa-institution", "fa fa-flag", "fa fa-flag-o", "fa fa-globe",
    // People
    "fa fa-user", "fa fa-user-circle", "fa fa-user-circle-o", "fa fa-users",
    "fa fa-child", "fa fa-male", "fa fa-female", "fa fa-id-badge",
    "fa fa-id-card", "fa fa-handshake-o", "fa fa-user-secret", "fa fa-address-book",
    // Roles / tags
    "fa fa-briefcase", "fa fa-star", "fa fa-bookmark", "fa fa-tag",
    "fa fa-tags", "fa fa-trophy", "fa fa-certificate", "fa fa-shield",
    // Tools / admin
    "fa fa-cog", "fa fa-cogs", "fa fa-key", "fa fa-lock",
    "fa fa-folder", "fa fa-folder-open", "fa fa-file", "fa fa-archive",
    "fa fa-cube", "fa fa-cubes", "fa fa-puzzle-piece", "fa fa-th-large",
    // Misc
    "fa fa-heart", "fa fa-bell", "fa fa-envelope", "fa fa-comments",
    "fa fa-question-circle", "fa fa-info-circle", "fa fa-check-circle",
    "fa fa-exclamation-circle",
];

const HEX_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

// ============================================================
// Color popover
// ============================================================

class MsColorPalette extends Component {
    static template = "myschool_admin.MsColorPalette";
    static props = {
        currentValue: { type: String, optional: true },
        onSelect: Function,
        onClear: Function,
        close: Function,  // injected by popover service
    };

    setup() {
        this.state = useState({
            customHex: this.props.currentValue || "",
        });
        this.palette = PALETTE;
    }

    isCurrent(hex) {
        return (this.props.currentValue || "").toLowerCase() === hex.toLowerCase();
    }

    pick(hex) {
        this.props.onSelect(hex);
        this.props.close();
    }

    onCustomInput(ev) {
        this.state.customHex = ev.target.value;
    }

    onCustomKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.applyCustom();
        }
    }

    applyCustom() {
        const v = (this.state.customHex || "").trim();
        if (!v) {
            this.props.onClear();
            this.props.close();
            return;
        }
        if (!HEX_RE.test(v)) return;  // ignore invalid; user can keep editing
        this.props.onSelect(v.toLowerCase());
        this.props.close();
    }

    clearValue() {
        this.props.onClear();
        this.props.close();
    }
}

// ============================================================
// Icon popover
// ============================================================

class MsIconPalette extends Component {
    static template = "myschool_admin.MsIconPalette";
    static props = {
        currentValue: { type: String, optional: true },
        currentColor: { type: String, optional: true },
        onSelect: Function,
        onClear: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ filter: "" });
    }

    get filteredIcons() {
        const f = this.state.filter.trim().toLowerCase();
        if (!f) return ICONS;
        return ICONS.filter(i => i.toLowerCase().includes(f));
    }

    isCurrent(icon) {
        return (this.props.currentValue || "").trim() === icon;
    }

    iconStyle(icon) {
        if (!this.isCurrent(icon)) return "";
        return this.props.currentColor ? `color: ${this.props.currentColor};` : "";
    }

    onFilterInput(ev) {
        this.state.filter = ev.target.value;
    }

    pick(icon) {
        this.props.onSelect(icon);
        this.props.close();
    }

    clearValue() {
        this.props.onClear();
        this.props.close();
    }
}

// ============================================================
// Color swatch field
// ============================================================

export class MsColorSwatchField extends Component {
    static template = "myschool_admin.MsColorSwatchField";
    static props = { ...standardFieldProps };

    setup() {
        this.anchorRef = useRef("anchor");
        this.popover = usePopover(MsColorPalette, { position: "bottom-start" });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get isValidHex() {
        return HEX_RE.test(this.value);
    }

    async update(newVal) {
        await this.props.record.update({ [this.props.name]: newVal });
    }

    onClickSwatch() {
        if (this.props.readonly) return;
        this.popover.open(this.anchorRef.el, {
            currentValue: this.value,
            onSelect: (hex) => this.update(hex),
            onClear: () => this.update(false),
        });
    }

    onInput(ev) {
        // Inline hex editing — only commit on blur to avoid spamming updates.
        this._pending = ev.target.value;
    }

    onBlur() {
        if (this._pending === undefined) return;
        const v = (this._pending || "").trim();
        this._pending = undefined;
        if (!v) return this.update(false);
        if (HEX_RE.test(v)) this.update(v.toLowerCase());
    }
}

export const msColorSwatchField = {
    component: MsColorSwatchField,
    supportedTypes: ["char"],
};

registry.category("fields").add("ms_color_swatch", msColorSwatchField);

// ============================================================
// Icon picker field
// ============================================================

export class MsIconPickerField extends Component {
    static template = "myschool_admin.MsIconPickerField";
    static props = { ...standardFieldProps };

    setup() {
        this.anchorRef = useRef("anchor");
        this.popover = usePopover(MsIconPalette, { position: "bottom-start" });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    // Read sibling field "icon_color" off the same record so the preview
    // shows what users will see in the Organisation Manager.
    get color() {
        return this.props.record.data["icon_color"] || "";
    }

    async update(newVal) {
        await this.props.record.update({ [this.props.name]: newVal });
    }

    onClickPreview() {
        if (this.props.readonly) return;
        this.popover.open(this.anchorRef.el, {
            currentValue: this.value,
            currentColor: this.color,
            onSelect: (icon) => this.update(icon),
            onClear: () => this.update(false),
        });
    }

    onInput(ev) {
        this._pending = ev.target.value;
    }

    onBlur() {
        if (this._pending === undefined) return;
        const v = (this._pending || "").trim();
        this._pending = undefined;
        this.update(v || false);
    }
}

export const msIconPickerField = {
    component: MsIconPickerField,
    supportedTypes: ["char"],
};

registry.category("fields").add("ms_icon_picker", msIconPickerField);
