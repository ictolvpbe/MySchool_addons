/** @odoo-module */

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ============================================================
// Utility: compute edge point on a shape for connection routing
// ============================================================
function shapeCenter(step) {
    const w = step.width || 140;
    const h = step.height || 60;
    if (step.step_type === 'start' || step.step_type === 'end') {
        const r = 25;
        return { x: step.x_position + r, y: step.y_position + r };
    }
    if (step.step_type === 'condition') {
        return { x: step.x_position + 50, y: step.y_position + 50 };
    }
    if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
        return { x: step.x_position + 30, y: step.y_position + 30 };
    }
    return { x: step.x_position + w / 2, y: step.y_position + h / 2 };
}

function shapeEdgePoint(step, targetCenter) {
    const center = shapeCenter(step);
    const dx = targetCenter.x - center.x;
    const dy = targetCenter.y - center.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist === 0) return center;
    const nx = dx / dist;
    const ny = dy / dist;

    if (step.step_type === 'start' || step.step_type === 'end') {
        const r = 25;
        return { x: center.x + nx * r, y: center.y + ny * r };
    }
    if (step.step_type === 'condition') {
        // Larger diamond: half-size=50
        const s = 50;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        const t = s / (ax + ay || 1);
        return { x: center.x + nx * t, y: center.y + ny * t };
    }
    if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
        // Diamond: half-size=30
        const s = 30;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        const t = s / (ax + ay || 1);
        return { x: center.x + nx * t, y: center.y + ny * t };
    }
    // Rectangle
    const hw = (step.width || 140) / 2;
    const hh = (step.height || 60) / 2;
    const scaleX = Math.abs(nx) > 0 ? hw / Math.abs(nx) : Infinity;
    const scaleY = Math.abs(ny) > 0 ? hh / Math.abs(ny) : Infinity;
    const scale = Math.min(scaleX, scaleY);
    return { x: center.x + nx * scale, y: center.y + ny * scale };
}

function computeConnectionPath(source, target) {
    const srcCenter = shapeCenter(source);
    const tgtCenter = shapeCenter(target);
    const p1 = shapeEdgePoint(source, tgtCenter);
    const p2 = shapeEdgePoint(target, srcCenter);
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist < 10) {
        return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
    }
    // Use a slight curve for better visuals
    const mx = (p1.x + p2.x) / 2;
    const my = (p1.y + p2.y) / 2;
    const perpX = -dy / dist * 0;
    const perpY = dx / dist * 0;
    // Straight line with possible future curve offset
    return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
}

function connectionMidpoint(source, target) {
    const srcCenter = shapeCenter(source);
    const tgtCenter = shapeCenter(target);
    const p1 = shapeEdgePoint(source, tgtCenter);
    const p2 = shapeEdgePoint(target, srcCenter);
    return { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
}

// ============================================================
// Toolbar Component
// ============================================================
class ProcessMapperToolbar extends Component {
    static template = "process_mapper.Toolbar";
    static props = {
        onSave: { type: Function },
        onZoomIn: { type: Function },
        onZoomOut: { type: Function },
        onFitView: { type: Function },
        onToggleGrid: { type: Function },
        gridEnabled: { type: Boolean },
        dirty: { type: Boolean },
        mapName: { type: String },
        mapState: { type: String },
    };

    onDragStart(ev, elementType) {
        ev.dataTransfer.setData("text/plain", elementType);
        ev.dataTransfer.effectAllowed = "copy";
    }
}

// ============================================================
// Field Builder Component (modal for data_fields)
// ============================================================
const FIELD_TYPES = [
    { type: 'Char', icon: 'fa-font', label: 'Text', hint: 'Short text value' },
    { type: 'Text', icon: 'fa-align-left', label: 'Long Text', hint: 'Multi-line text' },
    { type: 'Html', icon: 'fa-code', label: 'Rich Text', hint: 'HTML content' },
    { type: 'Integer', icon: 'fa-hashtag', label: 'Integer', hint: 'Whole number' },
    { type: 'Float', icon: 'fa-calculator', label: 'Decimal', hint: 'Decimal number' },
    { type: 'Monetary', icon: 'fa-eur', label: 'Monetary', hint: 'Currency amount' },
    { type: 'Boolean', icon: 'fa-toggle-on', label: 'Yes/No', hint: 'True or false' },
    { type: 'Date', icon: 'fa-calendar', label: 'Date', hint: 'Date only' },
    { type: 'Datetime', icon: 'fa-clock-o', label: 'Date & Time', hint: 'Date and time' },
    { type: 'Selection', icon: 'fa-list-ul', label: 'Selection', hint: 'Dropdown choices' },
    { type: 'Many2one', icon: 'fa-link', label: 'Many2one', hint: 'Link to one record' },
    { type: 'One2many', icon: 'fa-list', label: 'One2many', hint: 'List of child records' },
    { type: 'Many2many', icon: 'fa-exchange', label: 'Many2many', hint: 'Multiple links' },
    { type: 'Binary', icon: 'fa-file', label: 'File', hint: 'File attachment' },
    { type: 'Image', icon: 'fa-picture-o', label: 'Image', hint: 'Image upload' },
];

class FieldBuilder extends Component {
    static template = "process_mapper.FieldBuilder";
    static props = {
        dataFields: { type: String },
        onSave: { type: Function },
        onClose: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            fields: this._parseFields(this.props.dataFields),
            dragOverIndex: -1,
            paletteTab: 'types',  // 'types' or 'model'
            modelQuery: '',
            modelResults: [],
            selectedModel: null,
            modelFields: [],
            modelFieldsLoading: false,
        });
        this.nextId = 1000;
        this._searchTimeout = null;
    }

    get fieldTypes() {
        return FIELD_TYPES;
    }

    // --- Model browser ---
    switchTab(tab) {
        this.state.paletteTab = tab;
    }

    onModelQueryInput(ev) {
        this.state.modelQuery = ev.target.value;
        clearTimeout(this._searchTimeout);
        if (ev.target.value.length < 2) {
            this.state.modelResults = [];
            return;
        }
        this._searchTimeout = setTimeout(() => this._searchModels(ev.target.value), 300);
    }

    async _searchModels(query) {
        try {
            const results = await this.orm.call("process.map", "search_models", [query]);
            this.state.modelResults = results;
        } catch {
            this.state.modelResults = [];
        }
    }

    async onSelectModel(model) {
        this.state.selectedModel = model;
        this.state.modelFieldsLoading = true;
        try {
            const fields = await this.orm.call("process.map", "get_model_fields", [model.model]);
            this.state.modelFields = fields;
        } catch {
            this.state.modelFields = [];
        }
        this.state.modelFieldsLoading = false;
    }

    onBackToModelList() {
        this.state.selectedModel = null;
        this.state.modelFields = [];
    }

    onModelFieldDragStart(ev, mf) {
        const modelName = this.state.selectedModel ? this.state.selectedModel.model : '';
        const data = JSON.stringify({
            name: modelName ? `${modelName}.${mf.name}` : mf.name,
            type: mf.type,
            required: mf.required,
            relation: mf.relation || '',
            label: mf.label,
        });
        ev.dataTransfer.setData("application/pm-model-field", data);
        ev.dataTransfer.effectAllowed = "copy";
    }

    // --- Parse "name: Type (options)" text into structured array ---
    _parseFields(text) {
        if (!text || !text.trim()) return [];
        const fields = [];
        for (const line of text.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed) continue;
            const match = trimmed.match(/^(\w+)\s*:\s*(\w+)\s*(.*)$/);
            if (match) {
                const options = match[3] ? match[3].replace(/[()]/g, '').trim() : '';
                fields.push({
                    _id: this.nextId++,
                    name: match[1],
                    type: match[2],
                    required: options.includes('required'),
                    relation: '',
                    options: options.replace('required', '').replace(',', '').trim(),
                });
                // Extract relation model for relational fields
                const relMatch = options.match(/^([\w.]+)/);
                if (relMatch && ['Many2one', 'One2many', 'Many2many'].includes(match[2])) {
                    fields[fields.length - 1].relation = relMatch[1];
                    fields[fields.length - 1].options = options.replace(relMatch[1], '').replace(',', '').trim();
                }
            } else {
                fields.push({
                    _id: this.nextId++,
                    name: trimmed,
                    type: 'Char',
                    required: false,
                    relation: '',
                    options: '',
                });
            }
        }
        return fields;
    }

    // --- Serialize fields back to text ---
    _serializeFields() {
        return this.state.fields.map(f => {
            let line = `${f.name}: ${f.type}`;
            const parts = [];
            if (['Many2one', 'One2many', 'Many2many'].includes(f.type) && f.relation) {
                parts.push(f.relation);
            }
            if (f.required) parts.push('required');
            if (f.options && f.options.trim()) parts.push(f.options.trim());
            if (parts.length) line += ` (${parts.join(', ')})`;
            return line;
        }).join('\n');
    }

    // --- Drag from palette ---
    onPaletteDragStart(ev, fieldType) {
        ev.dataTransfer.setData("application/pm-field-type", fieldType.type);
        ev.dataTransfer.effectAllowed = "copy";
    }

    // --- Drop zone ---
    onDropZoneDragOver(ev, index) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
        this.state.dragOverIndex = index;
    }

    onDropZoneDragLeave(ev) {
        this.state.dragOverIndex = -1;
    }

    onDropZoneDrop(ev, index) {
        ev.preventDefault();
        this.state.dragOverIndex = -1;

        // Check if it's a model field drop
        const modelFieldData = ev.dataTransfer.getData("application/pm-model-field");
        if (modelFieldData) {
            try {
                const mf = JSON.parse(modelFieldData);
                this.state.fields.splice(index, 0, {
                    _id: this.nextId++,
                    name: mf.name,
                    type: mf.type,
                    required: mf.required || false,
                    relation: mf.relation || '',
                    options: '',
                });
            } catch { /* ignore parse errors */ }
            return;
        }

        // Otherwise it's a palette type drop
        const typeName = ev.dataTransfer.getData("application/pm-field-type");
        if (!typeName) return;
        const suggestedName = this._suggestFieldName(typeName);
        const newField = {
            _id: this.nextId++,
            name: suggestedName,
            type: typeName,
            required: false,
            relation: '',
            options: '',
        };
        this.state.fields.splice(index, 0, newField);
    }

    _suggestFieldName(typeName) {
        const base = typeName.toLowerCase();
        const nameMap = {
            'Char': 'name', 'Text': 'description', 'Html': 'body_html',
            'Integer': 'count', 'Float': 'amount', 'Monetary': 'price',
            'Boolean': 'is_active', 'Date': 'date', 'Datetime': 'datetime',
            'Selection': 'state', 'Many2one': 'partner_id', 'One2many': 'line_ids',
            'Many2many': 'tag_ids', 'Binary': 'attachment', 'Image': 'image',
        };
        let suggestion = nameMap[typeName] || base;
        const existing = new Set(this.state.fields.map(f => f.name));
        if (existing.has(suggestion)) {
            let i = 2;
            while (existing.has(`${suggestion}_${i}`)) i++;
            suggestion = `${suggestion}_${i}`;
        }
        return suggestion;
    }

    // --- Reorder via drag within list ---
    onFieldDragStart(ev, index) {
        ev.dataTransfer.setData("application/pm-field-index", String(index));
        ev.dataTransfer.effectAllowed = "move";
    }

    onFieldDropReorder(ev, targetIndex) {
        ev.preventDefault();
        const sourceIndex = parseInt(ev.dataTransfer.getData("application/pm-field-index"));
        if (isNaN(sourceIndex) || sourceIndex === targetIndex) return;
        const [moved] = this.state.fields.splice(sourceIndex, 1);
        this.state.fields.splice(targetIndex > sourceIndex ? targetIndex - 1 : targetIndex, 0, moved);
        this.state.dragOverIndex = -1;
    }

    // --- Field editing ---
    onFieldChange(index, field, ev) {
        this.state.fields[index][field] = ev.target.value;
    }

    onToggleRequired(index) {
        this.state.fields[index].required = !this.state.fields[index].required;
    }

    onRemoveField(index) {
        this.state.fields.splice(index, 1);
    }

    onMoveUp(index) {
        if (index <= 0) return;
        const [item] = this.state.fields.splice(index, 1);
        this.state.fields.splice(index - 1, 0, item);
    }

    onMoveDown(index) {
        if (index >= this.state.fields.length - 1) return;
        const [item] = this.state.fields.splice(index, 1);
        this.state.fields.splice(index + 1, 0, item);
    }

    isRelational(type) {
        return ['Many2one', 'One2many', 'Many2many'].includes(type);
    }

    // --- Save & close ---
    onSave() {
        this.props.onSave(this._serializeFields());
    }

    onClose() {
        this.props.onClose();
    }
}

// ============================================================
// Properties Panel Component
// ============================================================
class ProcessMapperProperties extends Component {
    static template = "process_mapper.PropertiesPanel";
    static components = { FieldBuilder };
    static props = {
        selectedElement: { type: Object, optional: true },
        selectedType: { type: String, optional: true },
        lanes: { type: Array },
        roles: { type: Array },
        orgs: { type: Array },
        onPropertyChange: { type: Function },
        onDelete: { type: Function },
    };

    setup() {
        this.state = useState({ showFieldBuilder: false });
    }

    onInputChange(field, ev) {
        let value = ev.target.value;
        if (field === 'lane_id' || field === 'role_id' || field === 'org_id') {
            value = value ? parseInt(value) : false;
        }
        this.props.onPropertyChange(field, value);
    }

    openFieldBuilder() {
        this.state.showFieldBuilder = true;
    }

    onFieldBuilderSave(serialized) {
        this.props.onPropertyChange('data_fields', serialized);
        this.state.showFieldBuilder = false;
    }

    onFieldBuilderClose() {
        this.state.showFieldBuilder = false;
    }
}

// ============================================================
// Canvas Component (SVG)
// ============================================================
class ProcessMapperCanvas extends Component {
    static template = "process_mapper.Canvas";
    static props = {
        steps: { type: Array },
        connections: { type: Array },
        lanes: { type: Array },
        selectedId: [{ type: Number }, { value: null }],
        selectedType: { type: String, optional: true },
        gridEnabled: { type: Boolean },
        zoom: { type: Number },
        panX: { type: Number },
        panY: { type: Number },
        onSelectElement: { type: Function },
        onMoveStep: { type: Function },
        onRenameStep: { type: Function },
        onCreateConnection: { type: Function },
        onCanvasDrop: { type: Function },
        onPan: { type: Function },
        onZoom: { type: Function },
    };

    setup() {
        this.svgRef = useRef("svgCanvas");
        this.editInputRef = useRef("editInput");
        this.dragging = null;
        this.panning = null;
        this.connecting = null;
        this.state = useState({
            rubberBandX: 0,
            rubberBandY: 0,
            showRubberBand: false,
            connectSourceId: null,
            editingStepId: null,
            editingText: '',
        });
    }

    getTransform() {
        return `translate(${this.props.panX}, ${this.props.panY}) scale(${this.props.zoom})`;
    }

    getStepClass(step) {
        let cls = "pm-step";
        if (this.props.selectedType === 'step' && this.props.selectedId === step.id) {
            cls += " pm-selected";
        }
        return cls;
    }

    getConnectionClass(conn) {
        let cls = "pm-connection-line";
        if (this.props.selectedType === 'connection' && this.props.selectedId === conn.id) {
            cls += " pm-selected";
        }
        return cls;
    }

    getConnectionPath(conn) {
        const source = this.props.steps.find(s => s.id === conn.source_step_id);
        const target = this.props.steps.find(s => s.id === conn.target_step_id);
        if (!source || !target) return "";
        return computeConnectionPath(source, target);
    }

    getConnectionLabelPos(conn) {
        const source = this.props.steps.find(s => s.id === conn.source_step_id);
        const target = this.props.steps.find(s => s.id === conn.target_step_id);
        if (!source || !target) return { x: 0, y: 0 };
        return connectionMidpoint(source, target);
    }

    // --- Connector dot positions for creating connections ---
    getConnectorDots(step) {
        const center = shapeCenter(step);
        const hw = (step.width || 140) / 2;
        const hh = (step.height || 60) / 2;
        if (step.step_type === 'start' || step.step_type === 'end') {
            const r = 25;
            return [
                { cx: center.x, cy: center.y - r, pos: 'top' },
                { cx: center.x + r, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + r, pos: 'bottom' },
                { cx: center.x - r, cy: center.y, pos: 'left' },
            ];
        }
        if (step.step_type === 'condition') {
            return [
                { cx: center.x, cy: center.y - 50, pos: 'top' },
                { cx: center.x + 50, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + 50, pos: 'bottom' },
                { cx: center.x - 50, cy: center.y, pos: 'left' },
            ];
        }
        if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
            return [
                { cx: center.x, cy: center.y - 30, pos: 'top' },
                { cx: center.x + 30, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + 30, pos: 'bottom' },
                { cx: center.x - 30, cy: center.y, pos: 'left' },
            ];
        }
        return [
            { cx: center.x, cy: step.y_position, pos: 'top' },
            { cx: step.x_position + (step.width || 140), cy: center.y, pos: 'right' },
            { cx: center.x, cy: step.y_position + (step.height || 60), pos: 'bottom' },
            { cx: step.x_position, cy: center.y, pos: 'left' },
        ];
    }

    // --- Convert screen coords to SVG coords ---
    screenToSvg(clientX, clientY) {
        const svg = this.svgRef.el;
        if (!svg) return { x: 0, y: 0 };
        const rect = svg.getBoundingClientRect();
        return {
            x: (clientX - rect.left - this.props.panX) / this.props.zoom,
            y: (clientY - rect.top - this.props.panY) / this.props.zoom,
        };
    }

    // --- Event handlers ---
    onSvgMouseDown(ev) {
        if (ev.button !== 0) return;
        if (ev.target === this.svgRef.el || ev.target.tagName === 'rect' && ev.target.classList.contains('pm-canvas-bg')) {
            // Click on empty canvas → start panning or deselect
            this.panning = { startX: ev.clientX, startY: ev.clientY, origPanX: this.props.panX, origPanY: this.props.panY };
            this.props.onSelectElement(null, null);
        }
    }

    onSvgMouseMove(ev) {
        if (this.panning) {
            const dx = ev.clientX - this.panning.startX;
            const dy = ev.clientY - this.panning.startY;
            this.props.onPan(this.panning.origPanX + dx, this.panning.origPanY + dy);
        }
        if (this.dragging) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            let x = pos.x - this.dragging.offsetX;
            let y = pos.y - this.dragging.offsetY;
            if (this.props.gridEnabled) {
                x = Math.round(x / 20) * 20;
                y = Math.round(y / 20) * 20;
            }
            this.props.onMoveStep(this.dragging.stepId, x, y);
        }
        if (this.connecting) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            this.state.rubberBandX = pos.x;
            this.state.rubberBandY = pos.y;
        }
    }

    onSvgMouseUp(ev) {
        if (this.connecting) {
            // Check if we're over a step
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const target = this._findStepAt(pos.x, pos.y);
            if (target && target.id !== this.connecting.sourceId) {
                this.props.onCreateConnection(this.connecting.sourceId, target.id);
            }
            this.connecting = null;
            this.state.showRubberBand = false;
            this.state.connectSourceId = null;
        }
        this.panning = null;
        this.dragging = null;
    }

    onStepMouseDown(ev, step) {
        ev.stopPropagation();
        if (ev.button !== 0) return;
        // Don't start drag if we're editing
        if (this.state.editingStepId === step.id) return;
        this.props.onSelectElement(step.id, 'step');
        const pos = this.screenToSvg(ev.clientX, ev.clientY);
        this.dragging = {
            stepId: step.id,
            offsetX: pos.x - step.x_position,
            offsetY: pos.y - step.y_position,
        };
    }

    onStepDblClick(ev, step) {
        ev.stopPropagation();
        ev.preventDefault();
        this.dragging = null;
        this.state.editingStepId = step.id;
        this.state.editingText = step.name;
        // Focus the input after OWL renders it
        setTimeout(() => {
            const el = this.editInputRef.el;
            if (el) {
                el.focus();
                el.select();
            }
        }, 50);
    }

    onEditInput(ev) {
        this.state.editingText = ev.target.value;
    }

    onEditKeydown(ev) {
        if (ev.key === 'Enter') {
            this._commitEdit();
        } else if (ev.key === 'Escape') {
            this._cancelEdit();
        }
    }

    onEditBlur() {
        this._commitEdit();
    }

    _commitEdit() {
        if (this.state.editingStepId !== null && this.state.editingText.trim()) {
            this.props.onRenameStep(this.state.editingStepId, this.state.editingText.trim());
        }
        this.state.editingStepId = null;
        this.state.editingText = '';
    }

    _cancelEdit() {
        this.state.editingStepId = null;
        this.state.editingText = '';
    }

    getEditBox(step) {
        const center = shapeCenter(step);
        const w = step.step_type === 'start' || step.step_type === 'end' ? 80 :
                  step.step_type === 'condition' ? 90 :
                  step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel' ? 70 :
                  (step.width || 140);
        const h = 26;
        return { x: center.x - w / 2, y: center.y - h / 2, w, h };
    }

    onConnectionClick(ev, conn) {
        ev.stopPropagation();
        this.props.onSelectElement(conn.id, 'connection');
    }

    onLaneClick(ev, lane) {
        ev.stopPropagation();
        this.props.onSelectElement(lane.id, 'lane');
    }

    onConnectorMouseDown(ev, step) {
        ev.stopPropagation();
        ev.preventDefault();
        const center = shapeCenter(step);
        this.connecting = { sourceId: step.id };
        this.state.showRubberBand = true;
        this.state.connectSourceId = step.id;
        this.state.rubberBandX = center.x;
        this.state.rubberBandY = center.y;
    }

    onWheel(ev) {
        ev.preventDefault();
        const delta = ev.deltaY > 0 ? -0.1 : 0.1;
        this.props.onZoom(delta);
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
    }

    onDrop(ev) {
        ev.preventDefault();
        const elementType = ev.dataTransfer.getData("text/plain");
        if (!elementType) return;
        const pos = this.screenToSvg(ev.clientX, ev.clientY);
        let x = pos.x;
        let y = pos.y;
        if (this.props.gridEnabled) {
            x = Math.round(x / 20) * 20;
            y = Math.round(y / 20) * 20;
        }
        this.props.onCanvasDrop(elementType, x, y);
    }

    getRubberBandPath() {
        if (!this.state.showRubberBand || !this.state.connectSourceId) return "";
        const source = this.props.steps.find(s => s.id === this.state.connectSourceId);
        if (!source) return "";
        const center = shapeCenter(source);
        return `M ${center.x} ${center.y} L ${this.state.rubberBandX} ${this.state.rubberBandY}`;
    }

    _findStepAt(x, y) {
        for (const step of this.props.steps) {
            const cx = shapeCenter(step);
            const hw = (step.width || 60) / 2;
            const hh = (step.height || 60) / 2;
            if (x >= cx.x - hw - 10 && x <= cx.x + hw + 10 &&
                y >= cx.y - hh - 10 && y <= cx.y + hh + 10) {
                return step;
            }
        }
        return null;
    }
}

// ============================================================
// Main Client Action Component
// ============================================================
class ProcessMapperClient extends Component {
    static template = "process_mapper.ProcessMapperClient";
    static components = { ProcessMapperToolbar, ProcessMapperCanvas, ProcessMapperProperties };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.nextTempId = -1;

        this.state = useState({
            mapId: null,
            mapName: "",
            mapState: "draft",
            steps: [],
            lanes: [],
            connections: [],
            selectedId: null,
            selectedType: null,
            zoom: 1.0,
            panX: 0,
            panY: 0,
            gridEnabled: true,
            dirty: false,
            loading: true,
            availableMaps: [],
            roles: [],
            orgs: [],
        });

        this._onKeydown = this._onKeydown.bind(this);

        onWillStart(async () => {
            const ctx = this.props.action && this.props.action.context;
            if (ctx && ctx.active_id) {
                this.state.mapId = ctx.active_id;
                await this.loadDiagram();
            } else {
                await this.loadMapList();
            }
            await this.loadRolesAndOrgs();
            this.state.loading = false;
        });

        onMounted(() => {
            document.addEventListener("keydown", this._onKeydown);
        });

        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeydown);
        });
    }

    // --- Data loading ---

    async loadDiagram() {
        try {
            const data = await this.orm.call("process.map", "get_diagram_data", [this.state.mapId]);
            this.state.mapName = data.name;
            this.state.mapState = data.state;
            this.state.steps = data.steps;
            this.state.lanes = data.lanes;
            this.state.connections = data.connections;
            this.state.dirty = false;
        } catch (e) {
            this.notification.add("Failed to load diagram: " + (e.message || e), { type: "danger" });
        }
    }

    async loadMapList() {
        try {
            const maps = await this.orm.searchRead("process.map", [], ["name", "state", "org_id"], { order: "name" });
            this.state.availableMaps = maps;
        } catch (e) {
            this.notification.add("Failed to load process maps", { type: "danger" });
        }
    }

    async loadRolesAndOrgs() {
        try {
            const [roles, orgs] = await Promise.all([
                this.orm.searchRead("myschool.role", [], ["name"], { limit: 200 }),
                this.orm.searchRead("myschool.org", [["is_active", "=", true]], ["name"], { limit: 200 }),
            ]);
            this.state.roles = roles;
            this.state.orgs = orgs;
        } catch {
            // Non-critical: dropdowns will be empty
        }
    }

    // --- Save ---

    async saveDiagram() {
        if (!this.state.mapId) return;
        try {
            const data = {
                lanes: this.state.lanes.map(l => ({ ...l })),
                steps: this.state.steps.map(s => ({ ...s })),
                connections: this.state.connections.map(c => ({ ...c })),
            };
            await this.orm.call("process.map", "save_diagram_data", [this.state.mapId], { data });
            await this.loadDiagram();
            this.notification.add("Diagram saved successfully", { type: "success" });
        } catch (e) {
            this.notification.add("Failed to save: " + (e.message || e), { type: "danger" });
        }
    }

    // --- Map selection ---

    async selectMap(mapId) {
        this.state.mapId = mapId;
        this.state.loading = true;
        await this.loadDiagram();
        this.state.loading = false;
    }

    // --- Element selection ---

    onSelectElement(id, type) {
        this.state.selectedId = id;
        this.state.selectedType = type;
    }

    getSelectedElement() {
        if (!this.state.selectedId || !this.state.selectedType) return null;
        if (this.state.selectedType === 'step') {
            return this.state.steps.find(s => s.id === this.state.selectedId) || null;
        }
        if (this.state.selectedType === 'connection') {
            return this.state.connections.find(c => c.id === this.state.selectedId) || null;
        }
        if (this.state.selectedType === 'lane') {
            return this.state.lanes.find(l => l.id === this.state.selectedId) || null;
        }
        return null;
    }

    // --- Step movement ---

    onMoveStep(stepId, x, y) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (step) {
            step.x_position = x;
            step.y_position = y;
            // Auto-assign lane based on y position
            const lane = this.state.lanes.find(l =>
                y >= l.y_position && y < l.y_position + l.height
            );
            step.lane_id = lane ? lane.id : false;
            this.state.dirty = true;
        }
    }

    // --- Rename step (inline edit) ---

    onRenameStep(stepId, newName) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (step) {
            step.name = newName;
            this.state.dirty = true;
        }
    }

    // --- Create connection ---

    onCreateConnection(sourceId, targetId) {
        // Check for duplicate
        const exists = this.state.connections.find(
            c => c.source_step_id === sourceId && c.target_step_id === targetId
        );
        if (exists) return;

        this.state.connections.push({
            id: this.nextTempId--,
            source_step_id: sourceId,
            target_step_id: targetId,
            label: "",
            connection_type: "sequence",
        });
        this.state.dirty = true;
    }

    // --- Drop from palette ---

    onCanvasDrop(elementType, x, y) {
        if (elementType === 'lane') {
            const lastLane = this.state.lanes.reduce(
                (max, l) => l.y_position + l.height > max ? l.y_position + l.height : max, 0
            );
            this.state.lanes.push({
                id: this.nextTempId--,
                name: 'New Lane',
                sequence: (this.state.lanes.length + 1) * 10,
                color: this._laneColors[this.state.lanes.length % this._laneColors.length],
                y_position: lastLane,
                height: 150,
                org_id: false,
                org_name: '',
                role_id: false,
                role_name: '',
            });
        } else {
            const defaults = this._stepDefaults(elementType);
            this.state.steps.push({
                id: this.nextTempId--,
                name: defaults.name,
                description: '',
                step_type: elementType,
                x_position: x,
                y_position: y,
                width: defaults.width,
                height: defaults.height,
                lane_id: false,
                role_id: false,
                role_name: '',
                responsible: '',
                system_action: '',
                data_fields: '',
            });
            // Auto-assign lane
            const newStep = this.state.steps[this.state.steps.length - 1];
            const lane = this.state.lanes.find(l =>
                y >= l.y_position && y < l.y_position + l.height
            );
            if (lane) newStep.lane_id = lane.id;
        }
        this.state.dirty = true;
    }

    _laneColors = ['#E3F2FD', '#FFF3E0', '#E8F5E9', '#FCE4EC', '#F3E5F5', '#E0F7FA'];

    _stepDefaults(stepType) {
        switch (stepType) {
            case 'start': return { name: 'Start', width: 50, height: 50 };
            case 'end': return { name: 'End', width: 50, height: 50 };
            case 'task': return { name: 'New Task', width: 140, height: 60 };
            case 'condition': return { name: 'Condition?', width: 100, height: 100 };
            case 'gateway_exclusive': return { name: 'Decision', width: 60, height: 60 };
            case 'gateway_parallel': return { name: 'Parallel', width: 60, height: 60 };
            default: return { name: 'Step', width: 140, height: 60 };
        }
    }

    // --- Property changes ---

    onPropertyChange(field, value) {
        const el = this.getSelectedElement();
        if (!el) return;
        el[field] = value;
        this.state.dirty = true;
    }

    // --- Delete ---

    onDelete() {
        if (!this.state.selectedId || !this.state.selectedType) return;
        if (this.state.selectedType === 'step') {
            // Also remove connections involving this step
            this.state.connections = this.state.connections.filter(
                c => c.source_step_id !== this.state.selectedId && c.target_step_id !== this.state.selectedId
            );
            this.state.steps = this.state.steps.filter(s => s.id !== this.state.selectedId);
        } else if (this.state.selectedType === 'connection') {
            this.state.connections = this.state.connections.filter(c => c.id !== this.state.selectedId);
        } else if (this.state.selectedType === 'lane') {
            // Unassign steps from this lane
            this.state.steps.forEach(s => {
                if (s.lane_id === this.state.selectedId) s.lane_id = false;
            });
            this.state.lanes = this.state.lanes.filter(l => l.id !== this.state.selectedId);
        }
        this.state.selectedId = null;
        this.state.selectedType = null;
        this.state.dirty = true;
    }

    // --- Zoom ---

    onZoomIn() {
        this.state.zoom = Math.min(3.0, this.state.zoom + 0.1);
    }

    onZoomOut() {
        this.state.zoom = Math.max(0.25, this.state.zoom - 0.1);
    }

    onZoomDelta(delta) {
        this.state.zoom = Math.min(3.0, Math.max(0.25, this.state.zoom + delta));
    }

    onFitView() {
        this.state.zoom = 1.0;
        this.state.panX = 0;
        this.state.panY = 0;
    }

    onToggleGrid() {
        this.state.gridEnabled = !this.state.gridEnabled;
    }

    onPan(x, y) {
        this.state.panX = x;
        this.state.panY = y;
    }

    // --- Keyboard ---

    _onKeydown(ev) {
        if (ev.key === 'Delete' || ev.key === 'Backspace') {
            // Don't delete if an input is focused
            if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA' || ev.target.tagName === 'SELECT') return;
            if (this.state.selectedId) {
                this.onDelete();
            }
        }
        if (ev.ctrlKey && ev.key === 's') {
            ev.preventDefault();
            this.saveDiagram();
        }
    }

    // --- Navigation ---

    goBackToList() {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'process.map',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }
}

registry.category("actions").add("process_mapper_canvas", ProcessMapperClient);
