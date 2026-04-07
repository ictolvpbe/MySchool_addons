/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TaskBoard extends Component {
    static template = "myschool_tasks.TaskBoard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            kpis: {},
            tasksTodo: [],
            tasksInProgress: [],
            tasksDone: [],
            tasksBlocked: [],
            instances: [],
            templates: [],
            hasComposerAccess: false,
            // New process dialog
            showNewProcessDialog: false,
            newProcessDescription: "",
            selectedTemplateId: null,
            // Active filter
            activeFilter: "all", // all, mine, group
            // Drag state
            dragTaskId: null,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const data = await this.orm.call(
                "myschool.taskboard",
                "get_dashboard_data",
                [],
            );
            this.state.kpis = data.kpis || {};
            this.state.tasksTodo = data.tasks_todo || [];
            this.state.tasksInProgress = data.tasks_in_progress || [];
            this.state.tasksDone = data.tasks_done || [];
            this.state.tasksBlocked = data.tasks_blocked || [];
            this.state.instances = data.instances || [];
            this.state.templates = data.templates || [];
            this.state.hasComposerAccess = data.has_composer_access || false;
        } catch (e) {
            console.error("Taskboard load error:", e);
            this.notification.add("Fout bij laden van het takenbord.", { type: "danger" });
        }
        this.state.loading = false;
    }

    async onRefresh() {
        this.state.loading = true;
        await this.loadData();
    }

    // ── Filters ──────────────────────────────────────────────

    setFilter(filter) {
        this.state.activeFilter = filter;
    }

    filterTasks(tasks) {
        if (this.state.activeFilter === "mine") {
            return tasks.filter((t) => t.is_mine);
        }
        if (this.state.activeFilter === "group") {
            return tasks.filter((t) => !t.is_mine && !t.assigned_user_id);
        }
        return tasks;
    }

    get filteredTodo() {
        return this.filterTasks(this.state.tasksTodo);
    }
    get filteredInProgress() {
        return this.filterTasks(this.state.tasksInProgress);
    }
    get filteredDone() {
        return this.filterTasks(this.state.tasksDone);
    }
    get filteredBlocked() {
        return this.filterTasks(this.state.tasksBlocked);
    }

    // ── Drag & Drop ──────────────────────────────────────────

    onDragStart(ev, taskId) {
        this.state.dragTaskId = taskId;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(taskId));
        ev.target.closest(".tb-task-card").classList.add("tb-dragging");
    }

    onDragEnd(ev) {
        this.state.dragTaskId = null;
        ev.target.closest(".tb-task-card")?.classList.remove("tb-dragging");
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        ev.currentTarget.classList.add("tb-drop-target");
    }

    onDragLeave(ev) {
        ev.currentTarget.classList.remove("tb-drop-target");
    }

    async onDrop(ev, newState) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("tb-drop-target");
        const taskId = parseInt(ev.dataTransfer.getData("text/plain"));
        if (!taskId) return;

        try {
            await this.orm.call("myschool.process.task", "update_task_state", [taskId, newState]);
            await this.loadData();
            this.notification.add(`Taak bijgewerkt naar "${this.stateLabel(newState)}".`, {
                type: "success",
            });
        } catch (e) {
            console.error("Drop error:", e);
            this.notification.add("Fout bij bijwerken van taakstatus.", { type: "danger" });
        }
    }

    // ── Task Actions ─────────────────────────────────────────

    async onAssignToMe(taskId) {
        try {
            await this.orm.call("myschool.process.task", "action_assign_to_me", [[taskId]]);
            await this.loadData();
            this.notification.add("Taak aan u toegewezen.", { type: "success" });
        } catch (e) {
            this.notification.add("Fout bij toewijzen.", { type: "danger" });
        }
    }

    async onChangeState(taskId, newState) {
        try {
            await this.orm.call("myschool.process.task", "update_task_state", [taskId, newState]);
            await this.loadData();
        } catch (e) {
            this.notification.add("Fout bij statuswijziging.", { type: "danger" });
        }
    }

    openTaskForm(taskId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "myschool.process.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openInstanceForm(instanceId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "myschool.process.instance",
            res_id: instanceId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ── New Process Dialog ───────────────────────────────────

    openNewProcessDialog() {
        this.state.showNewProcessDialog = true;
        this.state.selectedTemplateId = null;
        this.state.newProcessDescription = "";
    }

    closeNewProcessDialog() {
        this.state.showNewProcessDialog = false;
    }

    selectTemplate(templateId) {
        this.state.selectedTemplateId = templateId;
    }

    onDescriptionInput(ev) {
        this.state.newProcessDescription = ev.target.value;
    }

    async startNewProcess() {
        if (!this.state.selectedTemplateId) {
            this.notification.add("Selecteer een procestemplate.", { type: "warning" });
            return;
        }
        try {
            const instanceId = await this.orm.call(
                "myschool.process.instance",
                "create_from_template",
                [this.state.selectedTemplateId, this.state.newProcessDescription],
            );
            this.state.showNewProcessDialog = false;
            this.notification.add("Nieuw proces aangemaakt!", { type: "success" });

            // Start the process immediately
            await this.orm.call("myschool.process.instance", "action_start", [[instanceId]]);
            await this.loadData();
        } catch (e) {
            console.error("Create process error:", e);
            this.notification.add(
                e.message || "Fout bij aanmaken van proces.",
                { type: "danger" },
            );
        }
    }

    // ── Process Composer ─────────────────────────────────────

    openProcessComposer() {
        this.action.doAction("myschool_processcomposer.action_myschool_process_list");
    }

    // ── Navigation ───────────────────────────────────────────

    openMyTasks() {
        this.action.doAction("myschool_tasks.action_process_task_my");
    }

    openAllTasks() {
        this.action.doAction("myschool_tasks.action_process_task_all");
    }

    openInstances() {
        this.action.doAction("myschool_tasks.action_process_instance");
    }

    // ── Formatting helpers ───────────────────────────────────

    stateLabel(state) {
        const map = {
            todo: "Te doen",
            in_progress: "Bezig",
            done: "Voltooid",
            cancelled: "Geannuleerd",
            blocked: "Geblokkeerd",
        };
        return map[state] || state;
    }

    priorityClass(priority) {
        const map = {
            "0": "",
            "1": "tb-prio-low",
            "2": "tb-prio-high",
            "3": "tb-prio-urgent",
        };
        return map[priority] || "";
    }

    priorityLabel(priority) {
        const map = {
            "0": "Normaal",
            "1": "Laag",
            "2": "Hoog",
            "3": "Urgent",
        };
        return map[priority] || "";
    }

    priorityIcon(priority) {
        const map = {
            "0": "",
            "1": "fa-arrow-down",
            "2": "fa-arrow-up",
            "3": "fa-exclamation-triangle",
        };
        return map[priority] || "";
    }

    instanceStateClass(state) {
        const map = {
            draft: "tb-badge-neutral",
            running: "tb-badge-info",
            completed: "tb-badge-success",
            cancelled: "tb-badge-muted",
        };
        return map[state] || "tb-badge-neutral";
    }

    instanceStateLabel(state) {
        const map = {
            draft: "Concept",
            running: "Actief",
            completed: "Voltooid",
            cancelled: "Geannuleerd",
        };
        return map[state] || state;
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleDateString("nl-BE", { day: "2-digit", month: "short" });
    }
}

registry.category("actions").add("myschool_taskboard", TaskBoard);
