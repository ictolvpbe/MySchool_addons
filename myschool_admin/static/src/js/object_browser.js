/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * TreeNode component - renders a single node with expand/collapse
 */
export class TreeNode extends Component {
    static template = "myschool_admin.TreeNode";
    static components = { TreeNode }; // Self-reference for recursive rendering
    
    static props = {
        node: Object,
        level: { type: Number, optional: true },
        onOpenRecord: { type: Function, optional: true },
    };
    
    setup() {
        this.state = useState({
            expanded: (this.props.level || 0) === 0, // Root nodes start expanded
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
    
    toggle(ev) {
        ev.stopPropagation();
        this.state.expanded = !this.state.expanded;
    }
    
    openRecord(ev) {
        ev.stopPropagation();
        if (this.props.onOpenRecord) {
            this.props.onOpenRecord(this.props.node.model, this.props.node.id);
        }
    }
}

/**
 * ObjectBrowserClient - main client action component
 */
export class ObjectBrowserClient extends Component {
    static template = "myschool_admin.ObjectBrowserClient";
    static components = { TreeNode };
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            loading: true,
            searchText: '',
            showInactive: false,
            treeData: { organizations: [], roles: [] },
            searchResults: [],
            activeTab: 'orgs',
        });
        
        onWillStart(async () => {
            await this.loadTreeData();
        });
    }
    
    async loadTreeData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                'myschool.object.browser',
                'get_tree_data',
                [this.state.searchText, this.state.showInactive]
            );
            this.state.treeData = data;
        } catch (error) {
            console.error('Error loading tree data:', error);
        }
        this.state.loading = false;
    }
    
    async onSearchInput(ev) {
        this.state.searchText = ev.target.value;
        
        // Search persons if text is long enough
        if (this.state.searchText.length >= 2) {
            try {
                const results = await this.orm.call(
                    'myschool.object.browser',
                    'search_persons',
                    [this.state.searchText, 50]
                );
                this.state.searchResults = results;
                if (results.length > 0) {
                    this.state.activeTab = 'search';
                }
            } catch (error) {
                console.error('Search error:', error);
            }
        } else {
            this.state.searchResults = [];
        }
    }
    
    async onRefresh() {
        await this.loadTreeData();
    }
    
    onToggleInactive(ev) {
        this.state.showInactive = ev.target.checked;
        this.loadTreeData();
    }
    
    setTabOrgs() {
        this.state.activeTab = 'orgs';
    }
    
    setTabRoles() {
        this.state.activeTab = 'roles';
    }
    
    setTabSearch() {
        this.state.activeTab = 'search';
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
    
    onOpenRecord(model, id) {
        this.openRecord(model, id);
    }
}

// Register as a client action
registry.category("actions").add("myschool_object_browser", ObjectBrowserClient);
