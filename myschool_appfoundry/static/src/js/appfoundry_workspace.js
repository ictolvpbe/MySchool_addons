/** @odoo-module **/
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SegmentNav } from "@myschool_web/components/segment_nav/segment_nav";

/**
 * Lightweight right-click context menu (shared look with the rest of MySchool).
 * props: { x, y, title, items:[{action,label,icon,danger}|{divider:true}],
 *          onAction(action), onClose() }
 */
export class AfwContextMenu extends Component {
    static template = "myschool_appfoundry.ContextMenu";
    static props = ["*"];
    onItem(action) {
        this.props.onAction(action);
        this.props.onClose();
    }
}

const STORAGE_KEY = "myschool_appfoundry.workspace.sidebarWidth";

const TYPE_LABELS = {
    story: "Story", bug: "Bug", task: "Task", improvement: "Improvement",
};
const PRIORITY_LABELS = { "0": "Low", "1": "Normal", "2": "High", "3": "Critical" };

// Toggleable backlog columns (Subject is always shown). Order = display order.
const COLUMN_DEFS = [
    { key: "type", label: "Type" },
    { key: "id", label: "ID" },
    { key: "stage", label: "Stage" },
    { key: "sprint", label: "Sprint" },
    { key: "assignee", label: "Assignee" },
    { key: "points", label: "Points" },
    { key: "priority", label: "Priority" },
];
const DEFAULT_COLS = {
    type: true, id: true, stage: true, sprint: true,
    assignee: true, points: true, priority: false,
};
const COLS_STORAGE_KEY = "myschool_appfoundry.workspace.backlogCols";

/**
 * Hierarchical backlog table (OpenProject / myschool_projects style): a
 * flat-but-nested table of AppFoundry items (story → sub-tasks) with indent +
 * expand carets in the subject column, type badges, inline stage/sprint
 * editing, drag re-order / re-parent and a right-click menu.
 */
export class BacklogTable extends Component {
    static template = "myschool_appfoundry.BacklogTable";
    static components = { AfwContextMenu };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.typeLabels = TYPE_LABELS;
        this.priorityLabels = PRIORITY_LABELS;
        this.columnDefs = COLUMN_DEFS;
        this.renameInput = useRef("renameInput");
        let cols = { ...DEFAULT_COLS };
        try {
            const saved = JSON.parse(window.localStorage.getItem(COLS_STORAGE_KEY) || "null");
            if (saved) cols = { ...cols, ...saved };
        } catch (e) { /* ignore */ }
        this.state = useState({
            byId: {}, roots: [], expanded: {}, loading: true,
            editingId: false, editingName: "",
            stageOpenId: false, sprintOpenId: false,
            cols, colMenuOpen: false, search: "", typeFilter: "all",
            dragId: false, dragOverId: false, dropMode: "onto",
            ctx: null,
        });
        onWillStart(async () => { await this.load(); });
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
            "appfoundry.item",
            [["project_id", "=", this.props.projectId]],
            ["name", "sequence", "item_type", "stage_id", "assigned_id",
             "priority", "story_points", "parent_id", "sprint_id"],
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
        const expanded = { ...this.state.expanded };
        recs.forEach((r) => {
            if (byId[r.id].children.length && expanded[r.id] === undefined) {
                expanded[r.id] = true;
            }
        });
        this.state.byId = byId;
        this.state.roots = roots;
        this.state.expanded = expanded;
        this.state.loading = false;
        this._notifyChanged();
    }

    /** Tell the workspace that the open-item set changed so it can refresh the
     *  sidebar counters. */
    _notifyChanged() {
        if (this.props.onItemsChanged) this.props.onItemsChanged();
    }

    get stageById() { return this.props.stageById || {}; }

    matchesType(node) {
        const f = this.state.typeFilter;
        return f === "all" || node.item_type === f;
    }

    get visibleRows() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (q || this.state.typeFilter !== "all") {
            // Tijdens zoeken/filteren: vlakke lijst van matchende items (geen tree).
            return Object.values(this.state.byId)
                .filter((n) => this.matchesType(n)
                    && (n.name || "").toLowerCase().includes(q))
                .map((n) => ({ item: n, depth: 0, hasChildren: n.children.length > 0 }));
        }
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

    setTypeFilter(t) { this.state.typeFilter = t; }
    toggle(id) { this.state.expanded[id] = !this.state.expanded[id]; }

    get colCount() {
        return Object.values(this.state.cols).filter(Boolean).length + 1;
    }
    toggleColMenu() { this.state.colMenuOpen = !this.state.colMenuOpen; }
    toggleCol(key) {
        this.state.cols[key] = !this.state.cols[key];
        window.localStorage.setItem(COLS_STORAGE_KEY, JSON.stringify(this.state.cols));
    }

    itemRef(item) {
        return `${this.props.projectCode || "?"}-${item.sequence || "?"}`;
    }
    stageLabel(item) {
        return item.stage_id ? item.stage_id[1] : "";
    }
    stageClass(item) {
        const meta = item.stage_id && this.stageById[item.stage_id[0]];
        if (!meta) return "o_afw_stage_default";
        if (meta.is_done) return "o_afw_stage_done";
        if (meta.is_cancelled) return "o_afw_stage_cancelled";
        return "o_afw_stage_default";
    }
    sprintLabel(item) {
        return item.sprint_id ? item.sprint_id[1] : "— Backlog —";
    }

    /** Rolled-up % of done leaf items under a summary node. */
    summaryPct(node) {
        let done = 0, total = 0;
        const walk = (n) => {
            if (n.children.length) {
                n.children.forEach(walk);
            } else {
                const meta = n.stage_id && this.stageById[n.stage_id[0]];
                if (!(meta && meta.is_cancelled)) {
                    total += 1;
                    if (meta && meta.is_done) done += 1;
                }
            }
        };
        node.children.forEach(walk);
        return total ? Math.round((done / total) * 100) : 0;
    }

    // ---- form dialogs ----
    openItem(id) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.item",
                res_id: id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.load() },
        );
    }
    _createCtx(extra = {}) {
        const ctx = { default_project_id: this.props.projectId, ...extra };
        if (this.props.currentReleaseId) ctx.default_release_id = this.props.currentReleaseId;
        return ctx;
    }
    createItem() {
        const itype = this.state.typeFilter !== "all" ? this.state.typeFilter : "story";
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.item",
                views: [[false, "form"]],
                target: "new",
                context: this._createCtx({ default_item_type: itype }),
            },
            { onClose: () => this.load() },
        );
    }
    addChild(item) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.item",
                views: [[false, "form"]],
                target: "new",
                context: this._createCtx({
                    default_parent_id: item.id, default_item_type: "task",
                }),
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
            await this.orm.write("appfoundry.item", [item.id], { name });
            item.name = name;
        }
    }
    onRenameKeydown(ev, item) {
        if (ev.key === "Enter") { ev.preventDefault(); this.saveRename(item); }
        else if (ev.key === "Escape") { this.state.editingId = false; }
    }

    // ---- inline stage ----
    openStage(id) { this.state.stageOpenId = id; this.state.sprintOpenId = false; }
    async setStage(item, value) {
        this.state.stageOpenId = false;
        const id = parseInt(value, 10);
        if (id && (!item.stage_id || item.stage_id[0] !== id)) {
            await this.orm.write("appfoundry.item", [item.id], { stage_id: id });
            const meta = this.stageById[id];
            item.stage_id = [id, meta ? meta.name : ""];
            // A move into/out of a done/cancelled stage changes the open count.
            this._notifyChanged();
        }
    }
    // ---- inline sprint ----
    openSprint(id) { this.state.sprintOpenId = id; this.state.stageOpenId = false; }
    async setSprint(item, value) {
        this.state.sprintOpenId = false;
        const id = value ? parseInt(value, 10) : false;
        const cur = item.sprint_id ? item.sprint_id[0] : false;
        if (id !== cur) {
            await this.orm.write("appfoundry.item", [item.id], { sprint_id: id });
            const sp = (this.props.sprints || []).find((s) => s.id === id);
            item.sprint_id = id ? [id, sp ? sp.name : ""] : false;
        }
    }

    // ---- drag: reorder (before/after) + re-parent (onto) ----
    onDragStart(ev, item) {
        this.state.dragId = item.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(item.id));
    }
    onDragEnd() { this.state.dragId = false; this.state.dragOverId = false; }
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
                await this.orm.write("appfoundry.item", [id], { parent_id: item.id });
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
            const vals = { sequence: (i + 1) * 10 };
            if (n.id === id) vals.parent_id = npId;
            return this.orm.write("appfoundry.item", [n.id], vals);
        }));
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
            return [{ action: "add", label: "Add item", icon: "fa fa-plus" }];
        }
        const items = [
            { action: "add", label: "Add item", icon: "fa fa-plus" },
            { action: "add_sub", label: "Add sub-item", icon: "fa fa-level-down" },
            { action: "properties", label: "Properties", icon: "fa fa-pencil-square-o" },
            { action: "rename", label: "Rename", icon: "fa fa-i-cursor" },
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
            case "add_sub": this.addChild(item); break;
            case "properties": this.openItem(item.id); break;
            case "rename": this.startRename(item); break;
            case "outdent": this.outdentItem(item); break;
            case "delete": this.deleteItem(item); break;
        }
    }
    async outdentItem(item) {
        const parentId = item.parent_id ? item.parent_id[0] : false;
        if (!parentId) return;
        const parentNode = this.state.byId[parentId];
        const newParentId = parentNode && parentNode.parent_id ? parentNode.parent_id[0] : false;
        try {
            await this.orm.write("appfoundry.item", [item.id], { parent_id: newParentId });
        } catch (e) {
            this.notification.add("Kon item niet verplaatsen.", { type: "danger" });
        }
        await this.load();
    }
    deleteItem(item) {
        this.dialog.add(ConfirmationDialog, {
            title: "Delete",
            body: `"${item.name}" en alle sub-items verwijderen?`,
            confirm: async () => {
                try {
                    await this.orm.unlink("appfoundry.item", [item.id]);
                } catch (e) {
                    this.notification.add("Verwijderen mislukt.", { type: "danger" });
                }
                await this.load();
            },
        });
    }
}

/**
 * AppFoundry Work workspace — a modern PM shell: a project (app) selector on
 * the left, then a view-switcher that makes the scrum cycle explicit:
 *   Backlog  →  Sprint Board  →  Sprints  →  Board / List
 * Sprint Board / Board / List embed the native Odoo item views (scoped) so
 * drag-drop, group-by and filters come for free; Backlog is the custom
 * hierarchical table.
 */
export class AppfoundryWorkspace extends Component {
    static template = "myschool_appfoundry.Workspace";
    static components = { View, BacklogTable, AfwContextMenu, SegmentNav };
    static props = ["*"];

    /** Secties voor de SegmentNav-view-switcher (scrum-cyclus). */
    get viewTabs() {
        return [
            { key: "backlog", label: "Backlog" },
            { key: "sprintboard", label: "Sprint Board" },
            { key: "sprints", label: "Sprints" },
            { key: "board", label: "Board" },
            { key: "list", label: "List" },
        ];
    }

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        const savedW = parseInt(window.localStorage.getItem(STORAGE_KEY) || "300", 10);
        this.state = useState({
            projects: [], byId: {}, selectedId: false,
            view: "backlog",
            sprints: [], stages: [], stageById: {},
            projectCode: "", currentReleaseId: false, currentReleaseName: "",
            sprintBoardId: false,
            sidebarWidth: Number.isNaN(savedW) ? 300 : savedW,
            loading: true, search: "",
            ctx: null,
        });
        onWillStart(async () => {
            await this._loadStages();
            await this.loadProjects();
        });
    }

    async _loadStages() {
        const stages = await this.orm.searchRead(
            "appfoundry.item.stage", [],
            ["name", "sequence", "is_done", "is_cancelled"],
            { order: "sequence, id" });
        const byId = {};
        stages.forEach((s) => { byId[s.id] = s; });
        this.state.stages = stages;
        this.state.stageById = byId;
    }

    async loadProjects() {
        const recs = await this.orm.searchRead(
            "appfoundry.project",
            [["is_active", "=", true]],
            ["name", "code", "phase", "item_count", "open_bug_count"],
            { order: "name" },
        );
        const byId = {};
        recs.forEach((r) => { byId[r.id] = r; });
        this.state.projects = recs;
        this.state.byId = byId;
        this.state.loading = false;
        // Preselect: context active_project_id, else current selection, else first.
        const ctxId = this.props.action
            && this.props.action.context
            && this.props.action.context.active_project_id;
        if (ctxId && byId[ctxId]) {
            await this.selectProject(ctxId);
        } else if (this.state.selectedId && byId[this.state.selectedId]) {
            await this.selectProject(this.state.selectedId);
        } else if (recs.length) {
            await this.selectProject(recs[0].id);
        }
    }

    get selected() { return this.state.byId[this.state.selectedId] || null; }

    get filteredProjects() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) return this.state.projects;
        return this.state.projects.filter(
            (p) => (`${p.name} ${p.code || ""}`).toLowerCase().includes(q));
    }

    phaseLabel(p) {
        const labels = {
            idea: "Idea", design: "Design", dev: "Dev",
            test: "Test", stable: "Stable", eol: "E.O.L.",
        };
        return labels[p] || p;
    }

    async selectProject(id) {
        this.state.selectedId = id;
        // Project meta (code + current release) + sprints.
        const [proj] = await this.orm.read(
            "appfoundry.project", [id], ["code", "current_release_id"]);
        this.state.projectCode = proj ? proj.code : "";
        this.state.currentReleaseId = proj && proj.current_release_id
            ? proj.current_release_id[0] : false;
        this.state.currentReleaseName = proj && proj.current_release_id
            ? proj.current_release_id[1] : "";
        await this._loadSprints(id);
    }

    /** Re-read the open-item / open-bug counters of an app after backlog
     *  mutations. The sidebar object is shared by reference with state.byId,
     *  so patching it refreshes the badge. */
    async refreshProjectCounts(projectId) {
        const id = projectId || this.state.selectedId;
        if (!id) return;
        const [rec] = await this.orm.read(
            "appfoundry.project", [id], ["item_count", "open_bug_count"]);
        if (rec && this.state.byId[id]) {
            this.state.byId[id].item_count = rec.item_count;
            this.state.byId[id].open_bug_count = rec.open_bug_count;
        }
    }
    onBacklogChanged() { return this.refreshProjectCounts(this.state.selectedId); }

    async _loadSprints(projectId) {
        const sprints = await this.orm.searchRead(
            "appfoundry.sprint",
            [["project_id", "=", projectId]],
            ["name", "state", "date_start", "date_end", "goal",
             "item_count", "total_points", "completed_points", "velocity"],
            { order: "date_start desc, id desc" });
        this.state.sprints = sprints;
        // Default sprint board = the active sprint, else the most recent.
        const active = sprints.find((s) => s.state === "active");
        this.state.sprintBoardId = active ? active.id
            : (sprints.length ? sprints[0].id : false);
    }

    setView(v) {
        const prev = this.state.view;
        this.state.view = v;
        // Leaving a native board → the counters may have changed via drag.
        if (prev === "board" || prev === "sprintboard") {
            this.refreshProjectCounts(this.state.selectedId);
        }
    }
    setSprintBoard(id) { this.state.sprintBoardId = parseInt(id, 10) || false; }

    /** A kanban card drop in the embedded board ends with a pointerup. Debounce
     *  a counter refresh so a drag results in one read once the write settled. */
    onBoardPointerUp() {
        if (this._boardRefreshTimer) clearTimeout(this._boardRefreshTimer);
        this._boardRefreshTimer = setTimeout(() => {
            this.refreshProjectCounts(this.state.selectedId);
        }, 600);
    }

    get sprintBoard() {
        return this.state.sprints.find((s) => s.id === this.state.sprintBoardId) || null;
    }

    // ---- embedded native views ----
    get sprintBoardProps() {
        return {
            type: "kanban",
            resModel: "appfoundry.item",
            domain: [["sprint_id", "=", this.state.sprintBoardId]],
            context: {
                default_project_id: this.state.selectedId,
                default_sprint_id: this.state.sprintBoardId,
                default_release_id: this.state.currentReleaseId,
            },
            views: [[false, "kanban"]],
            display: { controlPanel: false },
        };
    }
    get boardProps() {
        return {
            type: "kanban",
            resModel: "appfoundry.item",
            domain: [["project_id", "=", this.state.selectedId]],
            context: { default_project_id: this.state.selectedId,
                       default_release_id: this.state.currentReleaseId },
            views: [[false, "kanban"]],
            display: { controlPanel: true },
        };
    }
    get listProps() {
        return {
            type: "list",
            resModel: "appfoundry.item",
            domain: [["project_id", "=", this.state.selectedId]],
            context: { default_project_id: this.state.selectedId,
                       default_release_id: this.state.currentReleaseId },
            views: [[false, "list"]],
            display: { controlPanel: true },
        };
    }

    // ---- sprint actions ----
    newSprint() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.sprint",
                views: [[false, "form"]],
                target: "new",
                context: { default_project_id: this.state.selectedId },
            },
            { onClose: () => this._loadSprints(this.state.selectedId) },
        );
    }
    openSprint(id) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.sprint",
                res_id: id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this._loadSprints(this.state.selectedId) },
        );
    }
    async startSprint(sprint) {
        await this.orm.call("appfoundry.sprint", "action_start", [[sprint.id]]);
        await this._loadSprints(this.state.selectedId);
        this.state.sprintBoardId = sprint.id;
        this.state.view = "sprintboard";
    }
    async completeSprint(sprint) {
        await this.orm.call("appfoundry.sprint", "action_complete", [[sprint.id]]);
        await this._loadSprints(this.state.selectedId);
    }

    // ---- project sidebar context menu ----
    onProjectContextMenu(ev, id) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, id };
    }
    onEmptyContextMenu(ev) {
        ev.preventDefault();
        this.state.ctx = { x: ev.clientX, y: ev.clientY, id: false };
    }
    closeCtx() { this.state.ctx = null; }
    get ctxItems() {
        if (!this.state.ctx || !this.state.ctx.id) {
            return [{ action: "add_project", label: "New project", icon: "fa fa-folder-o" }];
        }
        return [
            { action: "add_project", label: "New project", icon: "fa fa-folder-o" },
            { action: "properties", label: "Properties", icon: "fa fa-pencil-square-o" },
        ];
    }
    onCtxAction(action) {
        const id = this.state.ctx && this.state.ctx.id;
        switch (action) {
            case "add_project": this._newProject(); break;
            case "properties": if (id) this._openProjectForm(id); break;
        }
    }
    _newProject() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.project",
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.loadProjects() },
        );
    }
    _openProjectForm(id) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "appfoundry.project",
                res_id: id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.loadProjects() },
        );
    }
    openProjectForm() {
        if (!this.state.selectedId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "appfoundry.project",
            res_id: this.state.selectedId,
            views: [[false, "form"]],
            target: "current",
        });
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
}

registry.category("actions").add("appfoundry_workspace", AppfoundryWorkspace);
