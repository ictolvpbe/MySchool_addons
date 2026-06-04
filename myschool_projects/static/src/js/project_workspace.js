/** @odoo-module **/
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
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

const TYPE_LABELS = {
    task: "Task", milestone: "Milestone", phase: "Phase", epic: "Epic", bug: "Bug",
};
const STATE_LABELS = {
    todo: "To Do", in_progress: "In Progress", blocked: "Blocked",
    done: "Done", cancelled: "Cancelled",
};
const PRIORITY_LABELS = { "0": "Low", "1": "Normal", "2": "High", "3": "Critical" };

// Toggleable table columns (Subject is always shown). Order = display order.
const COLUMN_DEFS = [
    { key: "type", label: "Type" },
    { key: "id", label: "ID" },
    { key: "status", label: "Status" },
    { key: "milestone", label: "Milestone" },
    { key: "assignee", label: "Assignee" },
    { key: "priority", label: "Priority" },
    { key: "start", label: "Start" },
    { key: "deadline", label: "Deadline" },
];
const DEFAULT_COLS = {
    type: true, id: true, status: true, milestone: false,
    assignee: true, priority: false, start: false, deadline: true,
};
const COLS_STORAGE_KEY = "myschool_projects.workspace.wpCols";

/**
 * Hierarchical work-packages table (OpenProject-style): a flat-but-nested
 * table of work items with indent + expand carets in the subject column,
 * type/status badges, assignee and dates. Rows open the item form dialog.
 */
export class WorkPackageTable extends Component {
    static template = "myschool_projects.WorkPackageTable";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.typeLabels = TYPE_LABELS;
        this.stateLabels = STATE_LABELS;
        this.priorityLabels = PRIORITY_LABELS;
        this.columnDefs = COLUMN_DEFS;
        this.stateOptionList = Object.entries(STATE_LABELS).map(
            ([key, label]) => ({ key, label }));
        this.renameInput = useRef("renameInput");
        let cols = { ...DEFAULT_COLS };
        try {
            const saved = JSON.parse(window.localStorage.getItem(COLS_STORAGE_KEY) || "null");
            if (saved) cols = { ...cols, ...saved };
        } catch (e) { /* ignore */ }
        this.state = useState({
            byId: {}, roots: [], expanded: {}, loading: true,
            editingId: false, editingName: "", statusOpenId: false,
            cols, colMenuOpen: false,
        });
        onWillStart(async () => { await this.load(); });
        // Focus + select the rename input when it appears.
        useEffect(
            () => {
                if (this.state.editingId && this.renameInput.el) {
                    this.renameInput.el.focus();
                    this.renameInput.el.select();
                }
            },
            () => [this.state.editingId],
        );
    }

    async load() {
        this.state.loading = true;
        const recs = await this.orm.searchRead(
            "myschool.project.task",
            [["project_id", "=", this.props.projectId]],
            ["name", "item_type", "state", "assigned_id", "date_start",
             "date_deadline", "priority", "parent_id", "child_count", "milestone_id"],
            { order: "sequence, id" },
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
        const expanded = {};
        recs.forEach((r) => { if (byId[r.id].children.length) expanded[r.id] = true; });
        this.state.byId = byId;
        this.state.roots = roots;
        this.state.expanded = expanded;
        this.state.loading = false;
    }

    get visibleRows() {
        const out = [];
        const walk = (node, depth) => {
            out.push({ item: node, depth, hasChildren: node.children.length > 0 });
            if (node.children.length && this.state.expanded[node.id]) {
                node.children.forEach((c) => walk(c, depth + 1));
            }
        };
        this.state.roots.forEach((r) => walk(r, 0));
        return out;
    }

    toggle(id) { this.state.expanded[id] = !this.state.expanded[id]; }

    get colCount() {
        // visible toggleable columns + the always-on Subject column
        return Object.values(this.state.cols).filter(Boolean).length + 1;
    }

    // ---- column config ----
    toggleColMenu() { this.state.colMenuOpen = !this.state.colMenuOpen; }
    toggleCol(key) {
        this.state.cols[key] = !this.state.cols[key];
        window.localStorage.setItem(
            COLS_STORAGE_KEY, JSON.stringify(this.state.cols));
    }

    /** Rolled-up % of done leaf items under a summary node (milestones and
     *  cancelled items excluded), MS-Project style. */
    summaryPct(node) {
        let done = 0;
        let total = 0;
        const walk = (n) => {
            if (n.children.length) {
                n.children.forEach(walk);
            } else if (n.item_type !== "milestone" && n.state !== "cancelled") {
                total += 1;
                if (n.state === "done") done += 1;
            }
        };
        node.children.forEach(walk);
        return total ? Math.round((done / total) * 100) : 0;
    }

    openItem(id) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.task",
                res_id: id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.load() },
        );
    }

    createItem() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.task",
                views: [[false, "form"]],
                target: "new",
                context: { default_project_id: this.props.projectId },
            },
            { onClose: () => this.load() },
        );
    }

    addChild(item) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.task",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_project_id: this.props.projectId,
                    default_parent_id: item.id,
                },
            },
            { onClose: () => this.load() },
        );
    }

    // ---- inline rename ----
    startRename(item) {
        this.state.editingId = item.id;
        this.state.editingName = item.name;
    }
    async saveRename(item) {
        const name = (this.state.editingName || "").trim();
        this.state.editingId = false;
        if (name && name !== item.name) {
            await this.orm.write("myschool.project.task", [item.id], { name });
            item.name = name;
        }
    }
    onRenameKeydown(ev, item) {
        if (ev.key === "Enter") { ev.preventDefault(); this.saveRename(item); }
        else if (ev.key === "Escape") { this.state.editingId = false; }
    }

    // ---- inline status ----
    openStatus(id) { this.state.statusOpenId = id; }
    closeStatus() { this.state.statusOpenId = false; }
    async setStatus(item, value) {
        this.state.statusOpenId = false;
        if (value && value !== item.state) {
            await this.orm.write("myschool.project.task", [item.id], { state: value });
            item.state = value;
        }
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
    static components = { View, WbsNode, WorkPackageTable };
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
            view: "table",
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
