/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useRef, onMounted, onWillUnmount, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Single source of truth for the actions available on a node.
 *
 * Returns an ordered list of action descriptors:
 *   { key, label, iconClass, danger?, inQuick?, inMenu?, divider?,
 *     quickLabel?, quickIconClass?, when? }
 *
 * - ContextMenu filters by `inMenu` and inserts dividers where flagged.
 * - DetailsPanel quick-action bar filters by `inQuick`. When a quick
 *   variant of the label/icon is appropriate (e.g. "Edit" vs "Properties"),
 *   `quickLabel` / `quickIconClass` override the base label/iconClass.
 * - `when(node)` is an optional predicate; the action is dropped if false.
 *
 * Action keys mirror the cases handled in onContextMenuAction so existing
 * dispatch logic stays unchanged.
 */
export function actionsForNode(node) {
    if (!node) return [];
    // Tree-rendered persongroups have type='org' + org_type_name='PERSONGROUP'.
    // Member-pane clicks send type='persongroup' from the DOM dataset.
    // Accept either shape so both entry points get the same action set.
    const isPersongroup = (node.type === 'org' && node.org_type_name === 'PERSONGROUP')
        || node.type === 'persongroup';

    if (isPersongroup) {
        return [
            { key: 'open', label: 'Properties', iconClass: 'fa fa-cog', inMenu: true },
            { divider: true, inMenu: true },
            { key: 'manage_members', label: 'Members', iconClass: 'fa fa-users', inMenu: true, inQuick: true },
            { divider: true, inMenu: true },
            { key: 'move_org', label: 'Move', iconClass: 'fa fa-arrows', inMenu: true, inQuick: true,
              quickLabel: 'Move' },
            { divider: true, inMenu: true },
            { key: 'delete', label: 'Delete', iconClass: 'fa fa-trash', danger: true, inMenu: true, inQuick: true },
        ];
    }

    if (node.type === 'org') {
        return [
            { key: 'open', label: 'Properties', iconClass: 'fa fa-cog', inMenu: true },
            { divider: true, inMenu: true },
            { key: 'create_person', label: 'Create Person', iconClass: 'fa fa-user-plus', inMenu: true, inQuick: true },
            { key: 'add_child_org', label: 'Add Sub-Org', iconClass: 'fa fa-plus-circle', inMenu: true, inQuick: true },
            { key: 'create_persongroup', label: 'Create Persongroup', iconClass: 'fa fa-users', inMenu: true },
            { divider: true, inMenu: true },
            { key: 'manage_org_roles', label: 'Roles', iconClass: 'fa fa-id-badge', inMenu: true, inQuick: true },
            { divider: true, inMenu: true },
            { key: 'move_org', label: 'Move', iconClass: 'fa fa-arrows', inMenu: true, inQuick: true },
            { divider: true, inMenu: true },
            { key: 'delete', label: 'Delete', iconClass: 'fa fa-trash', danger: true, inMenu: true, inQuick: true },
        ];
    }

    if (node.type === 'person') {
        return [
            // "open" surfaces as "Properties" in the context menu and
            // "Edit" in the quick-action bar (same action key).
            { key: 'open', label: 'Properties', iconClass: 'fa fa-cog',
              inMenu: true, inQuick: true,
              quickLabel: 'Edit', quickIconClass: 'fa fa-pencil' },
            { divider: true, inMenu: true },
            { key: 'manage_person_roles', label: 'Manage Roles', iconClass: 'fa fa-id-badge', inMenu: true, inQuick: true },
            { key: 'move_person', label: 'Move', iconClass: 'fa fa-arrows', inMenu: true, inQuick: true },
            { divider: true, inMenu: true },
            { key: 'deactivate_person', label: 'Deactivate', iconClass: 'fa fa-ban', danger: true,
              inMenu: true, inQuick: true },
            { key: 'delete_person', label: 'Delete', iconClass: 'fa fa-trash', danger: true, inMenu: true },
            // Unlink only makes sense when the person sits in ≥2 orgs.
            { divider: true, inMenu: true,
              when: (n) => (n.other_active_org_count || 0) > 0 },
            { key: 'remove_from_org', label: 'Unlink from this Org',
              iconClass: 'fa fa-user-times', danger: true, inMenu: true,
              when: (n) => (n.other_active_org_count || 0) > 0 },
        ];
    }

    if (node.type === 'role') {
        return [
            { key: 'open', label: 'Properties', iconClass: 'fa fa-cog', inMenu: true },
        ];
    }

    return [];
}

/**
 * TreeNode component - renders a single node with expand/collapse, drag-drop, selection
 */
export class TreeNode extends Component {
    static template = "myschool_admin.TreeNode";
    static components = { TreeNode };
    
    static props = {
        node: Object,
        level: { type: Number, optional: true },
        activeNodeId: { type: Number, optional: true },
        activeNodeType: { type: String, optional: true },
        onSelectNode: { type: Function, optional: true },
        onContextMenu: { type: Function, optional: true },
        onToggleSelect: { type: Function, optional: true },
        onDragStart: { type: Function, optional: true },
        onDragOver: { type: Function, optional: true },
        onDrop: { type: Function, optional: true },
        selectedIds: { type: Object, optional: true },
        selectionMode: { type: Boolean, optional: true },
        draggedNode: { type: [Object, Boolean], optional: true },
        expandedIds: { type: Object, optional: true },
        onToggleExpand: { type: Function, optional: true },
        onOpenSlideOver: { type: Function, optional: true },
    };
    
    setup() {
        this.state = useState({
            dragOver: false,
        });
    }
    
    get nodeKey() {
        return `${this.props.node.type}_${this.props.node.id}`;
    }
    
    get isExpanded() {
        // Check expandedIds from parent - this is reactive
        if (this.props.expandedIds && this.nodeKey in this.props.expandedIds) {
            return this.props.expandedIds[this.nodeKey];
        }
        // Default: level 0 is expanded
        return (this.props.level || 0) === 0;
    }
    
    get hasChildren() {
        // Tree shows org hierarchy only — persons live in the members pane.
        const node = this.props.node;
        return !!(node.children && node.children.length > 0);
    }
    
    get level() {
        return this.props.level || 0;
    }
    
    get childLevel() {
        return this.level + 1;
    }
    
    get isSelected() {
        const key = `${this.props.node.type}_${this.props.node.id}`;
        return this.props.selectedIds && this.props.selectedIds[key];
    }
    
    get isActiveNode() {
        return this.props.activeNodeId === this.props.node.id &&
               this.props.activeNodeType === this.props.node.type;
    }
    
    get isDragging() {
        return this.props.draggedNode && 
               this.props.draggedNode.id === this.props.node.id &&
               this.props.draggedNode.type === this.props.node.type;
    }
    
    get canAcceptDrop() {
        if (!this.props.draggedNode) return false;
        if (this.props.node.type === 'org') {
            return this.props.draggedNode.type === 'org' || this.props.draggedNode.type === 'person';
        }
        return false;
    }
    
    get displayTitle() {
        const node = this.props.node;
        if (node.full_name && node.full_name !== node.name) {
            return node.full_name;
        }
        return node.name;
    }
    
    toggle(ev) {
        ev.stopPropagation();
        // Toggle by notifying parent - the parent's expandedIds controls the state
        if (this.props.onToggleExpand) {
            this.props.onToggleExpand(this.nodeKey, !this.isExpanded);
        }
    }
    
    onRowClick(ev) {
        ev.stopPropagation();
        if (this.props.onSelectNode) {
            this.props.onSelectNode(this.props.node);
        }
    }

    // Klik op het icoon vóór de naam → open slide-over voor org/persongroup
    // (single-click op de rest van de rij doet drilling-in via onSelectNode).
    onIconClick(ev) {
        if (ev && ev.stopPropagation) ev.stopPropagation();
        if (this.props.onOpenSlideOver) {
            this.props.onOpenSlideOver(this.props.node);
        }
    }
    
    onContextMenu(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.props.onContextMenu) {
            this.props.onContextMenu(ev, this.props.node);
        }
    }
    
    onCheckboxChange(ev) {
        ev.stopPropagation();
        if (this.props.onToggleSelect) {
            this.props.onToggleSelect(this.props.node, ev.target.checked);
        }
    }
    
    // Drag and Drop handlers
    onDragStart(ev) {
        ev.stopPropagation();
        if (this.props.onDragStart) {
            this.props.onDragStart(this.props.node);
        }
        ev.dataTransfer.effectAllowed = 'move';
        ev.dataTransfer.setData('text/plain', JSON.stringify({
            type: this.props.node.type,
            id: this.props.node.id,
            name: this.props.node.name
        }));
    }
    
    onDragOver(ev) {
        if (this.canAcceptDrop) {
            ev.preventDefault();
            ev.stopPropagation();
            this.state.dragOver = true;
            if (this.props.onDragOver) {
                this.props.onDragOver(ev, this.props.node);
            }
        }
    }
    
    onDragLeave(ev) {
        this.state.dragOver = false;
    }
    
    onDrop(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.dragOver = false;
        if (this.props.onDrop && this.canAcceptDrop) {
            this.props.onDrop(this.props.node);
        }
    }
    
    onDragEnd(ev) {
        this.state.dragOver = false;
    }
}

/**
 * DetailsPanel component - shows details of selected node
 */
export class DetailsPanel extends Component {
    static template = "myschool_admin.DetailsPanel";
    static props = {
        node: { type: [Object, { value: null }], optional: true },
        members: { type: Object, optional: true },
        onAction: { type: Function, optional: true },
        onOpenRecord: { type: Function, optional: true },
        onEditCi: { type: Function, optional: true },
        onRemoveCi: { type: Function, optional: true },
        onNavigateToOrg: { type: Function, optional: true },
    };

    // CSS-style for the person-type badge — mirrors avatarStyle()
    // tinting so the badge matches the person's icon color.
    get personTypeBadgeStyle() {
        const hex = this.props.node?.person_type_color || '';
        if (!hex) return '';
        const v = hex.startsWith('#') ? hex.slice(1) : hex;
        const isShort = v.length === 3;
        const r = parseInt(isShort ? v[0] + v[0] : v.slice(0, 2), 16);
        const g = parseInt(isShort ? v[1] + v[1] : v.slice(2, 4), 16);
        const b = parseInt(isShort ? v[2] + v[2] : v.slice(4, 6), 16);
        if ([r, g, b].some(x => Number.isNaN(x))) return '';
        return `background: rgba(${r},${g},${b},0.16); color: ${hex};`;
    }

    onParentOrgClick() {
        const orgId = this.props.node?.parent_org_id || this.props.node?.org_id;
        if (orgId && this.props.onNavigateToOrg) {
            this.props.onNavigateToOrg(orgId);
        }
    }

    get isPersongroup() {
        // Tree-rendered persongroups arrive as type='org' + org_type_name='PERSONGROUP';
        // member-pane clicks arrive as type='persongroup'. Accept both shapes.
        const n = this.props.node;
        return (n?.type === 'org' && n?.org_type_name === 'PERSONGROUP')
            || n?.type === 'persongroup';
    }

    // True for any org-like node (regular org, sub-org, persongroup). Used in
    // the template to gate the org info-cards branch so it also fires for
    // member-pane clicks where node.type === 'persongroup'.
    get isOrgLike() {
        const t = this.props.node?.type;
        return t === 'org' || t === 'persongroup';
    }

    // Tint for the header icon-bubble. Mirrors avatarStyle() in
    // MembersPanel but kept local to avoid coupling components.
    get headerIconStyle() {
        const n = this.props.node;
        if (!n) return '';
        const hex = n.org_type_color || n.person_type_color || '';
        if (!hex) return '';
        const v = hex.startsWith('#') ? hex.slice(1) : hex;
        const isShort = v.length === 3;
        const r = parseInt(isShort ? v[0] + v[0] : v.slice(0, 2), 16);
        const g = parseInt(isShort ? v[1] + v[1] : v.slice(2, 4), 16);
        const b = parseInt(isShort ? v[2] + v[2] : v.slice(4, 6), 16);
        if ([r, g, b].some(x => Number.isNaN(x))) return '';
        return `background: rgba(${r},${g},${b},0.16); color: ${hex};`;
    }

    get pgpMembers() {
        return this.props.members?.persons || [];
    }

    // Quick-action buttons rendered above the info-grid. Derived from
    // the canonical action list so context-menu and quick-actions stay
    // in lockstep (see actionsForNode in this module).
    get quickActions() {
        const node = this.props.node;
        if (!node) return [];
        return actionsForNode(node)
            .filter(a => a.inQuick)
            .filter(a => !a.when || a.when(node))
            .map(a => ({
                key: a.key,
                label: a.quickLabel || a.label,
                iconClass: a.quickIconClass || a.iconClass,
                danger: a.danger,
            }));
    }

    onQuickAction(key) {
        if (this.props.onAction) this.props.onAction(key);
    }

    openRecord() {
        if (this.props.onOpenRecord) {
            this.props.onOpenRecord();
        }
    }
    
    onEditCiClick(ev) {
        const ciId = parseInt(ev.currentTarget.dataset.ciId);
        if (this.props.onEditCi && ciId) {
            this.props.onEditCi(ciId);
        }
    }
    
    onRemoveCiClick(ev) {
        const ciId = parseInt(ev.currentTarget.dataset.ciId);
        if (this.props.onRemoveCi && ciId) {
            this.props.onRemoveCi(ciId);
        }
    }
    
    // Used by the inline "Manage" button next to the persongroup
    // members section heading — keeps that single shortcut explicit
    // even though all generic actions flow through onQuickAction.
    onManageMembersClick() {
        if (this.props.onAction) this.props.onAction('manage_members');
    }

    // Used by the inline "View"/"Configuration" link in the CI count card.
    onConfigurationClick() {
        if (this.props.onAction) this.props.onAction('configuration');
    }
}

/**
 * SlideOverDetails component — overlay panel that slides in from the right
 * with the same content as DetailsPanel, organised in tabs (Info /
 * Configuration). Triggered by double-click on a member row or the
 * "Details" button in the members header.
 */
export class SlideOverDetails extends Component {
    static template = "myschool_admin.SlideOverDetails";
    static props = {
        node: { type: [Object, { value: null }], optional: true },
        ciRelations: { type: Array, optional: true },
        ciLoading: { type: Boolean, optional: true },
        onClose: { type: Function, optional: true },
        onAction: { type: Function, optional: true },
        onOpenRecord: { type: Function, optional: true },
        onEditCi: { type: Function, optional: true },
        onRemoveCi: { type: Function, optional: true },
        onAddCi: { type: Function, optional: true },
    };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({
            tab: 'info',
            ciLoading: false,
        });

        onMounted(() => {
            // Focus the panel root so Escape works.
            this.rootRef.el?.focus();
        });
    }

    // Reset to Info tab whenever a different node is loaded. Without this,
    // re-opening with a new person while previously on 'config' would
    // leave a possibly-empty/irrelevant tab visible.
    setTab(tab) {
        this.state.tab = tab;
    }

    get isPersongroup() {
        const n = this.props.node;
        return (n?.type === 'org' && n?.org_type_name === 'PERSONGROUP')
            || n?.type === 'persongroup';
    }

    get isOrgLike() {
        const t = this.props.node?.type;
        return t === 'org' || t === 'persongroup';
    }

    // Configuration tab only makes sense for orgs (CI relations live on orgs).
    get hasConfigTab() {
        return this.isOrgLike;
    }

    get ciRelations() {
        return this.props.ciRelations || [];
    }

    get ciCount() {
        return this.ciRelations.length;
    }

    get headerIconStyle() {
        const n = this.props.node;
        if (!n) return '';
        const hex = n.org_type_color || n.person_type_color || '';
        if (!hex) return '';
        const v = hex.startsWith('#') ? hex.slice(1) : hex;
        const isShort = v.length === 3;
        const r = parseInt(isShort ? v[0] + v[0] : v.slice(0, 2), 16);
        const g = parseInt(isShort ? v[1] + v[1] : v.slice(2, 4), 16);
        const b = parseInt(isShort ? v[2] + v[2] : v.slice(4, 6), 16);
        if ([r, g, b].some(x => Number.isNaN(x))) return '';
        return `background: rgba(${r},${g},${b},0.16); color: ${hex};`;
    }

    get quickActions() {
        const node = this.props.node;
        if (!node) return [];
        return actionsForNode(node)
            .filter(a => a.inQuick)
            .filter(a => !a.when || a.when(node))
            .map(a => ({
                key: a.key,
                label: a.quickLabel || a.label,
                iconClass: a.quickIconClass || a.iconClass,
                danger: a.danger,
            }));
    }

    onQuickAction(key) {
        if (this.props.onAction) this.props.onAction(key, this.props.node);
    }

    openRecord() {
        if (this.props.onOpenRecord) this.props.onOpenRecord(this.props.node);
    }

    onCloseClick() {
        if (this.props.onClose) this.props.onClose();
    }

    onKeyDown(ev) {
        if (ev.key === 'Escape') {
            ev.preventDefault();
            this.onCloseClick();
        }
    }

    onEditCi(ciId) {
        if (this.props.onEditCi) this.props.onEditCi(ciId);
    }

    onRemoveCi(ciId) {
        if (this.props.onRemoveCi) this.props.onRemoveCi(ciId);
    }

    onAddCi() {
        if (this.props.onAddCi) this.props.onAddCi();
    }
}

/**
 * MembersPanel component - shows persons and persongroups related to selected org
 */
export class MembersPanel extends Component {
    static template = "myschool_admin.MembersPanel";
    static props = {
        node: { type: [Object, { value: null }], optional: true },
        members: { type: Object, optional: true },
        loading: { type: Boolean, optional: true },
        onOpenRecord: { type: Function, optional: true },
        onMemberContextMenu: { type: Function, optional: true },
        onPanelContextMenu: { type: Function, optional: true },
        onMemberSelect: { type: Function, optional: true },
        onMemberAction: { type: Function, optional: true },
        onMemberKebab: { type: Function, optional: true },
        onMemberOpenDetails: { type: Function, optional: true },
        onMemberShowDetails: { type: Function, optional: true },
        onOpenOrgDetails: { type: Function, optional: true },
        onMemberDragStart: { type: Function, optional: true },
        onMemberDragEnd: { type: Function, optional: true },
        onPasswordClick: { type: Function, optional: true },
        onFocus: { type: Function, optional: true },
        selectedMemberId: { type: Number, optional: true },
        selectedMemberType: { type: String, optional: true },
        selectedMemberIds: { type: Object, optional: true },
        focused: { type: Boolean, optional: true },
    };

    // Static catalogue of all optional columns. The header row + each
    // member row iterate this to decide which columns to render.
    static get COLUMN_OPTIONS() {
        return [
            { key: 'roles',   label: 'Rol' },
            { key: 'type',    label: 'Type' },
            { key: 'email',   label: 'E-mail' },
            { key: 'sap_ref', label: 'SAP-ref' },
            { key: 'active',  label: 'Status' },
        ];
    }

    static get DEFAULT_VISIBLE_COLUMNS() {
        return { roles: true, type: false, email: false, sap_ref: false, active: false };
    }

    static get DEFAULT_COLUMN_ORDER() {
        return ['roles', 'type', 'email', 'sap_ref', 'active'];
    }

    static get DEFAULT_COLUMN_WIDTHS() {
        return { roles: 110, type: 110, email: 220, sap_ref: 120, active: 90 };
    }

    static get MIN_COLUMN_WIDTH() { return 60; }

    static get _LS_KEY() { return 'myschool_admin.members.columnConfig'; }

    setup() {
        const cfg = this._loadConfig();
        this.state = useState({
            filterText: '',
            showColumnConfig: false,
            visibleColumns: cfg.visibleColumns,
            columnOrder: cfg.columnOrder,
            columnWidths: cfg.columnWidths,
            dragOverColumn: null,
        });
        // Track in-progress drag/resize (not in reactive state to avoid
        // unnecessary re-renders during continuous mousemove).
        this._resize = null;
        this._dragKey = null;
        this._onColumnResizeMove = this._onColumnResizeMove.bind(this);
        this._onColumnResizeEnd = this._onColumnResizeEnd.bind(this);

        // Reset the in-pane filter whenever the active org changes, so a
        // filter typed for org A doesn't silently hide all members of
        // org B (which would otherwise look like "count right, list empty").
        onWillUpdateProps((nextProps) => {
            const oldId = this.props.node?.id;
            const newId = nextProps.node?.id;
            if (oldId !== newId && this.state.filterText) {
                this.state.filterText = '';
            }
        });
    }

    // --- Persisted config: visibility + order + widths ----------------

    _loadConfig() {
        const defaults = {
            visibleColumns: { ...MembersPanel.DEFAULT_VISIBLE_COLUMNS },
            columnOrder:   [...MembersPanel.DEFAULT_COLUMN_ORDER],
            columnWidths:  { ...MembersPanel.DEFAULT_COLUMN_WIDTHS },
        };
        try {
            const raw = window.localStorage.getItem(MembersPanel._LS_KEY);
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return {
                visibleColumns: { ...defaults.visibleColumns, ...(parsed.visibleColumns || {}) },
                columnOrder: this._sanitiseOrder(parsed.columnOrder),
                columnWidths:  { ...defaults.columnWidths,  ...(parsed.columnWidths  || {}) },
            };
        } catch (e) {
            return defaults;
        }
    }

    // Strip unknown keys and append any new keys at the end so newer
    // columns become visible without manual reset.
    _sanitiseOrder(order) {
        const valid = new Set(MembersPanel.COLUMN_OPTIONS.map(c => c.key));
        const seen = new Set();
        const out = [];
        for (const k of (Array.isArray(order) ? order : [])) {
            if (valid.has(k) && !seen.has(k)) {
                out.push(k);
                seen.add(k);
            }
        }
        for (const c of MembersPanel.COLUMN_OPTIONS) {
            if (!seen.has(c.key)) out.push(c.key);
        }
        return out;
    }

    _saveConfig() {
        try {
            window.localStorage.setItem(
                MembersPanel._LS_KEY,
                JSON.stringify({
                    visibleColumns: this.state.visibleColumns,
                    columnOrder: this.state.columnOrder,
                    columnWidths: this.state.columnWidths,
                }));
        } catch (e) { /* ignore */ }
    }

    get visibleColumns() {
        return this.state.visibleColumns;
    }

    get columnOptions() {
        return MembersPanel.COLUMN_OPTIONS;
    }

    // Ordered + visible-only column descriptors, ready for t-foreach.
    get visibleOrderedColumns() {
        const labelFor = (k) => MembersPanel.COLUMN_OPTIONS.find(c => c.key === k)?.label || k;
        return this.state.columnOrder
            .filter(k => this.state.visibleColumns[k])
            .map(k => ({ key: k, label: labelFor(k) }));
    }

    // Inline style for a data/header cell. Returns "" when width is
    // unset, letting the default CSS flex-basis apply.
    columnStyle(key) {
        const w = this.state.columnWidths[key];
        return w ? `flex: 0 0 ${w}px; width: ${w}px;` : '';
    }

    onToggleColumnConfig() {
        this.state.showColumnConfig = !this.state.showColumnConfig;
    }

    onColumnToggle(key, checked) {
        this.state.visibleColumns = { ...this.state.visibleColumns, [key]: !!checked };
        this._saveConfig();
    }

    resetColumns() {
        this.state.visibleColumns = { ...MembersPanel.DEFAULT_VISIBLE_COLUMNS };
        this.state.columnOrder    = [...MembersPanel.DEFAULT_COLUMN_ORDER];
        this.state.columnWidths   = { ...MembersPanel.DEFAULT_COLUMN_WIDTHS };
        this._saveConfig();
    }

    // --- Drag-to-reorder ----------------------------------------------

    onColumnDragStart(ev, key) {
        ev.dataTransfer.effectAllowed = 'move';
        ev.dataTransfer.setData('text/plain', `col:${key}`);
        this._dragKey = key;
    }

    onColumnDragOver(ev, key) {
        if (!this._dragKey || this._dragKey === key) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = 'move';
        if (this.state.dragOverColumn !== key) {
            this.state.dragOverColumn = key;
        }
    }

    onColumnDragLeave() {
        if (this.state.dragOverColumn) this.state.dragOverColumn = null;
    }

    onColumnDrop(ev, key) {
        ev.preventDefault();
        const fromKey = this._dragKey;
        this._dragKey = null;
        this.state.dragOverColumn = null;
        if (!fromKey || fromKey === key) return;
        const order = [...this.state.columnOrder];
        const fromIdx = order.indexOf(fromKey);
        const toIdx   = order.indexOf(key);
        if (fromIdx < 0 || toIdx < 0) return;
        order.splice(fromIdx, 1);
        order.splice(toIdx, 0, fromKey);
        this.state.columnOrder = order;
        this._saveConfig();
    }

    onColumnDragEnd() {
        this._dragKey = null;
        this.state.dragOverColumn = null;
    }

    // --- Resize handle on right edge of a column header ---------------

    onColumnResizeStart(ev, key) {
        ev.preventDefault();
        ev.stopPropagation();
        const w = this.state.columnWidths[key] || MembersPanel.DEFAULT_COLUMN_WIDTHS[key] || 100;
        this._resize = { key, startX: ev.clientX, startW: w };
        document.addEventListener('mousemove', this._onColumnResizeMove);
        document.addEventListener('mouseup', this._onColumnResizeEnd);
        document.body.classList.add('ob-resizing');
    }

    _onColumnResizeMove(ev) {
        if (!this._resize) return;
        const delta = ev.clientX - this._resize.startX;
        const next = Math.max(
            MembersPanel.MIN_COLUMN_WIDTH,
            this._resize.startW + delta,
        );
        this.state.columnWidths = {
            ...this.state.columnWidths,
            [this._resize.key]: next,
        };
    }

    _onColumnResizeEnd() {
        document.removeEventListener('mousemove', this._onColumnResizeMove);
        document.removeEventListener('mouseup', this._onColumnResizeEnd);
        document.body.classList.remove('ob-resizing');
        this._resize = null;
        this._saveConfig();
    }

    // --- Row interactions ---

    // Row hover-action button. Action keys mirror onContextMenuAction
    // so the parent can dispatch via its existing switch.
    onRowAction(ev, action, member, type) {
        if (this.props.onMemberAction) {
            const node = {
                id: member.id,
                name: member.name,
                type: type,
                model: member.model,
                org_id: this.props.node?.id,
                other_active_org_count: member.other_active_org_count || 0,
                org_type_name: member.org_type_name,  // for persongroup-org distinction
            };
            this.props.onMemberAction(action, node);
        }
    }

    // Kebab button → open the context menu at the button's position.
    onRowKebab(ev, member, type) {
        if (this.props.onMemberKebab) {
            const rect = ev.currentTarget.getBoundingClientRect();
            const synthEv = { clientX: rect.left, clientY: rect.bottom + 4,
                              preventDefault: () => {}, stopPropagation: () => {} };
            const node = {
                id: member.id,
                name: member.name,
                type: type,
                model: member.model,
                org_id: this.props.node?.id,
                other_active_org_count: member.other_active_org_count || 0,
                org_type_name: member.org_type_name,
            };
            this.props.onMemberKebab(synthEv, node);
        }
    }

    // Double-click → open the slide-over details (Phase 3).
    onMemberDblClick(ev, member, type) {
        if (this.props.onMemberOpenDetails) {
            const node = {
                id: member.id,
                name: member.name,
                type: type,
                model: member.model,
                org_id: this.props.node?.id,
                person_type: member.person_type,
                person_type_color: member.person_type_color,
                person_type_icon_fa: member.person_type_icon_fa,
                person_type_icon_url: member.person_type_icon_url,
                org_type_name: member.org_type_name,
                org_type_color: member.org_type_color,
                org_type_icon_fa: member.org_type_icon_fa,
                org_type_icon_url: member.org_type_icon_url,
                email: member.email,
                sap_ref: member.sap_ref,
                roles: member.roles,
                is_active: member.is_active,
            };
            this.props.onMemberOpenDetails(node);
        }
    }

    // Members-header "Details" button → open slide-over for current org.
    onOrgDetailsClick() {
        if (this.props.onOpenOrgDetails) this.props.onOpenOrgDetails();
    }

    // Klik op de oog-knop links van de naam → open slide-over voor
    // deze member. Werkt voor zowel persons als orgs/persongroups —
    // de slide-over is een 1-klik shortcut zonder drilling.
    onRowShowDetails(ev, member, type) {
        if (!this.props.onMemberShowDetails) return;
        const node = {
            id: member.id,
            name: member.name,
            type: type,
            model: member.model,
            org_id: this.props.node?.id,
            person_type: member.person_type,
            person_type_color: member.person_type_color,
            person_type_icon_fa: member.person_type_icon_fa,
            person_type_icon_url: member.person_type_icon_url,
            org_type_name: member.org_type_name,
            org_type_color: member.org_type_color,
            org_type_icon_fa: member.org_type_icon_fa,
            org_type_icon_url: member.org_type_icon_url,
            email: member.email,
            sap_ref: member.sap_ref,
            roles: member.roles,
            is_active: member.is_active,
        };
        this.props.onMemberShowDetails(node);
    }
    
    getInitials(name) {
        if (!name) return '??';
        const parts = name.replace(',', '').split(/\s+/).filter(p => p.length > 0);
        if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
        return name.substring(0, 2).toUpperCase();
    }

    // Build a CSS `style` string for an avatar circle given a hex tint.
    // Light tint as background, solid colour for icon/initials text.
    // Empty input → empty string so the inline style attribute drops out
    // and the avatar-class default takes over.
    avatarStyle(hex) {
        if (!hex || typeof hex !== 'string') return '';
        // hex with optional leading '#'; accept #rgb or #rrggbb
        const v = hex.startsWith('#') ? hex.slice(1) : hex;
        const isShort = v.length === 3;
        const r = parseInt(isShort ? v[0] + v[0] : v.slice(0, 2), 16);
        const g = parseInt(isShort ? v[1] + v[1] : v.slice(2, 4), 16);
        const b = parseInt(isShort ? v[2] + v[2] : v.slice(4, 6), 16);
        if ([r, g, b].some(n => Number.isNaN(n))) return '';
        // 16/255 ≈ 0.063 — same alpha as the existing brand-tint pastels.
        return `background: rgba(${r},${g},${b},0.16); color: ${hex};`;
    }

    get filteredPersons() {
        const persons = this.props.members?.persons || [];
        if (!this.state.filterText) return persons;
        const filter = this.state.filterText.toLowerCase();
        return persons.filter(p => p.name.toLowerCase().includes(filter));
    }
    
    get filteredPersongroups() {
        const groups = this.props.members?.persongroups || [];
        if (!this.state.filterText) return groups;
        const filter = this.state.filterText.toLowerCase();
        return groups.filter(g => 
            g.name.toLowerCase().includes(filter) || 
            (g.full_name && g.full_name.toLowerCase().includes(filter))
        );
    }
    
    onFilterInput(ev) {
        this.state.filterText = ev.target.value;
    }
    
    clearFilter() {
        this.state.filterText = '';
    }
    
    onMemberClick(ev) {
        ev.stopPropagation();
        const model = ev.currentTarget.dataset.model;
        const id = parseInt(ev.currentTarget.dataset.id);
        const name = ev.currentTarget.dataset.name;
        const type = ev.currentTarget.dataset.type;

        if (this.props.onMemberSelect && id) {
            const node = this._buildMemberNode(id, name, type, model);
            this.props.onMemberSelect(node, {
                ctrlKey: ev.ctrlKey || ev.metaKey,
                shiftKey: ev.shiftKey,
            });
        }
    }

    // Build a fully-populated node from a member click. Member-pane
    // entries carry rich data (person_type, email, sap_ref, roles, …)
    // that the details pane needs — copy it onto the node instead of
    // shipping a stub. Also tag the parent org name/id so the details
    // pane can render the "Organisatie" card without an extra lookup.
    _buildMemberNode(id, name, type, model) {
        const parentOrg = this.props.node || null;
        const base = {
            id,
            name,
            type,
            model,
            org_id: parentOrg?.id || null,
            parent_org_id: parentOrg?.id || null,
            parent_org_name: parentOrg?.full_name || parentOrg?.name || '',
        };
        if (type === 'person') {
            const full = (this.props.members?.persons || []).find(p => p.id === id);
            if (full) Object.assign(base, full, base);  // base wins for org_id
        } else if (type === 'org' || type === 'persongroup') {
            const full = (this.props.members?.persongroups || []).find(g => g.id === id);
            if (full) Object.assign(base, full, base);
        }
        return base;
    }
    
    onMemberContextMenu(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        const model = ev.currentTarget.dataset.model;
        const id = parseInt(ev.currentTarget.dataset.id);
        const name = ev.currentTarget.dataset.name;
        const type = ev.currentTarget.dataset.type;
        const otherOrgs = parseInt(
            ev.currentTarget.dataset.otherOrgs || '0', 10) || 0;

        if (this.props.onMemberContextMenu && id) {
            const node = this._buildMemberNode(id, name, type, model);
            node.other_active_org_count = otherOrgs;
            this.props.onMemberContextMenu(ev, node);
        }
    }

    // Right-click on the empty area of the panel (i.e. NOT on a member
    // row — row handlers stop propagation). Surfaces a create-context
    // menu for the parent org so admins can quickly add a person or
    // sub-org without first hunting for the right-click target in the
    // tree. Skipped when the active container is a persongroup —
    // persongroups have their own member-management flow.
    onPanelContextMenu(ev) {
        if (!this.props.onPanelContextMenu) return;
        const org = this.props.node;
        if (!org || org.type !== 'org') return;
        if (org.org_type_name === 'PERSONGROUP') return;
        ev.preventDefault();
        this.props.onPanelContextMenu(ev, org);
    }
    
    onPasswordClick(ev, person) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.props.onPasswordClick) {
            this.props.onPasswordClick(person);
        }
    }
    
    isMemberSelected(memberId, memberType) {
        return this.props.selectedMemberId === memberId && this.props.selectedMemberType === memberType;
    }

    /**
     * Stub for the multi-select feature (referenced in the template).
     * Return false until proper multi-select state is wired up — that requires
     * a list of selected members in props/state, which isn't there yet.
     */
    isMemberMultiSelected(memberId, memberType) {
        return false;
    }

    isMemberMultiSelected(memberId, memberType) {
        const key = `${memberType}_${memberId}`;
        return !!(this.props.selectedMemberIds && this.props.selectedMemberIds[key]);
    }

    onMemberDragStart(ev, member, type) {
        const node = this._buildMemberNode(member.id, member.name, type, member.model);
        ev.dataTransfer.effectAllowed = 'move';
        ev.dataTransfer.setData('text/plain', JSON.stringify({
            type: node.type, id: node.id, name: node.name,
        }));
        if (this.props.onMemberDragStart) {
            this.props.onMemberDragStart(node);
        }
    }

    onMemberDragEnd(ev) {
        if (this.props.onMemberDragEnd) {
            this.props.onMemberDragEnd();
        }
    }

    onPaneClick() {
        if (this.props.onFocus) this.props.onFocus();
    }
}

/**
 * ContextMenu component
 */
export class ContextMenu extends Component {
    static template = "myschool_admin.ContextMenu";
    static props = {
        x: Number,
        y: Number,
        node: Object,
        bulkSource: { type: [String, { value: null }], optional: true },
        bulkCount: { type: Number, optional: true },
        onAction: Function,
        onClose: Function,
    };

    get menuItems() {
        const node = this.props.node;
        const bulkCount = this.props.bulkCount || 0;
        const hasBulk = bulkCount > 1 && this.props.bulkSource;

        // Filter the canonical list to context-menu entries, apply `when`
        // predicates, and translate keys to the {action,...} shape the
        // template expects.
        const items = actionsForNode(node)
            .filter(a => a.inMenu)
            .filter(a => !a.when || a.when(node))
            .map(a => a.divider
                ? { divider: true }
                : {
                    action: a.key,
                    label: a.label,
                    iconClass: a.iconClass,
                    danger: a.danger,
                });

        if (hasBulk) {
            items.push({ divider: true });
            items.push({
                action: 'bulk_delete',
                label: `Verwijder ${bulkCount} geselecteerde items`,
                iconClass: 'fa fa-trash',
                danger: true,
            });
        }

        return items;
    }

    onMenuItemClick(ev) {
        const action = ev.currentTarget.dataset.action;
        if (action) {
            this.props.onAction(action, this.props.node);
            this.props.onClose();
        }
    }
}

/**
 * Main ObjectBrowserClient component
 */
export class ObjectBrowserClient extends Component {
    static template = "myschool_admin.ObjectBrowserClient";
    static components = { TreeNode, ContextMenu, DetailsPanel, MembersPanel, SlideOverDetails };
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.containerRef = useRef("container");
        this.globalSearchRef = useRef("globalSearch");
        
        this.state = useState({
            loading: true,
            treeData: { organizations: [], roles: [] },
            searchText: '',
            searchResults: [],
            globalSearchText: '',
            globalSearchResults: [],
            showInactive: false,
            showAdministrative: false,
            selectionMode: false,
            selectedIds: {},
            expandedIds: {},
            contextMenu: null,
            draggedNode: false,
            activeNode: null,
            activeOrgNode: null,  // Keep track of selected org for members panel
            activeTab: 'orgs',  // 'orgs' or 'roles'
            membersData: { persons: [], persongroups: [] },
            membersLoading: false,
            // Multi-select set for the members pane (ctrl/shift+click).
            // Keys: `${type}_${id}` where type is 'person' or 'persongroup'.
            selectedMemberIds: {},
            // Anchor for shift+click range select on members pane.
            lastSelectedMemberKey: null,
            // Active splitter ('tree' | 'members' | null) — used to apply
            // a hover-locked class and a global resize cursor while dragging.
            resizing: null,
            // Which pane has keyboard focus ('tree' | 'members'). Updated
            // by mousedown on a pane; arrow keys navigate within it.
            focusedPane: 'tree',
            // Global-search scope: 'all' | 'orgs' | 'persons' | 'roles'.
            // Filter is applied client-side on the result set.
            searchScope: 'all',
            // Slide-over (Phase 3): when set, the SlideOverDetails panel
            // is rendered as an overlay above the members pane. null = closed.
            slideOverNode: null,
            slideOverCiRelations: [],
            slideOverCiLoading: false,

            // ----- AD-browser tab (Fase G) -----
            // Lazy-loaded tree van de live AD-inhoud. Map: dn(lowercase)
            // → { node, children: [...] }. Tree-render leest hieruit.
            adConfigs: [],
            adActiveConfigId: null,
            adRootDn: null,
            adTreeNodes: {},        // dn-lowercase → cached node
            adChildren: {},         // dn-lowercase → list of child-DNs
            adExpanded: {},         // dn-lowercase → bool
            adLoading: {},          // dn-lowercase → bool (children-fetch in flight)
            adSelectedDn: null,
            adError: null,
        });
        
        // Bind methods that are passed as props
        this.onSelectNode = this.onSelectNode.bind(this);
        this.onContextMenu = this.onContextMenu.bind(this);
        this.onMemberContextMenu = this.onMemberContextMenu.bind(this);
        this.onMemberSelect = this.onMemberSelect.bind(this);
        this.onMemberRowAction = this.onMemberRowAction.bind(this);
        this.onMemberRowKebab = this.onMemberRowKebab.bind(this);
        this.onMembersPanelContextMenu = this.onMembersPanelContextMenu.bind(this);
        this.onMemberOpenDetails = this.onMemberOpenDetails.bind(this);
        this.onOpenOrgDetails = this.onOpenOrgDetails.bind(this);
        this.closeSlideOver = this.closeSlideOver.bind(this);
        this.onSlideOverAction = this.onSlideOverAction.bind(this);
        this.onSlideOverOpenRecord = this.onSlideOverOpenRecord.bind(this);
        this.openAddCiForActiveOrg = this.openAddCiForActiveOrg.bind(this);
        this.onPasswordClick = this.onPasswordClick.bind(this);
        this.onToggleSelect = this.onToggleSelect.bind(this);
        this.onDragStart = this.onDragStart.bind(this);
        this.onDragOver = this.onDragOver.bind(this);
        this.onDrop = this.onDrop.bind(this);
        this.onMemberDragStart = this.onMemberDragStart.bind(this);
        this.onMemberDragEnd = this.onMemberDragEnd.bind(this);
        this.onBreadcrumbClick = this.onBreadcrumbClick.bind(this);
        this.onTreeIconClick = this.onTreeIconClick.bind(this);
        this.onMemberShowDetails = this.onMemberShowDetails.bind(this);
        this.onSplitterMouseDown = this.onSplitterMouseDown.bind(this);
        this.onSplitterDoubleClick = this.onSplitterDoubleClick.bind(this);
        this._onSplitterMouseMove = this._onSplitterMouseMove.bind(this);
        this._onSplitterMouseUp = this._onSplitterMouseUp.bind(this);
        this.onKeyDown = this.onKeyDown.bind(this);
        this.onPaneFocus = this.onPaneFocus.bind(this);
        this.onContextMenuAction = this.onContextMenuAction.bind(this);
        this.onCloseContextMenu = this.onCloseContextMenu.bind(this);
        this.onDetailsAction = this.onDetailsAction.bind(this);
        this.openActiveRecord = this.openActiveRecord.bind(this);
        this.openEditCiWizard = this.openEditCiWizard.bind(this);
        this.openRemoveCiWizard = this.openRemoveCiWizard.bind(this);
        this.onDocumentClick = this.onDocumentClick.bind(this);
        this.openRecord = this.openRecord.bind(this);
        this.navigateToOrg = this.navigateToOrg.bind(this);
        this.onToggleExpand = this.onToggleExpand.bind(this);
        this.onGlobalSearchInput = this.onGlobalSearchInput.bind(this);
        this.onGlobalSearchKeydown = this.onGlobalSearchKeydown.bind(this);
        this.onGlobalSearchResultClick = this.onGlobalSearchResultClick.bind(this);
        this.onSearchScopeChange = this.onSearchScopeChange.bind(this);

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            document.addEventListener('click', this.onDocumentClick);
            // Container ref is available now — restore persisted pane widths.
            this._loadPaneWidths();
            // Give the container initial focus so keydown is delivered.
            this.containerRef.el?.focus();
        });

        onWillUnmount(() => {
            document.removeEventListener('click', this.onDocumentClick);
            // Defensive: drop dangling splitter listeners if unmount during resize.
            document.removeEventListener('mousemove', this._onSplitterMouseMove);
            document.removeEventListener('mouseup', this._onSplitterMouseUp);
            document.body.classList.remove('ob-resizing');
        });
    }
    
    get selectedCount() {
        return Object.keys(this.state.selectedIds).filter(k => this.state.selectedIds[k]).length;
    }

    get memberSelectedCount() {
        return Object.keys(this.state.selectedMemberIds).filter(k => this.state.selectedMemberIds[k]).length;
    }

    get totalSelectedCount() {
        return this.selectedCount + this.memberSelectedCount;
    }

    // Resolve a person -> their parent org node by walking the tree.
    // Persons appear under their org via state.treeData.organizations[*].persons.
    findOrgNodeForPersonId(personId) {
        if (!personId) return null;
        const walk = (nodes) => {
            if (!nodes) return null;
            for (const n of nodes) {
                if (n.persons) {
                    for (const p of n.persons) {
                        if (p.id === personId) return n;
                    }
                }
                if (n.children) {
                    const found = walk(n.children);
                    if (found) return found;
                }
            }
            return null;
        };
        return walk(this.state.treeData?.organizations || []);
    }

    // Jump tree+members+details to a specific org (used by the
    // "Organisatie" card in the details pane). Expands the path so
    // the org is visible, then selects it to drive _loadOrgContext.
    async navigateToOrg(orgId) {
        if (!orgId) return;
        this.expandPathToOrg(orgId);
        const orgNode = this.findOrgNodeById(orgId)
            || { id: orgId, type: 'org', model: 'myschool.org', name: '' };
        await this.onSelectNode(orgNode);
    }

    // Resolve an org id -> its node anywhere in the tree.
    findOrgNodeById(orgId) {
        if (!orgId) return null;
        const walk = (nodes) => {
            if (!nodes) return null;
            for (const n of nodes) {
                if (n.id === orgId && n.type === 'org') return n;
                if (n.children) {
                    const found = walk(n.children);
                    if (found) return found;
                }
            }
            return null;
        };
        return walk(this.state.treeData?.organizations || []);
    }

    // Breadcrumb path for the currently focused thing. Returns an array of
    // segment objects { id, name, type, model }. Begint altijd met een
    // 'home' segment ("Organisations") zodat de breadcrumb-bar zichtbaar
    // is vanaf opstart, ook wanneer er nog niets geselecteerd is. Daarna
    // het pad van root org naar de active node (org / person / persongroup).
    get breadcrumbPath() {
        const homeSegment = {
            id: 0, name: 'Organisations', type: 'home', model: '',
        };
        const buildOrgPath = (orgId) => {
            const segs = [];
            const walk = (nodes, trail) => {
                if (!nodes) return false;
                for (const n of nodes) {
                    if (n.type !== 'org') continue;
                    const here = [...trail, n];
                    if (n.id === orgId) {
                        for (const s of here) {
                            segs.push({ id: s.id, name: s.name, type: 'org', model: 'myschool.org' });
                        }
                        return true;
                    }
                    if (n.children && walk(n.children, here)) return true;
                }
                return false;
            };
            walk(this.state.treeData?.organizations || [], []);
            return segs;
        };
        const node = this.state.activeNode;
        if (!node) return [homeSegment];
        if (node.type === 'org') {
            return [homeSegment, ...buildOrgPath(node.id)];
        }
        if (node.type === 'person') {
            const orgId = node.org_id || this.state.activeOrgNode?.id;
            const segs = orgId ? buildOrgPath(orgId) : [];
            segs.push({ id: node.id, name: node.name, type: 'person', model: 'myschool.person' });
            return [homeSegment, ...segs];
        }
        if (node.type === 'persongroup') {
            const orgId = node.org_id || this.state.activeOrgNode?.id;
            const segs = orgId ? buildOrgPath(orgId) : [];
            segs.push({ id: node.id, name: node.name, type: 'persongroup', model: 'myschool.org' });
            return [homeSegment, ...segs];
        }
        return [homeSegment];
    }
    
    async loadData() {
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                'myschool.object.browser',
                'get_tree_data',
                [],
                {
                    search_text: this.state.searchText,
                    show_inactive: this.state.showInactive,
                    show_administrative: this.state.showAdministrative,
                }
            );
            // Ensure result has expected structure
            this.state.treeData = {
                organizations: result?.organizations || [],
                roles: result?.roles || [],
            };
        } catch (error) {
            console.error('Error loading tree data:', error);
            this.notification.add('Error loading data', { type: 'danger' });
            // Reset to empty state on error
            this.state.treeData = { organizations: [], roles: [] };
        }
        this.state.loading = false;
    }
    
    // Track expanded/collapsed nodes
    onToggleExpand(nodeKey, isExpanded) {
        this.state.expandedIds[nodeKey] = isExpanded;
    }
    
    // Expand path to a specific org (used after actions to keep tree open)
    expandPathToOrg(orgId) {
        // Mark the org and find its parents to expand
        const nodeKey = `org_${orgId}`;
        this.state.expandedIds[nodeKey] = true;
        
        // Find parent orgs in tree and expand them
        const findAndExpandParents = (nodes, targetId, path = []) => {
            for (const node of nodes) {
                if (node.id === targetId && node.type === 'org') {
                    // Found it, expand all nodes in path
                    for (const p of path) {
                        this.state.expandedIds[`org_${p.id}`] = true;
                    }
                    return true;
                }
                if (node.children && node.children.length > 0) {
                    if (findAndExpandParents(node.children, targetId, [...path, node])) {
                        return true;
                    }
                }
            }
            return false;
        };
        
        findAndExpandParents(this.state.treeData.organizations || [], orgId);
    }

    // Centralised post-mutation refresh. Wizards that create / edit /
    // delete persons or orgs should call this from their onClose hook
    // so all visible state catches up:
    //   1. Reload the tree (loadData) — picks up new orgs, deletions,
    //      moves, count badges, etc.
    //   2. Reload the members of the currently-active org so the rows
    //      in the members pane appear/disappear immediately.
    //   3. If the slide-over is open for that same org, refresh its
    //      CI relations too so the Configuration tab stays in sync.
    //
    // ``focusOrgId`` (optional): the org whose path should be expanded
    // in the tree afterwards (typically the wizard's target org).
    async _refreshTreeAndMembers(focusOrgId = null) {
        await this.loadData();
        if (focusOrgId) this.expandPathToOrg(focusOrgId);

        const activeOrg = this.state.activeOrgNode;
        if (activeOrg?.id) {
            // Use the freshly-loaded tree node when available — that one
            // has the most recent display name, child_count, etc.
            const fresh = this.findOrgNodeById(activeOrg.id) || activeOrg;
            await this._loadOrgContext(fresh, { setActive: false });
        }

        const slideOrg = this.state.slideOverNode;
        if (slideOrg && (slideOrg.type === 'org' || slideOrg.type === 'persongroup')) {
            try {
                const ciRelations = await this.orm.call(
                    'myschool.object.browser',
                    'get_ci_relations_for_org',
                    [slideOrg.id],
                );
                this.state.slideOverCiRelations = ciRelations || [];
            } catch (e) {
                // Non-fatal: the slide-over keeps its current state.
            }
        }
    }

    // Node selection for details panel
    async onSelectNode(node) {
        // Enrich person nodes with parent_org_name so the details pane
        // can render the "Organisatie" card without an extra lookup.
        if (node.type === 'person' && node.org_id && !node.parent_org_name) {
            const orgNode = this.findOrgNodeById(node.org_id);
            if (orgNode) {
                node = {
                    ...node,
                    parent_org_id: node.org_id,
                    parent_org_name: orgNode.full_name || orgNode.name || '',
                };
            }
        }
        this.state.activeNode = node;

        // For persons, make the members panel context follow: switch
        // activeOrgNode to the person's parent org and load its members
        // (if different from what's already shown). This keeps the 3
        // panes coherent — selecting a person never leaves the middle
        // pane pointing at an unrelated org.
        if (node.type === 'person') {
            const orgId = node.org_id;
            if (orgId && this.state.activeOrgNode?.id !== orgId) {
                const orgNode = this.findOrgNodeById(orgId)
                    || { id: orgId, type: 'org', model: 'myschool.org', name: '' };
                await this._loadOrgContext(orgNode);
            }
            return;
        }

        // Load CI relations and members for orgs
        if (node.type === 'org') {
            await this._loadOrgContext(node, { setActive: true });
        }
        // For persons, don't clear members data - keep showing the org's members
    }

    // Load the org-scoped context: CI relations + members. Shared by
    // direct org clicks (setActive=true) and indirect activation via
    // a person click (setActive=false — activeNode stays on the person).
    async _loadOrgContext(node, { setActive = true } = {}) {
        this.state.activeOrgNode = node;
        this.state.membersData = { persons: [], persongroups: [] };

        try {
            const ciRelations = await this.orm.call(
                'myschool.object.browser',
                'get_ci_relations_for_org',
                [node.id]
            );
            const merged = { ...node, ciRelations };
            this.state.activeOrgNode = merged;
            if (setActive) this.state.activeNode = merged;
        } catch (error) {
            console.warn('Could not load CI relations:', error);
            const merged = { ...node, ciRelations: [] };
            this.state.activeOrgNode = merged;
            if (setActive) this.state.activeNode = merged;
        }

        this.state.membersLoading = true;
        try {
            const membersData = await this.orm.call(
                'myschool.object.browser',
                'get_members_for_org',
                [node.id],
                {
                    show_inactive: this.state.showInactive,
                    show_administrative: this.state.showAdministrative,
                },
            );
            this.state.membersData = membersData || { persons: [], persongroups: [] };
        } catch (error) {
            console.error('Could not load members:', error);
            this.state.membersData = { persons: [], persongroups: [] };
        }
        this.state.membersLoading = false;
    }

    // ============================================================
    // Pane resize (splitters between Tree | Members | Details)
    // ============================================================
    // Widths persist per browser via localStorage; reset to defaults on
    // dblclick of a splitter handle. Defaults match the CSS fallbacks.
    static get _PANE_DEFAULTS() { return { tree: 320, members: 400 }; }
    static get _PANE_MIN() { return { tree: 180, members: 220 }; }
    static get _LS_KEY() { return 'myschool_admin.object_browser.paneWidths'; }

    _loadPaneWidths() {
        try {
            const raw = window.localStorage.getItem(ObjectBrowserClient._LS_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            this._applyPaneWidth('tree', parsed.tree);
            this._applyPaneWidth('members', parsed.members);
        } catch (e) {
            // Bad localStorage data — ignore and fall back to defaults.
        }
    }

    _savePaneWidths() {
        const data = {
            tree: this._currentPaneWidth('tree'),
            members: this._currentPaneWidth('members'),
        };
        try {
            window.localStorage.setItem(
                ObjectBrowserClient._LS_KEY, JSON.stringify(data));
        } catch (e) {
            // Quota / private mode — silently skip.
        }
    }

    _currentPaneWidth(which) {
        const root = this.containerRef.el;
        if (!root) return ObjectBrowserClient._PANE_DEFAULTS[which];
        const varName = which === 'tree' ? '--ob-tree-width' : '--ob-members-width';
        const cur = root.style.getPropertyValue(varName);
        if (cur) {
            const n = parseInt(cur, 10);
            if (!Number.isNaN(n)) return n;
        }
        return ObjectBrowserClient._PANE_DEFAULTS[which];
    }

    _applyPaneWidth(which, px) {
        const root = this.containerRef.el;
        if (!root) return;
        const min = ObjectBrowserClient._PANE_MIN[which];
        const value = Math.max(min, parseInt(px, 10) || ObjectBrowserClient._PANE_DEFAULTS[which]);
        const varName = which === 'tree' ? '--ob-tree-width' : '--ob-members-width';
        root.style.setProperty(varName, `${value}px`);
    }

    onSplitterMouseDown(ev, which) {
        ev.preventDefault();
        this.state.resizing = which;
        this._resizeStart = {
            x: ev.clientX,
            width: this._currentPaneWidth(which),
            which,
        };
        document.addEventListener('mousemove', this._onSplitterMouseMove);
        document.addEventListener('mouseup', this._onSplitterMouseUp);
        document.body.classList.add('ob-resizing');
    }

    _onSplitterMouseMove(ev) {
        if (!this._resizeStart) return;
        const dx = ev.clientX - this._resizeStart.x;
        this._applyPaneWidth(this._resizeStart.which, this._resizeStart.width + dx);
    }

    _onSplitterMouseUp() {
        document.removeEventListener('mousemove', this._onSplitterMouseMove);
        document.removeEventListener('mouseup', this._onSplitterMouseUp);
        document.body.classList.remove('ob-resizing');
        this.state.resizing = null;
        this._resizeStart = null;
        this._savePaneWidths();
    }

    onSplitterDoubleClick(which) {
        this._applyPaneWidth(which, ObjectBrowserClient._PANE_DEFAULTS[which]);
        this._savePaneWidths();
    }


    // ============================================================
    // Keyboard navigation
    // ============================================================

    onPaneFocus(pane) {
        if (this.state.focusedPane !== pane) {
            this.state.focusedPane = pane;
        }
        // Re-focus the container so keydown events keep flowing.
        // (Inputs inside panes will keep their own focus — that's fine,
        // the keydown handler bails out when target is an input.)
        const root = this.containerRef.el;
        if (root && document.activeElement && !root.contains(document.activeElement)) {
            root.focus();
        }
    }

    // Visible-orgs flattener for tree navigation (depth-first, expanded only).
    flattenVisibleTreeOrgs() {
        const out = [];
        const walk = (nodes) => {
            if (!nodes) return;
            for (const n of nodes) {
                if (n.type !== 'org') continue;
                out.push(n);
                const key = `${n.type}_${n.id}`;
                const expanded = (key in this.state.expandedIds)
                    ? this.state.expandedIds[key]
                    : true;  // level-0 default-open; deeper levels default-closed
                if (expanded && n.children?.length) walk(n.children);
            }
        };
        walk(this.state.treeData?.organizations || []);
        return out;
    }

    onKeyDown(ev) {
        // Don't interfere when user is typing in an input/textarea/contentEditable.
        const tag = (ev.target?.tagName || '').toLowerCase();
        const isTyping = tag === 'input' || tag === 'textarea' || ev.target?.isContentEditable;
        if (isTyping && ev.key !== 'Escape') {
            return;
        }

        // Ctrl+K / Cmd+K → focus global search (works from any pane).
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) {
            ev.preventDefault();
            const input = this.globalSearchRef.el
                || this.containerRef.el?.querySelector('.ob-global-search');
            if (input) {
                input.focus();
                input.select?.();
            }
            return;
        }

        if (ev.key === 'Escape') {
            // Inside an input → let onGlobalSearchKeydown handle its own state.
            // At pane level, drop selection and close context menu.
            if (!isTyping) {
                if (this.state.contextMenu) this.state.contextMenu = null;
                this.state.selectedIds = {};
                this.state.selectedMemberIds = {};
            }
            return;
        }

        const pane = this.state.focusedPane;
        if (pane === 'tree') return this._handleKeyTree(ev);
        if (pane === 'members') return this._handleKeyMembers(ev);
    }

    _handleKeyTree(ev) {
        const flat = this.flattenVisibleTreeOrgs();
        if (!flat.length) return;
        const activeId = this.state.activeNode?.type === 'org' ? this.state.activeNode.id : null;
        const idx = activeId != null ? flat.findIndex(n => n.id === activeId) : -1;

        const move = (delta) => {
            ev.preventDefault();
            const next = idx < 0 ? 0 : Math.max(0, Math.min(flat.length - 1, idx + delta));
            this.onSelectNode(flat[next]);
        };

        switch (ev.key) {
            case 'ArrowDown': return move(1);
            case 'ArrowUp':   return move(-1);
            case 'ArrowRight': {
                if (idx < 0) return;
                ev.preventDefault();
                const node = flat[idx];
                const key = `${node.type}_${node.id}`;
                if (node.children?.length) {
                    this.state.expandedIds[key] = true;
                }
                return;
            }
            case 'ArrowLeft': {
                if (idx < 0) return;
                ev.preventDefault();
                const node = flat[idx];
                const key = `${node.type}_${node.id}`;
                const expanded = (key in this.state.expandedIds)
                    ? this.state.expandedIds[key] : true;
                if (expanded && node.children?.length) {
                    this.state.expandedIds[key] = false;
                }
                return;
            }
            case 'Enter': {
                if (idx < 0) return;
                ev.preventDefault();
                const node = flat[idx];
                this.openRecord(node.model, node.id);
                return;
            }
            case 'Tab': {
                ev.preventDefault();
                this.state.focusedPane = 'members';
                return;
            }
            case ' ': /* Space */ {
                if (idx < 0) return;
                ev.preventDefault();
                const node = flat[idx];
                const key = `${node.type}_${node.id}`;
                const cur = !!this.state.selectedIds[key];
                this.state.selectedIds = { ...this.state.selectedIds, [key]: !cur };
                return;
            }
        }
    }

    _handleKeyMembers(ev) {
        const flat = this.flattenVisibleMembers();
        if (!flat.length) {
            if (ev.key === 'Tab' || ev.key === 'ArrowLeft') {
                ev.preventDefault();
                this.state.focusedPane = 'tree';
            }
            return;
        }
        const an = this.state.activeNode;
        const activeKey = (an && an.type !== 'org')
            ? `${an.type}_${an.id}` : null;
        const idx = activeKey
            ? flat.findIndex(n => `${n.type}_${n.id}` === activeKey)
            : -1;

        const selectAt = (i) => {
            const target = flat[i];
            const members = this.state.membersData || {};
            const obj = target.type === 'person'
                ? (members.persons || []).find(p => p.id === target.id)
                : (members.persongroups || []).find(g => g.id === target.id);
            if (!obj) return;
            // Build the "node" shape that onMemberSelect expects.
            const node = {
                id: obj.id,
                name: obj.name,
                type: target.type,
                model: obj.model,
                org_id: this.state.activeOrgNode?.id,
            };
            this.onMemberSelect(node, { ctrlKey: false, shiftKey: false });
        };

        switch (ev.key) {
            case 'ArrowDown':
                ev.preventDefault();
                return selectAt(idx < 0 ? 0 : Math.min(flat.length - 1, idx + 1));
            case 'ArrowUp':
                ev.preventDefault();
                return selectAt(idx < 0 ? 0 : Math.max(0, idx - 1));
            case 'Enter': {
                if (idx < 0) return;
                ev.preventDefault();
                const target = flat[idx];
                this.openRecord(
                    target.type === 'person' ? 'myschool.person' : 'myschool.org',
                    target.id);
                return;
            }
            case ' ': /* Space — toggle multi-select */ {
                if (idx < 0) return;
                ev.preventDefault();
                const target = flat[idx];
                const key = `${target.type}_${target.id}`;
                const cur = !!this.state.selectedMemberIds[key];
                this.state.selectedMemberIds = { ...this.state.selectedMemberIds, [key]: !cur };
                return;
            }
            case 'Tab':
            case 'ArrowLeft': {
                ev.preventDefault();
                this.state.focusedPane = 'tree';
                return;
            }
        }
    }

    // Flat list of members shown in the panel (persons then persongroups,
    // matching template order). Used for shift+click range selection.
    flattenVisibleMembers() {
        const result = [];
        const m = this.state.membersData || {};
        for (const p of (m.persons || [])) {
            result.push({ id: p.id, type: 'person' });
        }
        for (const g of (m.persongroups || [])) {
            result.push({ id: g.id, type: 'persongroup' });
        }
        return result;
    }

    // Member selection from members panel — supports plain, ctrl+ and
    // shift+click. Single click resets the multi-set; ctrl toggles a key;
    // shift adds the range from the last anchor.
    onMemberSelect(node, mods) {
        const memberKey = `${node.type}_${node.id}`;
        const ctrl = !!(mods && mods.ctrlKey);
        const shift = !!(mods && mods.shiftKey);

        if (ctrl) {
            const next = { ...this.state.selectedMemberIds };
            if (next[memberKey]) {
                delete next[memberKey];
            } else {
                next[memberKey] = true;
            }
            this.state.selectedMemberIds = next;
            this.state.lastSelectedMemberKey = memberKey;
            return;
        }

        if (shift && this.state.lastSelectedMemberKey) {
            const flat = this.flattenVisibleMembers();
            const anchorIdx = flat.findIndex(
                n => `${n.type}_${n.id}` === this.state.lastSelectedMemberKey);
            const thisIdx = flat.findIndex(
                n => `${n.type}_${n.id}` === memberKey);
            if (anchorIdx >= 0 && thisIdx >= 0) {
                const [start, end] = anchorIdx <= thisIdx
                    ? [anchorIdx, thisIdx]
                    : [thisIdx, anchorIdx];
                const next = { ...this.state.selectedMemberIds };
                for (let i = start; i <= end; i++) {
                    const n = flat[i];
                    next[`${n.type}_${n.id}`] = true;
                }
                this.state.selectedMemberIds = next;
                return;
            }
        }

        // Plain click — reset multi-set, focus this one in the details pane.
        this.state.selectedMemberIds = {};
        this.state.lastSelectedMemberKey = memberKey;

        // Org-typed members (persongroups + sub-orgs) drill in: switch
        // members panel to that org and load its CI relations. Mirrors
        // tree-click semantics. Member-pane clicks may arrive as
        // type='persongroup' (DOM dataset literal); the tree always uses
        // type='org'. Use the tree's representation of the node so the
        // TreeNode active-highlight check matches, and expand the path
        // so the row is actually visible in the tree.
        // Also close any open slide-over so its stale content for a
        // previously-clicked member doesn't linger over the new context.
        if (node.type === 'org' || node.type === 'persongroup') {
            if (this.state.slideOverNode) this.closeSlideOver();
            const treeNode = this.findOrgNodeById(node.id) || {
                ...node,
                type: 'org',
                model: node.model || 'myschool.org',
            };
            this.expandPathToOrg(node.id);
            this._loadOrgContext(treeNode, { setActive: true });
            return;
        }

        this.state.activeNode = node;
        // For person clicks, keep activeOrgNode/membersData unchanged
        // so the members panel keeps showing the org context.
    }
    
    openActiveRecord() {
        if (this.state.activeNode) {
            this.openRecord(this.state.activeNode.model, this.state.activeNode.id);
        }
    }
    
    onDetailsAction(action) {
        if (this.state.activeNode) {
            this.onContextMenuAction(action, this.state.activeNode);
        }
    }
    
    openRecord(model, id) {
        // Store active org for when we return
        const activeOrgId = this.state.activeOrgNode?.id;
        if (activeOrgId) {
            this.expandPathToOrg(activeOrgId);
        }
        
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            res_id: id,
            views: [[false, 'form']],
            target: 'new',  // Open in dialog to preserve tree state
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(activeOrgId);
            }
        });
    }

    // Search
    onSearchInput(ev) {
        this.state.searchText = ev.target.value;
        this.debounceSearch();
    }
    
    debounceSearch() {
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        this.searchTimeout = setTimeout(() => {
            this.loadData();
        }, 300);
    }
    
    // Global Search
    onGlobalSearchInput(ev) {
        this.state.globalSearchText = ev.target.value;
        this.debounceGlobalSearch();
    }
    
    onGlobalSearchKeydown(ev) {
        if (ev.key === 'Escape') {
            this.state.globalSearchText = '';
            this.state.globalSearchResults = [];
        }
    }
    
    debounceGlobalSearch() {
        if (this.globalSearchTimeout) {
            clearTimeout(this.globalSearchTimeout);
        }
        this.globalSearchTimeout = setTimeout(async () => {
            await this.performGlobalSearch();
        }, 300);
    }
    
    async performGlobalSearch() {
        const query = this.state.globalSearchText.trim();
        if (!query || query.length < 2) {
            this.state.globalSearchResults = [];
            return;
        }
        
        try {
            const results = await this.orm.call(
                'myschool.object.browser',
                'global_search',
                [query]
            );
            this.state.globalSearchResults = results || [];
        } catch (error) {
            console.error('Global search error:', error);
            this.state.globalSearchResults = [];
        }
    }
    
    onGlobalSearchResultClick(result) {
        // Clear search
        this.state.globalSearchText = '';
        this.state.globalSearchResults = [];

        // Open the record
        this.openRecord(result.model, result.id);
    }

    // Scope chips for the global search. Static — kept here so the
    // template can iterate over them.
    get searchScopes() {
        return [
            { key: 'all', label: 'Alles', iconClass: 'fa fa-asterisk' },
            { key: 'orgs', label: 'Orgs', iconClass: 'fa fa-building' },
            { key: 'persons', label: 'Personen', iconClass: 'fa fa-user' },
            { key: 'roles', label: 'Rollen', iconClass: 'fa fa-id-badge' },
        ];
    }

    // Client-side filter on the result set based on the current scope.
    // Avoids extra round-trips since global_search() returns mixed types.
    get filteredGlobalResults() {
        const results = this.state.globalSearchResults || [];
        const scope = this.state.searchScope;
        if (scope === 'all') return results;
        // Map scope-name to the result `type` field returned by backend.
        const typeForScope = { orgs: 'org', persons: 'person', roles: 'role' };
        const wanted = typeForScope[scope];
        return wanted ? results.filter(r => r.type === wanted) : results;
    }

    onSearchScopeChange(scope) {
        this.state.searchScope = scope;
    }
    
    // Password management
    onPasswordClick(person) {
        // Open password management wizard
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.password.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_id: person.id,
            },
        }, {
            onClose: async () => {
                // Refresh after password change
                await this._refreshTreeAndMembers(this.state.activeOrgNode?.id);
            }
        });
    }

    // Filters
    onToggleInactive(ev) {
        this.state.showInactive = ev.target.checked;
        this._refreshTreeAndMembers(this.state.activeOrgNode?.id);
    }

    onToggleAdministrative(ev) {
        this.state.showAdministrative = ev.target.checked;
        this._refreshTreeAndMembers(this.state.activeOrgNode?.id);
    }
    
    // Refresh
    onRefresh() {
        this.loadData();
    }
    
    // Tab switching
    switchTab(tab) {
        this.state.activeTab = tab;
        this.state.activeNode = null;
    }
    
    onSwitchToOrgsTab() {
        this.switchTab('orgs');
    }
    
    onSwitchToRolesTab() {
        this.switchTab('roles');
    }

    async onSwitchToADTab() {
        this.switchTab('ad');
        // Eerste-keer: laad de config-lijst zodat de dropdown gevuld is.
        if (!this.state.adConfigs.length) {
            await this.loadAdConfigs();
        }
    }

    async loadAdConfigs() {
        try {
            const configs = await this.orm.call(
                'myschool.object.browser', 'ad_get_ldap_configs', []);
            this.state.adConfigs = configs;
            // Auto-select de eerste prod-config; anders gewoon de eerste.
            const prod = configs.find(c => c.environment === 'prod');
            const pick = prod || configs[0];
            if (pick) {
                await this.onAdConfigChange(pick.id);
            }
        } catch (e) {
            this.state.adError = 'Configs ophalen mislukt: ' + (e?.message || e);
        }
    }

    async onAdConfigChange(configId) {
        const cfgId = typeof configId === 'object'
            ? parseInt(configId.target?.value, 10)
            : parseInt(configId, 10);
        if (!cfgId) return;
        this.state.adActiveConfigId = cfgId;
        // Reset tree-state
        this.state.adTreeNodes = {};
        this.state.adChildren = {};
        this.state.adExpanded = {};
        this.state.adLoading = {};
        this.state.adSelectedDn = null;
        this.state.adError = null;
        // Root-DN = base_dn van de gekozen config
        const cfg = this.state.adConfigs.find(c => c.id === cfgId);
        const rootDn = cfg?.base_dn || null;
        this.state.adRootDn = rootDn;
        if (rootDn) {
            await this.loadAdChildren(rootDn, /*expand=*/true);
        }
    }

    async loadAdChildren(dn, expand) {
        const key = (dn || '').toLowerCase();
        if (!key) return;
        this.state.adLoading[key] = true;
        try {
            const result = await this.orm.call(
                'myschool.object.browser', 'ad_browse_dn',
                [this.state.adActiveConfigId, dn]);
            if (result.error) {
                this.state.adError = result.error;
                return;
            }
            this.state.adError = null;
            if (result.node) {
                this.state.adTreeNodes[key] = result.node;
            }
            this.state.adChildren[key] = (result.children || [])
                .map(c => c.dn);
            // Cache de child-nodes
            for (const c of result.children || []) {
                this.state.adTreeNodes[c.dn.toLowerCase()] = c;
            }
            if (expand) {
                this.state.adExpanded[key] = true;
            }
        } catch (e) {
            this.state.adError = 'AD-browse mislukt: ' + (e?.message || e);
        } finally {
            this.state.adLoading[key] = false;
        }
    }

    async onAdToggleExpand(dn) {
        const key = (dn || '').toLowerCase();
        if (this.state.adExpanded[key]) {
            this.state.adExpanded[key] = false;
            return;
        }
        // Niet gecached? laad eerst de children
        if (!(key in this.state.adChildren)) {
            await this.loadAdChildren(dn, /*expand=*/true);
        } else {
            this.state.adExpanded[key] = true;
        }
    }

    async onAdSelectNode(dn) {
        this.state.adSelectedDn = dn;
        // Zorg dat de full-attrs van deze node geladen zijn (incl. attrs
        // — kindeer-lookups droppen de attrs voor performance).
        const key = (dn || '').toLowerCase();
        const cached = this.state.adTreeNodes[key];
        if (!cached || !cached.attrs) {
            // Trigger volledige load (deze RPC retourneert ook attrs)
            await this.loadAdChildren(dn, /*expand=*/false);
        }
    }

    get adRootChildren() {
        const rootKey = (this.state.adRootDn || '').toLowerCase();
        const childDns = this.state.adChildren[rootKey] || [];
        return childDns.map(dn => this.state.adTreeNodes[dn.toLowerCase()])
                       .filter(Boolean);
    }

    adChildrenOf(dn) {
        const key = (dn || '').toLowerCase();
        const childDns = this.state.adChildren[key] || [];
        return childDns.map(d => this.state.adTreeNodes[d.toLowerCase()])
                       .filter(Boolean);
    }

    get flatAdNodes() {
        // Plat depth-first traversal van de zichtbare AD-tree. Resultaat:
        // [{node, depth}]. Niet-uitgeklapte OUs hun children worden
        // overgeslagen. Vervangt de recursieve t-call die OWL2 niet
        // betrouwbaar resolved binnen genest template.
        const out = [];
        const visit = (dnList, depth) => {
            for (const dn of dnList) {
                const node = this.state.adTreeNodes[dn.toLowerCase()];
                if (!node) continue;
                out.push({ node, depth });
                const key = dn.toLowerCase();
                if (node.kind === 'ou' && this.state.adExpanded[key]) {
                    const childDns = this.state.adChildren[key] || [];
                    visit(childDns, depth + 1);
                }
            }
        };
        const rootKey = (this.state.adRootDn || '').toLowerCase();
        visit(this.state.adChildren[rootKey] || [], 1);
        return out;
    }

    get adSelectedNode() {
        if (!this.state.adSelectedDn) return null;
        const key = this.state.adSelectedDn.toLowerCase();
        return this.state.adTreeNodes[key] || null;
    }
    
    // Selection mode
    toggleSelectionMode() {
        this.state.selectionMode = !this.state.selectionMode;
        if (!this.state.selectionMode) {
            this.state.selectedIds = {};
        }
    }
    
    onToggleSelect(node, selected) {
        const key = `${node.type}_${node.id}`;
        this.state.selectedIds[key] = selected;
    }
    
    clearSelection() {
        this.state.selectedIds = {};
    }
    
    // Helpers: how many items are in each multi-select set, and is the
    // right-clicked node part of it? The context menu uses both to decide
    // whether to surface a "Delete N selected" entry.
    _treeBulkInfo(node) {
        const ids = this.state.selectedIds || {};
        const keys = Object.keys(ids).filter(k => ids[k]);
        const inSet = !!ids[`${node.type}_${node.id}`];
        return { count: keys.length, inSet };
    }

    _memberBulkInfo(node) {
        const ids = this.state.selectedMemberIds || {};
        const keys = Object.keys(ids).filter(k => ids[k]);
        const inSet = !!ids[`${node.type}_${node.id}`];
        return { count: keys.length, inSet };
    }

    // Context Menu
    onContextMenu(ev, node) {
        const tb = this._treeBulkInfo(node);
        this.state.contextMenu = {
            x: ev.clientX,
            y: ev.clientY,
            node: node,
            bulkSource: tb.inSet && tb.count > 1 ? 'tree' : null,
            bulkCount: tb.inSet && tb.count > 1 ? tb.count : 0,
        };
        this.state.activeNode = node;
    }

    // Context Menu for members panel - doesn't change activeNode to preserve members list
    onMemberContextMenu(ev, node) {
        const mb = this._memberBulkInfo(node);
        this.state.contextMenu = {
            x: ev.clientX,
            y: ev.clientY,
            node: node,
            bulkSource: mb.inSet && mb.count > 1 ? 'members' : null,
            bulkCount: mb.inSet && mb.count > 1 ? mb.count : 0,
        };
        // Don't change activeNode - keep the org selected so members panel stays visible
    }

    // Bridge: hover-action button on a member row dispatches an action
    // key that matches one of the cases in onContextMenuAction. We just
    // forward the call; no special handling needed.
    onMemberRowAction(action, node) {
        return this.onContextMenuAction(action, node);
    }

    // Right-click on the empty area of the members panel → context menu
    // scoped to the parent org. Reuses onContextMenu (the same one tree
    // nodes use), so all org-level actions are available.
    onMembersPanelContextMenu(ev, orgNode) {
        return this.onContextMenu(ev, orgNode);
    }

    // Bridge: kebab button opens the context menu at the button's
    // position. Same as right-click on the row.
    onMemberRowKebab(ev, node) {
        return this.onMemberContextMenu(ev, node);
    }

    // Klik op het icoon vóór een naam in de tree → open de slide-over
    // met details. Aparte hitbox van onRowClick zodat een gebruiker
    // tegelijk kan drillen (rij-klik) en bekijken (icoon-klik) zonder
    // dubbelklikken te hoeven.
    onTreeIconClick(node) {
        if (!node) return;
        if (this.state.slideOverNode) this.closeSlideOver();
        return this._openSlideOver(node);
    }

    // Klik op de oog-knop in een member-row → open slide-over voor zowel
    // persons als sub-orgs / persongroups. Anders dan de dubbelklik-flow
    // (`onMemberOpenDetails`) drilt deze NOOIT door — het is een snelle
    // 1-klik shortcut naar de details.
    onMemberShowDetails(node) {
        if (!node) return;
        if (this.state.slideOverNode) this.closeSlideOver();
        return this._openSlideOver(node);
    }

    // Open the slide-over for a member (double-click on row).
    // For persongroup/sub-org members: drilling-in is more useful than
    // showing details (single-click does the same — making both gestures
    // consistent). Use the "Details" button in the members header to see
    // info about the current persongroup instead.
    onMemberOpenDetails(node) {
        if (node && (node.type === 'persongroup' || node.type === 'org')) {
            if (this.state.slideOverNode) this.closeSlideOver();
            const treeNode = this.findOrgNodeById(node.id) || {
                ...node,
                type: 'org',
                model: node.model || 'myschool.org',
            };
            this.expandPathToOrg(node.id);
            return this._loadOrgContext(treeNode, { setActive: true });
        }
        return this._openSlideOver(node);
    }

    // Open the slide-over for the currently-selected org (header button).
    onOpenOrgDetails() {
        const org = this.state.activeOrgNode;
        if (org) this._openSlideOver(org);
    }

    async _openSlideOver(node) {
        if (!node) return;
        this.state.slideOverNode = node;
        // Load CI relations for orgs (also persongroups have org_type_id).
        const isOrgLike = node.type === 'org' || node.type === 'persongroup';
        if (isOrgLike) {
            this.state.slideOverCiLoading = true;
            this.state.slideOverCiRelations = [];
            try {
                const ciRelations = await this.orm.call(
                    'myschool.object.browser',
                    'get_ci_relations_for_org',
                    [node.id]
                );
                this.state.slideOverCiRelations = ciRelations || [];
            } catch (e) {
                console.warn('Could not load CI relations:', e);
                this.state.slideOverCiRelations = [];
            }
            this.state.slideOverCiLoading = false;
        } else {
            this.state.slideOverCiRelations = [];
        }
    }

    closeSlideOver() {
        this.state.slideOverNode = null;
        this.state.slideOverCiRelations = [];
    }

    // Quick-action click inside the slide-over → reuse the canonical
    // context-menu-action dispatcher.
    onSlideOverAction(action, node) {
        this.onContextMenuAction(action, node || this.state.slideOverNode);
    }

    // "Open form" link inside the slide-over header.
    onSlideOverOpenRecord(node) {
        const n = node || this.state.slideOverNode;
        if (n && n.model && n.id) {
            this.openRecord(n.model, n.id);
        }
    }

    // "Add Configuration Item" button on the empty-state of the Config tab.
    openAddCiForActiveOrg() {
        const n = this.state.slideOverNode;
        if (n && (n.type === 'org' || n.type === 'persongroup')) {
            this.openAddCiWizard(n.id);
        }
    }
    
    onCloseContextMenu() {
        this.state.contextMenu = null;
    }
    
    onDocumentClick(ev) {
        if (this.state.contextMenu) {
            this.state.contextMenu = null;
        }
    }
    
    async onContextMenuAction(action, node) {
        switch (action) {
            case 'open':
                this.openRecord(node.model, node.id);
                break;
            case 'create_person':
                this.openCreatePersonWizard(node);
                break;
            case 'add_child_org':
                this.openAddChildOrgWizard(node);
                break;
            case 'create_persongroup':
                this.openCreatePersongroupWizard(node);
                break;
            case 'manage_members':
                this.openManagePersongroupMembersWizard(node);
                break;
            case 'configuration':
                this.openManageCiWizard(node);
                break;
            case 'manage_org_roles':
                this.openManageOrgRolesWizard(node);
                break;
            case 'manage_person_roles':
                this.openManagePersonRolesWizard(node);
                break;
            case 'move_org':
                this.openMoveOrgWizard(node);
                break;
            case 'move_person':
                this.openMovePersonWizard(node);
                break;
            case 'remove_from_org':
                await this.removePersonFromOrg(node);
                break;
            case 'deactivate_person':
                await this.deactivatePerson(node);
                break;
            case 'delete_person':
                await this.deletePerson(node);
                break;
            case 'delete':
                await this.deleteNode(node);
                break;
            case 'bulk_delete':
                if (this.state.contextMenu && this.state.contextMenu.bulkSource === 'members') {
                    await this.bulkDeleteMembers();
                } else {
                    await this.bulkDelete();
                }
                break;
        }
    }
    
    // Wizards
    openCreatePersonWizard(orgNode) {
        const orgId = orgNode.id;
        // Store context for when dialogs close
        this._pendingRefreshOrgId = orgId;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.create.person.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
        }, {
            onClose: async () => {
                const refreshOrgId = this._pendingRefreshOrgId;
                this._pendingRefreshOrgId = null;
                await this._refreshTreeAndMembers(refreshOrgId);
            }
        });
    }

    openAddChildOrgWizard(orgNode) {
        const orgId = orgNode.id;
        // Store context for when dialogs close
        this._pendingRefreshOrgId = orgId;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.child.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_parent_org_id: orgNode.id,
            },
        }, {
            onClose: async () => {
                const refreshOrgId = this._pendingRefreshOrgId;
                this._pendingRefreshOrgId = null;
                await this._refreshTreeAndMembers(refreshOrgId);
            }
        });
    }

    openCreatePersongroupWizard(orgNode) {
        const orgId = orgNode.id;
        this._pendingRefreshOrgId = orgId;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.create.persongroup.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_parent_org_id: orgNode.id,
            },
        }, {
            onClose: async () => {
                const refreshOrgId = this._pendingRefreshOrgId;
                this._pendingRefreshOrgId = null;
                await this._refreshTreeAndMembers(refreshOrgId);
            }
        });
    }

    openManagePersongroupMembersWizard(node) {
        const orgId = node.org_id || node.id;
        if (orgId) this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'myschool_persongroup_member_browser',
            target: 'new',
            params: {
                persongroup_id: node.id,
            },
            context: {
                default_persongroup_id: node.id,
            },
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    openMoveOrgWizard(orgNode) {
        const orgId = orgNode.id;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.move.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
                default_org_name: orgNode.name_tree || orgNode.name,
            },
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    openMovePersonWizard(personNode) {
        const orgId = personNode.org_id;
        if (orgId) this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.move.person.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_id: personNode.id,
                default_person_name: personNode.name,
            },
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    async openManageOrgRolesWizard(orgNode) {
        const orgId = orgNode.id;
        this.expandPathToOrg(orgId);
        const action = await this.orm.call(
            'myschool.manage.org.roles.wizard',
            'action_open',
            [orgNode.id, orgNode.name_tree || orgNode.name],
        );
        this.action.doAction(action, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    async openManagePersonRolesWizard(personNode) {
        const orgId = personNode.org_id;
        if (orgId) this.expandPathToOrg(orgId);
        const action = await this.orm.call(
            'myschool.manage.person.roles.wizard',
            'action_open',
            [personNode.id, personNode.name],
        );
        this.action.doAction(action, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    openManageCiWizard(orgNode) {
        const orgId = orgNode.id;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.manage.ci.relations.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }

    openLinkRoleWizard(orgNode) {
        const orgId = orgNode.id;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.link.role.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
        }, {
            onClose: async () => {
                await this._refreshTreeAndMembers(orgId);
            }
        });
    }
    
    openRoleRelationsManager() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.role.relations.manager',
            views: [[false, 'form']],
            target: 'new',
        });
    }
    
    openAddCiWizard(orgId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.ci.relation.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgId,
            },
        });
    }
    
    openEditCiWizard(ciRelationId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.edit.ci.relation.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_ci_relation_id: ciRelationId,
            },
        });
    }
    
    openRemoveCiWizard(ciRelationId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.remove.ci.relation.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_ci_relation_id: ciRelationId,
            },
        });
    }
    
    // Role Relations Manager methods
    openAddSRBRWizard() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.srbr.wizard',
            views: [[false, 'form']],
            target: 'new',
        });
    }
    
    openAddBRSOWizard() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.brso.wizard',
            views: [[false, 'form']],
            target: 'new',
        });
    }
    
    openAddPPBRSOWizard() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.ppbrso.wizard',
            views: [[false, 'form']],
            target: 'new',
        });
    }
    
    async viewSRBRRelations() {
        try {
            const relTypeId = await this._getRelationTypeId('SRBR');
            let domain = [['is_active', '=', true]];
            if (relTypeId) {
                domain.unshift(['proprelation_type_id', '=', relTypeId]);
            }
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'SRBR Relations',
                res_model: 'myschool.proprelation',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                target: 'current',
                context: {},
            });
        } catch (error) {
            console.error('Error viewing SRBR relations:', error);
            this.notification.add('Error opening relations view', { type: 'danger' });
        }
    }
    
    async viewBRSORelations() {
        try {
            const relTypeId = await this._getRelationTypeId('BRSO');
            let domain = [['is_active', '=', true]];
            if (relTypeId) {
                domain.unshift(['proprelation_type_id', '=', relTypeId]);
            }
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'BRSO Relations',
                res_model: 'myschool.proprelation',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                target: 'current',
                context: {},
            });
        } catch (error) {
            console.error('Error viewing BRSO relations:', error);
            this.notification.add('Error opening relations view', { type: 'danger' });
        }
    }
    
    async viewPPBRSORelations() {
        try {
            const relTypeId = await this._getRelationTypeId('PPBRSO');
            let domain = [['is_active', '=', true]];
            if (relTypeId) {
                domain.unshift(['proprelation_type_id', '=', relTypeId]);
            }
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'PPBRSO Relations',
                res_model: 'myschool.proprelation',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                target: 'current',
                context: {},
            });
        } catch (error) {
            console.error('Error viewing PPBRSO relations:', error);
            this.notification.add('Error opening relations view', { type: 'danger' });
        }
    }
    
    async _getRelationTypeId(typeName) {
        try {
            const result = await this.orm.searchRead(
                'myschool.proprelation.type',
                [['name', '=', typeName]],
                ['id'],
                { limit: 1 }
            );
            return (result && result.length > 0) ? result[0].id : null;
        } catch (error) {
            console.warn('Could not find relation type:', typeName, error);
            return null;
        }
    }
    
    async removePersonFromOrg(personNode) {
        if (!confirm(`Remove ${personNode.name} from this organization?`)) {
            return;
        }
        
        try {
            await this.orm.call(
                'myschool.object.browser',
                'remove_person_from_org',
                [personNode.id, personNode.org_id]
            );
            this.notification.add('Person removed from organization', { type: 'success' });
            const orgId = personNode.org_id;
            this.state.activeNode = null;
            await this._refreshTreeAndMembers(orgId);
        } catch (error) {
            this.notification.add('Error removing person', { type: 'danger' });
        }
    }
    
    async deactivatePerson(personNode) {
        if (!confirm(`Deactivate ${personNode.name}? This will set the person and all related proprelations to inactive.`)) {
            return;
        }
        
        const orgId = personNode.org_id;
        try {
            await this.orm.call(
                'myschool.object.browser',
                'deactivate_person',
                [personNode.id]
            );
            this.notification.add('Person deactivated successfully', { type: 'success' });
            this.state.activeNode = null;
            await this._refreshTreeAndMembers(orgId);
        } catch (error) {
            let message = 'Error deactivating person';
            if (error.data && error.data.message) {
                message = error.data.message;
            } else if (error.data && error.data.arguments && error.data.arguments[0]) {
                message = error.data.arguments[0];
            }
            this.notification.add(message, { type: 'danger' });
        }
    }
    
    async deletePerson(personNode) {
        if (!confirm(`Delete ${personNode.name}? This will permanently delete the person and all related proprelations.`)) {
            return;
        }
        
        const orgId = personNode.org_id;
        try {
            await this.orm.call(
                'myschool.object.browser',
                'delete_person',
                [personNode.id]
            );
            this.notification.add('Person deleted successfully', { type: 'success' });
            this.state.activeNode = null;
            await this._refreshTreeAndMembers(orgId);
        } catch (error) {
            let message = 'Error deleting person';
            if (error.data && error.data.message) {
                message = error.data.message;
            } else if (error.data && error.data.arguments && error.data.arguments[0]) {
                message = error.data.arguments[0];
            }
            this.notification.add(message, { type: 'danger' });
        }
    }
    
    async deleteNode(node) {
        if (!confirm(`Delete ${node.name}?`)) {
            return;
        }
        
        // Get parent org id for org nodes, or org_id for person nodes
        const orgId = node.type === 'org' ? node.parent_id : node.org_id;
        
        try {
            await this.orm.call(
                'myschool.object.browser',
                'delete_node',
                [node.type, node.id]
            );
            this.notification.add('Deleted successfully', { type: 'success' });
            this.state.activeNode = null;
            await this._refreshTreeAndMembers(orgId);
        } catch (error) {
            // Extract the error message from various possible locations in Odoo's error structure
            let message = 'Error deleting';
            if (error.data && error.data.message) {
                message = error.data.message;
            } else if (error.message && error.message.data && error.message.data.message) {
                message = error.message.data.message;
            } else if (error.message && typeof error.message === 'string') {
                message = error.message;
            } else if (error.data && error.data.arguments && error.data.arguments[0]) {
                message = error.data.arguments[0];
            }
            
            // For UserError, the message is often in error.data.arguments
            if (error.data && error.data.name === 'odoo.exceptions.UserError') {
                message = error.data.arguments ? error.data.arguments[0] : message;
            }
            
            // Show as a dialog for longer messages, notification for short ones
            if (message.length > 100 || message.includes('\n')) {
                alert(message);
            } else {
                this.notification.add(message, { type: 'danger', sticky: true });
            }
        }
    }
    
    // Drag and Drop
    onDragStart(node) {
        this.state.draggedNode = node;
    }

    // Drag from members pane → tree (or tree-cross-pane). Same drop target
    // logic as tree drag (an org node, handled by onDrop).
    onMemberDragStart(node) {
        this.state.draggedNode = node;
    }

    // Jump to a breadcrumb segment. Org segments select the org (loading
    // its members context); a persongroup segment is treated as org with
    // its members; person segments select the person (members pane keeps
    // showing the persons's parent org).
    async onBreadcrumbClick(seg) {
        if (seg.type === 'home') {
            // Reset naar geen selectie — breadcrumb toont enkel "Home"
            // en de members-pane keert terug naar de welkom-staat.
            this.state.activeNode = null;
            this.state.activeOrgNode = null;
            return;
        }
        if (seg.type === 'org' || seg.type === 'persongroup') {
            const orgNode = this.findOrgNodeById(seg.id);
            if (orgNode) {
                this.expandPathToOrg(seg.id);
                await this.onSelectNode(orgNode);
            } else {
                await this.onSelectNode({
                    id: seg.id, type: 'org',
                    model: seg.model || 'myschool.org',
                    name: seg.name,
                });
            }
            return;
        }
        if (seg.type === 'person') {
            // Already showing this person if it's the last segment — no-op.
            await this.onSelectNode({
                id: seg.id, type: 'person',
                model: seg.model || 'myschool.person',
                name: seg.name,
                org_id: this.state.activeOrgNode?.id,
            });
        }
    }

    onMemberDragEnd() {
        // dragend may fire before drop on some browsers; the actual drop
        // sets this back to false anyway. Keep here as cleanup if no drop.
        // (Race window is negligible; onDrop's finally branch wins.)
        if (this.state.draggedNode) {
            this.state.draggedNode = false;
        }
    }
    
    onDragOver(ev, node) {
        // Visual feedback handled in TreeNode
    }
    
    async onDrop(targetNode) {
        const draggedNode = this.state.draggedNode;
        if (!draggedNode || !targetNode) return;
        
        if (targetNode.type !== 'org') {
            this.notification.add('Can only drop on organizations', { type: 'warning' });
            return;
        }
        
        try {
            if (draggedNode.type === 'org') {
                await this.orm.call(
                    'myschool.object.browser',
                    'move_org',
                    [draggedNode.id, targetNode.id]
                );
                this.notification.add(`Moved ${draggedNode.name} under ${targetNode.name}`, { type: 'success' });
            } else if (draggedNode.type === 'person') {
                await this.orm.call(
                    'myschool.object.browser',
                    'move_person_to_org',
                    [draggedNode.id, targetNode.id]
                );
                this.notification.add(`Moved ${draggedNode.name} to ${targetNode.name}`, { type: 'success' });
            }
            // Refresh both source (current org) and target view.
            await this._refreshTreeAndMembers(targetNode.id);
        } catch (error) {
            console.error('Drop error:', error);
            this.notification.add('Error moving item', { type: 'danger' });
        } finally {
            this.state.draggedNode = false;
        }
    }
    
    // Persons selected in the members pane (selectedMemberIds keys are
    // type_id strings; type is 'person' or 'persongroup'). Returns a
    // simple list of { id, type } records.
    getMemberSelectedByType(type) {
        const ids = this.state.selectedMemberIds || {};
        return Object.keys(ids)
            .filter(k => ids[k])
            .map(k => {
                const idx = k.indexOf('_');
                return { type: k.slice(0, idx), id: parseInt(k.slice(idx + 1)) };
            })
            .filter(r => r.type === type);
    }

    // Bulk Actions
    async bulkAssignRole() {
        // Persons can be selected either from members pane or, legacy, from tree.
        const fromTree = this.getSelectedByType('person');
        const fromMembers = this.getMemberSelectedByType('person');
        const byId = new Map();
        for (const p of fromTree) byId.set(p.id, p);
        for (const p of fromMembers) if (!byId.has(p.id)) byId.set(p.id, p);
        const selectedPersons = Array.from(byId.values());
        if (selectedPersons.length === 0) {
            this.notification.add('Select at least one person', { type: 'warning' });
            return;
        }

        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.bulk.assign.role.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_ids: selectedPersons.map(p => p.id),
            },
        });
    }

    async bulkMoveToOrg() {
        // Orgs come from the tree-selection; persons can come from tree
        // (legacy) or the members pane.
        const persons = [
            ...this.getSelectedByType('person'),
            ...this.getMemberSelectedByType('person'),
        ];
        const orgs = this.getSelectedByType('org');
        // De-dup persons by id (tree+members overlap is unlikely but harmless).
        const seen = new Set();
        const selected = [];
        for (const r of [...orgs, ...persons]) {
            const key = `${r.type}_${r.id}`;
            if (seen.has(key)) continue;
            seen.add(key);
            selected.push(r);
        }
        if (selected.length === 0) {
            this.notification.add('Select at least one item', { type: 'warning' });
            return;
        }

        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.bulk.move.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_item_ids: JSON.stringify(selected.map(s => ({ type: s.type, id: s.id }))),
            },
        });
    }

    // Combined delete that handles whichever selection sets have items.
    // Replaces the old `bulkDelete` button (still kept for tree-only path).
    async bulkDeleteAll() {
        const hasTree = this.selectedCount > 0;
        const hasMembers = this.memberSelectedCount > 0;
        if (!hasTree && !hasMembers) return;
        if (hasTree && hasMembers) {
            if (!confirm(`Delete ${this.totalSelectedCount} selected items (tree + members)?`)) return;
            await this._deleteSelectedSet(this.state.selectedIds);
            await this._deleteSelectedSet(this.state.selectedMemberIds);
            this.state.selectedIds = {};
            this.state.selectedMemberIds = {};
            this.state.activeNode = null;
            await this._refreshTreeAndMembers(this.state.activeOrgNode?.id);
            return;
        }
        if (hasTree) return this.bulkDelete();
        return this.bulkDeleteMembers();
    }

    async _deleteSelectedSet(idsObj) {
        const items = Object.keys(idsObj)
            .filter(k => idsObj[k])
            .map(k => {
                const idx = k.indexOf('_');
                return { type: k.slice(0, idx), id: parseInt(k.slice(idx + 1)) };
            });
        for (const item of items) {
            try {
                await this.orm.call(
                    'myschool.object.browser',
                    'delete_node',
                    [item.type, item.id]
                );
            } catch (error) {
                console.error('Error deleting:', item, error);
            }
        }
    }

    clearAllSelections() {
        this.state.selectedIds = {};
        this.state.selectedMemberIds = {};
    }
    
    async bulkDelete() {
        const count = this.selectedCount;
        if (count === 0) return;

        if (!confirm(`Delete ${count} selected items?`)) {
            return;
        }

        const selected = Object.keys(this.state.selectedIds)
            .filter(k => this.state.selectedIds[k])
            .map(k => {
                const [type, id] = k.split('_');
                return { type, id: parseInt(id) };
            });

        for (const item of selected) {
            try {
                await this.orm.call(
                    'myschool.object.browser',
                    'delete_node',
                    [item.type, item.id]
                );
            } catch (error) {
                console.error('Error deleting:', error);
            }
        }

        this.notification.add(`Deleted ${selected.length} items`, { type: 'success' });
        this.state.selectedIds = {};
        this.state.activeNode = null;
        await this._refreshTreeAndMembers(this.state.activeOrgNode?.id);
    }

    async bulkDeleteMembers() {
        // Same as bulkDelete, but works on ``selectedMemberIds`` (the
        // ctrl/shift+click selection in the members panel). Members
        // are persons or persongroups; ``delete_node`` understands both
        // type strings.
        const ids = this.state.selectedMemberIds || {};
        const selected = Object.keys(ids)
            .filter(k => ids[k])
            .map(k => {
                const idx = k.indexOf('_');
                const type = k.slice(0, idx);
                const id = parseInt(k.slice(idx + 1));
                return { type, id };
            });
        if (!selected.length) return;

        if (!confirm(`Verwijder ${selected.length} geselecteerde items? Dit is onomkeerbaar.`)) {
            return;
        }

        const orgId = this.state.activeOrgNode?.id;
        let ok = 0;
        const errors = [];
        for (const item of selected) {
            try {
                await this.orm.call(
                    'myschool.object.browser',
                    'delete_node',
                    [item.type, item.id]
                );
                ok += 1;
            } catch (error) {
                let message = '';
                if (error.data && error.data.arguments && error.data.arguments[0]) {
                    message = error.data.arguments[0];
                } else if (error.data && error.data.message) {
                    message = error.data.message;
                } else if (error.message) {
                    message = error.message;
                }
                errors.push(`${item.type}#${item.id}: ${message || 'unknown error'}`);
            }
        }

        this.state.selectedMemberIds = {};
        this.state.activeNode = null;
        await this._refreshTreeAndMembers(orgId);

        if (errors.length) {
            const detail = errors.slice(0, 5).join('\n')
                + (errors.length > 5 ? `\n…en ${errors.length - 5} meer` : '');
            this.notification.add(
                `${ok}/${selected.length} verwijderd. Fouten:\n${detail}`,
                { type: 'warning', sticky: true });
        } else {
            this.notification.add(
                `${ok} item(s) verwijderd`, { type: 'success' });
        }
    }
    
    getSelectedByType(type) {
        const result = [];
        const findNodes = (nodes) => {
            if (!nodes || !Array.isArray(nodes)) return;
            for (const node of nodes) {
                const key = `${node.type}_${node.id}`;
                if (node.type === type && this.state.selectedIds[key]) {
                    result.push(node);
                }
                if (node.children) findNodes(node.children);
                if (node.persons) findNodes(node.persons);
            }
        };
        findNodes(this.state.treeData?.organizations || []);
        return result;
    }
}

// Register the client action
registry.category("actions").add("myschool_object_browser", ObjectBrowserClient);
