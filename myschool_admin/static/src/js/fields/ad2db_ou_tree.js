/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const MODEL = "myschool.ad.takeover.ou.exclusion";

/**
 * Ad2dbOuTreeNode — recursive node in the AD2DB OU-exclusion tree.
 *
 * Presentational: all data + state lives in the parent field widget and is
 * passed down. A node shows an expand caret (when it may have children), an
 * "exclude" checkbox, the OU/container name and its DN. Clicking the caret/
 * name expands; expanding an un-loaded node triggers a lazy LEVEL-scan.
 */
export class Ad2dbOuTreeNode extends Component {
    static template = "myschool_admin.Ad2dbOuTreeNode";
    static components = { Ad2dbOuTreeNode };
    static props = {
        node: Object,
        level: { type: Number, optional: true },
        expanded: Object,
        busy: Object,
        onToggle: Function,
        onExclude: Function,
    };

    get level() { return this.props.level || 0; }
    get childLevel() { return this.level + 1; }
    get indentStyle() { return `padding-left:${8 + this.level * 18}px`; }

    get isExpanded() { return this.props.expanded[this.props.node.id] === true; }
    get isBusy() { return this.props.busy[this.props.node.id] === true; }

    // Show a caret when there are loaded children OR the node was never
    // drilled into yet (so it *might* have sub-OUs).
    get canExpand() {
        const n = this.props.node;
        return n.children.length > 0 || (!n.loaded && n.has_children);
    }
}

/**
 * Ad2dbOuTreeField — one2many field widget rendering the exclusion tree.
 *
 * Self-contained: it reads/writes ``myschool.ad.takeover.ou.exclusion`` rows
 * for the current session straight through the ORM service (keyed on the
 * session id), keeping its own reactive state, rather than coupling to the
 * form's in-memory o2m + save/load cycle. Top nodes are produced by the
 * session's "Toon top-OU's" button; deeper levels load lazily here.
 */
export class Ad2dbOuTreeField extends Component {
    static template = "myschool_admin.Ad2dbOuTreeField";
    static components = { Ad2dbOuTreeNode };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            nodes: [],
            expanded: {},
            busy: {},
            loading: false,
        });
        onWillStart(() => this.refresh());
    }

    get sessionId() { return this.props.record.resId; }

    async refresh() {
        if (!this.sessionId) {
            this.state.nodes = [];
            return;
        }
        this.state.loading = true;
        try {
            const rows = await this.orm.searchRead(
                MODEL,
                [["session_id", "=", this.sessionId]],
                ["dn", "name", "level", "parent_id", "exclude",
                 "has_children", "loaded"],
                { order: "name" }
            );
            this.state.nodes = this._buildTree(rows);
        } finally {
            this.state.loading = false;
        }
    }

    _buildTree(rows) {
        const byId = {};
        for (const r of rows) {
            byId[r.id] = {
                id: r.id,
                dn: r.dn,
                name: r.name || r.dn,
                level: r.level || 0,
                exclude: r.exclude,
                loaded: r.loaded,
                has_children: r.has_children,
                parentId: r.parent_id ? r.parent_id[0] : false,
                children: [],
            };
        }
        const roots = [];
        for (const n of Object.values(byId)) {
            if (n.parentId && byId[n.parentId]) {
                byId[n.parentId].children.push(n);
            } else {
                roots.push(n);
            }
        }
        const sortRec = (arr) => {
            arr.sort((a, b) => a.name.localeCompare(b.name));
            arr.forEach((n) => sortRec(n.children));
        };
        sortRec(roots);
        return roots;
    }

    _descendantIds(node) {
        const ids = [node.id];
        for (const c of node.children) ids.push(...this._descendantIds(c));
        return ids;
    }

    async onToggle(node) {
        // Lazy drill-down: first expand of an un-loaded node fetches its
        // direct sub-OUs from AD, then expands.
        if (!node.loaded && node.has_children && node.children.length === 0) {
            this.state.busy[node.id] = true;
            try {
                await this.orm.call(MODEL, "action_load_children", [[node.id]]);
                await this.refresh();
            } finally {
                delete this.state.busy[node.id];
            }
            this.state.expanded[node.id] = true;
            return;
        }
        this.state.expanded[node.id] = !this.state.expanded[node.id];
    }

    async onExclude(node) {
        // Toggle the node + cascade to its loaded descendants (cosmetic —
        // the scan-skip is DN-based, so the subtree is excluded regardless).
        const newVal = !node.exclude;
        const ids = this._descendantIds(node);
        await this.orm.write(MODEL, ids, { exclude: newVal });
        await this.refresh();
    }
}

export const ad2dbOuTreeField = {
    component: Ad2dbOuTreeField,
    supportedTypes: ["one2many"],
};

registry.category("fields").add("ad2db_ou_tree", ad2dbOuTreeField);
