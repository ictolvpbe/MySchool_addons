/** @odoo-module **/
import { Component, onWillStart, useChildSubEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

export class DirectieDashboardAction extends Component {
    static template = "myschool_directie_dashboard.DashboardAction";
    static components = { View };
    static props = ["*"];
    static displayName = "Directie Dashboard";

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
            // Find or create a singleton dashboard record for this user
            let ids = await this.orm.search("myschool.directie.dashboard", [], { limit: 1 });
            let resId;
            if (ids.length) {
                resId = ids[0];
            } else {
                resId = await this.orm.create("myschool.directie.dashboard", [{}]);
                resId = Array.isArray(resId) ? resId[0] : resId;
            }
            this.viewProps = {
                type: "form",
                resModel: "myschool.directie.dashboard",
                resId: resId,
                display: { controlPanel: false },
                views: [[false, "form"]],
            };
        });
    }
}

registry.category("actions").add("myschool_directie_dashboard_action", DirectieDashboardAction);
