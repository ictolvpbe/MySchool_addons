/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

/**
 * Log Viewer Widget Component
 * 
 * Provides real-time log viewing with auto-refresh capability.
 * Similar to 'tail -f' command in Linux.
 */
export class LogViewerWidget extends Component {
    static template = "myschool_admin.LogViewerWidget";
    static props = {
        logFile: { type: String, optional: true },
        numLines: { type: Number, optional: true },
        filterLevel: { type: String, optional: true },
        searchText: { type: String, optional: true },
        autoRefresh: { type: Boolean, optional: true },
        refreshInterval: { type: Number, optional: true },
    };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        
        this.state = useState({
            logContent: "",
            isLoading: false,
            lastRefresh: null,
            fileSize: "",
            fileModified: "",
            error: null,
        });
        
        this.refreshTimer = null;
        
        onMounted(() => {
            if (this.props.autoRefresh) {
                this.startAutoRefresh();
            }
        });
        
        onWillUnmount(() => {
            this.stopAutoRefresh();
        });
    }

    async refreshLog() {
        if (!this.props.logFile) {
            this.state.logContent = "No log file selected.";
            return;
        }
        
        this.state.isLoading = true;
        this.state.error = null;
        
        try {
            const result = await this.rpc("/myschool/logviewer/refresh", {
                log_file: this.props.logFile,
                num_lines: this.props.numLines || 100,
                filter_level: this.props.filterLevel || "all",
                search_text: this.props.searchText || "",
            });
            
            if (result.error) {
                this.state.error = result.error;
                this.state.logContent = `Error: ${result.error}`;
            } else {
                this.state.logContent = result.content;
                this.state.lastRefresh = result.timestamp;
                this.state.fileSize = result.file_size;
                this.state.fileModified = result.file_modified;
            }
        } catch (error) {
            this.state.error = error.message;
            this.state.logContent = `Error: ${error.message}`;
            this.notification.add(error.message, { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    startAutoRefresh() {
        if (this.refreshTimer) {
            this.stopAutoRefresh();
        }
        
        const interval = (this.props.refreshInterval || 5) * 1000;
        this.refreshTimer = setInterval(() => {
            this.refreshLog();
        }, interval);
        
        // Initial refresh
        this.refreshLog();
    }

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    scrollToBottom() {
        const logContainer = document.querySelector(".log-content-container");
        if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }
}

// Register the component
registry.category("view_widgets").add("log_viewer_widget", LogViewerWidget);


/**
 * Auto-refresh handler for the standard form view.
 * This adds auto-refresh capability to the standard log viewer form.
 */
document.addEventListener("DOMContentLoaded", function() {
    let autoRefreshTimer = null;
    
    function setupAutoRefresh() {
        const autoRefreshCheckbox = document.querySelector('input[name="auto_refresh"]');
        const refreshIntervalInput = document.querySelector('input[name="refresh_interval"]');
        const refreshButton = document.querySelector('button[name="action_refresh"]');
        
        if (!autoRefreshCheckbox || !refreshButton) {
            return;
        }
        
        function startAutoRefresh() {
            const interval = parseInt(refreshIntervalInput?.value || 5) * 1000;
            
            if (autoRefreshTimer) {
                clearInterval(autoRefreshTimer);
            }
            
            autoRefreshTimer = setInterval(() => {
                refreshButton.click();
                scrollLogToBottom();
            }, interval);
        }
        
        function stopAutoRefresh() {
            if (autoRefreshTimer) {
                clearInterval(autoRefreshTimer);
                autoRefreshTimer = null;
            }
        }
        
        function scrollLogToBottom() {
            const logTextarea = document.querySelector('textarea[name="log_content"]');
            if (logTextarea) {
                logTextarea.scrollTop = logTextarea.scrollHeight;
            }
        }
        
        autoRefreshCheckbox.addEventListener("change", function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
        
        // Check initial state
        if (autoRefreshCheckbox.checked) {
            startAutoRefresh();
        }
    }
    
    // Setup when form is loaded
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
                setupAutoRefresh();
            }
        });
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
});
