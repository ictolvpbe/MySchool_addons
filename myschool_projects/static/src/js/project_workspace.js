/** @odoo-module **/
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SegmentNav } from "@myschool_web/components/segment_nav/segment_nav";
import {
    DAY_MS, itemStart, itemEnd, dayIndex as utilDayIndex, computeRange, spanFor,
    barGeom, applyDragGeom, applyDragDates, computeArrows,
} from "@myschool_projects/js/gantt_utils";

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
        dragId: { type: [Number, Boolean], optional: true },
        dropTargetId: { type: [Number, String, Boolean], optional: true },
        onSelect: { type: Function, optional: true },
        onToggle: { type: Function, optional: true },
        onContextMenu: { type: Function, optional: true },
        onDragStart: { type: Function, optional: true },
        onDragOver: { type: Function, optional: true },
        onDragLeave: { type: Function, optional: true },
        onDrop: { type: Function, optional: true },
        onDragEnd: { type: Function, optional: true },
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
    get isDropTarget() { return this.props.dropTargetId === this.props.node.id; }
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

    // ---- drag&drop: verplaats het project naar een ander niveau ----
    onDragStart(ev) {
        ev.stopPropagation();
        if (this.props.onDragStart) this.props.onDragStart(ev, this.props.node.id);
    }
    onDragOver(ev) {
        if (this.props.onDragOver) this.props.onDragOver(ev, this.props.node.id);
    }
    onDragLeave(ev) {
        if (this.props.onDragLeave) this.props.onDragLeave(ev, this.props.node.id);
    }
    onDrop(ev) {
        ev.stopPropagation();
        if (this.props.onDrop) this.props.onDrop(ev, this.props.node.id);
    }
    onDragEnd(ev) {
        if (this.props.onDragEnd) this.props.onDragEnd(ev);
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
            cols, colMenuOpen: false, search: "",
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
        const q = (this.state.search || "").trim().toLowerCase();
        if (q) {
            // Tijdens zoeken: vlakke lijst van alle matchende items (geen tree).
            return Object.values(this.state.byId)
                .filter((n) => (n.name || "").toLowerCase().includes(q))
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

    /** Voeg een proces in als work items, optioneel onder ``parentId``. */
    insertProcess(parentId) {
        const context = { default_project_id: this.props.projectId };
        if (parentId) context.default_parent_id = parentId;
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.process.apply",
                views: [[false, "form"]],
                target: "new",
                context,
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
            return [
                { action: "add", label: "Add", icon: "fa fa-plus" },
                { action: "insert_process", label: "Voeg proces in", icon: "fa fa-sitemap" },
            ];
        }
        const items = [
            { action: "add", label: "Add", icon: "fa fa-plus" },
            { action: "add_sub", label: "Add sub-item", icon: "fa fa-level-down" },
            { action: "insert_process", label: "Voeg proces in", icon: "fa fa-sitemap" },
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
        if (action === "insert_process") {
            this.insertProcess(item ? item.id : false);
            return;
        }
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

const GANTT_LABEL_W = 260;
const GANTT_ROW_H = 30;

/**
 * Custom Gantt/Timeline voor de workspace (web_gantt = Enterprise/afwezig).
 * Read-gericht v1: balken per date_start..date_deadline, summary-spans,
 * milestone-ruiten, maand+dag-header, vandaag-lijn en zoom. Klik = form.
 */
export class GanttTimeline extends Component {
    static template = "myschool_projects.GanttTimeline";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.typeLabels = TYPE_LABELS;
        this.labelW = GANTT_LABEL_W;
        this.rowH = GANTT_ROW_H;
        this.state = useState({
            byId: {}, roots: [], expanded: {}, loading: true,
            dayWidth: 28, rangeStart: null, totalDays: 0,
            drag: null, showDeps: true,
        });
        this._dragged = false;
        onWillStart(async () => { await this.load(); });
    }

    async load() {
        this.state.loading = true;
        const recs = await this.orm.searchRead(
            "myschool.project.task",
            [["project_id", "=", this.props.projectId]],
            ["name", "item_type", "state", "date_start", "date_deadline",
             "parent_id", "child_count", "milestone_id", "depends_on_ids"],
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
        this._computeRange(recs);
        this.state.loading = false;
    }

    _itemStart(n) { return itemStart(n); }
    _itemEnd(n) { return itemEnd(n); }

    _computeRange(recs) {
        const { rangeStart, totalDays } = computeRange(recs, new Date());
        this.state.rangeStart = rangeStart;
        this.state.totalDays = totalDays;
    }

    dayIndex(date) { return utilDayIndex(this.state.rangeStart, date); }

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

    get timelineWidth() { return this.state.totalDays * this.state.dayWidth; }

    get months() {
        const out = [];
        const dw = this.state.dayWidth;
        let i = 0;
        while (i < this.state.totalDays) {
            const d = new Date(this.state.rangeStart.getTime() + i * DAY_MS);
            const y = d.getFullYear(), m = d.getMonth();
            let span = 0;
            while (i + span < this.state.totalDays) {
                const dd = new Date(this.state.rangeStart.getTime() + (i + span) * DAY_MS);
                if (dd.getFullYear() !== y || dd.getMonth() !== m) break;
                span += 1;
            }
            out.push({
                key: `${y}-${m}`,
                label: d.toLocaleDateString("nl-BE", { month: "short", year: "numeric" }),
                left: i * dw, width: span * dw,
            });
            i += span;
        }
        return out;
    }

    get days() {
        const out = [];
        const dw = this.state.dayWidth;
        for (let i = 0; i < this.state.totalDays; i++) {
            const d = new Date(this.state.rangeStart.getTime() + i * DAY_MS);
            const wd = d.getDay();
            out.push({ key: i, left: i * dw, width: dw, num: d.getDate(),
                       weekend: wd === 0 || wd === 6 });
        }
        return out;
    }

    get todayLeft() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const idx = this.dayIndex(today);
        if (idx < 0 || idx >= this.state.totalDays) return null;
        return idx * this.state.dayWidth;
    }

    _spanFor(node) { return spanFor(node); }

    _baseBar(row) {
        return barGeom(this.state.rangeStart, this.state.dayWidth, row);
    }

    /** Display-geometrie incl. live drag-preview voor het gesleepte item. */
    barFor(row) {
        const base = this._baseBar(row);
        const d = this.state.drag;
        const drag = d && d.id === row.item.id ? d : null;
        return applyDragGeom(base, drag, this.state.dayWidth);
    }

    milestoneLeft(item) {
        const e = this._itemEnd(item);
        if (!e) return null;
        let idx = this.dayIndex(e);
        const d = this.state.drag;
        if (d && d.id === item.id && d.mode === "move") idx += d.dayDelta;
        return idx * this.state.dayWidth;
    }

    zoom(delta) {
        this.state.dayWidth = Math.max(10, Math.min(60, this.state.dayWidth + delta));
    }

    toggleDeps() { this.state.showDeps = !this.state.showDeps; }

    /** Finish-to-start dependency-pijlen tussen zichtbare balken. */
    get arrows() {
        if (!this.state.showDeps) return [];
        const geomOf = (row) => {
            if (row.item.item_type === "milestone") {
                const x = this.milestoneLeft(row.item);
                return x === null ? null : { left: x, width: 0 };
            }
            return this.barFor(row);
        };
        return computeArrows(this.visibleRows, geomOf, this.labelW, this.rowH);
    }

    // ---- drag-to-reschedule ----
    onBarMouseDown(ev, row, mode) {
        if (row.hasChildren) return;          // summary-span is afgeleid → niet sleepbaar
        const start = this._itemStart(row.item);
        const end = this._itemEnd(row.item);
        if (!start || !end) return;
        ev.preventDefault();
        this.state.drag = {
            id: row.item.id, mode, startX: ev.clientX,
            origStart: start, origEnd: end, dayDelta: 0,
            isMilestone: row.item.item_type === "milestone",
        };
        const onMove = (e) => {
            if (!this.state.drag) return;
            this.state.drag.dayDelta = Math.round(
                (e.clientX - this.state.drag.startX) / this.state.dayWidth);
        };
        const onUp = async () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            const d = this.state.drag;
            this.state.drag = null;
            if (!d || !d.dayDelta) return;
            this._dragged = true;             // onderdruk de klik-na-sleep
            await this._applyDrag(d);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
    }

    onBarClick(row) {
        if (this._dragged) { this._dragged = false; return; }
        this.openItem(row.item.id);
    }

    async _applyDrag(d) {
        const vals = applyDragDates(d);
        try {
            await this.orm.write("myschool.project.task", [d.id], vals);
        } catch (e) {
            this.notification.add("Kon datums niet bijwerken.", { type: "danger" });
        }
        await this.load();
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
}

/**
 * Project Workspace — a modern PM shell: WBS sidebar + view-switcher
 * (Overview / Board / List / Calendar). Board/List/Calendar embed the
 * native Odoo task views (scoped to the selected project) so drag-drop,
 * group-by and filters come for free.
 */
export class ProjectWorkspace extends Component {
    static template = "myschool_projects.Workspace";
    static components = { View, WbsNode, WorkPackageTable, GanttTimeline, WsContextMenu, SegmentNav };
    static props = ["*"];

    /** Secties voor de SegmentNav-view-switcher. */
    get viewTabs() {
        return [
            { key: "table", label: "Table" },
            { key: "timeline", label: "Timeline" },
            { key: "overview", label: "Overview" },
            { key: "kanban", label: "Board" },
            { key: "calendar", label: "Calendar" },
        ];
    }

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
            search: "",
            ctx: null,
            dragId: false,
            dropTargetId: false,
            taskReload: 0,
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
        const node = this.state.byId[this.state.ctx.id];
        const items = [
            { action: "add_project", label: "Add Project", icon: "fa fa-folder-o" },
            { action: "add_sub", label: "Add sub-project", icon: "fa fa-sitemap" },
            { action: "rename", label: "Rename", icon: "fa fa-i-cursor" },
            { action: "properties", label: "Properties", icon: "fa fa-pencil-square-o" },
            { action: "move", label: "Verplaats onder…", icon: "fa fa-arrows" },
        ];
        if (node && node.parent_id) {
            items.push({ action: "to_root", label: "Naar niveau 0", icon: "fa fa-outdent" });
        }
        items.push({ divider: true });
        items.push({ action: "delete", label: "Delete", icon: "fa fa-trash", danger: true });
        return items;
    }
    onCtxAction(action) {
        const id = this.state.ctx && this.state.ctx.id;
        switch (action) {
            case "add_project": this._newProject(false); break;
            case "add_sub": this._newProject(id); break;
            case "rename": this._renameProject(id); break;
            case "properties": this._openProjectForm(id); break;
            case "move": this._moveProject(id); break;
            case "to_root": this._reparentProject(id, false); break;
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

    // ------------------------------------------------------------------
    // Verplaats een project naar een ander niveau (drag&drop + context-menu)
    // ------------------------------------------------------------------
    _descendantIds(id) {
        const root = this.state.byId[id];
        const out = [];
        if (!root) return out;
        const walk = (n) => { n.children.forEach((c) => { out.push(c.id); walk(c); }); };
        walk(root);
        return out;
    }
    _isDescendant(rootId, nodeId) {
        return this._descendantIds(rootId).includes(nodeId);
    }
    /** Mag het gesleepte project onder `targetId` (false = niveau 0)? */
    _canDropProject(targetId) {
        const id = this.state.dragId;
        if (!id || id === targetId) return false;
        if (targetId && this._isDescendant(id, targetId)) return false;  // geen cyclus
        const node = this.state.byId[id];
        const curParent = node && node.parent_id ? node.parent_id[0] : false;
        if (curParent === targetId) return false;                        // geen no-op
        return true;
    }
    async _reparentProject(id, parentId) {
        try {
            await this.orm.write("myschool.project", [id], { parent_id: parentId });
        } catch (e) {
            this.notification.add(
                "Verplaatsen mislukt (zou een cyclus maken?).", { type: "danger" });
            return;
        }
        if (parentId) this.state.expanded[parentId] = true;
        await this.loadProjects();
    }
    _moveProject(id) {
        const exclude = [id, ...this._descendantIds(id)];
        this.dialog.add(SelectCreateDialog, {
            resModel: "myschool.project",
            title: "Verplaats onder…",
            noCreate: true,
            multiSelect: false,
            domain: [["id", "not in", exclude]],
            onSelected: async (resIds) => {
                if (resIds && resIds.length) await this._reparentProject(id, resIds[0]);
            },
        });
    }

    // ---- drag&drop op de WBS-boom ----
    onNodeDragStart(ev, id) {
        this.state.dragId = id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(id));
    }
    onNodeDragEnd() {
        this.state.dragId = false;
        this.state.dropTargetId = false;
    }
    onNodeDragOver(ev, id) {
        if (this._canDropProject(id)) {
            ev.preventDefault();
            this.state.dropTargetId = id;
        }
    }
    onNodeDragLeave(ev, id) {
        if (this.state.dropTargetId === id) this.state.dropTargetId = false;
    }
    async onNodeDrop(ev, id) {
        ev.preventDefault();
        const dragId = this.state.dragId;
        const ok = this._canDropProject(id);
        this.state.dropTargetId = false;
        this.state.dragId = false;
        if (!dragId || !ok) return;
        await this._reparentProject(dragId, id);
    }
    // root-dropzone = naar niveau 0 (hoofdproject)
    onRootDragOver(ev) {
        const id = this.state.dragId;
        if (!id) return;
        const node = this.state.byId[id];
        if (node && !node.parent_id) return;     // al top-level → geen drop nodig
        ev.preventDefault();
        this.state.dropTargetId = "root";
    }
    onRootDragLeave() {
        if (this.state.dropTargetId === "root") this.state.dropTargetId = false;
    }
    async onRootDrop(ev) {
        ev.preventDefault();
        const dragId = this.state.dragId;
        this.state.dropTargetId = false;
        this.state.dragId = false;
        if (!dragId) return;
        await this._reparentProject(dragId, false);
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

    /** Sidebar-tree, of een vlakke gefilterde lijst tijdens het zoeken
     *  (match op naam of code). */
    get filteredRoots() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) return this.state.roots;
        return Object.values(this.state.byId)
            .filter((n) => (`${n.name} ${n.code || ""}`).toLowerCase().includes(q))
            .map((n) => ({ ...n, children: [] }));
    }

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

    /** Maak een taak aan vanuit de embedded Board/Calendar "Nieuw"-knop.
     *  Na sluiten van het form remount de view (taskReload) zodat de nieuwe
     *  taak meteen zichtbaar is. */
    createTask() {
        const id = this.state.selectedId;
        if (!id) return;
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.task",
                views: [[false, "form"]],
                target: "new",
                context: { default_project_id: id },
            },
            { onClose: () => { this.state.taskReload += 1; } },
        );
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
            // Verberg de "Workspace"-breadcrumb in de embedded control panel
            // (knoppen + zoekbalk blijven).
            noBreadcrumbs: true,
            // Eigen create-handler: de standaard "Nieuw"-knop van de embedded
            // Board/Calendar opent zo het task-form (werkt ook bij een leeg
            // project, waar de Table-view nog geen rij-plusje toont).
            createRecord: () => this.createTask(),
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

    /** Voeg een proces (uit de Process Composer) in het geselecteerde project
     *  in als work items. Na sluiten herladen we de view + sidebar-tellers. */
    applyProcess() {
        const id = this.state.selectedId;
        if (!id) return;
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "myschool.project.process.apply",
                views: [[false, "form"]],
                target: "new",
                context: { default_project_id: id },
            },
            {
                onClose: () => {
                    this.state.taskReload += 1;
                    this.loadProjects();
                    if (this.state.view === "overview") this.loadOverview();
                },
            },
        );
    }
}

registry.category("actions").add("myschool_projects_workspace", ProjectWorkspace);
