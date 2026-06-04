/** @odoo-module **/

/**
 * Global theme toggle in the navbar systray.
 *
 * Cycles auto → dark → light → auto via the myschool_theme service.
 * The icon reflects the current mode; tooltip shows the next state.
 *
 * Registered in the "systray" registry so it appears on every backend
 * page (same area as the user menu / notifications icon).
 */

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MsThemeToggle extends Component {
    static template = "myschool_admin.MsThemeToggle";
    static props = {};

    setup() {
        this.theme = useService("myschool_theme");
        this.state = useState({ mode: "auto" });

        const onChange = (ev) => {
            const next = ev?.detail?.mode;
            if (next) this.state.mode = next;
        };

        onWillStart(() => {
            this.state.mode = this.theme.mode;
            this.theme.bus.addEventListener("change", onChange);
        });

        onWillUnmount(() => {
            this.theme.bus.removeEventListener("change", onChange);
        });
    }

    get iconClass() {
        if (this.state.mode === "dark") return "fa fa-moon-o";
        if (this.state.mode === "light") return "fa fa-sun-o";
        return "fa fa-adjust";
    }

    get title() {
        if (this.state.mode === "dark") return "Thema: Donker (klik → Licht)";
        if (this.state.mode === "light") return "Thema: Licht (klik → Volg systeem)";
        return "Thema: Volg systeem (klik → Donker)";
    }

    onClick() {
        this.theme.cycle();
    }
}

// Sequence: lower numbers appear first (left-most). 50 places the
// toggle to the left of the user menu (typically sequence 100+).
registry.category("systray").add(
    "myschool_admin.theme_toggle",
    { Component: MsThemeToggle },
    { sequence: 50 },
);
