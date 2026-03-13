/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onWillStart, onWillUnmount } from "@odoo/owl";

/**
 * LogViewerClient — OWL2 client-action component.
 *
 * Real-time server-log viewer (tail -f style).
 * Polls the backend via orm.call() and auto-scrolls.
 */
export class LogViewerClient extends Component {
    static template = "myschool_admin.LogViewerClient";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.logOutputRef = useRef("logOutput");

        this.state = useState({
            selectedLog: "",
            numLines: 100,
            filterLevel: "all",
            searchText: "",
            logContent: "",
            autoRefresh: false,
            refreshInterval: 5,
            loading: false,
            availableLogs: [],
            fileSize: "",
            lastRefresh: "",
            fileModified: "",
            isConsole: false,
            // config hints
            hasLogfileConfig: false,
            hasFileLogs: false,
            showConfigHint: false,
        });

        this._refreshTimer = null;
        this._searchDebounce = null;

        onWillStart(async () => {
            await this._loadAvailableLogs();
        });

        onWillUnmount(() => {
            this._stopAutoRefresh();
            if (this._searchDebounce) {
                clearTimeout(this._searchDebounce);
            }
        });
    }

    // ---- Data loading ----

    async _loadAvailableLogs() {
        try {
            const info = await this.orm.call(
                "myschool.log.viewer",
                "get_viewer_info",
                [],
            );
            this.state.availableLogs = info.available_logs || [];
            this.state.hasLogfileConfig = info.has_logfile_config;
            this.state.hasFileLogs = info.has_file_logs;
            this.state.showConfigHint = !info.has_logfile_config;

            // Auto-select the first log and load it
            const logs = this.state.availableLogs;
            if (logs.length && logs[0][0] !== "none") {
                this.state.selectedLog = logs[0][0];
                await this.refreshLog();
            }
        } catch (e) {
            console.error("Failed to load available logs:", e);
            this.notification.add("Could not load log files", { type: "danger" });
        }
    }

    async refreshLog() {
        const logFile = this.state.selectedLog;
        if (!logFile || logFile === "none") {
            this.state.logContent = "No log file selected.";
            return;
        }

        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "myschool.log.viewer",
                "get_log_content_ajax",
                [logFile, this.state.numLines, this.state.filterLevel, this.state.searchText || ""],
            );
            this.state.logContent = result.content || "";
            this.state.lastRefresh = result.timestamp || "";
            this.state.fileSize = result.file_size || "";
            this.state.fileModified = result.file_modified || "";
            this.state.isConsole = result.is_console || false;

            this._scrollToBottom();
        } catch (e) {
            console.error("Log refresh error:", e);
            this.state.logContent = `Error: ${e.message || e}`;
            this.notification.add("Error loading log", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // ---- Auto-refresh ----

    _startAutoRefresh() {
        this._stopAutoRefresh();
        const ms = (this.state.refreshInterval || 5) * 1000;
        this._refreshTimer = setInterval(() => this.refreshLog(), ms);
    }

    _stopAutoRefresh() {
        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }
    }

    // ---- Scroll ----

    _scrollToBottom() {
        requestAnimationFrame(() => {
            const el = this.logOutputRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    // ---- Event handlers ----

    onLogFileChange(ev) {
        this.state.selectedLog = ev.target.value;
        this.refreshLog();
    }

    onNumLinesChange(ev) {
        this.state.numLines = parseInt(ev.target.value) || 100;
        this.refreshLog();
    }

    onFilterLevelChange(ev) {
        this.state.filterLevel = ev.target.value;
        this.refreshLog();
    }

    onSearchInput(ev) {
        const value = ev.target.value;
        if (this._searchDebounce) {
            clearTimeout(this._searchDebounce);
        }
        this._searchDebounce = setTimeout(() => {
            this.state.searchText = value;
            this.refreshLog();
        }, 300);
    }

    onToggleAutoRefresh() {
        this.state.autoRefresh = !this.state.autoRefresh;
        if (this.state.autoRefresh) {
            this._startAutoRefresh();
        } else {
            this._stopAutoRefresh();
        }
    }

    onIntervalChange(ev) {
        this.state.refreshInterval = parseInt(ev.target.value) || 5;
        if (this.state.autoRefresh) {
            this._startAutoRefresh();
        }
    }

    onClickRefresh() {
        this.refreshLog();
    }

    onClickScrollBottom() {
        this._scrollToBottom();
    }

    async onClickDownload() {
        const logFile = this.state.selectedLog;
        if (!logFile || logFile === "none") {
            this.notification.add("No log file selected", { type: "warning" });
            return;
        }
        try {
            // Create a temporary record and call action_download
            const ids = await this.orm.call(
                "myschool.log.viewer",
                "create",
                [{ log_file: logFile, num_lines: 10000 }],
            );
            const action = await this.orm.call(
                "myschool.log.viewer",
                "action_download",
                [Array.isArray(ids) ? ids : [ids]],
            );
            if (action && action.url) {
                window.open(action.url, "_blank");
            }
        } catch (e) {
            console.error("Download error:", e);
            this.notification.add("Download failed", { type: "danger" });
        }
    }

    onClickClearFilters() {
        this.state.filterLevel = "all";
        this.state.searchText = "";
        this.refreshLog();
    }

    // ---- Formatting helpers ----

    get lineCount() {
        if (!this.state.logContent) return 0;
        return this.state.logContent.split("\n").length;
    }

    get formattedRefresh() {
        if (!this.state.lastRefresh) return "";
        try {
            const d = new Date(this.state.lastRefresh);
            return d.toLocaleTimeString("nl-BE");
        } catch {
            return this.state.lastRefresh;
        }
    }

    get terminalTitle() {
        if (!this.state.selectedLog) return "log viewer";
        if (this.state.selectedLog === "__console__") return "stdout (live console)";
        const parts = this.state.selectedLog.split("/");
        return parts[parts.length - 1] || "log viewer";
    }

    onDismissConfigHint() {
        this.state.showConfigHint = false;
    }
}

registry.category("actions").add("myschool_log_viewer", LogViewerClient);
