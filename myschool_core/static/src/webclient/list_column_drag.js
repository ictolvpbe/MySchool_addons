/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useEffect } from "@odoo/owl";

/**
 * Patch op de standaard ListRenderer die toelaat dat gebruikers de
 * kolomvolgorde aanpassen door een kolomkop te slepen naar links of rechts.
 *
 * Persistentie: localStorage per (model, view_id, user). Dat houdt de
 * voorkeuren per browser/account vast zonder server-roundtrips. Niet gesynct
 * over devices — voor cross-device sync zou een res.users.settings-veld
 * nodig zijn.
 *
 * Werkt naast de standaard "optional"-toggle (de ≡-icoon rechtsboven). De
 * gebruiker kan dus zowel kolommen tonen/verbergen als hun volgorde wijzigen.
 */

const STORAGE_PREFIX = "myschool_col_order_";

function _storageKey(model, viewId) {
    // Het ir.ui.view-id is meestal vast per <list>-definitie; voeg het mee
    // zodat verschillende lijsten op hetzelfde model elk hun eigen volgorde
    // kunnen hebben (bv. "alle aanvragen" vs. "te beoordelen").
    return `${STORAGE_PREFIX}${model || "unknown"}_${viewId || "default"}`;
}

function _loadOrder(model, viewId) {
    try {
        const raw = localStorage.getItem(_storageKey(model, viewId));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : null;
    } catch (e) {
        return null;
    }
}

function _saveOrder(model, viewId, order) {
    try {
        localStorage.setItem(_storageKey(model, viewId), JSON.stringify(order));
    } catch (e) {
        // localStorage vol of disabled — silent fail, val terug op XML-volgorde
    }
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        this._msDragSrcName = null;

        // Hang drag-handlers aan de <th data-name="..."> elementen na elke
        // render. Een nieuwe useEffect met `() => [...]` als dep-array zou hem
        // alleen reinstalleren wanneer de zichtbare kolommen wijzigen.
        useEffect(
            () => {
                const tableEl = this.tableRef.el;
                if (!tableEl) return;
                const ths = tableEl.querySelectorAll("thead th[data-name]");
                if (!ths.length) return;

                const cleanups = [];
                ths.forEach((th) => {
                    // Alleen kolommen met een echte field-naam zijn versleepbaar.
                    // Dat sluit selector- en actie-kolommen automatisch uit
                    // (die hebben geen data-name).
                    th.setAttribute("draggable", "true");
                    th.classList.add("o_ms_col_draggable");

                    const onDragStart = (ev) => {
                        this._msDragSrcName = th.dataset.name;
                        if (ev.dataTransfer) {
                            ev.dataTransfer.effectAllowed = "move";
                            // Firefox vereist dat dataTransfer iets bevat.
                            ev.dataTransfer.setData("text/plain", th.dataset.name);
                        }
                        th.classList.add("o_ms_col_dragging");
                    };
                    const onDragOver = (ev) => {
                        if (
                            this._msDragSrcName &&
                            this._msDragSrcName !== th.dataset.name
                        ) {
                            ev.preventDefault();
                            if (ev.dataTransfer) {
                                ev.dataTransfer.dropEffect = "move";
                            }
                            th.classList.add("o_ms_col_drag_over");
                        }
                    };
                    const onDragLeave = () => {
                        th.classList.remove("o_ms_col_drag_over");
                    };
                    const onDrop = (ev) => {
                        ev.preventDefault();
                        th.classList.remove("o_ms_col_drag_over");
                        const srcName = this._msDragSrcName;
                        const dstName = th.dataset.name;
                        if (!srcName || srcName === dstName) return;
                        this._msReorderColumns(srcName, dstName);
                    };
                    const onDragEnd = () => {
                        this._msDragSrcName = null;
                        th.classList.remove("o_ms_col_dragging");
                        // Schoonmaak voor het geval dragleave gemist werd.
                        ths.forEach((other) =>
                            other.classList.remove("o_ms_col_drag_over")
                        );
                    };

                    th.addEventListener("dragstart", onDragStart);
                    th.addEventListener("dragover", onDragOver);
                    th.addEventListener("dragleave", onDragLeave);
                    th.addEventListener("drop", onDrop);
                    th.addEventListener("dragend", onDragEnd);

                    cleanups.push(() => {
                        th.removeEventListener("dragstart", onDragStart);
                        th.removeEventListener("dragover", onDragOver);
                        th.removeEventListener("dragleave", onDragLeave);
                        th.removeEventListener("drop", onDrop);
                        th.removeEventListener("dragend", onDragEnd);
                        th.removeAttribute("draggable");
                        th.classList.remove("o_ms_col_draggable");
                    });
                });

                return () => cleanups.forEach((fn) => fn());
            },
            () => [(this.columns || []).map((c) => c.name).join("|")]
        );
    },

    /**
     * Hergeef de actieve kolommen volgens de bewaarde gebruikersvolgorde.
     * Onbekende namen in de bewaarde volgorde worden genegeerd; kolommen die
     * nieuw zijn (niet in de bewaarde volgorde) komen achteraan.
     */
    getActiveColumns() {
        const cols = super.getActiveColumns();
        const model = this.props.list?.resModel;
        const viewId = this.props.archInfo?.viewId;
        const savedOrder = _loadOrder(model, viewId);
        if (!savedOrder || !savedOrder.length) {
            return cols;
        }
        const indexOf = (name) => {
            const idx = savedOrder.indexOf(name);
            return idx === -1 ? Number.MAX_SAFE_INTEGER : idx;
        };
        return [...cols].sort((a, b) => {
            const ai = indexOf(a.name);
            const bi = indexOf(b.name);
            if (ai === bi) {
                // Behoud relatieve volgorde van de XML voor onbekende kolommen
                return cols.indexOf(a) - cols.indexOf(b);
            }
            return ai - bi;
        });
    },

    /**
     * Verschuif `srcName` naar de positie van `dstName` in de zichtbare lijst,
     * persisteer de nieuwe volgorde en forceer een rerender.
     */
    _msReorderColumns(srcName, dstName) {
        const currentOrder = (this.columns || []).map((c) => c.name);
        const srcIdx = currentOrder.indexOf(srcName);
        const dstIdx = currentOrder.indexOf(dstName);
        if (srcIdx === -1 || dstIdx === -1) return;
        const newOrder = [...currentOrder];
        newOrder.splice(srcIdx, 1);
        newOrder.splice(dstIdx, 0, srcName);
        const model = this.props.list?.resModel;
        const viewId = this.props.archInfo?.viewId;
        _saveOrder(model, viewId, newOrder);
        // Forceer rerender zodat getActiveColumns() de nieuwe volgorde
        // toepast. `this.render(true)` is een Owl-component-API.
        this.render(true);
    },
});
