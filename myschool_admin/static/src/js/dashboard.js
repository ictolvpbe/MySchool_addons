/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Icon } from "@myschool_web/components/icon/icon";

/**
 * MySchool Admin Dashboard — OWL2 client-action component.
 */
export class MySchoolDashboard extends Component {
    static template = "myschool_admin.Dashboard";
    static components = { Icon };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            kpis: {},
            heroStats: {},
            recentTasks: [],
            systemEvents: [],
            recentActivity: [],
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const data = await this.orm.call(
                "myschool.admin.dashboard",
                "get_dashboard_data",
                [],
            );
            this.state.kpis = data.kpis || {};
            this.state.heroStats = data.hero_stats || {};
            this.state.recentTasks = data.recent_tasks || [];
            this.state.systemEvents = data.system_events || [];
            this.state.recentActivity = data.recent_activity || [];
        } catch (e) {
            console.error("Dashboard load error:", e);
        }
        this.state.loading = false;
    }

    async onRefresh() {
        this.state.loading = true;
        await this.loadData();
    }

    // ----- Begroeting (calm-tech header) -----

    get greeting() {
        const h = new Date().getHours();
        if (h < 6) return "Goedenacht";
        if (h < 12) return "Goedemorgen";
        if (h < 18) return "Goedemiddag";
        return "Goedenavond";
    }

    get firstName() {
        return (user.name || "").trim().split(/\s+/)[0] || "";
    }

    get todayLabel() {
        const s = new Date().toLocaleDateString("nl-BE", {
            weekday: "long",
            day: "numeric",
            month: "long",
        });
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    // ----- Navigation helpers -----

    openObjectBrowser() {
        this.action.doAction("myschool_admin.action_object_browser_client");
    }

    openPersons() {
        this.action.doAction("myschool_admin.action_myschool_person");
    }

    openTasks() {
        this.action.doAction("myschool_admin.action_betask_all");
    }

    openPendingTasks() {
        this.action.doAction("myschool_admin.action_betask_pending");
    }

    openEvents() {
        this.action.doAction("myschool_admin.action_sys_event_all");
    }

    // ----- Formatting helpers (used in template) -----

    formatNumber(n) {
        if (n === undefined || n === null) return "0";
        return n.toLocaleString("nl-BE");
    }

    statusBadgeClass(status) {
        const map = {
            done: "db-badge-success",
            pending: "db-badge-warning",
            processing: "db-badge-info",
            error: "db-badge-error",
        };
        return "db-badge-status " + (map[status] || "db-badge-neutral");
    }

    statusLabel(status) {
        const map = {
            done: "Voltooid",
            pending: "In wachtrij",
            processing: "Bezig",
            error: "Fout",
        };
        return map[status] || status;
    }

    severityBadgeClass(severity) {
        const map = {
            info: "db-badge-info",
            error: "db-badge-error",
            warning: "db-badge-warning",
            success: "db-badge-success",
        };
        return "db-badge-status " + (map[severity] || "db-badge-neutral");
    }

    severityLabel(severity) {
        const map = {
            info: "Info",
            error: "Fout",
            warning: "Waarschuwing",
            success: "Geslaagd",
        };
        return map[severity] || severity;
    }

    activityClass(status) {
        return "db-tl-item db-tl-" + (status || "info");
    }
}

registry.category("actions").add("myschool_dashboard", MySchoolDashboard);
