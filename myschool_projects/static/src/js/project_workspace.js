/** @odoo-module **/
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * Lightweight right-click context menu (à la myschool_admin object_browser).
 * props: { x, y, title, items:[{action,label,icon,danger}|{divider:true}],
 *          onAction(action), onClose() }
 */
export class WsContextMenu extends Component {
    static template = "myschool_projects.ContextMenu";
    static props = ["*"];
    onItem(action) {
        this.props.onAction(action);
        this.props.onClose();
    }
}

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
        onContextMenu: { type: Function, optional: true },
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
    onContextMenu(ev) {
        ev.stopPropagation();
        if (this.props.onContextMenu) this.props.onContextMenu(ev, this.props.node.id);
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
    static components = { WsContextMenu };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
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
            dragId: false, dragOverId: false, dropMode: "onto",
            ctx: null,
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

    // ---- drag: reorder (before/after) + re-parent (onto) ----
    onDragStart(ev, item) {
        this.state.dragId = item.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(item.id));
    }
    onDragEnd() {
        this.state.dragId = false;
        this.state.dragOverId = false;
    }
    _isInSubtree(rootId, nodeId) {
        const root = this.state.byId[rootId];
        if (!root) return false;
        let found = false;
        const walk = (n) => { if (n.id === nodeId) found = true; n.children.forEach(walk); };
        root.children.forEach(walk);
        return found;
    }
    _newParentFor(targetItem, mode) {
        if (mode === "onto") return targetItem.id;
        return targetItem.parent_id ? targetItem.parent_id[0] : false;
    }
    canDrop(targetItem, mode) {
        const id = this.state.dragId;
        if (!id || id === targetItem.id) return false;
        const np = this._newParentFor(targetItem, mode);
        if (np === id) return false;
        if (np && this._isInSubtree(id, np)) return false;
        return true;
    }
    _dropMode(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const y = ev.clientY - rect.top;
        const h = rect.height || 1;
        if (y < h * 0.3) return "before";
        if (y > h * 0.7) return "after";
        return "onto";
    }
    onDragOver(ev, item) {
        const mode = this._dropMode(ev);
        if (this.canDrop(item, mode)) {
            ev.preventDefault();
            this.state.dragOverId = item.id;
            this.state.dropMode = mode;
        }
    }
    onDragLeave(item) {
        if (this.state.dragOverId === item.id) this.state.dragOverId = false;
    }
    async onDrop(ev, item) {
        ev.preventDefault();
        const id = this.state.dragId;
        const mode = this.state.dropMode;
        const ok = this.canDrop(item, mode);
        this.state.dragOverId = false;
        this.state.dragId = false;
        if (!id || !ok) return;
        try {
            if (mode === "onto") {
                await this.orm.write("myschool.project.task", [id], { parent_id: item.id });
            } else {
                await this._reorder(id, item, mode === "after");
            }
        } catch (e) {
            this.notification.add("Kon item niet verplaatsen.", { type: "danger" });
        }
        await this.load();
    }
    async _reorder(id, targetItem, after) {
        const npId = targetItem.parent_id ? targetItem.parent_id[0] : false;
        const sibs = (npId ? this.state.byId[npId].children : this.state.roots)
            .filter((n) => n.id !== id);
        let idx = sibs.findIndex((n) => n.id === targetItem.id);
        if (after) idx += 1;
        sibs.splice(idx, 0, this.state.byId[id]);
        await Promise.all(sibs.map((n, i) => {
            const vals = { sequence: i * 10 };
            if (n.id === id) vals.parent_id = npId;
            return this.orm.write("myschool.project.task", [n.id], vals);
        }));
    }

    // ---- drop zone onder de tabel: maak top-level + laatste ----
    onDropZoneOver(ev) {
        if (this.state.dragId) {
            ev.preventDefault();
            this.state.dragOverId = "bottom";
        }
    }
    onDropZoneLeave() {
        if (this.state.dragOverId === "bottom") this.state.dragOverId = false;
    }
    async onDropBottom(ev) {
        ev.preventDefault();
        const id = this.state.dragId;
        this.state.dragOverId = false;
        this.state.dragId = false;
        if (!id) return;
        try {
            const roots = this.state.roots.filter((n) => n.id !== id);
            roots.push(this.state.byId[id]);
            await Promise.all(roots.map((n, i) => {
                const vals = { sequence: i * 10 };
                if (n.id === id) vals.parent_id = false;
                return this.orm.write("myschool.project.task", [n.id], vals);
            }));
        } catch (e) {
            this.notification.add("Kon item niet verplaatsen.", { type: "danger" });
        }
        await this.load();
    }

    // ---- right-click context menu ----
    onRowContextMenu(ev, item) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, item };
    }
    onEmptyContextMenu(ev) {
        ev.preventDefault();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, item: false };
    }
    closeCtx() { this.state.ctx = null; }
    get ctxItems() {
        const item = this.state.ctx && this.state.ctx.item;
        if (!item) {
            return [{ action: "add", label: "Add", icon: "fa fa-plus" }];
        }
        const items = [
            { action: "add", label: "Add", icon: "fa fa-plus" },
            { action: "add_sub", label: "Add sub-item", icon: "fa fa-level-down" },
            { action: "properties", label: "Properties", icon: "fa fa-pencil-square-o" },
            { action: "rename", label: "Rename", icon: "fa fa-i-cursor" },
            { action: "move", label: "Move…", icon: "fa fa-arrows" },
        ];
        if (item.parent_id) {
            items.push({ action: "outdent", label: "Een niveau omhoog", icon: "fa fa-outdent" });
        }
        items.push({ divider: true });
        items.push({ action: "delete", label: "Delete", icon: "fa fa-trash", danger: true });
        return items;
    }
    onCtxAction(action) {
        if (action === "add") { this.createItem(); return; }
        const item = this.state.ctx && this.state.ctx.item;
        if (!item) return;
        switch (action) {
            case "add": this.createItem(); break;
            case "add_sub": this.addChild(item); break;
            case "properties": this.openItem(item.id); break;
            case "rename": this.startRename(item); break;
            case "move": this.moveItem(item); break;
            case "outdent": this.outdentItem(item); break;
            case "delete": this.deleteItem(item); break;
        }
    }
    async outdentItem(item) {
        const parentId = item.parent_id ? item.parent_id[0] : false;
        if (!parentId) return;  // al top-level
        const parentNode = this.state.byId[parentId];
        const newParentId = parentNode && parentNode.parent_id ? parentNode.parent_id[0] : false;
        try {
            await this.orm.write("myschool.project.task", [item.id], { parent_id: newParentId });
        } catch (e) {
            this.notification.add("Kon item niet verplaatsen.", { type: "danger" });
        }
        await this.load();
    }
    moveItem(item) {
        this.dialog.add(SelectCreateDialog, {
            resModel: "myschool.project.task",
            title: "Move under…",
            noCreate: true,
            multiSelect: false,
            domain: [["project_id", "=", this.props.projectId], ["id", "!=", item.id]],
            onSelected: async (resIds) => {
                if (!resIds || !resIds.length) return;
                try {
                    await this.orm.write(
                        "myschool.project.task", [item.id], { parent_id: resIds[0] });
                } catch (e) {
                    this.notification.add("Verplaatsen mislukt (cyclus?).", { type: "danger" });
                }
                await this.load();
            },
        });
    }
    deleteItem(item) {
        this.dialog.add(ConfirmationDialog, {
            title: "Delete",
            body: `"${item.name}" en alle subtaken verwijderen?`,
            confirm: async () => {
                try {
                    await this.orm.unlink("myschool.project.task", [item.id]);
                } catch (e) {
                    this.notification.add("Verwijderen mislukt.", { type: "danger" });
                }
                await this.load();
            },
        });
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
    static components = { View, WbsNode, WorkPackageTable, WsContextMenu };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
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
            ctx: null,
        });
        onWillStart(async () => { await this.loadProjects(); });
    }

    // ---- sidebar project context menu ----
    onNodeContextMenu(ev, id) {
        ev.preventDefault();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, id };
    }
    onEmptyContextMenu(ev) {
        ev.preventDefault();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, id: false };
    }
    closeCtx() { this.state.ctx = null; }
    get ctxItems() {
        if (!this.state.ctx || !this.state.ctx.id) {
            return [
                { action: "add_project", label: "Add Project", icon: "fa fa-folder-o" },
            ];
        }
        return [
            { action: "add_project", label: "Add Project", icon: "fa fa-folder-o" },
            { action: "add_sub", label: "Add sub-project", icon: "fa fa-sitemap" },
            { action: "rename", label: "Rename", icon: "fa fa-i-cursor" },
            { action: "properties", label: "Properties", icon: "fa fa-pencil-square-o" },
            { divider: true },
            { action: "delete", label: "Delete", icon: "fa fa-trash", danger: true },
        ];
    }
    onCtxAction(action) {
        const id = this.state.ctx && this.state.ctx.id;
        switch (action) {
            case "add_project": this._newProject(false); break;
            case "add_sub": this._newProject(id); break;
            case "rename": this._renameProject(id); break;
            case "properties": this._openProjectForm(id); break;
            case "delete": this._deleteProject(id); break;
        }
    }
    _newProject(parentId) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project",
                views: [[false, "form"]],
                target: "new",
                context: parentId ? { default_parent_id: parentId } : {},
            },
            { onClose: () => this.loadProjects() },
        );
    }
    _openProjectForm(id) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project",
                res_id: id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.loadProjects() },
        );
    }
    async _renameProject(id) {
        const proj = this.state.byId[id];
        const name = window.prompt("Nieuwe projectnaam:", proj ? proj.name : "");
        if (name && name.trim()) {
            await this.orm.write("myschool.project", [id], { name: name.trim() });
            await this.loadProjects();
        }
    }
    _deleteProject(id) {
        const proj = this.state.byId[id];
        this.dialog.add(ConfirmationDialog, {
            title: "Delete project",
            body: `Project "${proj ? proj.name : id}" verwijderen? `
                + `(sub-projecten moeten eerst weg)`,
            confirm: async () => {
                try {
                    await this.orm.unlink("myschool.project", [id]);
                    if (this.state.selectedId === id) this.state.selectedId = false;
                } catch (e) {
                    this.notification.add(
                        "Verwijderen mislukt (heeft het sub-projecten?).",
                        { type: "danger" });
                }
                await this.loadProjects();
            },
        });
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
