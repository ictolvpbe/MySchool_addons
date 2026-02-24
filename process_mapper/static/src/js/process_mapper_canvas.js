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
        const r = (step.width || 50) / 2;
        return { x: step.x_position + r, y: step.y_position + r };
    }
    if (step.step_type === 'condition') {
        const cw = step.width || 100;
        const ch = step.height || 100;
        return { x: step.x_position + cw / 2, y: step.y_position + ch / 2 };
    }
    if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
        const gw = step.width || 60;
        const gh = step.height || 60;
        return { x: step.x_position + gw / 2, y: step.y_position + gh / 2 };
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
        const r = (step.width || 50) / 2;
        return { x: center.x + nx * r, y: center.y + ny * r };
    }
    if (step.step_type === 'condition') {
        const hw = (step.width || 100) / 2;
        const hh = (step.height || 100) / 2;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        const t = 1 / ((ax / hw + ay / hh) || 1);
        return { x: center.x + nx * t, y: center.y + ny * t };
    }
    if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
        const hw = (step.width || 60) / 2;
        const hh = (step.height || 60) / 2;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        const t = 1 / ((ax / hw + ay / hh) || 1);
        return { x: center.x + nx * t, y: center.y + ny * t };
    }
    // Rectangle (task, subprocess)
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
// Orthogonal (Manhattan) connection routing
// ============================================================

/**
 * Return the {x,y} of a port on a given side (top/right/bottom/left).
 */
function shapePortPoint(step, side) {
    const center = shapeCenter(step);
    const w = step.width || 140;
    const h = step.height || 60;

    if (step.step_type === 'start' || step.step_type === 'end') {
        const r = (step.width || 50) / 2;
        switch (side) {
            case 'top':    return { x: center.x, y: center.y - r };
            case 'right':  return { x: center.x + r, y: center.y };
            case 'bottom': return { x: center.x, y: center.y + r };
            case 'left':   return { x: center.x - r, y: center.y };
        }
    }
    if (step.step_type === 'condition') {
        const hw = (step.width || 100) / 2;
        const hh = (step.height || 100) / 2;
        switch (side) {
            case 'top':    return { x: center.x, y: center.y - hh };
            case 'right':  return { x: center.x + hw, y: center.y };
            case 'bottom': return { x: center.x, y: center.y + hh };
            case 'left':   return { x: center.x - hw, y: center.y };
        }
    }
    if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
        const hw = (step.width || 60) / 2;
        const hh = (step.height || 60) / 2;
        switch (side) {
            case 'top':    return { x: center.x, y: center.y - hh };
            case 'right':  return { x: center.x + hw, y: center.y };
            case 'bottom': return { x: center.x, y: center.y + hh };
            case 'left':   return { x: center.x - hw, y: center.y };
        }
    }
    // Rectangle (task, subprocess)
    switch (side) {
        case 'top':    return { x: center.x, y: step.y_position };
        case 'right':  return { x: step.x_position + w, y: center.y };
        case 'bottom': return { x: center.x, y: step.y_position + h };
        case 'left':   return { x: step.x_position, y: center.y };
    }
    return center;
}

/**
 * Select ports based on relative position of source→target.
 * Returns { sourceSide, targetSide }.
 */
function selectPorts(source, target) {
    const sc = shapeCenter(source);
    const tc = shapeCenter(target);
    const dx = tc.x - sc.x;
    const dy = tc.y - sc.y;

    if (Math.abs(dx) > Math.abs(dy)) {
        // Horizontal dominant
        return dx > 0
            ? { sourceSide: 'right', targetSide: 'left' }
            : { sourceSide: 'left', targetSide: 'right' };
    } else {
        // Vertical dominant
        return dy > 0
            ? { sourceSide: 'bottom', targetSide: 'top' }
            : { sourceSide: 'top', targetSide: 'bottom' };
    }
}

const GRID_SNAP = 20;
function snapToGrid(val) {
    return Math.round(val / GRID_SNAP) * GRID_SNAP;
}

/**
 * Compute orthogonal route points from source to target.
 * @param {Object} source - source step
 * @param {Object} target - target step
 * @param {Array} waypoints - user-defined waypoints [{x,y}, ...]
 * @param {string|null} sourcePort - fixed source port (top/right/bottom/left) or null for auto
 * @param {string|null} targetPort - fixed target port (top/right/bottom/left) or null for auto
 * @returns {Array} points [{x,y}, ...]
 */
function computeOrthogonalPath(source, target, waypoints, sourcePort, targetPort) {
    const auto = selectPorts(source, target);
    const sourceSide = sourcePort || auto.sourceSide;
    const targetSide = targetPort || auto.targetSide;
    const p1 = shapePortPoint(source, sourceSide);
    const p2 = shapePortPoint(target, targetSide);

    // With user-defined waypoints: connect start → waypoints → end via H/V segments
    if (waypoints && waypoints.length > 0) {
        const points = [p1];
        let prev = p1;
        for (const wp of waypoints) {
            // Alternate H then V to reach waypoint
            points.push({ x: wp.x, y: prev.y });
            points.push({ x: wp.x, y: wp.y });
            prev = wp;
        }
        // Connect last waypoint to end
        points.push({ x: p2.x, y: prev.y });
        points.push(p2);
        return points;
    }

    // Auto-route without waypoints
    const MARGIN = 30;

    if (sourceSide === 'right' && targetSide === 'left') {
        if (p2.x > p1.x + MARGIN) {
            // Simple 3-segment: H → V → H
            const midX = snapToGrid((p1.x + p2.x) / 2);
            return [p1, { x: midX, y: p1.y }, { x: midX, y: p2.y }, p2];
        } else {
            // U-route: go right, then up/down, then left
            const extX = snapToGrid(p1.x + MARGIN);
            const extX2 = snapToGrid(p2.x - MARGIN);
            const midY = snapToGrid(p1.y < p2.y ? Math.min(p1.y, p2.y) - 40 : Math.max(p1.y, p2.y) + 40);
            return [p1, { x: extX, y: p1.y }, { x: extX, y: midY }, { x: extX2, y: midY }, { x: extX2, y: p2.y }, p2];
        }
    }
    if (sourceSide === 'left' && targetSide === 'right') {
        if (p2.x < p1.x - MARGIN) {
            const midX = snapToGrid((p1.x + p2.x) / 2);
            return [p1, { x: midX, y: p1.y }, { x: midX, y: p2.y }, p2];
        } else {
            const extX = snapToGrid(p1.x - MARGIN);
            const extX2 = snapToGrid(p2.x + MARGIN);
            const midY = snapToGrid(p1.y < p2.y ? Math.min(p1.y, p2.y) - 40 : Math.max(p1.y, p2.y) + 40);
            return [p1, { x: extX, y: p1.y }, { x: extX, y: midY }, { x: extX2, y: midY }, { x: extX2, y: p2.y }, p2];
        }
    }
    if (sourceSide === 'bottom' && targetSide === 'top') {
        if (p2.y > p1.y + MARGIN) {
            const midY = snapToGrid((p1.y + p2.y) / 2);
            return [p1, { x: p1.x, y: midY }, { x: p2.x, y: midY }, p2];
        } else {
            const extY = snapToGrid(p1.y + MARGIN);
            const extY2 = snapToGrid(p2.y - MARGIN);
            const midX = snapToGrid(p1.x < p2.x ? Math.min(p1.x, p2.x) - 40 : Math.max(p1.x, p2.x) + 40);
            return [p1, { x: p1.x, y: extY }, { x: midX, y: extY }, { x: midX, y: extY2 }, { x: p2.x, y: extY2 }, p2];
        }
    }
    if (sourceSide === 'top' && targetSide === 'bottom') {
        if (p2.y < p1.y - MARGIN) {
            const midY = snapToGrid((p1.y + p2.y) / 2);
            return [p1, { x: p1.x, y: midY }, { x: p2.x, y: midY }, p2];
        } else {
            const extY = snapToGrid(p1.y - MARGIN);
            const extY2 = snapToGrid(p2.y + MARGIN);
            const midX = snapToGrid(p1.x < p2.x ? Math.min(p1.x, p2.x) - 40 : Math.max(p1.x, p2.x) + 40);
            return [p1, { x: p1.x, y: extY }, { x: midX, y: extY }, { x: midX, y: extY2 }, { x: p2.x, y: extY2 }, p2];
        }
    }

    // Fallback: simple L-route
    return [p1, { x: p2.x, y: p1.y }, p2];
}

/**
 * Convert array of points to SVG path string.
 */
function pointsToSvgPath(points) {
    if (!points || points.length === 0) return "";
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
        d += ` L ${points[i].x} ${points[i].y}`;
    }
    return d;
}

/**
 * Detect crossings between all connection paths.
 * Returns [{x, y, connIdH, connIdV}] for each crossing point.
 */
function detectCrossings(allPaths) {
    const hSegments = []; // { y, x1, x2, connId }
    const vSegments = []; // { x, y1, y2, connId }

    for (const { connId, points } of allPaths) {
        for (let i = 0; i < points.length - 1; i++) {
            const a = points[i];
            const b = points[i + 1];
            if (Math.abs(a.y - b.y) < 0.5) {
                // Horizontal segment
                hSegments.push({ y: a.y, x1: Math.min(a.x, b.x), x2: Math.max(a.x, b.x), connId });
            } else if (Math.abs(a.x - b.x) < 0.5) {
                // Vertical segment
                vSegments.push({ x: a.x, y1: Math.min(a.y, b.y), y2: Math.max(a.y, b.y), connId });
            }
        }
    }

    const crossings = [];
    for (const h of hSegments) {
        for (const v of vSegments) {
            if (h.connId === v.connId) continue;
            if (v.x > h.x1 + 1 && v.x < h.x2 - 1 && h.y > v.y1 + 1 && h.y < v.y2 - 1) {
                crossings.push({ x: v.x, y: h.y });
            }
        }
    }
    return crossings;
}

// ============================================================
// Utility: word-wrap text into lines
// ============================================================
function wrapText(text, maxWidth, fontSize) {
    if (!text) return [];
    const charWidth = fontSize * 0.6;
    const maxChars = Math.max(3, Math.floor(maxWidth / charWidth));
    const paragraphs = text.split('\n');
    const lines = [];
    for (const para of paragraphs) {
        if (!para.trim()) { lines.push(''); continue; }
        const words = para.split(/\s+/);
        let currentLine = '';
        for (const word of words) {
            if (!currentLine) {
                currentLine = word;
            } else if ((currentLine + ' ' + word).length <= maxChars) {
                currentLine += ' ' + word;
            } else {
                lines.push(currentLine);
                currentLine = word;
            }
        }
        if (currentLine) lines.push(currentLine);
    }
    return lines;
}

/**
 * Return default width/height for a step type.
 */
function defaultSize(stepType) {
    switch (stepType) {
        case 'start': case 'end': return { w: 50, h: 50 };
        case 'condition': return { w: 100, h: 100 };
        case 'gateway_exclusive': case 'gateway_parallel': return { w: 60, h: 60 };
        default: return { w: 140, h: 60 };
    }
}

// ============================================================
// Common icon list for icon picker
// ============================================================
const STEP_ICONS = [
    'fa-envelope', 'fa-file-text', 'fa-check', 'fa-times', 'fa-user',
    'fa-users', 'fa-cog', 'fa-bell', 'fa-calendar', 'fa-clock-o',
    'fa-database', 'fa-cloud-upload', 'fa-cloud-download', 'fa-paper-plane',
    'fa-pencil', 'fa-search', 'fa-lock', 'fa-unlock', 'fa-flag', 'fa-star',
];

// Default step colors by type
const DEFAULT_STEP_COLORS = {
    start: '#4CAF50',
    end: '#ffebee',
    task: '#42A5F5',
    subprocess: '#7E57C2',
    condition: '#26C6DA',
    gateway_exclusive: '#FFC107',
    gateway_parallel: '#FFC107',
};

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
        onUndo: { type: Function },
        onRedo: { type: Function },
        onAutoLayout: { type: Function },
        onToggleMinimap: { type: Function },
        onToggleVersions: { type: Function },
        onExportPNG: { type: Function },
        onExportSVG: { type: Function },
        onPrint: { type: Function },
        gridEnabled: { type: Boolean },
        dirty: { type: Boolean },
        canUndo: { type: Boolean },
        canRedo: { type: Boolean },
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
            paletteTab: 'types',
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

    onPaletteDragStart(ev, fieldType) {
        ev.dataTransfer.setData("application/pm-field-type", fieldType.type);
        ev.dataTransfer.effectAllowed = "copy";
    }

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
        const nameMap = {
            'Char': 'name', 'Text': 'description', 'Html': 'body_html',
            'Integer': 'count', 'Float': 'amount', 'Monetary': 'price',
            'Boolean': 'is_active', 'Date': 'date', 'Datetime': 'datetime',
            'Selection': 'state', 'Many2one': 'partner_id', 'One2many': 'line_ids',
            'Many2many': 'tag_ids', 'Binary': 'attachment', 'Image': 'image',
        };
        let suggestion = nameMap[typeName] || typeName.toLowerCase();
        const existing = new Set(this.state.fields.map(f => f.name));
        if (existing.has(suggestion)) {
            let i = 2;
            while (existing.has(`${suggestion}_${i}`)) i++;
            suggestion = `${suggestion}_${i}`;
        }
        return suggestion;
    }

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
        selectedCount: { type: Number },
        lanes: { type: Array },
        roles: { type: Array },
        orgs: { type: Array },
        availableMaps: { type: Array },
        onPropertyChange: { type: Function },
        onDelete: { type: Function },
    };

    setup() {
        this.state = useState({ showFieldBuilder: false, showIconPicker: false });
        this.stepIcons = STEP_ICONS;
    }

    onInputChange(field, ev) {
        let value = ev.target.value;
        if (field === 'lane_id' || field === 'role_id' || field === 'org_id' || field === 'sub_process_id') {
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

    toggleIconPicker() {
        this.state.showIconPicker = !this.state.showIconPicker;
    }

    selectIcon(icon) {
        this.props.onPropertyChange('icon', icon);
        this.state.showIconPicker = false;
    }

    clearIcon() {
        this.props.onPropertyChange('icon', '');
        this.state.showIconPicker = false;
    }
}

// ============================================================
// Minimap Component
// ============================================================
class ProcessMapperMinimap extends Component {
    static template = "process_mapper.Minimap";
    static props = {
        steps: { type: Array },
        connections: { type: Array },
        zoom: { type: Number },
        panX: { type: Number },
        panY: { type: Number },
        canvasWidth: { type: Number },
        canvasHeight: { type: Number },
        onNavigate: { type: Function },
    };

    setup() {
        this.mmWidth = 200;
        this.mmHeight = 140;
    }

    get scale() {
        // Compute scale to fit all steps into minimap
        if (this.props.steps.length === 0) return 0.05;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const s of this.props.steps) {
            const c = shapeCenter(s);
            minX = Math.min(minX, c.x - 80);
            minY = Math.min(minY, c.y - 40);
            maxX = Math.max(maxX, c.x + 80);
            maxY = Math.max(maxY, c.y + 40);
        }
        const rangeX = Math.max(maxX - minX, 200);
        const rangeY = Math.max(maxY - minY, 140);
        return Math.min(this.mmWidth / rangeX, this.mmHeight / rangeY) * 0.85;
    }

    get offset() {
        if (this.props.steps.length === 0) return { x: 0, y: 0 };
        let minX = Infinity, minY = Infinity;
        for (const s of this.props.steps) {
            const c = shapeCenter(s);
            minX = Math.min(minX, c.x - 80);
            minY = Math.min(minY, c.y - 40);
        }
        return { x: -minX * this.scale + 10, y: -minY * this.scale + 10 };
    }

    getStepRect(step) {
        const c = shapeCenter(step);
        const w = (step.width || 50) * this.scale;
        const h = (step.height || 50) * this.scale;
        return {
            x: c.x * this.scale + this.offset.x - w / 2,
            y: c.y * this.scale + this.offset.y - h / 2,
            w, h,
        };
    }

    getStepColor(step) {
        return step.color || DEFAULT_STEP_COLORS[step.step_type] || '#999';
    }

    getConnectionLine(conn) {
        const source = this.props.steps.find(s => s.id === conn.source_step_id);
        const target = this.props.steps.find(s => s.id === conn.target_step_id);
        if (!source || !target) return null;
        const points = computeOrthogonalPath(source, target, conn.waypoints || [],
            conn.source_port || null, conn.target_port || null);
        if (points.length === 0) return null;
        const scaled = points.map(p => ({
            x: p.x * this.scale + this.offset.x,
            y: p.y * this.scale + this.offset.y,
        }));
        return pointsToSvgPath(scaled);
    }

    get viewportRect() {
        // Viewport in minimap coords
        const vx = (-this.props.panX / this.props.zoom) * this.scale + this.offset.x;
        const vy = (-this.props.panY / this.props.zoom) * this.scale + this.offset.y;
        const vw = (this.props.canvasWidth / this.props.zoom) * this.scale;
        const vh = (this.props.canvasHeight / this.props.zoom) * this.scale;
        return { x: vx, y: vy, w: vw, h: vh };
    }

    onMinimapClick(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        // Convert minimap coords to canvas coords
        const canvasX = (mx - this.offset.x) / this.scale;
        const canvasY = (my - this.offset.y) / this.scale;
        // Center viewport on this point
        const newPanX = -canvasX * this.props.zoom + this.props.canvasWidth / 2;
        const newPanY = -canvasY * this.props.zoom + this.props.canvasHeight / 2;
        this.props.onNavigate(newPanX, newPanY);
    }
}

// ============================================================
// Version Panel Component
// ============================================================
class ProcessMapperVersionPanel extends Component {
    static template = "process_mapper.VersionPanel";
    static props = {
        versions: { type: Array },
        onRestore: { type: Function },
        onClose: { type: Function },
    };
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
        selectedIds: { type: Array },
        selectedType: { type: String, optional: true },
        gridEnabled: { type: Boolean },
        zoom: { type: Number },
        panX: { type: Number },
        panY: { type: Number },
        alignGuides: { type: Array },
        onSelectElement: { type: Function },
        onMultiSelect: { type: Function },
        onMoveStep: { type: Function },
        onMoveSteps: { type: Function },
        onRenameStep: { type: Function },
        onCreateConnection: { type: Function },
        onCanvasDrop: { type: Function },
        onPan: { type: Function },
        onZoom: { type: Function },
        onDragStart: { type: Function },
        onDragEnd: { type: Function },
        onOpenSubProcess: { type: Function },
        onUpdateConnectionWaypoints: { type: Function },
        onResizeStep: { type: Function },
        onResizeLane: { type: Function },
        onSnapStepToGrid: { type: Function },
        onSnapStepsToGrid: { type: Function },
        snapIndicators: { type: Array },
    };

    setup() {
        this.svgRef = useRef("svgCanvas");
        this.editInputRef = useRef("editInput");
        this.dragging = null;
        this.panning = null;
        this.connecting = null;
        this.rubberBandSelect = null;
        this.segmentDragging = null;
        this.resizing = null;
        this.laneResizing = null;
        this.state = useState({
            rubberBandX: 0,
            rubberBandY: 0,
            showRubberBand: false,
            connectSourceId: null,
            editingStepId: null,
            editingText: '',
            selectionRect: null,
        });
    }

    getTransform() {
        return `translate(${this.props.panX}, ${this.props.panY}) scale(${this.props.zoom})`;
    }

    getStepClass(step) {
        let cls = "pm-step";
        if (this.props.selectedType === 'step' && this.props.selectedIds.includes(step.id)) {
            cls += " pm-selected";
        }
        return cls;
    }

    getConnectionClass(conn) {
        let cls = "pm-connection-line";
        if (this.props.selectedType === 'connection' && this.props.selectedIds.includes(conn.id)) {
            cls += " pm-selected";
        }
        return cls;
    }

    getConnectionPoints(conn) {
        const source = this.props.steps.find(s => s.id === conn.source_step_id);
        const target = this.props.steps.find(s => s.id === conn.target_step_id);
        if (!source || !target) return [];
        return computeOrthogonalPath(source, target, conn.waypoints || [],
            conn.source_port || null, conn.target_port || null);
    }

    getConnectionPath(conn) {
        const points = this.getConnectionPoints(conn);
        return pointsToSvgPath(points);
    }

    getConnectionLabelPos(conn) {
        const points = this.getConnectionPoints(conn);
        if (points.length === 0) return { x: 0, y: 0 };
        // Midpoint of the middle segment
        const midIdx = Math.floor(points.length / 2);
        const a = points[midIdx - 1] || points[0];
        const b = points[midIdx] || points[0];
        return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    }

    getConnectionSegments(conn) {
        if (this.props.selectedType !== 'connection' || !this.props.selectedIds.includes(conn.id)) {
            return [];
        }
        const points = this.getConnectionPoints(conn);
        const segments = [];
        for (let i = 0; i < points.length - 1; i++) {
            const a = points[i];
            const b = points[i + 1];
            // Skip first and last segment (attached to shapes)
            if (i === 0 || i === points.length - 2) continue;
            const isHorizontal = Math.abs(a.y - b.y) < 0.5;
            segments.push({
                midX: (a.x + b.x) / 2,
                midY: (a.y + b.y) / 2,
                segmentIndex: i,
                isHorizontal,
            });
        }
        return segments;
    }

    getCrossingArcs() {
        const allPaths = [];
        for (const conn of this.props.connections) {
            const points = this.getConnectionPoints(conn);
            if (points.length > 0) {
                allPaths.push({ connId: conn.id, points });
            }
        }
        const crossings = detectCrossings(allPaths);
        return crossings.map(c => ({
            x: c.x,
            y: c.y,
            d: `M ${c.x} ${c.y - 6} A 6 6 0 0 1 ${c.x} ${c.y + 6}`,
        }));
    }

    onSegmentHandleMouseDown(ev, conn, segIdx) {
        ev.stopPropagation();
        ev.preventDefault();
        const points = this.getConnectionPoints(conn);
        const a = points[segIdx];
        const b = points[segIdx + 1];
        const isHorizontal = Math.abs(a.y - b.y) < 0.5;

        this.segmentDragging = {
            connId: conn.id,
            segmentIndex: segIdx,
            isHorizontal,
            startPos: this.screenToSvg(ev.clientX, ev.clientY),
        };
    }

    getStepFill(step) {
        return step.color || DEFAULT_STEP_COLORS[step.step_type] || '#42A5F5';
    }

    getStepStroke(step) {
        const strokes = {
            start: '#2E7D32', end: '#D32F2F', task: '#1565C0',
            subprocess: '#4527A0', condition: '#00838F',
            gateway_exclusive: '#F57F17', gateway_parallel: '#F57F17',
        };
        return strokes[step.step_type] || '#1565C0';
    }

    getConnectorDots(step) {
        const center = shapeCenter(step);
        if (step.step_type === 'start' || step.step_type === 'end') {
            const r = (step.width || 50) / 2;
            return [
                { cx: center.x, cy: center.y - r, pos: 'top' },
                { cx: center.x + r, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + r, pos: 'bottom' },
                { cx: center.x - r, cy: center.y, pos: 'left' },
            ];
        }
        if (step.step_type === 'condition') {
            const hw = (step.width || 100) / 2;
            const hh = (step.height || 100) / 2;
            return [
                { cx: center.x, cy: center.y - hh, pos: 'top' },
                { cx: center.x + hw, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + hh, pos: 'bottom' },
                { cx: center.x - hw, cy: center.y, pos: 'left' },
            ];
        }
        if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
            const hw = (step.width || 60) / 2;
            const hh = (step.height || 60) / 2;
            return [
                { cx: center.x, cy: center.y - hh, pos: 'top' },
                { cx: center.x + hw, cy: center.y, pos: 'right' },
                { cx: center.x, cy: center.y + hh, pos: 'bottom' },
                { cx: center.x - hw, cy: center.y, pos: 'left' },
            ];
        }
        return [
            { cx: center.x, cy: step.y_position, pos: 'top' },
            { cx: step.x_position + (step.width || 140), cy: center.y, pos: 'right' },
            { cx: center.x, cy: step.y_position + (step.height || 60), pos: 'bottom' },
            { cx: step.x_position, cy: center.y, pos: 'left' },
        ];
    }

    // --- Resize handles (visible when single step selected) ---
    getResizeHandles(step) {
        if (this.props.selectedType !== 'step' || !this.props.selectedIds.includes(step.id)) return [];
        if (this.props.selectedIds.length > 1) return [];
        const x = step.x_position;
        const y = step.y_position;
        const ds = defaultSize(step.step_type);
        const w = step.width || ds.w;
        const h = step.height || ds.h;

        if (step.step_type === 'start' || step.step_type === 'end') {
            // 4 corner handles for circle (uniform resize)
            return [
                { x: x, y: y, cursor: 'nwse-resize', handle: 'nw' },
                { x: x + w, y: y, cursor: 'nesw-resize', handle: 'ne' },
                { x: x + w, y: y + h, cursor: 'nwse-resize', handle: 'se' },
                { x: x, y: y + h, cursor: 'nesw-resize', handle: 'sw' },
            ];
        }
        if (step.step_type === 'condition' || step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
            // 4 edge handles for diamonds
            return [
                { x: x + w / 2, y: y, cursor: 'ns-resize', handle: 'n' },
                { x: x + w, y: y + h / 2, cursor: 'ew-resize', handle: 'e' },
                { x: x + w / 2, y: y + h, cursor: 'ns-resize', handle: 's' },
                { x: x, y: y + h / 2, cursor: 'ew-resize', handle: 'w' },
            ];
        }
        // Rectangle: 8 handles
        return [
            { x: x, y: y, cursor: 'nwse-resize', handle: 'nw' },
            { x: x + w / 2, y: y, cursor: 'ns-resize', handle: 'n' },
            { x: x + w, y: y, cursor: 'nesw-resize', handle: 'ne' },
            { x: x + w, y: y + h / 2, cursor: 'ew-resize', handle: 'e' },
            { x: x + w, y: y + h, cursor: 'nwse-resize', handle: 'se' },
            { x: x + w / 2, y: y + h, cursor: 'ns-resize', handle: 's' },
            { x: x, y: y + h, cursor: 'nesw-resize', handle: 'sw' },
            { x: x, y: y + h / 2, cursor: 'ew-resize', handle: 'w' },
        ];
    }

    onResizeHandleMouseDown(ev, step, handle) {
        ev.stopPropagation();
        ev.preventDefault();
        const ds = defaultSize(step.step_type);
        this.resizing = {
            stepId: step.id,
            handle,
            origX: step.x_position,
            origY: step.y_position,
            origW: step.width || ds.w,
            origH: step.height || ds.h,
            stepType: step.step_type,
            startPos: this.screenToSvg(ev.clientX, ev.clientY),
        };
    }

    // --- Multi-line text tspans ---
    getTextTspans(step) {
        const name = step.name || '';
        const center = shapeCenter(step);

        if (step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel') {
            return [];
        }

        let maxWidth, fontSize, lineHeight;
        if (step.step_type === 'start' || step.step_type === 'end') {
            const r = (step.width || 50) / 2;
            maxWidth = r * 1.4;
            fontSize = 10;
            lineHeight = 12;
        } else if (step.step_type === 'condition') {
            maxWidth = (step.width || 100) * 0.45;
            fontSize = 11;
            lineHeight = 13;
        } else {
            maxWidth = (step.width || 140) - 16;
            fontSize = 12;
            lineHeight = 14;
        }

        let yOffset = step.icon ? 10 : 0;
        const lines = wrapText(name, maxWidth, fontSize);
        const ds = defaultSize(step.step_type);
        const h = step.height || ds.h;
        const maxLines = Math.max(1, Math.floor((h - (step.icon ? 20 : 0) - 8) / lineHeight));
        const displayLines = lines.slice(0, maxLines);

        const totalHeight = displayLines.length * lineHeight;
        const startY = center.y + yOffset - totalHeight / 2 + lineHeight / 2;

        return displayLines.map((text, i) => ({
            text,
            x: center.x,
            y: startY + i * lineHeight,
            fontSize,
        }));
    }

    // --- Lane resize handle ---
    onLaneResizeMouseDown(ev, lane) {
        ev.stopPropagation();
        ev.preventDefault();
        this.laneResizing = {
            laneId: lane.id,
            origHeight: lane.height,
            startMouseY: this.screenToSvg(ev.clientX, ev.clientY).y,
        };
    }

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
            if (ev.shiftKey) {
                // Start rubber-band selection
                const pos = this.screenToSvg(ev.clientX, ev.clientY);
                this.rubberBandSelect = { startX: pos.x, startY: pos.y };
                this.state.selectionRect = { x: pos.x, y: pos.y, w: 0, h: 0 };
            } else {
                // Pan or deselect
                this.panning = { startX: ev.clientX, startY: ev.clientY, origPanX: this.props.panX, origPanY: this.props.panY };
                this.props.onSelectElement(null, null);
            }
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
            // No grid snap during drag movement (applied on release instead)
            const dx = x - this.dragging.lastX;
            const dy = y - this.dragging.lastY;
            this.dragging.lastX = x;
            this.dragging.lastY = y;

            // Multi-move: if dragging step is selected, move all selected
            if (this.props.selectedIds.includes(this.dragging.stepId) && this.props.selectedIds.length > 1) {
                this.props.onMoveSteps(this.props.selectedIds, dx, dy);
            } else {
                this.props.onMoveStep(this.dragging.stepId, x, y);
            }
            // Notify parent about drag for snap guides
            this.props.onDragStart(this.dragging.stepId, x, y);
        }
        if (this.resizing) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const r = this.resizing;
            let newX = r.origX, newY = r.origY, newW = r.origW, newH = r.origH;
            const h = r.handle;

            if (h.includes('e')) newW = pos.x - r.origX;
            if (h.includes('s')) newH = pos.y - r.origY;
            if (h.includes('w')) { newW = r.origX + r.origW - pos.x; newX = pos.x; }
            if (h.includes('n')) { newH = r.origY + r.origH - pos.y; newY = pos.y; }

            const isUniform = r.stepType === 'start' || r.stepType === 'end' ||
                              r.stepType === 'gateway_exclusive' || r.stepType === 'gateway_parallel';
            if (isUniform) {
                const size = Math.max(newW, newH);
                if (h.includes('w')) newX = r.origX + r.origW - size;
                if (h.includes('n')) newY = r.origY + r.origH - size;
                newW = size;
                newH = size;
            }

            const minW = isUniform ? 30 : (r.stepType === 'condition' ? 60 : 60);
            const minH = isUniform ? 30 : (r.stepType === 'condition' ? 60 : 30);
            if (newW < minW) { if (h.includes('w')) newX = r.origX + r.origW - minW; newW = minW; }
            if (newH < minH) { if (h.includes('n')) newY = r.origY + r.origH - minH; newH = minH; }

            if (this.props.gridEnabled) {
                newX = Math.round(newX / 20) * 20;
                newY = Math.round(newY / 20) * 20;
                newW = Math.round(newW / 20) * 20;
                newH = Math.round(newH / 20) * 20;
                if (isUniform) { newW = Math.max(newW, newH); newH = newW; }
            }

            this.props.onResizeStep(r.stepId, newX, newY, newW, newH);
        }
        if (this.laneResizing) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const dy = pos.y - this.laneResizing.startMouseY;
            let newHeight = this.laneResizing.origHeight + dy;
            if (this.props.gridEnabled) {
                newHeight = Math.round(newHeight / 20) * 20;
            }
            newHeight = Math.max(60, newHeight);
            this.props.onResizeLane(this.laneResizing.laneId, newHeight);
        }
        if (this.segmentDragging) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const conn = this.props.connections.find(c => c.id === this.segmentDragging.connId);
            if (conn) {
                const source = this.props.steps.find(s => s.id === conn.source_step_id);
                const target = this.props.steps.find(s => s.id === conn.target_step_id);
                if (source && target) {
                    const points = computeOrthogonalPath(source, target, conn.waypoints || []);
                    const segIdx = this.segmentDragging.segmentIndex;
                    if (segIdx >= 0 && segIdx < points.length - 1) {
                        // Build waypoints from the intermediate points (exclude first/last which are ports)
                        const newWaypoints = [];
                        for (let i = 1; i < points.length - 1; i++) {
                            newWaypoints.push({ ...points[i] });
                        }
                        // Adjust the segment being dragged
                        const wpIdxA = segIdx - 1; // index in waypoints array
                        const wpIdxB = segIdx;
                        if (this.segmentDragging.isHorizontal) {
                            // H-segment: move vertically
                            const newY = snapToGrid(pos.y);
                            if (wpIdxA >= 0 && wpIdxA < newWaypoints.length) newWaypoints[wpIdxA].y = newY;
                            if (wpIdxB >= 0 && wpIdxB < newWaypoints.length) newWaypoints[wpIdxB].y = newY;
                        } else {
                            // V-segment: move horizontally
                            const newX = snapToGrid(pos.x);
                            if (wpIdxA >= 0 && wpIdxA < newWaypoints.length) newWaypoints[wpIdxA].x = newX;
                            if (wpIdxB >= 0 && wpIdxB < newWaypoints.length) newWaypoints[wpIdxB].x = newX;
                        }
                        this.props.onUpdateConnectionWaypoints(conn.id, newWaypoints);
                    }
                }
            }
        }
        if (this.connecting) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            this.state.rubberBandX = pos.x;
            this.state.rubberBandY = pos.y;
        }
        if (this.rubberBandSelect) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const sx = this.rubberBandSelect.startX;
            const sy = this.rubberBandSelect.startY;
            this.state.selectionRect = {
                x: Math.min(sx, pos.x), y: Math.min(sy, pos.y),
                w: Math.abs(pos.x - sx), h: Math.abs(pos.y - sy),
            };
        }
    }

    onSvgMouseUp(ev) {
        if (this.connecting) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const target = this._findStepAt(pos.x, pos.y);
            if (target && target.id !== this.connecting.sourceId) {
                // Find nearest port on target based on mouse position
                const sides = ['top', 'right', 'bottom', 'left'];
                let bestPort = 'top';
                let bestDist = Infinity;
                for (const side of sides) {
                    const pp = shapePortPoint(target, side);
                    const d = (pp.x - pos.x) ** 2 + (pp.y - pos.y) ** 2;
                    if (d < bestDist) { bestDist = d; bestPort = side; }
                }
                this.props.onCreateConnection(
                    this.connecting.sourceId, target.id,
                    this.connecting.sourcePort, bestPort
                );
            }
            this.connecting = null;
            this.state.showRubberBand = false;
            this.state.connectSourceId = null;
        }
        if (this.dragging) {
            // Snap to grid on release
            if (this.props.gridEnabled) {
                const stepId = this.dragging.stepId;
                if (this.props.selectedIds.includes(stepId) && this.props.selectedIds.length > 1) {
                    this.props.onSnapStepsToGrid(this.props.selectedIds);
                } else {
                    this.props.onSnapStepToGrid(stepId);
                }
            }
            this.props.onDragEnd();
        }
        if (this.resizing) {
            this.resizing = null;
            this.props.onDragEnd();
        }
        if (this.laneResizing) {
            this.laneResizing = null;
            this.props.onDragEnd();
        }
        if (this.segmentDragging) {
            this.segmentDragging = null;
            this.props.onDragEnd();
        }
        if (this.rubberBandSelect && this.state.selectionRect) {
            // Select all steps within rectangle
            const r = this.state.selectionRect;
            const ids = [];
            for (const step of this.props.steps) {
                const c = shapeCenter(step);
                if (c.x >= r.x && c.x <= r.x + r.w && c.y >= r.y && c.y <= r.y + r.h) {
                    ids.push(step.id);
                }
            }
            if (ids.length > 0) {
                this.props.onMultiSelect(ids);
            }
            this.rubberBandSelect = null;
            this.state.selectionRect = null;
        }
        this.panning = null;
        this.dragging = null;
    }

    onStepMouseDown(ev, step) {
        ev.stopPropagation();
        if (ev.button !== 0) return;
        if (this.state.editingStepId === step.id) return;

        if (ev.shiftKey) {
            // Toggle multi-select
            const ids = [...this.props.selectedIds];
            const idx = ids.indexOf(step.id);
            if (idx >= 0) {
                ids.splice(idx, 1);
            } else {
                ids.push(step.id);
            }
            this.props.onMultiSelect(ids);
        } else {
            if (!this.props.selectedIds.includes(step.id)) {
                this.props.onSelectElement(step.id, 'step');
            }
        }

        const pos = this.screenToSvg(ev.clientX, ev.clientY);
        this.dragging = {
            stepId: step.id,
            offsetX: pos.x - step.x_position,
            offsetY: pos.y - step.y_position,
            lastX: step.x_position,
            lastY: step.y_position,
        };
    }

    onStepDblClick(ev, step) {
        ev.stopPropagation();
        ev.preventDefault();
        // If it's a subprocess, navigate to linked map
        if (step.step_type === 'subprocess' && step.sub_process_id) {
            this.props.onOpenSubProcess(step.sub_process_id);
            return;
        }
        this.dragging = null;
        this.state.editingStepId = step.id;
        this.state.editingText = step.name;
        setTimeout(() => {
            const el = this.editInputRef.el;
            if (el) { el.focus(); el.select(); }
        }, 50);
    }

    onEditInput(ev) {
        this.state.editingText = ev.target.value;
    }

    onEditKeydown(ev) {
        if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this._commitEdit();
        } else if (ev.key === 'Escape') {
            this._cancelEdit();
        }
        // Plain Enter inserts newline in textarea
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
        const ds = defaultSize(step.step_type);
        const sw = step.width || ds.w;
        const sh = step.height || ds.h;
        const w = step.step_type === 'start' || step.step_type === 'end'
            ? Math.max(80, sw)
            : step.step_type === 'condition'
            ? Math.max(90, sw * 0.6)
            : step.step_type === 'gateway_exclusive' || step.step_type === 'gateway_parallel'
            ? 70
            : sw;
        const h = Math.max(40, sh * 0.6);
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

    onConnectorMouseDown(ev, step, port) {
        ev.stopPropagation();
        ev.preventDefault();
        const portPoint = shapePortPoint(step, port);
        this.connecting = { sourceId: step.id, sourcePort: port };
        this.state.showRubberBand = true;
        this.state.connectSourceId = step.id;
        this.state.rubberBandX = portPoint.x;
        this.state.rubberBandY = portPoint.y;
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
        if (!this.state.showRubberBand || !this.state.connectSourceId || !this.connecting) return "";
        const source = this.props.steps.find(s => s.id === this.state.connectSourceId);
        if (!source) return "";
        const portPoint = shapePortPoint(source, this.connecting.sourcePort);
        return `M ${portPoint.x} ${portPoint.y} L ${this.state.rubberBandX} ${this.state.rubberBandY}`;
    }

    // Annotation icon position
    getAnnotationPos(step) {
        const c = shapeCenter(step);
        const ds = defaultSize(step.step_type);
        const hw = (step.width || ds.w) / 2;
        const hh = (step.height || ds.h) / 2;
        return { x: c.x + hw - 5, y: c.y - hh - 5 };
    }

    // Icon position inside step
    getIconPos(step) {
        const c = shapeCenter(step);
        return { x: c.x, y: c.y - 10 };
    }

    _findStepAt(x, y) {
        for (const step of this.props.steps) {
            const cx = shapeCenter(step);
            const ds = defaultSize(step.step_type);
            const hw = (step.width || ds.w) / 2;
            const hh = (step.height || ds.h) / 2;
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
    static components = { ProcessMapperToolbar, ProcessMapperCanvas, ProcessMapperProperties, ProcessMapperMinimap, ProcessMapperVersionPanel };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.nextTempId = -1;
        this._history = [];
        this._historyIndex = -1;
        this._clipboard = null;
        this._historyPaused = false;

        this.state = useState({
            mapId: null,
            mapName: "",
            mapState: "draft",
            steps: [],
            lanes: [],
            connections: [],
            selectedIds: [],
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
            canUndo: false,
            canRedo: false,
            showMinimap: false,
            showVersionPanel: false,
            versions: [],
            alignGuides: [],
            snapIndicators: [],
            canvasWidth: 800,
            canvasHeight: 600,
        });

        this._onKeydown = this._onKeydown.bind(this);
        this._onResize = this._onResize.bind(this);

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
            window.addEventListener("resize", this._onResize);
            this._onResize();
        });

        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeydown);
            window.removeEventListener("resize", this._onResize);
        });
    }

    _onResize() {
        const el = document.querySelector('.pm-canvas-wrapper');
        if (el) {
            this.state.canvasWidth = el.clientWidth;
            this.state.canvasHeight = el.clientHeight;
        }
    }

    // --- History (Undo/Redo) ---

    _pushHistory() {
        if (this._historyPaused) return;
        const snapshot = JSON.stringify({
            steps: this.state.steps,
            lanes: this.state.lanes,
            connections: this.state.connections,
        });
        // Trim future history
        this._history = this._history.slice(0, this._historyIndex + 1);
        this._history.push(snapshot);
        if (this._history.length > 50) {
            this._history.shift();
        }
        this._historyIndex = this._history.length - 1;
        this._updateHistoryState();
    }

    _updateHistoryState() {
        this.state.canUndo = this._historyIndex > 0;
        this.state.canRedo = this._historyIndex < this._history.length - 1;
    }

    undo() {
        if (this._historyIndex <= 0) return;
        this._historyIndex--;
        this._restoreFromHistory();
    }

    redo() {
        if (this._historyIndex >= this._history.length - 1) return;
        this._historyIndex++;
        this._restoreFromHistory();
    }

    _restoreFromHistory() {
        const data = JSON.parse(this._history[this._historyIndex]);
        this._historyPaused = true;
        this.state.steps = data.steps;
        this.state.lanes = data.lanes;
        this.state.connections = data.connections;
        this.state.dirty = true;
        this._historyPaused = false;
        this._updateHistoryState();
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
            // Initialize history
            this._history = [];
            this._historyIndex = -1;
            this._pushHistory();
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
            // Non-critical
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
        this.state.selectedIds = id !== null ? [id] : [];
        this.state.selectedType = type;
    }

    onMultiSelect(ids) {
        this.state.selectedIds = ids;
        this.state.selectedType = ids.length > 0 ? 'step' : null;
    }

    getSelectedElement() {
        if (this.state.selectedIds.length !== 1 || !this.state.selectedType) return null;
        const id = this.state.selectedIds[0];
        if (this.state.selectedType === 'step') {
            return this.state.steps.find(s => s.id === id) || null;
        }
        if (this.state.selectedType === 'connection') {
            return this.state.connections.find(c => c.id === id) || null;
        }
        if (this.state.selectedType === 'lane') {
            return this.state.lanes.find(l => l.id === id) || null;
        }
        return null;
    }

    // --- Step movement ---

    onMoveStep(stepId, x, y) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (step) {
            step.x_position = x;
            step.y_position = y;
            const lane = this.state.lanes.find(l =>
                y >= l.y_position && y < l.y_position + l.height
            );
            step.lane_id = lane ? lane.id : false;
            this.state.dirty = true;
        }
    }

    onMoveSteps(ids, dx, dy) {
        for (const id of ids) {
            const step = this.state.steps.find(s => s.id === id);
            if (step) {
                step.x_position += dx;
                step.y_position += dy;
                const lane = this.state.lanes.find(l =>
                    step.y_position >= l.y_position && step.y_position < l.y_position + l.height
                );
                step.lane_id = lane ? lane.id : false;
            }
        }
        this.state.dirty = true;
    }

    // --- Snap alignment guides ---
    onDragStart(stepId, x, y) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (!step) return;
        const guides = [];
        const center = shapeCenter(step);
        const SNAP_THRESHOLD = 5;

        for (const other of this.state.steps) {
            if (other.id === stepId) continue;
            if (this.state.selectedIds.includes(other.id)) continue;
            const oc = shapeCenter(other);

            // Horizontal center alignment
            if (Math.abs(center.y - oc.y) < SNAP_THRESHOLD) {
                guides.push({ x1: Math.min(center.x, oc.x) - 50, y1: oc.y, x2: Math.max(center.x, oc.x) + 50, y2: oc.y });
                step.y_position += (oc.y - center.y);
            }
            // Vertical center alignment
            if (Math.abs(center.x - oc.x) < SNAP_THRESHOLD) {
                guides.push({ x1: oc.x, y1: Math.min(center.y, oc.y) - 50, x2: oc.x, y2: Math.max(center.y, oc.y) + 50 });
                step.x_position += (oc.x - center.x);
            }
        }
        this.state.alignGuides = guides;
    }

    onDragEnd() {
        this.state.alignGuides = [];
        this._pushHistory();
    }

    // --- Snap to grid on release ---

    onSnapStepToGrid(stepId) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (!step) return;
        const gridSize = 20;
        const snappedX = Math.round(step.x_position / gridSize) * gridSize;
        const snappedY = Math.round(step.y_position / gridSize) * gridSize;
        if (snappedX === step.x_position && snappedY === step.y_position) return;
        step.x_position = snappedX;
        step.y_position = snappedY;
        this._showSnapIndicators([step]);
        this.state.dirty = true;
    }

    onSnapStepsToGrid(ids) {
        const gridSize = 20;
        const snapped = [];
        for (const id of ids) {
            const step = this.state.steps.find(s => s.id === id);
            if (!step) continue;
            const snappedX = Math.round(step.x_position / gridSize) * gridSize;
            const snappedY = Math.round(step.y_position / gridSize) * gridSize;
            if (snappedX !== step.x_position || snappedY !== step.y_position) {
                step.x_position = snappedX;
                step.y_position = snappedY;
                snapped.push(step);
            }
        }
        if (snapped.length > 0) {
            this._showSnapIndicators(snapped);
            this.state.dirty = true;
        }
    }

    _showSnapIndicators(steps) {
        const gridSize = 20;
        const indicators = [];
        for (const step of steps) {
            const x = step.x_position;
            const y = step.y_position;
            const ds = defaultSize(step.step_type);
            const w = step.width || ds.w;
            const h = step.height || ds.h;
            // Horizontal grid line at top edge
            indicators.push({ x1: x - 10, y1: y, x2: x + w + 10, y2: y });
            // Horizontal grid line at bottom edge
            indicators.push({ x1: x - 10, y1: y + h, x2: x + w + 10, y2: y + h });
            // Vertical grid line at left edge
            indicators.push({ x1: x, y1: y - 10, x2: x, y2: y + h + 10 });
            // Vertical grid line at right edge
            indicators.push({ x1: x + w, y1: y - 10, x2: x + w, y2: y + h + 10 });
        }
        this.state.snapIndicators = indicators;
        // Clear after a brief flash
        clearTimeout(this._snapIndicatorTimeout);
        this._snapIndicatorTimeout = setTimeout(() => {
            this.state.snapIndicators = [];
        }, 400);
    }

    // --- Rename step (inline edit) ---

    onRenameStep(stepId, newName) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (step) {
            step.name = newName;
            this.state.dirty = true;
            this._pushHistory();
        }
    }

    // --- Create connection ---

    onCreateConnection(sourceId, targetId, sourcePort, targetPort) {
        const exists = this.state.connections.find(
            c => c.source_step_id === sourceId && c.target_step_id === targetId
        );
        if (exists) return;

        // Auto-label for condition/gateway sources
        let label = "";
        const sourceStep = this.state.steps.find(s => s.id === sourceId);
        if (sourceStep && ['condition', 'gateway_exclusive'].includes(sourceStep.step_type)) {
            const outgoing = this.state.connections.filter(c => c.source_step_id === sourceId);
            if (outgoing.length === 0) label = "Yes";
            else if (outgoing.length === 1) label = "No";
        }

        this.state.connections.push({
            id: this.nextTempId--,
            source_step_id: sourceId,
            target_step_id: targetId,
            label,
            connection_type: "sequence",
            waypoints: [],
            source_port: sourcePort || false,
            target_port: targetPort || false,
        });
        this.state.dirty = true;
        this._pushHistory();
    }

    // --- Resize lane ---

    onResizeLane(laneId, newHeight) {
        const lane = this.state.lanes.find(l => l.id === laneId);
        if (!lane) return;

        newHeight = Math.max(60, newHeight);
        const delta = newHeight - lane.height;
        if (Math.abs(delta) < 1) return;

        const oldBottom = lane.y_position + lane.height;
        lane.height = newHeight;

        // Shift all lanes below this one
        for (const otherLane of this.state.lanes) {
            if (otherLane.id !== laneId && otherLane.y_position >= oldBottom - 1) {
                otherLane.y_position += delta;
            }
        }
        // Shift steps that are positioned below this lane's old bottom edge
        for (const step of this.state.steps) {
            if (step.y_position >= oldBottom - 1) {
                step.y_position += delta;
            }
        }

        this.state.dirty = true;
    }

    // --- Resize step ---

    onResizeStep(stepId, x, y, w, h) {
        const step = this.state.steps.find(s => s.id === stepId);
        if (step) {
            step.x_position = x;
            step.y_position = y;
            step.width = w;
            step.height = h;
            this.state.dirty = true;
        }
    }

    // --- Update connection waypoints ---

    onUpdateConnectionWaypoints(connId, waypoints) {
        const conn = this.state.connections.find(c => c.id === connId);
        if (conn) {
            conn.waypoints = waypoints;
            this.state.dirty = true;
        }
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
                color: '',
                icon: '',
                annotation: '',
                sub_process_id: false,
                sub_process_name: '',
            });
            const newStep = this.state.steps[this.state.steps.length - 1];
            const lane = this.state.lanes.find(l =>
                y >= l.y_position && y < l.y_position + l.height
            );
            if (lane) newStep.lane_id = lane.id;
        }
        this.state.dirty = true;
        this._pushHistory();
    }

    _laneColors = ['#E3F2FD', '#FFF3E0', '#E8F5E9', '#FCE4EC', '#F3E5F5', '#E0F7FA'];

    _stepDefaults(stepType) {
        switch (stepType) {
            case 'start': return { name: 'Start', width: 50, height: 50 };
            case 'end': return { name: 'End', width: 50, height: 50 };
            case 'task': return { name: 'New Task', width: 140, height: 60 };
            case 'subprocess': return { name: 'Sub-Process', width: 140, height: 60 };
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
        this._pushHistory();
    }

    // --- Delete ---

    onDelete() {
        if (this.state.selectedIds.length === 0 || !this.state.selectedType) return;

        if (this.state.selectedType === 'step') {
            for (const id of this.state.selectedIds) {
                this.state.connections = this.state.connections.filter(
                    c => c.source_step_id !== id && c.target_step_id !== id
                );
                this.state.steps = this.state.steps.filter(s => s.id !== id);
            }
        } else if (this.state.selectedType === 'connection') {
            for (const id of this.state.selectedIds) {
                this.state.connections = this.state.connections.filter(c => c.id !== id);
            }
        } else if (this.state.selectedType === 'lane') {
            for (const id of this.state.selectedIds) {
                this.state.steps.forEach(s => {
                    if (s.lane_id === id) s.lane_id = false;
                });
                this.state.lanes = this.state.lanes.filter(l => l.id !== id);
            }
        }
        this.state.selectedIds = [];
        this.state.selectedType = null;
        this.state.dirty = true;
        this._pushHistory();
    }

    // --- Copy/Paste ---

    _copySelected() {
        if (this.state.selectedType !== 'step' || this.state.selectedIds.length === 0) return;
        this._clipboard = this.state.steps
            .filter(s => this.state.selectedIds.includes(s.id))
            .map(s => ({ ...s }));
    }

    _pasteClipboard() {
        if (!this._clipboard || this._clipboard.length === 0) return;
        const newIds = [];
        for (const original of this._clipboard) {
            const newStep = {
                ...original,
                id: this.nextTempId--,
                x_position: original.x_position + 20,
                y_position: original.y_position + 20,
            };
            this.state.steps.push(newStep);
            newIds.push(newStep.id);
        }
        this.state.selectedIds = newIds;
        this.state.selectedType = 'step';
        this.state.dirty = true;
        this._pushHistory();
    }

    // --- Auto Layout ---

    autoLayout() {
        if (this.state.steps.length === 0) return;

        // Build adjacency from connections
        const outgoing = {};
        const incoming = {};
        for (const s of this.state.steps) {
            outgoing[s.id] = [];
            incoming[s.id] = [];
        }
        for (const c of this.state.connections) {
            if (outgoing[c.source_step_id]) outgoing[c.source_step_id].push(c.target_step_id);
            if (incoming[c.target_step_id]) incoming[c.target_step_id].push(c.source_step_id);
        }

        // Find start nodes (no incoming) or fallback to all
        let startNodes = this.state.steps.filter(s => incoming[s.id] && incoming[s.id].length === 0);
        if (startNodes.length === 0) startNodes = [this.state.steps[0]];

        // BFS to assign depth
        const depth = {};
        const queue = [];
        for (const s of startNodes) {
            depth[s.id] = 0;
            queue.push(s.id);
        }
        while (queue.length > 0) {
            const id = queue.shift();
            for (const next of (outgoing[id] || [])) {
                if (depth[next] === undefined || depth[next] < depth[id] + 1) {
                    depth[next] = depth[id] + 1;
                    queue.push(next);
                }
            }
        }

        // Assign positions: unvisited steps get depth 0
        for (const s of this.state.steps) {
            if (depth[s.id] === undefined) depth[s.id] = 0;
        }

        // Group by depth
        const byDepth = {};
        for (const s of this.state.steps) {
            const d = depth[s.id];
            if (!byDepth[d]) byDepth[d] = [];
            byDepth[d].push(s);
        }

        const xSpacing = 200;
        const ySpacing = 100;
        const startX = 100;
        const startY = 80;

        for (const [d, steps] of Object.entries(byDepth)) {
            for (let i = 0; i < steps.length; i++) {
                steps[i].x_position = startX + parseInt(d) * xSpacing;
                steps[i].y_position = startY + i * ySpacing;
            }
        }

        // Reset all connection waypoints and ports for clean auto-routing
        for (const conn of this.state.connections) {
            conn.waypoints = [];
            conn.source_port = false;
            conn.target_port = false;
        }

        this.state.dirty = true;
        this._pushHistory();
        this.notification.add("Auto-layout applied", { type: "info" });
    }

    // --- Minimap ---

    onToggleMinimap() {
        this.state.showMinimap = !this.state.showMinimap;
    }

    onMinimapNavigate(panX, panY) {
        this.state.panX = panX;
        this.state.panY = panY;
    }

    // --- Version Panel ---

    async onToggleVersions() {
        this.state.showVersionPanel = !this.state.showVersionPanel;
        if (this.state.showVersionPanel) {
            await this._loadVersions();
        }
    }

    async _loadVersions() {
        try {
            const versions = await this.orm.call("process.map", "get_versions", [this.state.mapId]);
            this.state.versions = versions;
        } catch {
            this.state.versions = [];
        }
    }

    async onRestoreVersion(versionId) {
        try {
            await this.orm.call("process.map", "restore_version", [this.state.mapId], { version_id: versionId });
            await this.loadDiagram();
            this.notification.add("Version restored", { type: "success" });
            this.state.showVersionPanel = false;
        } catch (e) {
            this.notification.add("Failed to restore version: " + (e.message || e), { type: "danger" });
        }
    }

    // --- Export ---

    onExportPNG() {
        const svg = document.querySelector('.pm-canvas');
        if (!svg) return;
        const clone = svg.cloneNode(true);
        this._inlineStyles(clone);
        // Remove UI-only elements
        clone.querySelectorAll('.pm-connector-dot, .pm-rubber-band, .pm-canvas-bg').forEach(el => {
            if (el.classList.contains('pm-canvas-bg')) {
                el.setAttribute('fill', '#ffffff');
            }
        });
        const serializer = new XMLSerializer();
        const svgStr = serializer.serializeToString(clone);
        const img = new Image();
        const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        img.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = img.width || 1200;
            canvas.height = img.height || 800;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
            URL.revokeObjectURL(url);
            const link = document.createElement('a');
            link.download = `${this.state.mapName || 'process_map'}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
        };
        img.src = url;
    }

    onExportSVG() {
        const svg = document.querySelector('.pm-canvas');
        if (!svg) return;
        const clone = svg.cloneNode(true);
        this._inlineStyles(clone);
        const serializer = new XMLSerializer();
        const svgStr = serializer.serializeToString(clone);
        const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
        const link = document.createElement('a');
        link.download = `${this.state.mapName || 'process_map'}.svg`;
        link.href = URL.createObjectURL(blob);
        link.click();
    }

    _inlineStyles(svgEl) {
        // Basic inline styling for export
        svgEl.querySelectorAll('.pm-shape-text').forEach(el => {
            el.style.fontSize = '12px';
            el.style.fontWeight = '500';
            el.style.textAnchor = 'middle';
            el.style.dominantBaseline = 'central';
        });
        svgEl.querySelectorAll('.pm-connection-line').forEach(el => {
            if (!el.style.stroke) el.style.stroke = '#555';
            if (!el.style.strokeWidth) el.style.strokeWidth = '2';
            el.style.fill = 'none';
        });
    }

    // --- Print ---

    onPrint() {
        window.print();
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

    // --- Open sub-process ---

    onOpenSubProcess(mapId) {
        this.actionService.doAction({
            type: 'ir.actions.client',
            tag: 'process_mapper_canvas',
            name: 'Sub-Process',
            context: { active_id: mapId },
        });
    }

    // --- Keyboard ---

    _onKeydown(ev) {
        // Don't handle if input focused
        if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA' || ev.target.tagName === 'SELECT') return;

        if (ev.key === 'Delete' || ev.key === 'Backspace') {
            if (this.state.selectedIds.length > 0) {
                this.onDelete();
            }
        }
        if (ev.ctrlKey && ev.key === 's') {
            ev.preventDefault();
            this.saveDiagram();
        }
        if (ev.ctrlKey && !ev.shiftKey && ev.key === 'z') {
            ev.preventDefault();
            this.undo();
        }
        if (ev.ctrlKey && ev.shiftKey && ev.key === 'Z') {
            ev.preventDefault();
            this.redo();
        }
        if (ev.ctrlKey && ev.key === 'c') {
            ev.preventDefault();
            this._copySelected();
        }
        if (ev.ctrlKey && ev.key === 'v') {
            ev.preventDefault();
            this._pasteClipboard();
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
