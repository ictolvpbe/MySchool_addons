/** @odoo-module **/
import { Component, onWillStart, useChildSubEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

export class KostenDashboardAction extends Component {
    static template = "kosten_dashboard.KostenDashboardAction";
    static components = { View };
    static props = ["*"];
    static displayName = "Kosten";

    setup() {
        this.orm = useService("orm");
        this.viewProps = null;

        useChildSubEnv({
            config: {
                ...this.env.config,
                setDisplayName: () => {},
            },
        });

        onWillStart(async () => {
            const ids = await this.orm.search("kosten.dashboard", [], { limit: 1 });
            const resId = ids.length ? ids[0] : false;

            this.viewProps = {
                type: "form",
                resModel: "kosten.dashboard",
                resId: resId,
                display: { controlPanel: false },
                views: [[false, "form"]],
            };
        });
    }
}

registry.category("actions").add("kosten_dashboard_action", KostenDashboardAction);
