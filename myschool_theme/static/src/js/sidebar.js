/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { cookie } from "@web/core/browser/cookie";

export class AppSidebar extends Component {
    static template = "myschool_theme.AppSidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.state = useState({
            collapsed: cookie.get("ms_sidebar_collapsed") === "1",
        });
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.render());
    }

    get apps() {
        return this.menuService.getApps();
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    toggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        cookie.set("ms_sidebar_collapsed", this.state.collapsed ? "1" : "0", 365 * 24 * 60 * 60);
    }

    onAppClick(app) {
        this.menuService.selectMenu(app);
    }
}
