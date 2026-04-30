/** @odoo-module **/
import { Component, onWillStart, onMounted, onWillUnmount, useChildSubEnv } from "@odoo/owl";
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

        // Toggle .is-zero on badge buttons so empty counters render muted.
        onMounted(() => {
            const root = document.querySelector(".o_myschool_dashboard_container");
            if (!root) return;
            const apply = () => {
                root.querySelectorAll(".ms-badge-btn").forEach((btn) => {
                    const fld = btn.querySelector(".o_field_widget");
                    if (!fld) return;
                    const val = parseInt((fld.textContent || "").trim(), 10);
                    btn.classList.toggle("is-zero", val === 0);
                });
            };
            apply();
            this._zeroObserver = new MutationObserver(() => apply());
            this._zeroObserver.observe(root, {
                childList: true, subtree: true, characterData: true,
            });
        });

        onWillUnmount(() => {
            if (this._zeroObserver) this._zeroObserver.disconnect();
        });
    }
}

registry.category("actions").add("myschool_dashboard_action", DashboardAction);
