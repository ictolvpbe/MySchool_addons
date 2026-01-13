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
        expandedIds: { type: Object, optional: true },
        onToggleExpand: { type: Function, optional: true },
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
    
    onManageOrgRolesClick() {
        if (this.props.onAction) {
            this.props.onAction('manage_org_roles');
        }
    }
    
    onDeleteOrgClick() {
        if (this.props.onAction) {
            this.props.onAction('delete');
        }
    }
    
    onManagePersonRolesClick() {
        if (this.props.onAction) {
            this.props.onAction('manage_person_roles');
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
        onMemberContextMenu: { type: Function, optional: true },
        onMemberSelect: { type: Function, optional: true },
        onPasswordClick: { type: Function, optional: true },
        selectedMemberId: { type: Number, optional: true },
        selectedMemberType: { type: String, optional: true },
    };
    
    setup() {
        this.state = useState({
            filterText: '',
        });
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
            // Create a node object and select it to show in details panel
            const node = {
                id: id,
                name: name,
                type: type,
                model: model,
                org_id: this.props.node?.id,
            };
            this.props.onMemberSelect(node);
        }
    }
    
    onMemberContextMenu(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        
        const model = ev.currentTarget.dataset.model;
        const id = parseInt(ev.currentTarget.dataset.id);
        const name = ev.currentTarget.dataset.name;
        const type = ev.currentTarget.dataset.type;
        
        if (this.props.onMemberContextMenu && id) {
            // Create a node object for the context menu
            const node = {
                id: id,
                name: name,
                type: type,
                model: model,
                org_id: this.props.node?.id,  // Parent org for person context
            };
            this.props.onMemberContextMenu(ev, node);
        }
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
            items.push({ action: 'manage_org_roles', label: 'Roles', iconClass: 'fa fa-id-badge' });
            items.push({ action: 'configuration', label: 'Configuration', iconClass: 'fa fa-sliders' });
            items.push({ divider: true });
            items.push({ action: 'move_org', label: 'Move Organization', iconClass: 'fa fa-arrows' });
            items.push({ divider: true });
            items.push({ action: 'delete', label: 'Delete', iconClass: 'fa fa-trash', danger: true });
        } else if (node.type === 'person') {
            items.push({ action: 'open', label: 'Properties', iconClass: 'fa fa-cog' });
            items.push({ divider: true });
            items.push({ action: 'manage_person_roles', label: 'Roles', iconClass: 'fa fa-id-badge' });
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
            globalSearchText: '',
            globalSearchResults: [],
            showInactive: false,
            showAdministrative: false,
            selectionMode: false,
            selectedIds: {},
            expandedIds: {},
            contextMenu: null,
            draggedNode: null,
            activeNode: null,
            activeOrgNode: null,  // Keep track of selected org for members panel
            activeTab: 'orgs',  // 'orgs' or 'roles'
            membersData: { persons: [], persongroups: [] },
            membersLoading: false,
        });
        
        // Bind methods that are passed as props
        this.onSelectNode = this.onSelectNode.bind(this);
        this.onContextMenu = this.onContextMenu.bind(this);
        this.onMemberContextMenu = this.onMemberContextMenu.bind(this);
        this.onMemberSelect = this.onMemberSelect.bind(this);
        this.onPasswordClick = this.onPasswordClick.bind(this);
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
        this.onToggleExpand = this.onToggleExpand.bind(this);
        this.onGlobalSearchInput = this.onGlobalSearchInput.bind(this);
        this.onGlobalSearchKeydown = this.onGlobalSearchKeydown.bind(this);
        this.onGlobalSearchResultClick = this.onGlobalSearchResultClick.bind(this);
        
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
    
    // Node selection for details panel
    async onSelectNode(node) {
        this.state.activeNode = node;
        
        console.log('onSelectNode called with node:', node);
        
        // Load CI relations and members for orgs
        if (node.type === 'org') {
            // Track this org for members panel
            this.state.activeOrgNode = node;
            this.state.membersData = { persons: [], persongroups: [] };
            
            // Load CI relations
            try {
                const ciRelations = await this.orm.call(
                    'myschool.object.browser',
                    'get_ci_relations_for_org',
                    [node.id]
                );
                this.state.activeNode = { ...node, ciRelations: ciRelations };
                this.state.activeOrgNode = { ...node, ciRelations: ciRelations };
            } catch (error) {
                console.warn('Could not load CI relations:', error);
                this.state.activeNode = { ...node, ciRelations: [] };
                this.state.activeOrgNode = { ...node, ciRelations: [] };
            }
            
            // Load members (persons and persongroups)
            this.state.membersLoading = true;
            try {
                console.log('Calling get_members_for_org with org_id:', node.id);
                const membersData = await this.orm.call(
                    'myschool.object.browser',
                    'get_members_for_org',
                    [node.id]
                );
                console.log('get_members_for_org returned:', membersData);
                this.state.membersData = membersData || { persons: [], persongroups: [] };
                console.log('membersData set to:', this.state.membersData);
            } catch (error) {
                console.error('Could not load members:', error);
                this.state.membersData = { persons: [], persongroups: [] };
            }
            this.state.membersLoading = false;
        }
        // For persons, don't clear members data - keep showing the org's members
    }
    
    // Member selection from members panel - shows details without clearing members
    onMemberSelect(node) {
        this.state.activeNode = node;
        // Don't change activeOrgNode or membersData - keep members panel showing
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
                await this.loadData();
                if (activeOrgId) {
                    this.expandPathToOrg(activeOrgId);
                }
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
                const activeOrgId = this.state.activeOrgNode?.id;
                await this.loadData();
                if (activeOrgId) {
                    this.expandPathToOrg(activeOrgId);
                }
            }
        });
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
    
    // Context Menu for members panel - doesn't change activeNode to preserve members list
    onMemberContextMenu(ev, node) {
        this.state.contextMenu = {
            x: ev.clientX,
            y: ev.clientY,
            node: node,
        };
        // Don't change activeNode - keep the org selected so members panel stays visible
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
                await this.loadData();
                if (refreshOrgId) this.expandPathToOrg(refreshOrgId);
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
                await this.loadData();
                if (refreshOrgId) this.expandPathToOrg(refreshOrgId);
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
                default_org_name: orgNode.name,
            },
        }, {
            onClose: async () => {
                await this.loadData();
                this.expandPathToOrg(orgId);
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
                await this.loadData();
                if (orgId) this.expandPathToOrg(orgId);
            }
        });
    }
    
    openManageOrgRolesWizard(orgNode) {
        const orgId = orgNode.id;
        this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.manage.org.roles.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_org_id: orgNode.id,
                default_org_name: orgNode.name,
            },
        }, {
            onClose: async () => {
                await this.loadData();
                this.expandPathToOrg(orgId);
            }
        });
    }
    
    openManagePersonRolesWizard(personNode) {
        const orgId = personNode.org_id;
        if (orgId) this.expandPathToOrg(orgId);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'myschool.manage.person.roles.wizard',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_person_id: personNode.id,
                default_person_name: personNode.name,
            },
        }, {
            onClose: async () => {
                await this.loadData();
                if (orgId) this.expandPathToOrg(orgId);
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
                await this.loadData();
                this.expandPathToOrg(orgId);
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
                await this.loadData();
                this.expandPathToOrg(orgId);
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
            await this.loadData();
            if (orgId) this.expandPathToOrg(orgId);
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
            await this.loadData();
            if (orgId) this.expandPathToOrg(orgId);
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
            await this.loadData();
            if (orgId) this.expandPathToOrg(orgId);
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
            await this.loadData();
            if (orgId) this.expandPathToOrg(orgId);
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
