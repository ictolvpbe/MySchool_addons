/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

const STORAGE_KEY = "myschool_projects.workspace.sidebarWidth";

const TASK_STATES = [
    { key: "todo", label: "To Do" },
    { key: "in_progress", label: "In Progress" },
    { key: "blocked", label: "Blocked" },
    { key: "done", label: "Done" },
    { key: "cancelled", label: "Cancelled" },
];

/**
 * One node of the WBS sidebar tree (recursive).
 */
export class WbsNode extends Component {
    static template = "myschool_projects.WbsNode";
    static components = { WbsNode };
    static props = {
        node: Object,
        level: { type: Number, optional: true },
        selectedId: { type: [Number, Boolean], optional: true },
        expanded: { type: Object, optional: true },
        onSelect: { type: Function, optional: true },
        onToggle: { type: Function, optional: true },
    };

    get level() { return this.props.level || 0; }
    get childLevel() { return this.level + 1; }
    get hasChildren() {
        return this.props.node.children && this.props.node.children.length > 0;
    }
    get isExpanded() {
        return !!(this.props.expanded && this.props.expanded[this.props.node.id]);
    }
    get isSelected() { return this.props.selectedId === this.props.node.id; }
    get pct() { return Math.round(this.props.node.progress || 0); }

    onRowClick(ev) {
        ev.stopPropagation();
        if (this.props.onSelect) this.props.onSelect(this.props.node.id);
    }
    onCaretClick(ev) {
        ev.stopPropagation();
        if (this.props.onToggle) this.props.onToggle(this.props.node.id);
    }
}

/**
 * Project Workspace — a modern PM shell: WBS sidebar + view-switcher
 * (Overview / Board / List / Calendar). Board/List/Calendar embed the
 * native Odoo task views (scoped to the selected project) so drag-drop,
 * group-by and filters come for free.
 */
export class ProjectWorkspace extends Component {
    static template = "myschool_projects.Workspace";
    static components = { View, WbsNode };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.taskStates = TASK_STATES;
        const savedW = parseInt(window.localStorage.getItem(STORAGE_KEY) || "300", 10);
        this.state = useState({
            roots: [],
            byId: {},
            selectedId: false,
            view: "overview",
            expanded: {},
            overview: null,
            sidebarWidth: Number.isNaN(savedW) ? 300 : savedW,
            loading: true,
        });
        onWillStart(async () => { await this.loadProjects(); });
    }

    async loadProjects() {
        const recs = await this.orm.searchRead(
            "myschool.project",
            [],
            ["name", "code", "parent_id", "state", "progress", "child_count"],
            { order: "name" },
        );
        const byId = {};
        recs.forEach((r) => { byId[r.id] = { ...r, children: [] }; });
        const roots = [];
        recs.forEach((r) => {
            const node = byId[r.id];
            const pid = r.parent_id ? r.parent_id[0] : false;
            if (pid && byId[pid]) byId[pid].children.push(node);
            else roots.push(node);
        });
        this.state.byId = byId;
        this.state.roots = roots;
        this.state.loading = false;
        if (!this.state.selectedId && roots.length) {
            this.state.expanded[roots[0].id] = true;
            await this.selectProject(roots[0].id);
        }
    }

    get selected() { return this.state.byId[this.state.selectedId] || null; }

    async selectProject(id) {
        this.state.selectedId = id;
        if (this.state.view === "overview") await this.loadOverview();
    }

    onToggle(id) { this.state.expanded[id] = !this.state.expanded[id]; }

    async setView(v) {
        this.state.view = v;
        if (v === "overview") await this.loadOverview();
    }

    async loadOverview() {
        const id = this.state.selectedId;
        if (!id) { this.state.overview = null; return; }
        const tasks = await this.orm.searchRead(
            "myschool.project.task",
            [["project_id", "=", id], ["item_type", "!=", "milestone"]],
            ["state"]);
        const counts = {};
        tasks.forEach((t) => { counts[t.state] = (counts[t.state] || 0) + 1; });
        const milestones = await this.orm.searchRead(
            "myschool.project.task",
            [["project_id", "=", id], ["item_type", "=", "milestone"]],
            ["name", "date_deadline", "state"], { order: "date_deadline" });
        const proj = this.state.byId[id];
        this.state.overview = {
            taskCounts: counts,
            taskTotal: tasks.length,
            milestones,
            children: proj ? proj.children : [],
        };
    }

    get taskViewProps() {
        const id = this.state.selectedId;
        return {
            type: this.state.view,
            resModel: "myschool.project.task",
            domain: [["project_id", "=", id]],
            context: { default_project_id: id },
            views: [[false, this.state.view]],
            display: { controlPanel: true },
        };
    }

    onSplitterDown(ev) {
        ev.preventDefault();
        const startX = ev.clientX;
        const startW = this.state.sidebarWidth;
        const onMove = (e) => {
            let w = startW + (e.clientX - startX);
            w = Math.max(200, Math.min(560, w));
            this.state.sidebarWidth = w;
        };
        const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            window.localStorage.setItem(STORAGE_KEY, String(this.state.sidebarWidth));
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
    }

    openProjectForm() {
        if (!this.state.selectedId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "myschool.project",
            res_id: this.state.selectedId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("myschool_projects_workspace", ProjectWorkspace);
