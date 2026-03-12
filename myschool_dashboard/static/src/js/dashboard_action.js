/** @odoo-module **/
import { Component, onWillStart, useChildSubEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

export class DashboardAction extends Component {
    static template = "myschool_dashboard.DashboardAction";
    static components = { View };
    static props = ["*"];
    static displayName = "Aanvragen";

    setup() {
        this.orm = useService("orm");
        this.viewProps = null;

        // Prevent the inner form view from overwriting the client action's
        // displayName (which Odoo uses for the breadcrumb "Back to" link).
        // Without this, the form controller sets it to "" because
        // controlPanel is false and display_name is not loaded.
        useChildSubEnv({
            config: {
                ...this.env.config,
                setDisplayName: () => {},
            },
        });

        onWillStart(async () => {
            // Find the singleton dashboard record
            const ids = await this.orm.search("myschool.dashboard", [], { limit: 1 });
            const resId = ids.length ? ids[0] : false;

            this.viewProps = {
                type: "form",
                resModel: "myschool.dashboard",
                resId: resId,
                display: { controlPanel: false },
                views: [[false, "form"]],
            };
        });
    }
}

registry.category("actions").add("myschool_dashboard_action", DashboardAction);
