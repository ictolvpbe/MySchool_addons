/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

/**
 * SapSyncReview — OWL2 client-action voor de SAP-sync review-UI.
 *
 * Verwacht ``params.run_id`` (vanuit ``run.action_open_review()``).
 * Toont:
 *  - header met run-info + drempel-badges per object_type
 *  - tabs per object_type met tabel van geplande wijzigingen
 *  - per-rij acties: ✅ approve, ⛔ block, 🕒 review-later, 🔍 detail
 *  - bulk-acties + run-acties (apply / cancel)
 *
 * Server-side: alle data via ``myschool.sap.sync.service``.
 */
export class SapSyncReview extends Component {
    static template = "myschool_admin.SapSyncReview";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");

        const runId =
            this.props.action.params?.run_id ||
            this.props.action.context?.run_id ||
            this.props.action.context?.default_run_id ||
            null;

        this.state = useState({
            runId: runId,
            overview: null,
            activeType: null,
            stateFilter: "open", // open | all | applied | blocked
            changes: [],
            selectedIds: new Set(),
            blockReason: "",
            detail: null, // {id, payload_old, payload_new, ...}
            loading: false,
        });

        onWillStart(async () => {
            if (this.state.runId) {
                await this._loadOverview();
            }
        });
    }

    // --------------------------------------------------------------
    // Data loaders
    // --------------------------------------------------------------

    async _loadOverview() {
        this.state.loading = true;
        try {
            const ov = await this.orm.call(
                "myschool.sap.sync.service",
                "get_run_overview",
                [this.state.runId],
            );
            this.state.overview = ov;
            if (!this.state.activeType && ov?.types?.length) {
                this.state.activeType = ov.types[0].object_type;
            }
            if (this.state.activeType) {
                await this._loadChanges();
            }
        } catch (e) {
            console.error("SAP-sync review: overview faalde", e);
            this.notification.add("Kon run-overzicht niet laden", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async _loadChanges() {
        const filter = this._stateFilterDomain(this.state.stateFilter);
        try {
            const result = await this.orm.call(
                "myschool.sap.sync.service",
                "get_changes",
                [],
                {
                    run_id: this.state.runId,
                    object_type: this.state.activeType,
                    filter_state: filter,
                },
            );
            this.state.changes = result || [];
            this.state.selectedIds = new Set();
        } catch (e) {
            console.error("SAP-sync review: changes laden faalde", e);
            this.notification.add("Kon wijzigingen niet laden", {
                type: "danger",
            });
        }
    }

    _stateFilterDomain(filter) {
        switch (filter) {
            case "open":
                return ["planned", "approved", "blocked", "to_review_later"];
            case "applied":
                return ["applied"];
            case "blocked":
                return ["blocked"];
            case "review_later":
                return ["to_review_later"];
            case "all":
            default:
                return null;
        }
    }

    // --------------------------------------------------------------
    // Tab / filter handlers
    // --------------------------------------------------------------

    async onSelectType(objectType) {
        this.state.activeType = objectType;
        await this._loadChanges();
    }

    async onChangeStateFilter(ev) {
        this.state.stateFilter = ev.target.value;
        await this._loadChanges();
    }

    // --------------------------------------------------------------
    // Row selection
    // --------------------------------------------------------------

    onToggleRow(id) {
        if (this.state.selectedIds.has(id)) {
            this.state.selectedIds.delete(id);
        } else {
            this.state.selectedIds.add(id);
        }
        // Tikje hack om OWL te triggeren — Set-mutatie wordt anders niet gevolgd.
        this.state.selectedIds = new Set(this.state.selectedIds);
    }

    onToggleAll() {
        if (this.state.selectedIds.size === this.state.changes.length) {
            this.state.selectedIds = new Set();
        } else {
            this.state.selectedIds = new Set(this.state.changes.map((c) => c.id));
        }
    }

    isSelected(id) {
        return this.state.selectedIds.has(id);
    }

    isAllSelected() {
        return (
            this.state.changes.length > 0 &&
            this.state.selectedIds.size === this.state.changes.length
        );
    }

    // --------------------------------------------------------------
    // State-changing actions
    // --------------------------------------------------------------

    async _applyState(ids, newState, reason = "") {
        if (!ids.length) return;
        try {
            await this.orm.call(
                "myschool.sap.sync.service",
                "set_change_state",
                [ids, newState, reason],
            );
            await this._loadOverview();
            this.notification.add(
                `${ids.length} wijziging(en) → ${newState}`,
                { type: "success" },
            );
        } catch (e) {
            console.error("SAP-sync review: set_change_state faalde", e);
            this.notification.add("Kon status niet wijzigen", {
                type: "danger",
            });
        }
    }

    async onApproveRow(id) {
        await this._applyState([id], "approved");
    }

    async onBlockRow(id) {
        const reason = window.prompt("Reden voor blokkeren (optioneel):", "");
        if (reason === null) return;
        await this._applyState([id], "blocked", reason);
    }

    async onReviewLaterRow(id) {
        await this._applyState([id], "to_review_later");
    }

    async onBulkApprove() {
        const ids = Array.from(this.state.selectedIds);
        await this._applyState(ids, "approved");
    }

    async onBulkBlock() {
        const ids = Array.from(this.state.selectedIds);
        if (!ids.length) return;
        const reason = window.prompt(
            `Reden voor blokkeren (${ids.length} rij(en)):`,
            "",
        );
        if (reason === null) return;
        await this._applyState(ids, "blocked", reason);
    }

    async onBulkReviewLater() {
        const ids = Array.from(this.state.selectedIds);
        await this._applyState(ids, "to_review_later");
    }

    // --------------------------------------------------------------
    // Partial commit (apply NOW for selected rows / single row)
    // --------------------------------------------------------------

    async _applyNow(ids) {
        if (!ids.length) return;
        if (
            !window.confirm(
                `${ids.length} wijziging(en) onmiddellijk toepassen?\n\n` +
                    "Hiermee worden betasks aangemaakt en de volledige " +
                    "cascade (LDAP/Cloud/AD/…) gestart voor deze rijen. " +
                    "De rest van de batch blijft openstaan voor review.",
            )
        ) {
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "myschool.sap.sync.service",
                "apply_changes",
                [ids],
            );
            await this._loadOverview();
            const msg = `${result.created} toegepast` +
                (result.failed ? `, ${result.failed} fout(en)` : "") +
                (result.skipped ? `, ${result.skipped} overgeslagen` : "");
            this.notification.add(msg, {
                type: result.failed ? "warning" : "success",
            });
        } catch (e) {
            console.error("SAP-sync review: apply_changes faalde", e);
            this.notification.add("Toepassen faalde", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onApplyRow(id) {
        await this._applyNow([id]);
    }

    async onBulkApplyNow() {
        const ids = Array.from(this.state.selectedIds);
        await this._applyNow(ids);
    }

    async onApproveRemaining() {
        if (
            !window.confirm(
                "Alle resterende 'geplande' wijzigingen goedkeuren? " +
                    "(Reeds geblokkeerde en 'na te kijken' rijen blijven onaangeroerd.)",
            )
        ) {
            return;
        }
        try {
            await this.orm.call(
                "myschool.sap.sync.service",
                "bulk_approve_remaining",
                [this.state.runId],
            );
            await this._loadOverview();
            this.notification.add("Resterende wijzigingen goedgekeurd", {
                type: "success",
            });
        } catch (e) {
            console.error("SAP-sync review: bulk-approve faalde", e);
            this.notification.add("Bulk-approve faalde", { type: "danger" });
        }
    }

    // --------------------------------------------------------------
    // Run-level actions
    // --------------------------------------------------------------

    async onApplyRun() {
        if (
            !window.confirm(
                "Goedgekeurde wijzigingen toepassen? " +
                    "Dit maakt de betasks aan en start de cascade " +
                    "(LDAP/Cloud/AD/…).",
            )
        ) {
            return;
        }
        this.state.loading = true;
        try {
            await this.orm.call(
                "myschool.sap.sync.service",
                "commit_run",
                [this.state.runId],
            );
            await this._loadOverview();
            this.notification.add("Wijzigingen toegepast", {
                type: "success",
            });
        } catch (e) {
            console.error("SAP-sync review: commit faalde", e);
            this.notification.add("Toepassen faalde", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onCancelRun() {
        if (
            !window.confirm(
                "De volledige sync-batch annuleren? " +
                    "Geen enkele wijziging wordt doorgevoerd.",
            )
        ) {
            return;
        }
        try {
            await this.orm.call(
                "myschool.sap.sync.service",
                "cancel_run",
                [this.state.runId],
            );
            this.notification.add("Batch geannuleerd", { type: "warning" });
            await this._loadOverview();
        } catch (e) {
            console.error("SAP-sync review: cancel faalde", e);
            this.notification.add("Annuleren faalde", { type: "danger" });
        }
    }

    // --------------------------------------------------------------
    // Detail modal
    // --------------------------------------------------------------

    async onOpenDetail(id) {
        try {
            const detail = await this.orm.call(
                "myschool.sap.sync.service",
                "get_change_detail",
                [id],
            );
            this.state.detail = detail;
        } catch (e) {
            console.error("SAP-sync review: detail faalde", e);
            this.notification.add("Kon detail niet laden", {
                type: "danger",
            });
        }
    }

    onCloseDetail() {
        this.state.detail = null;
    }

    // --------------------------------------------------------------
    // Display helpers
    // --------------------------------------------------------------

    get isRunDone() {
        const s = this.state.overview?.state;
        return s === "applied" || s === "cancelled" || s === "failed";
    }

    get canCommit() {
        return !this.isRunDone;
    }

    formatJson(value) {
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value || "");
        }
    }

    stateLabel(state) {
        return (
            {
                planned: "Gepland",
                approved: "Goedgekeurd",
                blocked: "Geblokkeerd",
                to_review_later: "Na te kijken",
                applied: "Toegepast",
                superseded: "Vervangen",
                failed: "Mislukt",
                cancelled: "Geannuleerd",
            }[state] || state
        );
    }

    runStateLabel(state) {
        return (
            {
                analysing: "Analyseren",
                awaiting_approval: "Wacht op goedkeuring (drempel)",
                awaiting_review: "Wacht op review",
                applying: "Toepassen",
                applied: "Toegepast",
                cancelled: "Geannuleerd",
                failed: "Mislukt",
            }[state] || state
        );
    }

    isRowApplyable(ch) {
        // Een rij is "apply now"-baar als de batch nog leeft EN de rij
        // nog in een beslisbare staat zit (niet al toegepast/geblokkeerd/...).
        if (this.isRunDone) return false;
        return ch.state === "planned" || ch.state === "approved";
    }

    typeIcon(objectType) {
        return (
            {
                PERSON: "fa fa-user",
                ORG: "fa fa-building-o",
                ORGGROUP: "fa fa-users",
                PROPRELATION: "fa fa-link",
                ROLE: "fa fa-id-badge",
                RELATION: "fa fa-exchange",
            }[objectType] || "fa fa-cube"
        );
    }
}

registry.category("actions").add("myschool_sap_sync_review", SapSyncReview);
