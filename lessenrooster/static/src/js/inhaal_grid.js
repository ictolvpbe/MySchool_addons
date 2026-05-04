/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * Lessenrooster — Inhaalplanning
 * ------------------------------
 * Toont het lessenrooster van de ingelogde leerkracht. Markeert lessen die
 * gemist worden door een eigen activiteit/professionalisering of door een
 * activiteit van de klas. Klik op een gemarkeerde les opent een side-panel
 * met vrije slots voor die specifieke klas, en klik op een vrij slot maakt
 * een planner.record + stuurt notificatie naar de planner-beheerders.
 */

class InhaalGridAction extends Component {
    static template = "lessenrooster.InhaalGrid";
    static props = ["*"];
    static displayName = "Mijn lessenrooster (inhaalplanning)";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.state = useState({
            loading: true,
            error: null,
            data: null,
            weekStart: this._mondayOf(new Date()),
            showOnlyMissed: false,
            // Right panel state
            selectedLesson: null,
            slotSearchFrom: this._fmtDate(new Date()),
            slotSearchTo: this._fmtDate(this._addDays(new Date(), 14)),
            slots: null,
            slotLoading: false,
        });

        onWillStart(async () => {
            await this._fetchGrid();
        });
    }

    // --- Date helpers ---

    _mondayOf(date) {
        const d = new Date(date);
        const day = d.getDay();
        const diff = day === 0 ? -6 : 1 - day;
        d.setDate(d.getDate() + diff);
        return this._fmtDate(d);
    }

    _addDays(date, n) {
        const d = new Date(date);
        d.setDate(d.getDate() + n);
        return d;
    }

    _fmtDate(d) {
        const date = (d instanceof Date) ? d : new Date(d);
        const yyyy = date.getFullYear();
        const mm = String(date.getMonth() + 1).padStart(2, "0");
        const dd = String(date.getDate()).padStart(2, "0");
        return `${yyyy}-${mm}-${dd}`;
    }

    _fmtDayMonth(dStr) {
        const d = new Date(dStr);
        return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
    }

    // --- RPC ---

    async _fetchGrid() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const result = await this.orm.call(
                "lessenrooster.inhaal.view",
                "get_grid_data",
                [this.state.weekStart],
            );
            if (result.error) {
                this.state.error = result.error;
            } else {
                this.state.data = result;
            }
        } catch (e) {
            this.state.error = e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    async _fetchSlots() {
        if (!this.state.selectedLesson) return;
        this.state.slotLoading = true;
        this.state.slots = null;
        try {
            const slots = await this.orm.call(
                "lessenrooster.inhaal.view",
                "get_free_slots",
                [
                    this.state.selectedLesson.klas_id,
                    this.state.slotSearchFrom,
                    this.state.slotSearchTo,
                ],
            );
            this.state.slots = slots;
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        } finally {
            this.state.slotLoading = false;
        }
    }

    // --- Event handlers ---

    onPrevWeek() {
        const d = this._addDays(this.state.weekStart, -7);
        this.state.weekStart = this._fmtDate(d);
        this._fetchGrid();
    }

    onNextWeek() {
        const d = this._addDays(this.state.weekStart, 7);
        this.state.weekStart = this._fmtDate(d);
        this._fetchGrid();
    }

    onToday() {
        this.state.weekStart = this._mondayOf(new Date());
        this._fetchGrid();
    }

    onToggleMissed() {
        this.state.showOnlyMissed = !this.state.showOnlyMissed;
    }

    onLessonClick(lesson) {
        if (!lesson.missed_self && !lesson.missed_class) return;
        this.state.selectedLesson = lesson;
        this.state.slots = null;
        this._fetchSlots();
    }

    onCloseSidePanel() {
        this.state.selectedLesson = null;
        this.state.slots = null;
    }

    onSlotSearchChange(field, ev) {
        this.state[field] = ev.target.value;
    }

    onSearchSlots() {
        this._fetchSlots();
    }

    setRange(days) {
        const today = new Date();
        this.state.slotSearchFrom = this._fmtDate(today);
        this.state.slotSearchTo = this._fmtDate(this._addDays(today, days));
        this._fetchSlots();
    }

    async onApplySlot(slot) {
        const lesson = this.state.selectedLesson;
        if (!lesson) return;
        const confirmed = await this._confirmDialog(
            `Plan inhaalmoment op ${this._fmtDayMonth(slot.date)} (${slot.day_name}) — lesuur ${slot.lesuur} voor klas ${lesson.klas_name}?`,
        );
        if (!confirmed) return;
        try {
            const result = await this.orm.call(
                "lessenrooster.inhaal.view",
                "create_inhaal",
                [lesson.klas_id, slot.date, slot.lesuur, lesson.id],
            );
            this.notification.add(
                `Inhaalmoment ${result.planner_name} aangemaakt. Beheerder is verwittigd.`,
                { type: "success" },
            );
            this.onCloseSidePanel();
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        }
    }

    _confirmDialog(message) {
        return new Promise((resolve) => {
            let resolved = false;
            this.dialog.add(ConfirmationDialog, {
                title: "Bevestigen",
                body: message,
                confirmLabel: "Bevestigen",
                cancelLabel: "Annuleren",
                confirm: () => { resolved = true; resolve(true); },
                cancel: () => { resolved = true; resolve(false); },
            }, { onClose: () => { if (!resolved) resolve(false); } });
        });
    }

    // --- Computed getters for template ---

    get weekRangeLabel() {
        if (!this.state.data) return "";
        const start = this._fmtDayMonth(this.state.data.week_start);
        const end = this._fmtDayMonth(this.state.data.week_end);
        return `${start} – ${end}`;
    }

    /** Returns lessons grouped by (dag, lesuur) for grid rendering. */
    get lessonsByCell() {
        const map = {};
        if (!this.state.data) return map;
        for (const lesson of this.state.data.lessons) {
            if (this.state.showOnlyMissed
                && !lesson.missed_self && !lesson.missed_class) continue;
            const key = `${lesson.dag}-${lesson.lesuur}`;
            if (!map[key]) map[key] = [];
            map[key].push(lesson);
        }
        return map;
    }

    cellClass(lesson) {
        if (lesson.missed_self) return "lr-cell-missed-self";
        if (lesson.missed_class) return "lr-cell-missed-class";
        return "lr-cell-normal";
    }

    cellIcon(lesson) {
        if (lesson.missed_self) return "fa-user-times";
        if (lesson.missed_class) return "fa-users";
        return "";
    }
}

registry.category("actions").add("lessenrooster_inhaal_grid", InhaalGridAction);
