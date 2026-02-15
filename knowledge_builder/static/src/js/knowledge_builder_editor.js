/** @odoo-module */

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount, onPatched } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ============================================================
// Constants
// ============================================================

const MAX_IMAGE_WIDTH = 1200;
const MAX_IMAGE_HEIGHT = 1200;
const AUTO_SAVE_INTERVAL = 30000; // 30 seconds

const STEP_TEMPLATES = {
    procedure: { name: 'New Step', text: '' },
    qa: [
        { name: 'Question', text: '' },
        { name: 'Answer', text: '' },
    ],
    solution: { name: 'Solution Step', text: '' },
    information: { name: 'New Section', text: '' },
};

// ============================================================
// Utility: resize image before storing
// ============================================================

function resizeImage(base64, maxW, maxH) {
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
            let { width, height } = img;
            if (width <= maxW && height <= maxH) {
                resolve(base64);
                return;
            }
            const ratio = Math.min(maxW / width, maxH / height);
            width = Math.round(width * ratio);
            height = Math.round(height * ratio);
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);
            const resized = canvas.toDataURL('image/png').split(',')[1];
            resolve(resized);
        };
        img.src = 'data:image/png;base64,' + base64;
    });
}

// ============================================================
// Toolbar
// ============================================================

class KnowledgeBuilderToolbar extends Component {
    static template = "knowledge_builder.Toolbar";
    static props = {
        title: String,
        knowledgeType: String,
        state: String,
        dirty: Boolean,
        showPreview: Boolean,
        showVersions: Boolean,
        onSave: Function,
        onAddStep: Function,
        onTogglePreview: Function,
        onToggleVersions: Function,
        onPrint: Function,
        onBack: Function,
    };
}

// ============================================================
// Step List (left panel with drag-and-drop reorder)
// ============================================================

class KnowledgeBuilderStepList extends Component {
    static template = "knowledge_builder.StepList";
    static props = {
        steps: Array,
        selectedStepIndex: Number,
        searchFilter: String,
        onSelectStep: Function,
        onAddStep: Function,
        onDuplicateStep: Function,
        onRemoveStep: Function,
        onMoveStep: Function,
        onSearchChange: Function,
    };

    setup() {
        this.state = useState({
            dragOverIndex: -1,
        });
    }

    get filteredSteps() {
        const q = this.props.searchFilter.toLowerCase();
        if (!q) return this.props.steps.map((s, i) => ({ ...s, _origIndex: i }));
        return this.props.steps
            .map((s, i) => ({ ...s, _origIndex: i }))
            .filter(s => s.name.toLowerCase().includes(q) || (s.text || '').toLowerCase().includes(q));
    }

    onStepDragStart(ev, origIndex) {
        ev.dataTransfer.setData("application/kb-step-index", String(origIndex));
        ev.dataTransfer.effectAllowed = "move";
    }

    onDropZoneDragOver(ev, targetIndex) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        this.state.dragOverIndex = targetIndex;
    }

    onDropZoneDragLeave() {
        this.state.dragOverIndex = -1;
    }

    onDropZoneDrop(ev, targetIndex) {
        ev.preventDefault();
        this.state.dragOverIndex = -1;
        const raw = ev.dataTransfer.getData("application/kb-step-index");
        if (raw === "") return;
        const fromIndex = parseInt(raw, 10);
        if (isNaN(fromIndex)) return;
        this.props.onMoveStep(fromIndex, targetIndex);
    }
}

// ============================================================
// Rich Text Toolbar (simple formatting)
// ============================================================

class RichTextToolbar extends Component {
    static template = "knowledge_builder.RichTextToolbar";
    static props = {
        onCommand: Function,
    };
}

// ============================================================
// Step Editor (center panel)
// ============================================================

class KnowledgeBuilderStepEditor extends Component {
    static template = "knowledge_builder.StepEditor";
    static components = { RichTextToolbar };
    static props = {
        step: { type: Object, optional: true },
        comments: { type: Array, optional: true },
        onTitleChange: Function,
        onTextChange: Function,
        onImageChange: Function,
        onImageRemove: Function,
        onAddComment: Function,
        onDeleteComment: Function,
    };

    setup() {
        this.fileInputRef = useRef("fileInput");
        this.editorAreaRef = useRef("editorArea");
        this.richTextRef = useRef("richText");
        this._onPaste = this._onPaste.bind(this);

        this.state = useState({
            newComment: '',
            showComments: false,
        });

        onMounted(() => {
            const el = this.editorAreaRef.el;
            if (el) el.addEventListener("paste", this._onPaste);
            this._syncRichText();
        });

        onPatched(() => {
            this._syncRichText();
        });

        onWillUnmount(() => {
            const el = this.editorAreaRef.el;
            if (el) el.removeEventListener("paste", this._onPaste);
        });
    }

    _syncRichText() {
        const el = this.richTextRef.el;
        if (el && this.props.step) {
            // Only update if content differs to preserve cursor position
            if (el.innerHTML !== (this.props.step.text || '')) {
                el.innerHTML = this.props.step.text || '';
            }
        }
    }

    _onPaste(ev) {
        if (!this.props.step) return;
        const items = ev.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith("image/")) {
                ev.preventDefault();
                const blob = item.getAsFile();
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const raw = e.target.result.split(",")[1];
                    const resized = await resizeImage(raw, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT);
                    this.props.onImageChange(resized);
                };
                reader.readAsDataURL(blob);
                break;
            }
        }
    }

    onUploadClick() {
        this.fileInputRef.el?.click();
    }

    onFileUpload(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            const raw = e.target.result.split(",")[1];
            const resized = await resizeImage(raw, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT);
            this.props.onImageChange(resized);
        };
        reader.readAsDataURL(file);
        ev.target.value = "";
    }

    onRichTextInput() {
        const el = this.richTextRef.el;
        if (el) {
            this.props.onTextChange(el.innerHTML);
        }
    }

    onRichTextCommand(cmd, value) {
        document.execCommand(cmd, false, value || null);
        this.onRichTextInput();
    }

    // --- Comments ---
    toggleComments() {
        this.state.showComments = !this.state.showComments;
    }

    submitComment() {
        const body = this.state.newComment.trim();
        if (!body) return;
        this.props.onAddComment(body);
        this.state.newComment = '';
    }

    onCommentKeydown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            this.submitComment();
        }
    }
}

// ============================================================
// Preview Panel
// ============================================================

class KnowledgeBuilderPreview extends Component {
    static template = "knowledge_builder.Preview";
    static props = {
        title: String,
        details: String,
        knowledgeType: String,
        steps: Array,
    };
}

// ============================================================
// Version History Panel
// ============================================================

class KnowledgeBuilderVersions extends Component {
    static template = "knowledge_builder.Versions";
    static props = {
        versions: Array,
        onRestore: Function,
        onClose: Function,
    };
}

// ============================================================
// Main Client Component
// ============================================================

class KnowledgeBuilderClient extends Component {
    static template = "knowledge_builder.KnowledgeBuilderClient";
    static components = {
        KnowledgeBuilderToolbar,
        KnowledgeBuilderStepList,
        KnowledgeBuilderStepEditor,
        KnowledgeBuilderPreview,
        KnowledgeBuilderVersions,
    };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.nextTempId = -1;
        this.autoSaveTimer = null;

        this.state = useState({
            objectId: null,
            title: "",
            details: "",
            knowledgeType: "information",
            objectState: "draft",
            steps: [],
            selectedStepIndex: -1,
            dirty: false,
            loading: true,
            showPreview: false,
            showVersions: false,
            searchFilter: "",
            availableObjects: [],
            versions: [],
            shareUrl: false,
        });

        this._onKeydown = this._onKeydown.bind(this);

        onWillStart(async () => {
            const ctx = this.props.action?.context || {};
            const activeId = ctx.active_id;
            if (activeId) {
                this.state.objectId = activeId;
                await this.loadEditorData();
            } else {
                await this.loadObjectList();
            }
            this.state.loading = false;
        });

        onMounted(() => {
            document.addEventListener("keydown", this._onKeydown);
            this._startAutoSave();
        });

        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeydown);
            this._stopAutoSave();
        });
    }

    _onKeydown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "s") {
            ev.preventDefault();
            if (this.state.objectId && this.state.dirty) {
                this.saveEditorData();
            }
            return;
        }
        // Keyboard navigation: arrow up/down to change selected step
        if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA' ||
            ev.target.isContentEditable) return;

        if (ev.key === 'ArrowUp' && this.state.selectedStepIndex > 0) {
            ev.preventDefault();
            this.state.selectedStepIndex--;
        } else if (ev.key === 'ArrowDown' && this.state.selectedStepIndex < this.state.steps.length - 1) {
            ev.preventDefault();
            this.state.selectedStepIndex++;
        } else if (ev.key === 'Delete' && this.state.selectedStepIndex >= 0) {
            ev.preventDefault();
            this.removeStep(this.state.selectedStepIndex);
        }
    }

    // ------------------------------------------------------------------
    // Auto-save
    // ------------------------------------------------------------------

    _startAutoSave() {
        this.autoSaveTimer = setInterval(() => {
            if (this.state.objectId && this.state.dirty) {
                this.saveEditorData(true);
            }
        }, AUTO_SAVE_INTERVAL);
    }

    _stopAutoSave() {
        if (this.autoSaveTimer) {
            clearInterval(this.autoSaveTimer);
            this.autoSaveTimer = null;
        }
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadEditorData() {
        const data = await this.orm.call(
            "knowledge.object", "get_editor_data", [this.state.objectId]
        );
        this.state.title = data.title;
        this.state.details = data.details;
        this.state.knowledgeType = data.knowledge_type;
        this.state.objectState = data.state;
        this.state.steps = data.steps;
        this.state.versions = data.versions || [];
        this.state.shareUrl = data.share_url || false;
        this.state.selectedStepIndex = data.steps.length > 0 ? 0 : -1;
        this.state.dirty = false;
    }

    async loadObjectList() {
        const objects = await this.orm.searchRead(
            "knowledge.object", [], ["name", "knowledge_type", "state"], { limit: 100 }
        );
        this.state.availableObjects = objects;
    }

    async loadObject(id) {
        this.state.objectId = id;
        this.state.loading = true;
        await this.loadEditorData();
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Save
    // ------------------------------------------------------------------

    async saveEditorData(isAutoSave = false) {
        const data = {
            title: this.state.title,
            details: this.state.details,
            knowledge_type: this.state.knowledgeType,
            steps: this.state.steps.map((s, idx) => ({
                id: s.id,
                name: s.name,
                text: s.text,
                image: s.image || false,
                sequence: (idx + 1) * 10,
            })),
        };
        await this.orm.call(
            "knowledge.object", "save_editor_data",
            [this.state.objectId], { data }
        );
        // Reload to get real IDs and updated versions
        const prevIndex = this.state.selectedStepIndex;
        await this.loadEditorData();
        this.state.selectedStepIndex = Math.min(prevIndex, this.state.steps.length - 1);
        if (!isAutoSave) {
            this.notification.add("Saved successfully", { type: "success" });
        }
    }

    // ------------------------------------------------------------------
    // Step operations
    // ------------------------------------------------------------------

    addStep() {
        const type = this.state.knowledgeType;
        const templates = STEP_TEMPLATES[type];

        if (Array.isArray(templates)) {
            // Q&A: add a pair
            for (const tmpl of templates) {
                this.state.steps.push({
                    id: this.nextTempId--,
                    name: tmpl.name,
                    text: tmpl.text,
                    image: false,
                    sequence: (this.state.steps.length + 1) * 10,
                    comments: [],
                });
            }
        } else {
            this.state.steps.push({
                id: this.nextTempId--,
                name: templates.name,
                text: templates.text,
                image: false,
                sequence: (this.state.steps.length + 1) * 10,
                comments: [],
            });
        }
        this.state.selectedStepIndex = this.state.steps.length - 1;
        this.state.dirty = true;
    }

    duplicateStep(index) {
        const original = this.state.steps[index];
        if (!original) return;
        const dup = {
            id: this.nextTempId--,
            name: original.name + ' (copy)',
            text: original.text,
            image: original.image,
            sequence: (this.state.steps.length + 1) * 10,
            comments: [],
        };
        this.state.steps.splice(index + 1, 0, dup);
        this.state.selectedStepIndex = index + 1;
        this.state.dirty = true;
    }

    removeStep(index) {
        this.state.steps.splice(index, 1);
        if (this.state.steps.length === 0) {
            this.state.selectedStepIndex = -1;
        } else if (this.state.selectedStepIndex >= this.state.steps.length) {
            this.state.selectedStepIndex = this.state.steps.length - 1;
        } else if (this.state.selectedStepIndex === index) {
            this.state.selectedStepIndex = Math.min(index, this.state.steps.length - 1);
        }
        this.state.dirty = true;
    }

    selectStep(index) {
        this.state.selectedStepIndex = index;
    }

    moveStep(fromIndex, toIndex) {
        if (fromIndex === toIndex || fromIndex === toIndex - 1) return;
        const steps = this.state.steps;
        const [moved] = steps.splice(fromIndex, 1);
        const insertAt = fromIndex < toIndex ? toIndex - 1 : toIndex;
        steps.splice(insertAt, 0, moved);
        this.state.selectedStepIndex = insertAt;
        this.state.dirty = true;
    }

    getSelectedStep() {
        if (this.state.selectedStepIndex >= 0 && this.state.selectedStepIndex < this.state.steps.length) {
            return this.state.steps[this.state.selectedStepIndex];
        }
        return null;
    }

    getSelectedStepComments() {
        const step = this.getSelectedStep();
        return step ? (step.comments || []) : [];
    }

    // ------------------------------------------------------------------
    // Step property changes
    // ------------------------------------------------------------------

    onStepTitleChange(value) {
        const step = this.getSelectedStep();
        if (step) {
            step.name = value;
            this.state.dirty = true;
        }
    }

    onStepTextChange(value) {
        const step = this.getSelectedStep();
        if (step) {
            step.text = value;
            this.state.dirty = true;
        }
    }

    onStepImageChange(base64) {
        const step = this.getSelectedStep();
        if (step) {
            step.image = base64;
            this.state.dirty = true;
        }
    }

    onStepImageRemove() {
        const step = this.getSelectedStep();
        if (step) {
            step.image = false;
            this.state.dirty = true;
        }
    }

    // ------------------------------------------------------------------
    // Comments
    // ------------------------------------------------------------------

    async onAddComment(body) {
        const step = this.getSelectedStep();
        if (!step || !step.id || step.id < 0) {
            this.notification.add("Save first before adding comments.", { type: "warning" });
            return;
        }
        const comment = await this.orm.call(
            "knowledge.object", "add_step_comment",
            [this.state.objectId], { step_id: step.id, body }
        );
        if (!step.comments) step.comments = [];
        step.comments.unshift(comment);
    }

    async onDeleteComment(commentId) {
        await this.orm.call(
            "knowledge.object", "delete_step_comment",
            [this.state.objectId], { comment_id: commentId }
        );
        const step = this.getSelectedStep();
        if (step && step.comments) {
            step.comments = step.comments.filter(c => c.id !== commentId);
        }
    }

    // ------------------------------------------------------------------
    // Versions
    // ------------------------------------------------------------------

    toggleVersions() {
        this.state.showVersions = !this.state.showVersions;
    }

    async restoreVersion(versionId) {
        await this.orm.call(
            "knowledge.object", "restore_version",
            [this.state.objectId], { version_id: versionId }
        );
        await this.loadEditorData();
        this.state.showVersions = false;
        this.notification.add("Version restored", { type: "success" });
    }

    // ------------------------------------------------------------------
    // UI toggles
    // ------------------------------------------------------------------

    togglePreview() {
        this.state.showPreview = !this.state.showPreview;
    }

    onSearchChange(value) {
        this.state.searchFilter = value;
    }

    onPrint() {
        window.print();
    }

    goBack() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "knowledge.object",
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("knowledge_builder_editor", KnowledgeBuilderClient);
