/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

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
        draggedNode: { type: Object, optional: true },
    };
    
    setup() {
        this.state = useState({
            expanded: (this.props.level || 0) === 0,
            dragOver: false,
        });
    }
    
    get hasChildren() {
        const node = this.props.node;
        return (node.children && node.children.length > 0) || 
               (node.persons && node.persons.length > 0);
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
        this.state.expanded = !this.state.expanded;
    }
    
    onRowClick(ev) {
        ev.stopPropagation();
        if (this.props.onSelectNode) {
            this.props.onSelectNode(this.props.node);
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
        node: { type: Object, optional: true },
        onAction: { type: Function, optional: true },
        onOpenRecord: { type: Function, optional: true },
        onEditCi: { type: Function, optional: true },
        onRemoveCi: { type: Function, optional: true },
    };
    
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
    
    onConfigurationClick() {
        if (this.props.onAction) {
            this.props.onAction('configuration');
        }
    }
    
    onCreatePersonClick() {
        if (this.props.onAction) {
            this.props.onAction('create_person');
        }
    }
    
    onAddChildOrgClick() {
        if (this.props.onAction) {
            this.props.onAction('add_child_org');
        }
    }
    
    onMoveOrgClick() {
        if (this.props.onAction) {
            this.props.onAction('move_org');
        }
    }
    
    onAssignRoleClick() {
        if (this.props.onAction) {
            this.props.onAction('assign_role');
        }
    }
    
    onMovePersonClick() {
        if (this.props.onAction) {
            this.props.onAction('move_person');
        }
    }
    
    onDeactivatePersonClick() {
        if (this.props.onAction) {
            this.props.onAction('deactivate_person');
        }
    }
    
    onDeletePersonClick() {
        if (this.props.onAction) {
            this.props.onAction('delete_person');
        }
    }
}

/**
 * MembersPanel component - shows persons and persongroups related to selected org
 */
export class MembersPanel extends Component {
    static template = "myschool_admin.MembersPanel";
    static props = {
        node: { type: Object, optional: true },
        members: { type: Object, optional: true },
        loading: { type: Boolean, optional: true },
        onOpenRecord: { type: Function, optional: true },
    };
    
    onMemberClick(ev) {
        const model = ev.currentTarget.dataset.model;
        const id = parseInt(ev.currentTarget.dataset.id);
        if (model && id && this.props.onOpenRecord) {
            this.props.onOpenRecord(model, id);
        }
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
        onAction: Function,
        onClose: Function,
    };
    
    get menuItems() {
        const items = [];
        const node = this.props.node;
        
        if (node.type === 'org') {
            items.push({ action: 'open', label: 'Properties', iconClass: 'fa fa-cog' });
            items.push({ divider: true });
            items.push({ action: 'create_person', label: 'Create Person', iconClass: 'fa fa-user-plus' });
            items.push({ action: 'add_child_org', label: 'Add Sub-Organization', iconClass: 'fa fa-plus-circle' });
            items.push({ divider: true });
            items.push({ action: 'link_role', label: 'Link Role', iconClass: 'fa fa-link' });
            items.push({ action: 'configuration', label: 'Configuration', iconClass: 'fa fa-sliders' });
            items.push({ divider: true });
            items.push({ action: 'move_org', label: 'Move Organization', iconClass: 'fa fa-arrows' });
            items.push({ divider: true });
            items.push({ action: 'delete', label: 'Delete', iconClass: 'fa fa-trash', danger: true });
        } else if (node.type === 'person') {
            items.push({ action: 'open', label: 'Properties', iconClass: 'fa fa-cog' });
            items.push({ divider: true });
            items.push({ action: 'assign_role', label: 'Assign Role', iconClass: 'fa fa-id-badge' });
            items.push({ action: 'move_person', label: 'Move to Org', iconClass: 'fa fa-arrows' });
            items.push({ divider: true });
            items.push({ action: 'deactivate_person', label: 'Deactivate', iconClass: 'fa fa-ban', danger: true });
            items.push({ action: 'delete_person', label: 'Delete', iconClass: 'fa fa-trash', danger: true });
            items.push({ divider: true });
            items.push({ action: 'remove_from_org', label: 'Remove from Org', iconClass: 'fa fa-user-times', danger: true });
        } else if (node.type === 'role') {
            items.push({ action: 'open', label: 'Properties', iconClass: 'fa fa-cog' });
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
    static components = { TreeNode, ContextMenu, DetailsPanel, MembersPanel };
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.containerRef = useRef("container");
        
        this.state = useState({
            loading: true,
            treeData: { organizations: [], roles: [] },
            searchText: '',
            searchResults: [],
            showInactive: false,
            showAdministrative: false,
            selectionMode: false,
            selectedIds: {},
            contextMenu: null,
            draggedNode: null,
            activeNode: null,
            activeTab: 'orgs',  // 'orgs' or 'roles'
            membersData: { persons: [], persongroups: [] },
            membersLoading: false,
        });
        
        // Bind methods that are passed as props
        this.onSelectNode = this.onSelectNode.bind(this);
        this.onContextMenu = this.onContextMenu.bind(this);
        this.onToggleSelect = this.onToggleSelect.bind(this);
        this.onDragStart = this.onDragStart.bind(this);
        this.onDragOver = this.onDragOver.bind(this);
        this.onDrop = this.onDrop.bind(this);
        this.onContextMenuAction = this.onContextMenuAction.bind(this);
        this.onCloseContextMenu = this.onCloseContextMenu.bind(this);
        this.onDetailsAction = this.onDetailsAction.bind(this);
        this.openActiveRecord = this.openActiveRecord.bind(this);
        this.openEditCiWizard = this.openEditCiWizard.bind(this);
        this.openRemoveCiWizard = this.openRemoveCiWizard.bind(this);
        this.onDocumentClick = this.onDocumentClick.bind(this);
        this.openRecord = this.openRecord.bind(this);
        
        onWillStart(async () => {
            await this.loadData();
        });
        
        onMounted(() => {
            document.addEventListener('click', this.onDocumentClick);
        });
        
        onWillUnmount(() => {
            document.removeEventListener('click', this.onDocumentClick);
        });
    }
    
    get selectedCount() {
        return Object.keys(this.state.selectedIds).filter(k => this.state.selectedIds[k]).length;
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
    
    // Node selection for details panel
    async onSelectNode(node) {
        this.state.activeNode = node;
        this.state.membersData = { persons: [], persongroups: [] };
        
        // Load CI relations and members for orgs
        if (node.type === 'org') {
            // Load CI relations
            try {
                const ciRelations = await this.orm.call(
                    'myschool.object.browser',
                    'get_ci_relations_for_org',
                    [node.id]
                );
                this.state.activeNode = { ...node, ciRelations: ciRelations };
            } catch (error) {
                console.warn('Could not load CI relations:', error);
                this.state.activeNode = { ...node, ciRelations: [] };
            }
            
            // Load members (persons and persongroups)
            this.state.membersLoading = true;
            try {
                const membersData = await this.orm.call(
                    'myschool.object.browser',
                    'get_members_for_org',
                    [node.id]
                );
                this.state.membersData = membersData || { persons: [], persongroups: [] };
            } catch (error) {
                console.warn('Could not load members:', error);
                this.state.membersData = { persons: [], persongroups: [] };
            }
            this.state.membersLoading = false;
        }
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
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            res_id: id,
            views: [[false, 'form']],
            target: 'current',
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
    
    // Filters
    onToggleInactive(ev) {
        this.state.showInactive = ev.target.checked;
        this.loadData();
    }
    
    onToggleAdministrative(ev) {
        this.state.showAdministrative = ev.target.checked;
        this.loadData();
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
    
    // Context Menu
    onContextMenu(ev, node) {
        this.state.contextMenu = {
            x: ev.clientX,
            y: ev.clientY,
            node: node,
        };
        this.state.activeNode = node;
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
            case 'configuration':
                this.openManageCiWizard(node);
                break;
            case 'link_role':
                this.openLinkRoleWizard(node);
                break;
            case 'move_org':
                this.openMoveOrgWizard(node);
                break;
            case 'move_person':
                this.openMovePersonWizard(node);
                break;
            case 'assign_role':
                this.openAssignRoleWizard(node);
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
        }
    }
    
    // Wizards
    openCreatePersonWizard(orgNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.create.person.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
        });
    }
    
    openAddChildOrgWizard(orgNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.add.child.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_parent_org_id: orgNode.id,
            },
        });
    }
    
    openMoveOrgWizard(orgNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.move.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
                default_org_name: orgNode.name,
            },
        });
    }
    
    openMovePersonWizard(personNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.move.person.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_id: personNode.id,
                default_person_name: personNode.name,
            },
        });
    }
    
    openAssignRoleWizard(personNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.assign.role.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_id: personNode.id,
                default_person_name: personNode.name,
                default_org_id: personNode.org_id,
            },
        });
    }
    
    openManageCiWizard(orgNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.manage.ci.relations.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
        });
    }
    
    openLinkRoleWizard(orgNode) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.link.role.org.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
            },
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
            this.state.activeNode = null;
            this.loadData();
        } catch (error) {
            this.notification.add('Error removing person', { type: 'danger' });
        }
    }
    
    async deactivatePerson(personNode) {
        if (!confirm(`Deactivate ${personNode.name}? This will set the person and all related proprelations to inactive.`)) {
            return;
        }
        
        try {
            await this.orm.call(
                'myschool.object.browser',
                'deactivate_person',
                [personNode.id]
            );
            this.notification.add('Person deactivated successfully', { type: 'success' });
            this.state.activeNode = null;
            this.loadData();
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
        
        try {
            await this.orm.call(
                'myschool.object.browser',
                'delete_person',
                [personNode.id]
            );
            this.notification.add('Person deleted successfully', { type: 'success' });
            this.state.activeNode = null;
            this.loadData();
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
        
        try {
            await this.orm.call(
                'myschool.object.browser',
                'delete_node',
                [node.type, node.id]
            );
            this.notification.add('Deleted successfully', { type: 'success' });
            this.state.activeNode = null;
            this.loadData();
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
            this.loadData();
        } catch (error) {
            console.error('Drop error:', error);
            this.notification.add('Error moving item', { type: 'danger' });
        } finally {
            this.state.draggedNode = null;
        }
    }
    
    // Bulk Actions
    async bulkAssignRole() {
        const selectedPersons = this.getSelectedByType('person');
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
        const selected = this.getSelectedByType('person').concat(this.getSelectedByType('org'));
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
        this.loadData();
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
