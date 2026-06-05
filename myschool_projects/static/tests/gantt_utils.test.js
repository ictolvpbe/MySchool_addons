// Unit-tests voor de pure Gantt-rekenkern. Uitvoeren met:
//   cd myschool_projects && node --test static/tests/
// (de OWL-component deelt exact dezelfde functies — zie ../src/js/gantt_utils.js)
import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
    DAY_MS, parseDate, addDays, fmtDate, itemStart, itemEnd, dayIndex,
    computeRange, spanFor, barGeom, applyDragGeom, applyDragDates, computeArrows,
} from "../src/js/gantt_utils.js";

const D = (s) => parseDate(s);

// ---------------- datum-helpers ----------------
test("parseDate: geldig / leeg / ongeldig", () => {
    assert.equal(fmtDate(parseDate("2026-06-10")), "2026-06-10");
    assert.equal(parseDate(""), null);
    assert.equal(parseDate(false), null);
    assert.equal(parseDate(null), null);
    // negeert tijd-deel
    assert.equal(fmtDate(parseDate("2026-06-10 13:45:00")), "2026-06-10");
});

test("addDays + fmtDate: round-trip met maand-overgang", () => {
    assert.equal(fmtDate(addDays(D("2026-06-28"), 5)), "2026-07-03");
    assert.equal(fmtDate(addDays(D("2026-03-01"), -1)), "2026-02-28");
});

test("itemStart/itemEnd: deadline en start vallen op elkaar terug", () => {
    assert.equal(fmtDate(itemStart({ date_start: "2026-06-10", date_deadline: "2026-06-12" })), "2026-06-10");
    assert.equal(fmtDate(itemEnd({ date_start: "2026-06-10", date_deadline: "2026-06-12" })), "2026-06-12");
    // enkel deadline → start valt erop terug
    assert.equal(fmtDate(itemStart({ date_deadline: "2026-06-12" })), "2026-06-12");
    // enkel start → eind valt erop terug
    assert.equal(fmtDate(itemEnd({ date_start: "2026-06-10" })), "2026-06-10");
    assert.equal(itemStart({}), null);
});

test("dayIndex", () => {
    assert.equal(dayIndex(D("2026-06-07"), D("2026-06-07")), 0);
    assert.equal(dayIndex(D("2026-06-07"), D("2026-06-10")), 3);
});

// ---------------- venster ----------------
test("computeRange: marge -3/+5 dagen rond de items", () => {
    const items = [
        { date_start: "2026-06-10", date_deadline: "2026-06-12" },
        { date_start: "2026-06-20", date_deadline: "2026-06-25" },
    ];
    const { rangeStart, totalDays } = computeRange(items, new Date(2026, 5, 15));
    assert.equal(fmtDate(rangeStart), "2026-06-07");      // 06-10 minus 3
    // 06-25 plus 5 = 06-30 ; (06-30 - 06-07) = 23 dagen, +1 = 24
    assert.equal(totalDays, 24);
});

test("computeRange: zonder datums → rond vandaag", () => {
    const { rangeStart, totalDays } = computeRange([], new Date(2026, 5, 15));
    assert.equal(fmtDate(rangeStart), "2026-06-12");      // today - 3
    assert.equal(totalDays, 9);                           // (today+5) - (today-3) + 1
});

// ---------------- geometrie ----------------
test("spanFor: min start / max eind over alle nazaten", () => {
    const node = { children: [
        { date_start: "2026-06-10", date_deadline: "2026-06-12", children: [] },
        { date_start: "2026-06-08", date_deadline: "2026-06-20", children: [] },
    ] };
    const sp = spanFor(node);
    assert.equal(fmtDate(sp.min), "2026-06-08");
    assert.equal(fmtDate(sp.max), "2026-06-20");
});

test("barGeom: leaf met datums", () => {
    const rs = D("2026-06-07");
    const geom = barGeom(rs, 10, { item: { date_start: "2026-06-10", date_deadline: "2026-06-12" }, hasChildren: false });
    assert.deepEqual(geom, { left: 30, width: 30 });      // li=3, (5-3+1)*10
});

test("barGeom: summary gebruikt de span van zijn kinderen", () => {
    const rs = D("2026-06-07");
    const node = { children: [
        { date_start: "2026-06-08", date_deadline: "2026-06-10", children: [] },
        { date_start: "2026-06-15", date_deadline: "2026-06-20", children: [] },
    ] };
    const geom = barGeom(rs, 10, { item: node, hasChildren: true });
    assert.deepEqual(geom, { left: 10, width: 130 });     // span 06-08..06-20 → li=1, ri=13
});

test("barGeom: geen datums → null; minimale breedte van 1 dag", () => {
    const rs = D("2026-06-07");
    assert.equal(barGeom(rs, 10, { item: {}, hasChildren: false }), null);
    const oneDay = barGeom(rs, 10, { item: { date_start: "2026-06-10", date_deadline: "2026-06-10" }, hasChildren: false });
    assert.equal(oneDay.width, 10);
});

// ---------------- drag-preview ----------------
test("applyDragGeom: move verschuift, resize past breedte aan", () => {
    const base = { left: 30, width: 30 };
    assert.deepEqual(applyDragGeom(base, { mode: "move", dayDelta: 2 }, 10), { left: 50, width: 30 });
    assert.deepEqual(applyDragGeom(base, { mode: "resize-r", dayDelta: 2 }, 10), { left: 30, width: 50 });
    assert.deepEqual(applyDragGeom(base, { mode: "resize-l", dayDelta: 2 }, 10), { left: 50, width: 10 });
    // resize-l voorbij het einde → klemt op minimale breedte
    assert.deepEqual(applyDragGeom(base, { mode: "resize-l", dayDelta: 5 }, 10), { left: 50, width: 10 });
    assert.equal(applyDragGeom(null, { mode: "move", dayDelta: 2 }, 10), null);
    assert.deepEqual(applyDragGeom(base, null, 10), base);
});

// ---------------- drag → datums ----------------
test("applyDragDates: move verschuift beide datums", () => {
    const drag = { mode: "move", origStart: D("2026-06-10"), origEnd: D("2026-06-12"), dayDelta: 3, isMilestone: false };
    assert.deepEqual(applyDragDates(drag), { date_start: "2026-06-13", date_deadline: "2026-06-15" });
});

test("applyDragDates: resize-r/-l raken één datum", () => {
    const base = { origStart: D("2026-06-10"), origEnd: D("2026-06-12") };
    assert.deepEqual(
        applyDragDates({ ...base, mode: "resize-r", dayDelta: 2, isMilestone: false }),
        { date_start: "2026-06-10", date_deadline: "2026-06-14" });
    assert.deepEqual(
        applyDragDates({ ...base, mode: "resize-l", dayDelta: 1, isMilestone: false }),
        { date_start: "2026-06-11", date_deadline: "2026-06-12" });
});

test("applyDragDates: resize-l voorbij deadline klemt (start = eind)", () => {
    const drag = { mode: "resize-l", origStart: D("2026-06-10"), origEnd: D("2026-06-12"), dayDelta: 5, isMilestone: false };
    assert.deepEqual(applyDragDates(drag), { date_start: "2026-06-12", date_deadline: "2026-06-12" });
});

test("applyDragDates: milestone zet enkel de deadline", () => {
    const drag = { mode: "move", origStart: D("2026-06-12"), origEnd: D("2026-06-12"), dayDelta: 2, isMilestone: true };
    assert.deepEqual(applyDragDates(drag), { date_deadline: "2026-06-14" });
});

// ---------------- dependency-pijlen ----------------
test("computeArrows: finish-to-start tussen voorganger en opvolger", () => {
    const rows = [
        { item: { id: 1, item_type: "task", depends_on_ids: [] } },
        { item: { id: 2, item_type: "task", depends_on_ids: [1] } },
    ];
    const geom = { 1: { left: 0, width: 30 }, 2: { left: 50, width: 20 } };
    const arrows = computeArrows(rows, (row) => geom[row.item.id], 260, 30);
    assert.equal(arrows.length, 1);
    assert.equal(arrows[0].key, "1-2");
    // x1 = 260 + 0 + 30 = 290 ; y1 = 15 ; x2 = 260 + 50 = 310 ; y2 = 45 ; midx = 302
    assert.equal(arrows[0].d, "M 290 15 H 302 V 45 H 310");
    assert.equal(arrows[0].head, "304,41 310,45 304,49");
});

test("computeArrows: geen pijl als een eindpunt geen geometrie heeft", () => {
    const rows = [
        { item: { id: 1, item_type: "task", depends_on_ids: [] } },
        { item: { id: 2, item_type: "task", depends_on_ids: [1] } },
    ];
    // opvolger zonder balk (geen datums) → geen pijl
    const arrows = computeArrows(rows, (row) => (row.item.id === 1 ? { left: 0, width: 30 } : null), 260, 30);
    assert.equal(arrows.length, 0);
});

test("computeArrows: negeert dependency naar een niet-zichtbare rij", () => {
    const rows = [
        { item: { id: 2, item_type: "task", depends_on_ids: [99] } },  // 99 niet in rows
    ];
    const arrows = computeArrows(rows, () => ({ left: 0, width: 10 }), 260, 30);
    assert.equal(arrows.length, 0);
});

test("DAY_MS constante", () => {
    assert.equal(DAY_MS, 86400000);
});
