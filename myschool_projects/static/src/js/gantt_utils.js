/** @odoo-module **/
// Pure, dependency-vrije reken-helpers voor de Gantt/Timeline-view.
// Géén OWL/Odoo-imports → gedeeld door de OWL-component én los testbaar
// met `node --test` (zie static/tests/gantt_utils.test.js).

export const DAY_MS = 86400000;

/** Parse een 'YYYY-MM-DD'(...) string naar een lokale midnight-Date, of null. */
export function parseDate(s) {
    if (!s) return null;
    const [y, m, d] = String(s).slice(0, 10).split("-").map(Number);
    if (!y) return null;
    return new Date(y, m - 1, d);
}

export function addDays(date, n) {
    return new Date(date.getTime() + n * DAY_MS);
}

export function fmtDate(date) {
    const p = (x) => String(x).padStart(2, "0");
    return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

/** Effectieve start/eind van een record (deadline valt terug op start en omgekeerd). */
export function itemStart(rec) {
    return parseDate(rec.date_start) || parseDate(rec.date_deadline);
}
export function itemEnd(rec) {
    return parseDate(rec.date_deadline) || parseDate(rec.date_start);
}

export function dayIndex(rangeStart, date) {
    return Math.round((date - rangeStart) / DAY_MS);
}

/** Bepaal het zichtbare tijdsvenster uit de items (met marge), relatief tot `today`.
 *  Geeft { rangeStart: Date, totalDays: number }. */
export function computeRange(items, today) {
    let min = null, max = null;
    items.forEach((r) => {
        const s = itemStart(r), e = itemEnd(r);
        if (s && (!min || s < min)) min = s;
        if (e && (!max || e > max)) max = e;
    });
    const base = new Date(today.getTime());
    base.setHours(0, 0, 0, 0);
    if (!min) min = new Date(base);
    if (!max) max = new Date(base);
    min = new Date(min.getTime() - 3 * DAY_MS);
    max = new Date(max.getTime() + 5 * DAY_MS);
    min.setHours(0, 0, 0, 0);
    return { rangeStart: min, totalDays: Math.max(1, Math.round((max - min) / DAY_MS) + 1) };
}

/** Min start / max eind over alle nazaten van een tree-node ({children:[...]}). */
export function spanFor(node) {
    let min = null, max = null;
    const visit = (n) => {
        const s = itemStart(n), e = itemEnd(n);
        if (s && (!min || s < min)) min = s;
        if (e && (!max || e > max)) max = e;
        (n.children || []).forEach(visit);
    };
    (node.children || []).forEach(visit);
    return { min, max };
}

/** Basis-balkgeometrie {left,width} voor een rij, of null als er geen datums zijn.
 *  row = { item: node, hasChildren: bool }. */
export function barGeom(rangeStart, dayWidth, row) {
    let start, end;
    if (row.hasChildren) {
        const sp = spanFor(row.item);
        start = sp.min; end = sp.max;
    } else {
        start = itemStart(row.item); end = itemEnd(row.item);
    }
    if (!start || !end) return null;
    const li = dayIndex(rangeStart, start);
    const ri = dayIndex(rangeStart, end);
    return { left: li * dayWidth, width: Math.max(dayWidth, (ri - li + 1) * dayWidth) };
}

/** Pas een live drag-preview toe op een basisgeometrie. drag = {mode, dayDelta} of null. */
export function applyDragGeom(base, drag, dayWidth) {
    if (!base) return null;
    if (!drag) return base;
    const dx = drag.dayDelta * dayWidth;
    if (drag.mode === "move") return { left: base.left + dx, width: base.width };
    if (drag.mode === "resize-r") {
        return { left: base.left, width: Math.max(dayWidth, base.width + dx) };
    }
    if (drag.mode === "resize-l") {
        const w = Math.max(dayWidth, base.width - dx);
        return { left: base.left + (base.width - w), width: w };
    }
    return base;
}

/** Bereken de nieuwe datum-waarden uit een afgeronde drag.
 *  drag = {mode, origStart: Date, origEnd: Date, dayDelta, isMilestone}. */
export function applyDragDates(drag) {
    let ns = drag.origStart, ne = drag.origEnd;
    if (drag.mode === "move") {
        ns = addDays(drag.origStart, drag.dayDelta);
        ne = addDays(drag.origEnd, drag.dayDelta);
    } else if (drag.mode === "resize-r") {
        ne = addDays(drag.origEnd, drag.dayDelta);
        if (ne < ns) ne = ns;
    } else if (drag.mode === "resize-l") {
        ns = addDays(drag.origStart, drag.dayDelta);
        if (ns > ne) ns = ne;
    }
    return drag.isMilestone
        ? { date_deadline: fmtDate(ne) }
        : { date_start: fmtDate(ns), date_deadline: fmtDate(ne) };
}

/** Finish-to-start dependency-pijlen tussen zichtbare rijen.
 *  rows = [{item:{id,depends_on_ids}}], geomOf(row) -> {left,width}|null. */
export function computeArrows(rows, geomOf, labelW, rowH) {
    const map = {};
    rows.forEach((row, idx) => { map[row.item.id] = { idx, geom: geomOf(row) }; });
    const out = [];
    rows.forEach((row) => {
        const succ = map[row.item.id];
        if (!succ || !succ.geom) return;
        (row.item.depends_on_ids || []).forEach((pid) => {
            const pred = map[pid];
            if (!pred || !pred.geom) return;
            const x1 = labelW + pred.geom.left + pred.geom.width;
            const y1 = pred.idx * rowH + rowH / 2;
            const x2 = labelW + succ.geom.left;
            const y2 = succ.idx * rowH + rowH / 2;
            const midx = Math.max(x1 + 8, x2 - 8);
            out.push({
                key: `${pid}-${row.item.id}`,
                d: `M ${x1} ${y1} H ${midx} V ${y2} H ${x2}`,
                head: `${x2 - 6},${y2 - 4} ${x2},${y2} ${x2 - 6},${y2 + 4}`,
            });
        });
    });
    return out;
}
