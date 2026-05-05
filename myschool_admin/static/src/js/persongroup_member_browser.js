/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * OrgTreeNode — recursive tree node used in the right-pane org picker.
 *
 * Each node renders:
 *   - the org name (clickable to expand/collapse, never selectable),
 *   - any direct PERSON-TREE persons as leaf rows (selectable via
 *     checkbox or row-click; supports ctrl/shift multi-select),
 *   - all child orgs recursively.
 */
export class OrgTreeNode extends Component {
    static template = "myschool_admin.PgmbOrgTreeNode";
    static components = { OrgTreeNode };
    static props = {
        node: Object,
        level: { type: Number, optional: true },
        expandedOrgIds: Object,
        selectedPersonIds: Object,
        onToggleExpand: Function,
        onPersonClick: Function,
    };

    get level() { return this.props.level || 0; }
    get childLevel() { return this.level + 1; }

    get isExpanded() {
        const v = this.props.expandedOrgIds[this.props.node.id];
        return v === undefined ? this.level === 0 : v;
    }

    get hasContent() {
        const n = this.props.node;
        return (n.children && n.children.length > 0)
            || (n.persons && n.persons.length > 0);
    }

    toggle() {
        if (this.hasContent) {
            this.props.onToggleExpand(this.props.node.id, !this.isExpanded);
        }
    }

    isPersonSelected(personId) {
        return !!this.props.selectedPersonIds[personId];
    }

    onPersonRowClick(ev, person) {
        ev.stopPropagation();
        this.props.onPersonClick(person, {
            ctrlKey: ev.ctrlKey || ev.metaKey,
            shiftKey: ev.shiftKey,
        });
    }

    onPersonCheckboxChange(ev, person) {
        ev.stopPropagation();
        this.props.onPersonClick(person, { ctrlKey: true, shiftKey: false });
    }
}

/**
 * PersongroupMemberBrowserClient — two-pane group-membership manager.
 */
export class PersongroupMemberBrowserClient extends Component {
    static template = "myschool_admin.PersongroupMemberBrowserClient";
    static components = { OrgTreeNode };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            persongroup: null,           // { id, name, name_tree }
            members: [],                  // [{id, display, ...}, ...]
            tree: [],                     // org tree
            // Left pane state.
            memberFilter: "",
            selectedMemberIds: {},        // { [personId]: true }
            lastClickedMemberId: null,    // for shift-select
            // Right pane state.
            treeFilter: "",
            expandedOrgIds: {},
            selectedPersonIds: {},        // { [personId]: true }
            lastClickedPersonId: null,
            // UI state.
            loading: true,
        });

        // Resolve persongroup_id: priority is action params > context.
        this.persongroupId =
            (this.props.action && this.props.action.params
                && this.props.action.params.persongroup_id)
            || (this.props.action && this.props.action.context
                && this.props.action.context.default_persongroup_id)
            || (this.env.services.action
                && this.env.services.action.currentController
                && this.env.services.action.currentController.props
                && this.env.services.action.currentController.props.context
                && this.env.services.action.currentController.props.context.default_persongroup_id);

        onWillStart(async () => {
            await this.loadData();
        });
    }

    // ----- Data loading -----

    async loadData(treeSearch = "") {
        if (!this.persongroupId) {
            this.notification.add("No persongroup selected", { type: "danger" });
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "myschool.persongroup.member.browser",
                "get_data",
                [this.persongroupId, treeSearch],
            );
            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
            } else {
                this.state.persongroup = data.persongroup;
                this.state.members = data.members || [];
                this.state.tree = data.tree || [];
            }
        } catch (e) {
            console.error("[PGMB] loadData failed", e);
            this.notification.add("Failed to load member data", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // ----- Left pane: members -----

    get filteredMembers() {
        const f = this.state.memberFilter.toLowerCase();
        if (!f) return this.state.members;
        return this.state.members.filter(
            m => m.display.toLowerCase().includes(f)
              || (m.tree_org || '').toLowerCase().includes(f)
              || (m.person_type || '').toLowerCase().includes(f));
    }

    get selectedMemberCount() {
        return Object.keys(this.state.selectedMemberIds)
            .filter(k => this.state.selectedMemberIds[k]).length;
    }

    onMemberFilterInput(ev) { this.state.memberFilter = ev.target.value; }
    clearMemberFilter() { this.state.memberFilter = ""; }

    toggleAllMembers() {
        const visible = this.filteredMembers;
        const allSelected = visible.length > 0
            && visible.every(m => this.state.selectedMemberIds[m.id]);
        const next = { ...this.state.selectedMemberIds };
        for (const m of visible) {
            if (allSelected) delete next[m.id];
            else next[m.id] = true;
        }
        this.state.selectedMemberIds = next;
    }

    onMemberRowClick(ev, member) {
        const next = { ...this.state.selectedMemberIds };
        if (ev.shiftKey && this.state.lastClickedMemberId !== null) {
            // Range-select on the filtered list.
            const list = this.filteredMembers;
            const a = list.findIndex(m => m.id === this.state.lastClickedMemberId);
            const b = list.findIndex(m => m.id === member.id);
            if (a >= 0 && b >= 0) {
                const [lo, hi] = a < b ? [a, b] : [b, a];
                for (let i = lo; i <= hi; i++) next[list[i].id] = true;
            } else {
                next[member.id] = !next[member.id];
            }
        } else if (ev.ctrlKey || ev.metaKey) {
            if (next[member.id]) delete next[member.id];
            else next[member.id] = true;
        } else {
            // Plain click: single-select unless toggling current.
            const wasOnly = next[member.id]
                && Object.keys(next).filter(k => next[k]).length === 1;
            for (const k of Object.keys(next)) delete next[k];
            if (!wasOnly) next[member.id] = true;
        }
        this.state.selectedMemberIds = next;
        this.state.lastClickedMemberId = member.id;
    }

    onMemberCheckboxChange(ev, member) {
        ev.stopPropagation();
        const next = { ...this.state.selectedMemberIds };
        if (ev.target.checked) next[member.id] = true;
        else delete next[member.id];
        this.state.selectedMemberIds = next;
        this.state.lastClickedMemberId = member.id;
    }

    isMemberSelected(member) {
        return !!this.state.selectedMemberIds[member.id];
    }

    async removeSelected() {
        const ids = Object.keys(this.state.selectedMemberIds)
            .filter(k => this.state.selectedMemberIds[k]).map(k => parseInt(k));
        if (!ids.length) {
            this.notification.add("Selecteer minstens één lid.", { type: "warning" });
            return;
        }
        if (!confirm(`Verwijder ${ids.length} lid(en) uit "${this.state.persongroup.name}"?`)) {
            return;
        }
        try {
            const res = await this.orm.call(
                "myschool.persongroup.member.browser",
                "remove_members",
                [this.persongroupId, ids],
            );
            this.notification.add(`Verwijderd: ${res.removed}.`, { type: "success" });
            this.state.selectedMemberIds = {};
            await this.loadData(this.state.treeFilter);
        } catch (e) {
            console.error("[PGMB] remove failed", e);
            this.notification.add(`Verwijderen mislukt: ${e.message || e}`, { type: "danger" });
        }
    }

    // ----- Right pane: tree -----

    get selectedPersonCount() {
        return Object.keys(this.state.selectedPersonIds)
            .filter(k => this.state.selectedPersonIds[k]).length;
    }

    onTreeFilterInput(ev) { this.state.treeFilter = ev.target.value; }
    clearTreeFilter() {
        this.state.treeFilter = "";
        this.loadData("");
    }

    onTreeFilterKeydown(ev) {
        if (ev.key === "Enter") {
            this.loadData(this.state.treeFilter);
        }
    }

    onTreeFilterApply() { this.loadData(this.state.treeFilter); }

    onToggleExpand(orgId, isExpanded) {
        this.state.expandedOrgIds = {
            ...this.state.expandedOrgIds,
            [orgId]: isExpanded,
        };
    }

    onPersonClick(person, modifiers = {}) {
        const next = { ...this.state.selectedPersonIds };
        if (modifiers.ctrlKey) {
            if (next[person.id]) delete next[person.id];
            else next[person.id] = true;
        } else {
            const wasOnly = next[person.id]
                && Object.keys(next).filter(k => next[k]).length === 1;
            for (const k of Object.keys(next)) delete next[k];
            if (!wasOnly) next[person.id] = true;
        }
        this.state.selectedPersonIds = next;
        this.state.lastClickedPersonId = person.id;
    }

    expandAllInTree() {
        const next = {};
        const walk = (nodes) => {
            for (const n of nodes) {
                next[n.id] = true;
                if (n.children) walk(n.children);
            }
        };
        walk(this.state.tree);
        this.state.expandedOrgIds = next;
    }

    collapseAllInTree() {
        this.state.expandedOrgIds = {};
    }

    async addSelected() {
        const ids = Object.keys(this.state.selectedPersonIds)
            .filter(k => this.state.selectedPersonIds[k]).map(k => parseInt(k));
        if (!ids.length) {
            this.notification.add("Selecteer minstens één persoon.", { type: "warning" });
            return;
        }
        try {
            const res = await this.orm.call(
                "myschool.persongroup.member.browser",
                "add_members",
                [this.persongroupId, ids],
            );
            this.notification.add(`Toegevoegd: ${res.added}.`, { type: "success" });
            this.state.selectedPersonIds = {};
            await this.loadData(this.state.treeFilter);
        } catch (e) {
            console.error("[PGMB] add failed", e);
            this.notification.add(`Toevoegen mislukt: ${e.message || e}`, { type: "danger" });
        }
    }

    closeAction() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add(
    "myschool_persongroup_member_browser",
    PersongroupMemberBrowserClient,
);
