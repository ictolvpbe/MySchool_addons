/** @odoo-module */

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount, onWillUpdateProps } from "@odoo/owl";
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

    // Get shape half-sizes to compute actual edge-to-edge gaps
    const sds = defaultSize(source.step_type);
    const tds = defaultSize(target.step_type);
    const shw = (source.width || sds.w) / 2;
    const shh = (source.height || sds.h) / 2;
    const thw = (target.width || tds.w) / 2;
    const thh = (target.height || tds.h) / 2;

    // Compute edge-to-edge gap on each axis (negative = shapes overlap on that axis)
    const gapX = Math.abs(dx) - shw - thw;
    const gapY = Math.abs(dy) - shh - thh;

    // S-route (opposite ports, 3 segments): shapes are roughly aligned on one axis
    // Only use S-route when one axis has clear alignment (small gap or overlap)
    // and the other axis has a significant gap
    const alignedX = gapX < 20;  // shapes overlap or nearly touch horizontally
    const alignedY = gapY < 20;  // shapes overlap or nearly touch vertically

    if (alignedX && alignedY) {
        // Shapes are very close/overlapping on both axes → use dominant direction
        if (Math.abs(dx) > Math.abs(dy)) {
            return dx > 0
                ? { sourceSide: 'right', targetSide: 'left' }
                : { sourceSide: 'left', targetSide: 'right' };
        } else {
            return dy > 0
                ? { sourceSide: 'bottom', targetSide: 'top' }
                : { sourceSide: 'top', targetSide: 'bottom' };
        }
    }

    if (alignedX && !alignedY) {
        // Aligned horizontally (stacked vertically) → vertical S-route
        return dy > 0
            ? { sourceSide: 'bottom', targetSide: 'top' }
            : { sourceSide: 'top', targetSide: 'bottom' };
    }

    if (!alignedX && alignedY) {
        // Aligned vertically (side by side) → horizontal S-route
        return dx > 0
            ? { sourceSide: 'right', targetSide: 'left' }
            : { sourceSide: 'left', targetSide: 'right' };
    }

    // Both axes have significant gaps → shapes are diagonal → L-route (2 segments)
    // Pick the perpendicular port pair where both ports face toward the bend point
    // and the total path length is shortest.
    const candidates = [];
    const allSides = ['top', 'right', 'bottom', 'left'];
    for (const sp of allSides) {
        for (const tp of allSides) {
            const spH = (sp === 'left' || sp === 'right');
            const tpH = (tp === 'left' || tp === 'right');
            if (spH === tpH) continue; // need perpendicular
            const pp1 = shapePortPoint(source, sp);
            const pp2 = shapePortPoint(target, tp);
            // Compute bend point for this L-route
            const bend = spH ? { x: pp2.x, y: pp1.y } : { x: pp1.x, y: pp2.y };
            // Check that source port faces toward the bend (not away from shape)
            const srcOK = (sp === 'right' && bend.x >= pp1.x) ||
                          (sp === 'left' && bend.x <= pp1.x) ||
                          (sp === 'bottom' && bend.y >= pp1.y) ||
                          (sp === 'top' && bend.y <= pp1.y);
            // Check that target port faces toward the bend (not away from shape)
            const tgtOK = (tp === 'right' && bend.x >= pp2.x) ||
                          (tp === 'left' && bend.x <= pp2.x) ||
                          (tp === 'bottom' && bend.y >= pp2.y) ||
                          (tp === 'top' && bend.y <= pp2.y);
            const dist = Math.abs(pp1.x - pp2.x) + Math.abs(pp1.y - pp2.y);
            // Heavy penalty for ports facing away from the bend
            const penalty = (srcOK ? 0 : 10000) + (tgtOK ? 0 : 10000);
            candidates.push({ sp, tp, score: dist + penalty });
        }
    }
    candidates.sort((a, b) => a.score - b.score);
    return { sourceSide: candidates[0].sp, targetSide: candidates[0].tp };
}

const GRID_SNAP = 20;
function snapToGrid(val) {
    return Math.round(val / GRID_SNAP) * GRID_SNAP;
}

/**
 * Simplify a path by removing redundant points:
 * - Remove zero-length segments (duplicate consecutive points)
 * - Remove collinear middle points (3 points on same horizontal or vertical line)
 */
function simplifyPath(points) {
    if (points.length <= 2) return points;
    const result = [points[0]];
    for (let i = 1; i < points.length; i++) {
        const prev = result[result.length - 1];
        const cur = points[i];
        // Skip duplicate points (zero-length segments)
        if (Math.abs(prev.x - cur.x) < 0.5 && Math.abs(prev.y - cur.y) < 0.5) continue;
        // Remove collinear middle point: if prev, last-added and cur are all on same line
        if (result.length >= 2) {
            const mid = result[result.length - 1];
            const before = result[result.length - 2];
            const allSameX = Math.abs(before.x - mid.x) < 0.5 && Math.abs(mid.x - cur.x) < 0.5;
            const allSameY = Math.abs(before.y - mid.y) < 0.5 && Math.abs(mid.y - cur.y) < 0.5;
            if (allSameX || allSameY) {
                // Middle point is redundant, replace it with current
                result.pop();
            }
        }
        result.push(cur);
    }
    return result;
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
    // Use stored ports if available, otherwise auto-select based on shape positions
    const auto = selectPorts(source, target);
    let sourceSide = sourcePort || auto.sourceSide;
    let targetSide = targetPort || auto.targetSide;

    // Validate stored ports: L-routes need perpendicular ports (one H, one V)
    // If both are the same axis and it's not an opposite-ports S-route, reset to auto
    const sH = (sourceSide === 'left' || sourceSide === 'right');
    const tH = (targetSide === 'left' || targetSide === 'right');
    if (sourcePort && targetPort) {
        if (sH && tH && sourceSide !== ({ left: 'right', right: 'left' })[targetSide]) {
            sourceSide = auto.sourceSide;
            targetSide = auto.targetSide;
        }
        if (!sH && !tH && sourceSide !== ({ top: 'bottom', bottom: 'top' })[targetSide]) {
            sourceSide = auto.sourceSide;
            targetSide = auto.targetSide;
        }
    }

    const PORT_SNAP = 40;

    // When dragging (waypoints present), check ALL perpendicular port pairs
    // to find the closest L-route bend point and snap to it.
    // This works regardless of whether ports are stored — allows dragging S→L.
    if (waypoints && waypoints.length > 0) {
        const wp = waypoints[0];
        const allSides = ['top', 'right', 'bottom', 'left'];
        let bestDist = PORT_SNAP + 1;
        let bestSP = null, bestTP = null;

        for (const sp of allSides) {
            for (const tp of allSides) {
                const spH = (sp === 'left' || sp === 'right');
                const tpH = (tp === 'left' || tp === 'right');

                // Only check perpendicular (L-route) combinations
                if (spH === tpH) continue;

                const pp1 = shapePortPoint(source, sp);
                const pp2 = shapePortPoint(target, tp);

                // L-route bend point
                const bend = spH
                    ? { x: pp2.x, y: pp1.y }
                    : { x: pp1.x, y: pp2.y };

                // Skip if either port faces away from the bend (path would double back)
                const srcOK = (sp === 'right' && bend.x >= pp1.x) ||
                              (sp === 'left' && bend.x <= pp1.x) ||
                              (sp === 'bottom' && bend.y >= pp1.y) ||
                              (sp === 'top' && bend.y <= pp1.y);
                const tgtOK = (tp === 'right' && bend.x >= pp2.x) ||
                              (tp === 'left' && bend.x <= pp2.x) ||
                              (tp === 'bottom' && bend.y >= pp2.y) ||
                              (tp === 'top' && bend.y <= pp2.y);
                if (!srcOK || !tgtOK) continue;

                // Chebyshev distance (max of axis distances)
                const d = Math.max(Math.abs(wp.x - bend.x), Math.abs(wp.y - bend.y));
                if (d < bestDist) {
                    bestDist = d;
                    bestSP = sp;
                    bestTP = tp;
                }
            }
        }

        if (bestSP && bestDist <= PORT_SNAP) {
            sourceSide = bestSP;
            targetSide = bestTP;
        } else {
            // No L-route snap — fall back to S-route (opposite ports)
            const sc = shapeCenter(source);
            const tc = shapeCenter(target);
            const ddx = tc.x - sc.x;
            const ddy = tc.y - sc.y;
            if (Math.abs(ddx) > Math.abs(ddy)) {
                sourceSide = ddx > 0 ? 'right' : 'left';
                targetSide = ddx > 0 ? 'left' : 'right';
            } else {
                sourceSide = ddy > 0 ? 'bottom' : 'top';
                targetSide = ddy > 0 ? 'top' : 'bottom';
            }
        }
    }

    const p1 = shapePortPoint(source, sourceSide);
    const p2 = shapePortPoint(target, targetSide);

    const sourceH = (sourceSide === 'left' || sourceSide === 'right');
    const targetH = (targetSide === 'left' || targetSide === 'right');

    if (sourceH && targetH) {
        // Both horizontal (opposite ports) → H → V → H (3 segments)
        let midX = snapToGrid((p1.x + p2.x) / 2);
        if (waypoints && waypoints.length > 0) {
            const wpX = waypoints[0].x;
            const minX = Math.min(p1.x, p2.x) - 100;
            const maxX = Math.max(p1.x, p2.x) + 100;
            if (wpX >= minX && wpX <= maxX) midX = wpX;
        }
        return simplifyPath([p1, { x: midX, y: p1.y }, { x: midX, y: p2.y }, p2]);
    }
    if (!sourceH && !targetH) {
        // Both vertical (opposite ports) → V → H → V (3 segments)
        let midY = snapToGrid((p1.y + p2.y) / 2);
        if (waypoints && waypoints.length > 0) {
            const wpY = waypoints[0].y;
            const minY = Math.min(p1.y, p2.y) - 100;
            const maxY = Math.max(p1.y, p2.y) + 100;
            if (wpY >= minY && wpY <= maxY) midY = wpY;
        }
        return simplifyPath([p1, { x: p1.x, y: midY }, { x: p2.x, y: midY }, p2]);
    }
    if (sourceH && !targetH) {
        // L-route: horizontal first, then vertical
        return simplifyPath([p1, { x: p2.x, y: p1.y }, p2]);
    }
    // L-route: vertical first, then horizontal
    return simplifyPath([p1, { x: p1.x, y: p2.y }, p2]);
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
// Auto Layout: route connections around obstacle shapes
// ============================================================

/**
 * Return padded bounding box for a step.
 */
function shapeBBox(step, padding = 20) {
    const ds = defaultSize(step.step_type);
    const w = step.width || ds.w;
    const h = step.height || ds.h;
    return {
        x: step.x_position - padding,
        y: step.y_position - padding,
        x2: step.x_position + w + padding,
        y2: step.y_position + h + padding,
    };
}

/**
 * Check if a vertical segment at midX spanning y1..y2 intersects a bbox.
 */
function verticalSegmentIntersectsBBox(midX, y1, y2, bbox) {
    const minY = Math.min(y1, y2);
    const maxY = Math.max(y1, y2);
    return midX > bbox.x && midX < bbox.x2 && maxY > bbox.y && minY < bbox.y2;
}

/**
 * Check if a horizontal segment at midY spanning x1..x2 intersects a bbox.
 */
function horizontalSegmentIntersectsBBox(midY, x1, x2, bbox) {
    const minX = Math.min(x1, x2);
    const maxX = Math.max(x1, x2);
    return midY > bbox.y && midY < bbox.y2 && maxX > bbox.x && minX < bbox.x2;
}

/**
 * Check if the full 3-segment horizontal S-route (H→V→H) at midX is clear of all obstacles.
 * Segments: (p1x, p1y)→(midX, p1y)→(midX, p2y)→(p2x, p2y)
 */
function isHorizontalSRouteClear(midX, p1x, p1y, p2x, p2y, obstacles) {
    for (const bbox of obstacles) {
        // Vertical middle segment
        if (verticalSegmentIntersectsBBox(midX, p1y, p2y, bbox)) return false;
        // Horizontal segment from source to midX
        if (horizontalSegmentIntersectsBBox(p1y, p1x, midX, bbox)) return false;
        // Horizontal segment from midX to target
        if (horizontalSegmentIntersectsBBox(p2y, midX, p2x, bbox)) return false;
    }
    return true;
}

/**
 * Check if the full 3-segment vertical S-route (V→H→V) at midY is clear of all obstacles.
 * Segments: (p1x, p1y)→(p1x, midY)→(p2x, midY)→(p2x, p2y)
 */
function isVerticalSRouteClear(midY, p1x, p1y, p2x, p2y, obstacles) {
    for (const bbox of obstacles) {
        // Horizontal middle segment
        if (horizontalSegmentIntersectsBBox(midY, p1x, p2x, bbox)) return false;
        // Vertical segment from source to midY
        if (verticalSegmentIntersectsBBox(p1x, p1y, midY, bbox)) return false;
        // Vertical segment from midY to target
        if (verticalSegmentIntersectsBBox(p2x, midY, p2y, bbox)) return false;
    }
    return true;
}

/**
 * Find a clear X position for the middle vertical segment of a horizontal S-route.
 * Uses obstacle bbox edges as candidate positions (just outside each obstacle).
 */
function findClearMidX(defaultMidX, p1x, p1y, p2x, p2y, obstacles) {
    // Collect candidate X positions from obstacle bbox edges
    const candidates = [];
    for (const bbox of obstacles) {
        candidates.push(bbox.x - 1);   // just left of obstacle (bbox already has padding)
        candidates.push(bbox.x2 + 1);  // just right of obstacle
    }

    // Constrain to the range that computeOrthogonalPath will accept
    const rangeMin = Math.min(p1x, p2x) - 100;
    const rangeMax = Math.max(p1x, p2x) + 100;
    const valid = candidates.filter(x => x >= rangeMin && x <= rangeMax);

    // Sort by distance to defaultMidX (prefer closest alternative)
    valid.sort((a, b) => Math.abs(a - defaultMidX) - Math.abs(b - defaultMidX));

    for (const candX of valid) {
        if (isHorizontalSRouteClear(candX, p1x, p1y, p2x, p2y, obstacles)) {
            return candX;
        }
    }
    return defaultMidX; // fallback
}

/**
 * Find a clear Y position for the middle horizontal segment of a vertical S-route.
 * Uses obstacle bbox edges as candidate positions.
 */
function findClearMidY(defaultMidY, p1x, p1y, p2x, p2y, obstacles) {
    // Collect candidate Y positions from obstacle bbox edges
    const candidates = [];
    for (const bbox of obstacles) {
        candidates.push(bbox.y - 1);    // just above obstacle (bbox already has padding)
        candidates.push(bbox.y2 + 1);   // just below obstacle
    }

    // Constrain to the range that computeOrthogonalPath will accept
    const rangeMin = Math.min(p1y, p2y) - 100;
    const rangeMax = Math.max(p1y, p2y) + 100;
    const valid = candidates.filter(y => y >= rangeMin && y <= rangeMax);

    // Sort by distance to defaultMidY (prefer closest alternative)
    valid.sort((a, b) => Math.abs(a - defaultMidY) - Math.abs(b - defaultMidY));

    for (const candY of valid) {
        if (isVerticalSRouteClear(candY, p1x, p1y, p2x, p2y, obstacles)) {
            return candY;
        }
    }
    return defaultMidY; // fallback
}

/**
 * For each S-route connection, check if the default middle segment
 * intersects any non-source/non-target shape; if so, set waypoints to route around.
 */
function routeAroundObstacles(steps, connections) {
    const stepsById = {};
    for (const s of steps) stepsById[s.id] = s;

    for (const conn of connections) {
        const source = stepsById[conn.source_step_id];
        const target = stepsById[conn.target_step_id];
        if (!source || !target) continue;

        const sourceSide = conn.source_port;
        const targetSide = conn.target_port;
        if (!sourceSide || !targetSide) continue;

        const sourceH = (sourceSide === 'left' || sourceSide === 'right');
        const targetH = (targetSide === 'left' || targetSide === 'right');

        // Only process S-routes (both ports on same axis → 3 segments)
        if (sourceH !== targetH) continue;

        const p1 = shapePortPoint(source, sourceSide);
        const p2 = shapePortPoint(target, targetSide);

        // Build obstacle list: all shapes except source and target
        const obstacles = [];
        for (const s of steps) {
            if (s.id === conn.source_step_id || s.id === conn.target_step_id) continue;
            obstacles.push(shapeBBox(s));
        }
        if (obstacles.length === 0) continue;

        if (sourceH && targetH) {
            // Horizontal S-route: H → V → H
            const defaultMidX = (p1.x + p2.x) / 2;
            if (!isHorizontalSRouteClear(defaultMidX, p1.x, p1.y, p2.x, p2.y, obstacles)) {
                const clearX = findClearMidX(defaultMidX, p1.x, p1.y, p2.x, p2.y, obstacles);
                if (clearX !== defaultMidX) {
                    conn.waypoints = [{ x: clearX, y: (p1.y + p2.y) / 2 }];
                }
            }
        } else {
            // Vertical S-route: V → H → V
            const defaultMidY = (p1.y + p2.y) / 2;
            if (!isVerticalSRouteClear(defaultMidY, p1.x, p1.y, p2.x, p2.y, obstacles)) {
                const clearY = findClearMidY(defaultMidY, p1.x, p1.y, p2.x, p2.y, obstacles);
                if (clearY !== defaultMidY) {
                    conn.waypoints = [{ x: (p1.x + p2.x) / 2, y: clearY }];
                }
            }
        }
    }
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
    static template = "myschool_processcomposer.Toolbar";
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
        onExportDrawio: { type: Function },
        onImportDrawio: { type: Function },
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
    { type: 'Text', icon: 'fa-pencil-square-o', label: 'Notebook', hint: 'Long text'}
];

const LAYOUT_ELEMENTS = [
    { type: 'group', icon: 'fa-columns', label: 'Group', hint: 'Multi-column section' },
    { type: 'notebook', icon: 'fa-folder-o', label: 'Tab', hint: 'Tabbed sections' },
    { type: 'page', icon: 'fa-file-o', label: 'Page', hint: 'Page inside a notebook' },
    { type: 'separator', icon: 'fa-minus', label: 'Separator', hint: 'Section title with divider' },
];

// Type maps for converting between display (Char) and DB (char) types
const TTYPE_MAP = {
    'Char': 'char', 'Text': 'text', 'Html': 'html',
    'Integer': 'integer', 'Float': 'float', 'Monetary': 'monetary',
    'Boolean': 'boolean', 'Date': 'date', 'Datetime': 'datetime',
    'Selection': 'selection', 'Many2one': 'many2one', 'One2many': 'one2many',
    'Many2many': 'many2many', 'Binary': 'binary', 'Image': 'image',
};
const TTYPE_MAP_REVERSE = Object.fromEntries(
    Object.entries(TTYPE_MAP).map(([k, v]) => [v, k])
);

class FieldWidgetPreview extends Component {
    static template = "myschool_processcomposer.FieldWidgetPreview";
    static props = {
        field: { type: Object },
    };
}

class FieldBuilder extends Component {
    static template = "myschool_processcomposer.FieldBuilder";
    static components = { FieldWidgetPreview };
    static props = {
        dataFields: { type: String },
        fieldRecords: { type: Array, optional: true },
        formLayout: { type: String, optional: true },
        onSave: { type: Function },
        onClose: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.nextId = 1000;
        this._nodeIdCounter = 1;
        this._searchTimeout = null;
        const fr = this.props.fieldRecords;
        // Remember which DB field IDs existed when we opened, so we can detect deletions at save time
        this._originalFieldIds = new Set((fr || []).filter(r => r.id).map(r => r.id));
        const initialFields = (fr && fr.length > 0)
            ? this._loadFieldRecords(fr)
            : this._parseFields(this.props.dataFields);
        const layout = this._initLayout(initialFields);
        this.state = useState({
            fields: initialFields,
            layout: layout,
            dragOverNodeId: null,
            dragOverIndex: -1,
            isDragging: false,
            selectedFieldId: null,
            activeNotebookPages: {},
            paletteTab: 'types',
            modelQuery: '',
            modelResults: [],
            selectedModel: null,
            modelFields: [],
            modelFieldsLoading: false,
        });
    }

    // ====== Layout tree helpers ======

    _genNodeId() {
        return `n${this._nodeIdCounter++}`;
    }

    _initLayout(fields) {
        const raw = this.props.formLayout;
        if (raw) {
            try {
                const tree = this._deserializeLayout(JSON.parse(raw), fields);
                if (tree) return tree;
            } catch { /* fall through to default */ }
        }
        return this._buildDefaultLayout(fields);
    }

    _buildDefaultLayout(fields) {
        const sheet = { _nodeId: this._genNodeId(), type: 'sheet', children: [] };
        if (fields.length === 0) return sheet;

        const relational = fields.filter(f => ['One2many', 'Many2many'].includes(f.type));
        const normal = fields.filter(f => !['One2many', 'Many2many'].includes(f.type));

        if (normal.length > 0) {
            const group = { _nodeId: this._genNodeId(), type: 'group', cols: 2, children: [] };
            const left = { _nodeId: this._genNodeId(), type: 'group_column', children: [] };
            const right = { _nodeId: this._genNodeId(), type: 'group_column', children: [] };
            const mid = Math.ceil(normal.length / 2);
            for (let i = 0; i < normal.length; i++) {
                const col = i < mid ? left : right;
                col.children.push({ _nodeId: this._genNodeId(), type: 'field', fieldId: normal[i]._id });
            }
            group.children.push(left, right);
            sheet.children.push(group);
        }

        if (relational.length > 0) {
            const nb = { _nodeId: this._genNodeId(), type: 'notebook', children: [] };
            for (const f of relational) {
                const page = {
                    _nodeId: this._genNodeId(), type: 'page',
                    label: f.field_description || f.name, name: f.name,
                    children: [{ _nodeId: this._genNodeId(), type: 'field', fieldId: f._id }],
                };
                nb.children.push(page);
            }
            sheet.children.push(nb);
        }
        return sheet;
    }

    _findNode(nodeId, root, parent) {
        root = root || this.state.layout;
        if (root._nodeId === nodeId) return { parent, node: root, index: -1 };
        if (root.children) {
            for (let i = 0; i < root.children.length; i++) {
                if (root.children[i]._nodeId === nodeId) {
                    return { parent: root, node: root.children[i], index: i };
                }
                const found = this._findNode(nodeId, root.children[i], root);
                if (found) return found;
            }
        }
        return null;
    }

    _allFieldNodeIds(root) {
        const ids = [];
        root = root || this.state.layout;
        if (root.type === 'field' && root.fieldId) ids.push(root.fieldId);
        if (root.children) {
            for (const c of root.children) ids.push(...this._allFieldNodeIds(c));
        }
        return ids;
    }

    get unplacedFields() {
        const placed = new Set(this._allFieldNodeIds());
        return this.state.fields.filter(f => !placed.has(f._id));
    }

    get layoutElements() {
        return LAYOUT_ELEMENTS;
    }

    getColLabel(index, total) {
        if (total <= 2) return index === 0 ? 'Left' : 'Right';
        return `Col ${index + 1}`;
    }

    getGroupGridStyle(group) {
        const cols = group.cols || group.children.length || 2;
        return `grid-template-columns: repeat(${cols}, 1fr)`;
    }

    getFieldById(fieldId) {
        return this.state.fields.find(f => f._id === fieldId) || null;
    }

    _isValidDrop(itemType, parentType) {
        const rules = {
            sheet: ['group', 'notebook', 'separator', 'field'],
            group: ['group_column'],
            group_column: ['field'],
            notebook: ['page'],
            page: ['group', 'notebook', 'separator', 'field'],
        };
        return (rules[parentType] || []).includes(itemType);
    }

    // Notebook page management
    isActiveNotebookPage(notebookNodeId, pageNodeId) {
        const active = this.state.activeNotebookPages[notebookNodeId];
        if (active) return active === pageNodeId;
        // Default: first page
        const nb = this._findNode(notebookNodeId);
        if (nb && nb.node.children && nb.node.children.length > 0) {
            return nb.node.children[0]._nodeId === pageNodeId;
        }
        return false;
    }

    onSelectNotebookPage(notebookNodeId, pageNodeId) {
        this.state.activeNotebookPages[notebookNodeId] = pageNodeId;
    }

    onAddPage(notebookNodeId) {
        const nb = this._findNode(notebookNodeId);
        if (!nb) return;
        const page = {
            _nodeId: this._genNodeId(), type: 'page',
            label: `Page ${nb.node.children.length + 1}`, name: `page_${nb.node.children.length + 1}`,
            children: [],
        };
        nb.node.children.push(page);
        this.state.activeNotebookPages[notebookNodeId] = page._nodeId;
    }

    onRemovePage(notebookNodeId, pageNodeId) {
        const nb = this._findNode(notebookNodeId);
        if (!nb || !nb.node.children) return;
        // Don't delete the last page
        if (nb.node.children.length <= 1) return;
        const idx = nb.node.children.findIndex(p => p._nodeId === pageNodeId);
        if (idx === -1) return;
        nb.node.children.splice(idx, 1);
        // If the deleted page was active, switch to the nearest page
        if (this.state.activeNotebookPages[notebookNodeId] === pageNodeId) {
            const newIdx = Math.min(idx, nb.node.children.length - 1);
            this.state.activeNotebookPages[notebookNodeId] = nb.node.children[newIdx]._nodeId;
        }
    }

    onRemoveNode(nodeId) {
        const found = this._findNode(nodeId);
        if (!found || !found.parent) return;
        found.parent.children.splice(found.index, 1);
    }

    onAddGroupColumn(groupNodeId) {
        const found = this._findNode(groupNodeId);
        if (!found || found.node.type !== 'group') return;
        const cols = (found.node.cols || 2);
        if (cols >= 4) return; // max 4 columns
        found.node.cols = cols + 1;
        found.node.children.push({ _nodeId: this._genNodeId(), type: 'group_column', children: [] });
    }

    onRemoveGroupColumn(groupNodeId) {
        const found = this._findNode(groupNodeId);
        if (!found || found.node.type !== 'group') return;
        const cols = (found.node.cols || 2);
        if (cols <= 1) return; // min 1 column
        found.node.cols = cols - 1;
        // Remove last column; move its fields to the previous column
        const removed = found.node.children.pop();
        if (removed && removed.children && removed.children.length > 0) {
            const lastCol = found.node.children[found.node.children.length - 1];
            lastCol.children.push(...removed.children);
        }
    }

    _moveNode(nodeId, targetParentNodeId, targetIndex) {
        const found = this._findNode(nodeId);
        if (!found || !found.parent) return;
        const sourceParent = found.parent;
        const sourceIndex = found.index;
        // Remove from old location
        sourceParent.children.splice(sourceIndex, 1);
        // Insert at new location
        const target = this._findNode(targetParentNodeId);
        if (!target) return;
        // Adjust index if moving within the same parent and source was before target
        let adjustedIndex = targetIndex;
        if (target.node === sourceParent && sourceIndex < targetIndex) {
            adjustedIndex--;
        }
        target.node.children.splice(adjustedIndex, 0, found.node);
    }

    // Serialization: convert layout tree to portable JSON (field names, not IDs)
    _serializeLayout(root) {
        root = root || this.state.layout;
        const node = { type: root.type };
        if (root.label) node.label = root.label;
        if (root.name) node.name = root.name;
        if (root.type === 'group' && root.cols) node.cols = root.cols;
        if (root.type === 'field' && root.fieldId) {
            const f = this.getFieldById(root.fieldId);
            node.fieldName = f ? f.name : '';
        }
        if (root.children) {
            node.children = root.children.map(c => this._serializeLayout(c));
        }
        return node;
    }

    _deserializeLayout(data, fields) {
        if (!data || !data.type) return null;
        const node = { _nodeId: this._genNodeId(), type: data.type };
        if (data.label) node.label = data.label;
        if (data.name) node.name = data.name;
        if (data.type === 'group' && data.cols) node.cols = data.cols;
        if (data.type === 'field' && data.fieldName) {
            const f = fields.find(fd => fd.name === data.fieldName);
            node.fieldId = f ? f._id : null;
            if (!node.fieldId) return null; // skip fields no longer present
        }
        if (data.children) {
            node.children = data.children
                .map(c => this._deserializeLayout(c, fields))
                .filter(Boolean);
        }
        return node;
    }

    // Insert a new field into the layout at a given parent + index
    _insertFieldNode(fieldId, parentNodeId, index) {
        const parent = this._findNode(parentNodeId);
        if (!parent) return;
        const parentType = parent.node.type;

        if (parentType === 'sheet' || parentType === 'page' || parentType === 'group_column') {
            parent.node.children.splice(index, 0, {
                _nodeId: this._genNodeId(), type: 'field', fieldId,
            });
        }
    }

    _insertLayoutElement(elemType, parentNodeId, index) {
        const parent = this._findNode(parentNodeId);
        if (!parent) return;
        let node;
        switch (elemType) {
            case 'group':
                node = { _nodeId: this._genNodeId(), type: 'group', cols: 2, children: [
                    { _nodeId: this._genNodeId(), type: 'group_column', children: [] },
                    { _nodeId: this._genNodeId(), type: 'group_column', children: [] },
                ] };
                break;
            case 'notebook':
                node = { _nodeId: this._genNodeId(), type: 'notebook', children: [
                    { _nodeId: this._genNodeId(), type: 'page', label: 'Page 1', name: 'page_1', children: [] },
                ] };
                break;
            case 'page': {
                if (parent.node.type !== 'notebook') return; // pages only inside notebooks
                const pn = parent.node.children.length + 1;
                node = { _nodeId: this._genNodeId(), type: 'page', label: `Page ${pn}`, name: `page_${pn}`, children: [] };
                break;
            }
            case 'separator':
                node = { _nodeId: this._genNodeId(), type: 'separator', label: 'Section' };
                break;
            default:
                return;
        }
        parent.node.children.splice(index, 0, node);
    }

    // ====== Drag & Drop for Layout ======

    onSheetDragEnd() {
        this.state.isDragging = false;
        this.state.dragOverNodeId = null;
    }

    onLayoutDragOver(ev, parentNodeId, index) {
        ev.preventDefault();
        this.state.dragOverNodeId = `${parentNodeId}:${index}`;
    }

    onLayoutDragLeave(ev) {
        this.state.dragOverNodeId = null;
    }

    isDragOver(parentNodeId, index) {
        return this.state.dragOverNodeId === `${parentNodeId}:${index}`;
    }

    onLayoutDrop(ev, parentNodeId, index) {
        ev.preventDefault();
        this.state.dragOverNodeId = null;
        this.state.isDragging = false;

        // 0. Unplaced field being dropped back
        if (this._handleUnplacedFieldDrop(ev, parentNodeId, index)) return;

        // 1. Layout element from palette
        const layoutElemType = ev.dataTransfer.getData("application/pm-layout-element");
        if (layoutElemType) {
            this._insertLayoutElement(layoutElemType, parentNodeId, index);
            return;
        }

        // 2. Existing layout node being moved
        const moveNodeId = ev.dataTransfer.getData("application/pm-layout-node");
        if (moveNodeId) {
            this._moveNode(moveNodeId, parentNodeId, index);
            return;
        }

        // 3. Model field from model browser
        const modelFieldData = ev.dataTransfer.getData("application/pm-model-field");
        if (modelFieldData) {
            try {
                const mf = JSON.parse(modelFieldData);
                const newField = this._makeDefaultField({
                    name: mf.name,
                    type: mf.type,
                    required: mf.required || false,
                    relation: mf.relation || '',
                    field_description: mf.label || '',
                    readonly: mf.readonly || false,
                    store: mf.store !== undefined ? mf.store : true,
                    index: mf.index || '',
                    copy: mf.copy !== undefined ? mf.copy : true,
                    translate: mf.translate || false,
                    relation_field: mf.relation_field || '',
                    relation_table: mf.relation_table || '',
                    domain: mf.domain || '[]',
                    on_delete: mf.on_delete || 'set null',
                    help_text: mf.help || '',
                    groups: mf.groups || '',
                    size: mf.size || 0,
                    selection_values: mf.selection_values || '',
                    source_model: mf.source_model || '',
                });
                this.state.fields.push(newField);
                this._insertFieldNode(newField._id, parentNodeId, index);
            } catch { /* ignore */ }
            return;
        }

        // 4. Field type from palette
        const typeName = ev.dataTransfer.getData("application/pm-field-type");
        if (typeName) {
            const suggestedName = this._suggestFieldName(typeName);
            const newField = this._makeDefaultField({ name: suggestedName, type: typeName });
            this.state.fields.push(newField);
            this._insertFieldNode(newField._id, parentNodeId, index);
            return;
        }
    }

    onLayoutNodeDragStart(ev, nodeId) {
        ev.dataTransfer.setData("application/pm-layout-node", nodeId);
        ev.dataTransfer.effectAllowed = "move";
        this.state.isDragging = true;
    }

    onLayoutElemDragStart(ev, elemType) {
        ev.dataTransfer.setData("application/pm-layout-element", elemType);
        ev.dataTransfer.effectAllowed = "copy";
        this.state.isDragging = true;
    }

    // Clicking a field in layout selects it for detail editing
    onSelectField(fieldId) {
        this.state.selectedFieldId = this.state.selectedFieldId === fieldId ? null : fieldId;
    }

    get selectedField() {
        if (!this.state.selectedFieldId) return null;
        return this.state.fields.find(f => f._id === this.state.selectedFieldId) || null;
    }

    get selectedFieldIndex() {
        if (!this.state.selectedFieldId) return -1;
        return this.state.fields.findIndex(f => f._id === this.state.selectedFieldId);
    }

    onSeparatorLabelChange(nodeId, ev) {
        const found = this._findNode(nodeId);
        if (found) found.node.label = ev.target.value;
    }

    onPageLabelChange(nodeId, ev) {
        const found = this._findNode(nodeId);
        if (found) found.node.label = ev.target.value;
    }

    // Drop an unplaced field back into the layout
    onUnplacedFieldDragStart(ev, fieldId) {
        const field = this.getFieldById(fieldId);
        if (!field) return;
        ev.dataTransfer.setData("application/pm-unplaced-field", String(fieldId));
        ev.dataTransfer.effectAllowed = "copy";
        this.state.isDragging = true;
    }

    // Handle unplaced field drops in the layout drop handler
    _handleUnplacedFieldDrop(ev, parentNodeId, index) {
        const unplacedId = ev.dataTransfer.getData("application/pm-unplaced-field");
        if (unplacedId) {
            this._insertFieldNode(parseInt(unplacedId), parentNodeId, index);
            return true;
        }
        return false;
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
            const results = await this.orm.call("myschool.process", "search_models", [query]);
            this.state.modelResults = results;
        } catch {
            this.state.modelResults = [];
        }
    }

    async onSelectModel(model) {
        this.state.selectedModel = model;
        this.state.modelFieldsLoading = true;
        try {
            const fields = await this.orm.call("myschool.process", "get_model_fields", [model.model]);
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
            readonly: mf.readonly || false,
            store: mf.store !== undefined ? mf.store : true,
            index: mf.index || '',
            copy: mf.copy !== undefined ? mf.copy : true,
            translate: mf.translate || false,
            relation_field: mf.relation_field || '',
            relation_table: mf.relation_table || '',
            domain: mf.domain || '[]',
            on_delete: mf.on_delete || 'set null',
            help: mf.help || '',
            groups: mf.groups || '',
            size: mf.size || 0,
            selection_values: mf.selection_values || '',
            source_model: mf.source_model || '',
        });
        ev.dataTransfer.setData("application/pm-model-field", data);
        ev.dataTransfer.effectAllowed = "copy";
        this.state.isDragging = true;
    }

    _loadFieldRecords(records) {
        const fields = [];
        for (const r of records) {
            fields.push({
                _id: this.nextId ? this.nextId++ : fields.length + 1000,
                id: r.id || false,
                name: r.name || '',
                type: TTYPE_MAP_REVERSE[r.ttype] || 'Char',
                required: r.required || false,
                relation: r.relation || '',
                options: '',
                expanded: false,
                field_description: r.field_description || '',
                readonly: r.readonly || false,
                store: r.store !== undefined ? r.store : true,
                index: r.index || '',
                copy: r.copy !== undefined ? r.copy : true,
                translate: r.translate || false,
                relation_field: r.relation_field || '',
                relation_table: r.relation_table || '',
                domain: r.domain || '[]',
                on_delete: r.on_delete || 'set null',
                help_text: r.help_text || '',
                groups: r.groups || '',
                size: r.size || 0,
                digits: r.digits || '',
                selection_values: r.selection_values || '',
                default_value: r.default_value || '',
                source_model: r.source_model || '',
            });
        }
        // nextId may not be set yet during constructor; fix it
        this.nextId = Math.max(1000, ...fields.map(f => f._id)) + 1;
        return fields;
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
                const f = {
                    _id: this.nextId++,
                    id: false,
                    name: match[1],
                    type: match[2],
                    required: options.includes('required'),
                    relation: '',
                    options: options.replace('required', '').replace(',', '').trim(),
                    expanded: false,
                    field_description: '',
                    readonly: false,
                    store: true,
                    index: '',
                    copy: true,
                    translate: false,
                    relation_field: '',
                    relation_table: '',
                    domain: '[]',
                    on_delete: 'set null',
                    help_text: '',
                    groups: '',
                    size: 0,
                    digits: '',
                    selection_values: '',
                    default_value: '',
                    source_model: '',
                };
                const relMatch = options.match(/^([\w.]+)/);
                if (relMatch && ['Many2one', 'One2many', 'Many2many'].includes(match[2])) {
                    f.relation = relMatch[1];
                    f.options = options.replace(relMatch[1], '').replace(',', '').trim();
                }
                fields.push(f);
            } else {
                fields.push({
                    _id: this.nextId++,
                    id: false,
                    name: trimmed,
                    type: 'Char',
                    required: false,
                    relation: '',
                    options: '',
                    expanded: false,
                    field_description: '',
                    readonly: false,
                    store: true,
                    index: '',
                    copy: true,
                    translate: false,
                    relation_field: '',
                    relation_table: '',
                    domain: '[]',
                    on_delete: 'set null',
                    help_text: '',
                    groups: '',
                    size: 0,
                    digits: '',
                    selection_values: '',
                    default_value: '',
                    source_model: '',
                });
            }
        }
        return fields;
    }

    _getOrderedFields() {
        // Return fields in layout tree order, then any unplaced fields
        const orderedIds = this._allFieldNodeIds();
        const ordered = [];
        for (const fid of orderedIds) {
            const f = this.state.fields.find(fd => fd._id === fid);
            if (f) ordered.push(f);
        }
        // Append unplaced fields at end
        const placedSet = new Set(orderedIds);
        for (const f of this.state.fields) {
            if (!placedSet.has(f._id)) ordered.push(f);
        }
        return ordered;
    }

    _serializeFields() {
        return this._getOrderedFields().map(f => {
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

    _buildFieldRecords() {
        const records = this._getOrderedFields().map((f, idx) => ({
            id: f.id || false,
            sequence: (idx + 1) * 10,
            name: f.name,
            field_description: f.field_description || '',
            ttype: TTYPE_MAP[f.type] || 'char',
            required: f.required || false,
            readonly: f.readonly || false,
            store: f.store !== undefined ? f.store : true,
            index: f.index || '',
            copy: f.copy !== undefined ? f.copy : true,
            translate: f.translate || false,
            relation: f.relation || '',
            relation_field: f.relation_field || '',
            relation_table: f.relation_table || '',
            domain: f.domain || '[]',
            on_delete: f.on_delete || 'set null',
            help_text: f.help_text || '',
            groups: f.groups || '',
            size: f.size || 0,
            digits: f.digits || '',
            selection_values: f.selection_values || '',
            default_value: f.default_value || '',
            source_model: f.source_model || '',
        }));
        // Detect deleted fields by comparing original DB IDs with what remains
        const currentIds = new Set(records.filter(r => r.id).map(r => r.id));
        for (const origId of this._originalFieldIds) {
            if (!currentIds.has(origId)) {
                records.push({ id: origId, _delete: true });
            }
        }
        return records;
    }

    onPaletteDragStart(ev, fieldType) {
        ev.dataTransfer.setData("application/pm-field-type", fieldType.type);
        ev.dataTransfer.effectAllowed = "copy";
        this.state.isDragging = true;
    }

    onDropZoneDragOver(ev, index) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
        this.state.dragOverIndex = index;
    }

    onDropZoneDragLeave(ev) {
        this.state.dragOverIndex = -1;
    }

    _makeDefaultField(overrides) {
        return Object.assign({
            _id: this.nextId++,
            id: false,
            name: '',
            type: 'Char',
            required: false,
            relation: '',
            options: '',
            expanded: false,
            field_description: '',
            readonly: false,
            store: true,
            index: '',
            copy: true,
            translate: false,
            relation_field: '',
            relation_table: '',
            domain: '[]',
            on_delete: 'set null',
            help_text: '',
            groups: '',
            size: 0,
            digits: '',
            selection_values: '',
            default_value: '',
            source_model: '',
        }, overrides);
    }

    onDropZoneDrop(ev, index) {
        ev.preventDefault();
        this.state.dragOverIndex = -1;

        const modelFieldData = ev.dataTransfer.getData("application/pm-model-field");
        if (modelFieldData) {
            try {
                const mf = JSON.parse(modelFieldData);
                this.state.fields.splice(index, 0, this._makeDefaultField({
                    name: mf.name,
                    type: mf.type,
                    required: mf.required || false,
                    relation: mf.relation || '',
                    field_description: mf.label || '',
                    readonly: mf.readonly || false,
                    store: mf.store !== undefined ? mf.store : true,
                    index: mf.index || '',
                    copy: mf.copy !== undefined ? mf.copy : true,
                    translate: mf.translate || false,
                    relation_field: mf.relation_field || '',
                    relation_table: mf.relation_table || '',
                    domain: mf.domain || '[]',
                    on_delete: mf.on_delete || 'set null',
                    help_text: mf.help || '',
                    groups: mf.groups || '',
                    size: mf.size || 0,
                    selection_values: mf.selection_values || '',
                    source_model: mf.source_model || '',
                }));
            } catch { /* ignore parse errors */ }
            return;
        }

        const typeName = ev.dataTransfer.getData("application/pm-field-type");
        if (!typeName) return;
        const suggestedName = this._suggestFieldName(typeName);
        this.state.fields.splice(index, 0, this._makeDefaultField({
            name: suggestedName,
            type: typeName,
        }));
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

    onToggleExpand(index) {
        this.state.fields[index].expanded = !this.state.fields[index].expanded;
    }

    onToggleAttr(index, attr) {
        this.state.fields[index][attr] = !this.state.fields[index][attr];
    }

    onRemoveField(index) {
        const field = this.state.fields[index];
        if (field) {
            this._removeFieldFromLayout(field._id);
        }
        this.state.fields = this.state.fields.filter((_, i) => i !== index);
    }

    _removeFieldFromLayout(fieldId, root) {
        root = root || this.state.layout;
        if (root.children) {
            for (let i = root.children.length - 1; i >= 0; i--) {
                const child = root.children[i];
                if (child.type === 'field' && child.fieldId === fieldId) {
                    root.children.splice(i, 1);
                    return true;
                }
                if (this._removeFieldFromLayout(fieldId, child)) return true;
            }
        }
        return false;
    }

    onRemoveUnplacedField(fieldId) {
        this.state.fields = this.state.fields.filter(f => f._id !== fieldId);
    }

    onDeleteField(fieldId) {
        this._removeFieldFromLayout(fieldId);
        this.state.fields = this.state.fields.filter(f => f._id !== fieldId);
        if (this.state.selectedFieldId === fieldId) {
            this.state.selectedFieldId = null;
        }
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
        const text = this._serializeFields();
        const fieldRecords = this._buildFieldRecords();
        const formLayout = JSON.stringify(this._serializeLayout());
        this.props.onSave({ text, fieldRecords, formLayout });
    }

    onClose() {
        // Auto-apply changes when closing so deletions aren't lost
        this.onSave();
    }
}

// ============================================================
// Properties Panel Component
// ============================================================
class ProcessMapperProperties extends Component {
    static template = "myschool_processcomposer.PropertiesPanel";
    static components = { FieldBuilder };
    static props = {
        selectedElement: { type: Object, optional: true },
        selectedType: { type: String, optional: true },
        selectedCount: { type: Number },
        lanes: { type: Array },
        roles: { type: Array },
        orgs: { type: Array },
        availableMaps: { type: Array },
        lanePresets: { type: Array },
        onPropertyChange: { type: Function },
        onFieldRecordsSave: { type: Function },
        onCreatePreset: { type: Function },
        onUpdatePresetColor: { type: Function },
        onDelete: { type: Function },
        requestFieldBuilder: { type: Boolean, optional: true },
        onFieldBuilderOpened: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            showFieldBuilder: false,
            showIconPicker: false,
            showNewPresetForm: false,
            newPresetName: '',
            newPresetColor: '#E3F2FD',
        });
        this.stepIcons = STEP_ICONS;
        this._lastRequestFieldBuilder = false;

        onWillUpdateProps((nextProps) => {
            if (nextProps.requestFieldBuilder && !this._lastRequestFieldBuilder) {
                this.state.showFieldBuilder = true;
                if (nextProps.onFieldBuilderOpened) {
                    nextProps.onFieldBuilderOpened();
                }
            }
            this._lastRequestFieldBuilder = nextProps.requestFieldBuilder || false;
        });
    }

    onInputChange(field, ev) {
        let value = ev.target.value;
        if (field === 'lane_id' || field === 'role_id' || field === 'org_id' || field === 'sub_process_id') {
            value = value ? parseInt(value) : false;
        }
        if (field === 'preset') {
            if (value === '__new__') {
                this.state.showNewPresetForm = true;
                return;
            }
            this.state.showNewPresetForm = false;
        }
        this.props.onPropertyChange(field, value);
    }

    onNewPresetNameChange(ev) {
        this.state.newPresetName = ev.target.value;
    }

    onNewPresetColorChange(ev) {
        this.state.newPresetColor = ev.target.value;
    }

    async onSaveNewPreset() {
        const name = this.state.newPresetName.trim();
        if (!name) return;
        await this.props.onCreatePreset(name, this.state.newPresetColor);
        this.state.showNewPresetForm = false;
        this.state.newPresetName = '';
        this.state.newPresetColor = '#E3F2FD';
    }

    onCancelNewPreset() {
        this.state.showNewPresetForm = false;
        this.state.newPresetName = '';
        this.state.newPresetColor = '#E3F2FD';
    }

    get matchedPreset() {
        const el = this.props.selectedElement;
        if (!el || this.props.selectedType !== 'lane') return null;
        return this.props.lanePresets.find(p => p.name === el.name) || null;
    }

    get presetColorChanged() {
        const preset = this.matchedPreset;
        if (!preset) return false;
        const elColor = (this.props.selectedElement.color || '#E3F2FD').toUpperCase();
        return elColor !== preset.color.toUpperCase();
    }

    async onSavePresetColor() {
        const preset = this.matchedPreset;
        if (!preset) return;
        await this.props.onUpdatePresetColor(preset.id, this.props.selectedElement.color);
    }

    openFieldBuilder() {
        this.state.showFieldBuilder = true;
    }

    onFieldBuilderSave(result) {
        // Use dedicated save method with explicit step ID
        const stepId = this.props.selectedElement && this.props.selectedElement.id;
        this.props.onFieldRecordsSave(stepId, result);
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
    static template = "myschool_processcomposer.Minimap";
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
    static template = "myschool_processcomposer.VersionPanel";
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
    static template = "myschool_processcomposer.Canvas";
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
        onMoveLane: { type: Function },
        onSnapStepToGrid: { type: Function },
        onSnapStepsToGrid: { type: Function },
        onUpdateLabelOffset: { type: Function },
        onStepContextMenu: { type: Function, optional: true },
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
        this.laneDragging = null;
        this.draggingLabel = null;
        this.spaceHeld = false;
        this.state = useState({
            rubberBandX: 0,
            rubberBandY: 0,
            showRubberBand: false,
            connectSourceId: null,
            editingStepId: null,
            editingText: '',
            selectionRect: null,
            cursorGrab: false,
        });

        // Spacebar pan: hold Space to enter pan mode
        this._onKeyDown = (ev) => {
            const tag = document.activeElement?.tagName;
            const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable;
            if (ev.code === 'Space' && !this.spaceHeld && !this.state.editingStepId && !isTyping) {
                ev.preventDefault();
                this.spaceHeld = true;
                this.state.cursorGrab = true;
            }
        };
        this._onKeyUp = (ev) => {
            if (ev.code === 'Space') {
                this.spaceHeld = false;
                if (!this.panning) {
                    this.state.cursorGrab = false;
                }
            }
        };

        onMounted(() => {
            document.addEventListener('keydown', this._onKeyDown);
            document.addEventListener('keyup', this._onKeyUp);
        });
        onWillUnmount(() => {
            document.removeEventListener('keydown', this._onKeyDown);
            document.removeEventListener('keyup', this._onKeyUp);
        });
    }

    getTransform() {
        return `translate(${this.props.panX}, ${this.props.panY}) scale(${this.props.zoom})`;
    }

    getStickyLabelTransform() {
        return `translate(0, ${this.props.panY}) scale(${this.props.zoom})`;
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

    /** Compute total polyline length and cumulative segment lengths. */
    _pathMeasure(points) {
        const cumLen = [0];
        for (let i = 1; i < points.length; i++) {
            const dx = points[i].x - points[i - 1].x;
            const dy = points[i].y - points[i - 1].y;
            cumLen.push(cumLen[i - 1] + Math.sqrt(dx * dx + dy * dy));
        }
        return cumLen;
    }

    /** Get {x, y} at parameter t (0–1) along a polyline. */
    _pointAtT(points, t) {
        if (points.length === 0) return { x: 0, y: 0 };
        if (points.length === 1) return { ...points[0] };
        const cumLen = this._pathMeasure(points);
        const totalLen = cumLen[cumLen.length - 1];
        if (totalLen === 0) return { ...points[0] };
        const target = Math.max(0, Math.min(1, t)) * totalLen;
        for (let i = 1; i < cumLen.length; i++) {
            if (cumLen[i] >= target) {
                const segLen = cumLen[i] - cumLen[i - 1];
                const frac = segLen > 0 ? (target - cumLen[i - 1]) / segLen : 0;
                return {
                    x: points[i - 1].x + (points[i].x - points[i - 1].x) * frac,
                    y: points[i - 1].y + (points[i].y - points[i - 1].y) * frac,
                };
            }
        }
        return { ...points[points.length - 1] };
    }

    /** Project a point onto the polyline and return its t value (0–1). */
    _projectOntoPath(points, px, py) {
        if (points.length < 2) return 0.5;
        const cumLen = this._pathMeasure(points);
        const totalLen = cumLen[cumLen.length - 1];
        if (totalLen === 0) return 0.5;
        let bestDist = Infinity;
        let bestLen = 0;
        for (let i = 1; i < points.length; i++) {
            const ax = points[i - 1].x, ay = points[i - 1].y;
            const bx = points[i].x, by = points[i].y;
            const dx = bx - ax, dy = by - ay;
            const segLen = cumLen[i] - cumLen[i - 1];
            // Project point onto segment
            let frac = 0;
            if (segLen > 0) {
                frac = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
                frac = Math.max(0, Math.min(1, frac));
            }
            const cx = ax + dx * frac;
            const cy = ay + dy * frac;
            const dist = (px - cx) ** 2 + (py - cy) ** 2;
            if (dist < bestDist) {
                bestDist = dist;
                bestLen = cumLen[i - 1] + frac * segLen;
            }
        }
        return bestLen / totalLen;
    }

    getConnectionLabelPos(conn) {
        const points = this.getConnectionPoints(conn);
        if (points.length === 0) return { x: 0, y: 0 };
        const off = conn.label_offset || {};
        const t = (off.t !== undefined && off.t !== null) ? off.t : 0.5;
        return this._pointAtT(points, t);
    }

    onLabelMouseDown(ev, conn) {
        ev.stopPropagation();
        ev.preventDefault();
        this.draggingLabel = { connId: conn.id };
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
            const isHorizontal = Math.abs(a.y - b.y) < 0.5;
            const isMiddle = i > 0 && i < points.length - 2;
            segments.push({
                midX: (a.x + b.x) / 2,
                midY: (a.y + b.y) / 2,
                x1: a.x, y1: a.y,
                x2: b.x, y2: b.y,
                segmentIndex: i,
                isHorizontal,
                isMiddle,
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
        // Capture current full path so we can manipulate it stably during drag
        const points = this.getConnectionPoints(conn);
        const a = points[segIdx];
        const b = points[segIdx + 1];
        const isHorizontal = Math.abs(a.y - b.y) < 0.5;

        this.segmentDragging = {
            connId: conn.id,
            segmentIndex: segIdx,
            isHorizontal,
            startPos: this.screenToSvg(ev.clientX, ev.clientY),
            // Store the full original path points so we don't recompute mid-drag
            originalPoints: points.map(p => ({ x: p.x, y: p.y })),
            // Store port points so we can snap to them during drag
            sourcePort: { x: points[0].x, y: points[0].y },
            targetPort: { x: points[points.length - 1].x, y: points[points.length - 1].y },
            // Preserve the connection's route type (ports) during drag
            connSourcePort: conn.source_port || null,
            connTargetPort: conn.target_port || null,
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

    // --- Lane drag handle ---
    onLaneDragMouseDown(ev, lane) {
        ev.stopPropagation();
        ev.preventDefault();
        const pos = this.screenToSvg(ev.clientX, ev.clientY);
        this.laneDragging = {
            laneId: lane.id,
            startMouseY: pos.y,
            origY: lane.y_position,
        };
        this.props.onSelectElement(lane.id, 'lane');
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
        // Middle mouse button or spacebar+click: always pan (even over elements)
        if (ev.button === 1 || (ev.button === 0 && this.spaceHeld)) {
            ev.preventDefault();
            this.panning = { startX: ev.clientX, startY: ev.clientY, origPanX: this.props.panX, origPanY: this.props.panY };
            this.state.cursorGrab = true;
            return;
        }
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
        if (this.laneDragging) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            let newY = this.laneDragging.origY + (pos.y - this.laneDragging.startMouseY);
            if (this.props.gridEnabled) {
                newY = Math.round(newY / 20) * 20;
            }
            this.props.onMoveLane(this.laneDragging.laneId, newY);
        }
        if (this.segmentDragging) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const seg = this.segmentDragging;
            const snappedX = snapToGrid(pos.x);
            const snappedY = snapToGrid(pos.y);
            const wp = { x: snappedX, y: snappedY };

            // Start with the original ports (preserve route type)
            let sp = seg.connSourcePort;
            let tp = seg.connTargetPort;

            // Check if waypoint is close to an L-route bend point — if so, snap to L
            const conn = this.props.connections.find(c => c.id === seg.connId);
            if (conn) {
                const source = this.props.steps.find(s => s.id === conn.source_step_id);
                const target = this.props.steps.find(s => s.id === conn.target_step_id);
                if (source && target) {
                    const SNAP = 40;
                    const allSides = ['top', 'right', 'bottom', 'left'];
                    let bestDist = SNAP + 1;
                    let bestSP = null, bestTP = null;
                    for (const cs of allSides) {
                        for (const ct of allSides) {
                            const csH = (cs === 'left' || cs === 'right');
                            const ctH = (ct === 'left' || ct === 'right');
                            if (csH === ctH) continue; // only perpendicular (L-route)
                            const pp1 = shapePortPoint(source, cs);
                            const pp2 = shapePortPoint(target, ct);
                            const bend = csH
                                ? { x: pp2.x, y: pp1.y }
                                : { x: pp1.x, y: pp2.y };
                            // Skip if port faces away from bend
                            const srcOK = (cs === 'right' && bend.x >= pp1.x) ||
                                          (cs === 'left' && bend.x <= pp1.x) ||
                                          (cs === 'bottom' && bend.y >= pp1.y) ||
                                          (cs === 'top' && bend.y <= pp1.y);
                            const tgtOK = (ct === 'right' && bend.x >= pp2.x) ||
                                          (ct === 'left' && bend.x <= pp2.x) ||
                                          (ct === 'bottom' && bend.y >= pp2.y) ||
                                          (ct === 'top' && bend.y <= pp2.y);
                            if (!srcOK || !tgtOK) continue;
                            const d = Math.max(Math.abs(wp.x - bend.x), Math.abs(wp.y - bend.y));
                            if (d < bestDist) {
                                bestDist = d;
                                bestSP = cs;
                                bestTP = ct;
                            }
                        }
                    }
                    if (bestSP && bestDist <= SNAP) {
                        sp = bestSP;
                        tp = bestTP;
                    } else {
                        // No L-route snap — switch to S-route (opposite ports)
                        const sc = shapeCenter(source);
                        const tc = shapeCenter(target);
                        const ddx = tc.x - sc.x;
                        const ddy = tc.y - sc.y;
                        if (Math.abs(ddx) > Math.abs(ddy)) {
                            sp = ddx > 0 ? 'right' : 'left';
                            tp = ddx > 0 ? 'left' : 'right';
                        } else {
                            sp = ddy > 0 ? 'bottom' : 'top';
                            tp = ddy > 0 ? 'top' : 'bottom';
                        }
                    }
                }
            }

            this.props.onUpdateConnectionWaypoints(seg.connId, [wp], sp, tp);
        }
        if (this.draggingLabel) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const conn = this.props.connections.find(c => c.id === this.draggingLabel.connId);
            if (conn) {
                const points = this.getConnectionPoints(conn);
                const t = this._projectOntoPath(points, pos.x, pos.y);
                this.props.onUpdateLabelOffset(this.draggingLabel.connId, t);
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
        if (this.draggingLabel) {
            this.draggingLabel = null;
        }
        if (this.connecting) {
            const pos = this.screenToSvg(ev.clientX, ev.clientY);
            const target = this._findStepAt(pos.x, pos.y);
            const sourceId = this.connecting.sourceId;
            if (target && target.id !== sourceId) {
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
                    sourceId, target.id,
                    this.connecting.sourcePort, bestPort
                );
                // Keep gateway/condition selected so user can draw more connections
                const sourceStep = this.props.steps.find(s => s.id === sourceId);
                if (sourceStep && ['condition', 'gateway_exclusive', 'gateway_parallel'].includes(sourceStep.step_type)) {
                    this.props.onSelectElement(sourceId, 'step');
                }
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
        if (this.laneDragging) {
            this.laneDragging = null;
            this.props.onDragEnd();
        }
        if (this.segmentDragging) {
            // If the drag ended on an L-route, clear waypoints (L-routes don't use them)
            const seg = this.segmentDragging;
            const conn = this.props.connections.find(c => c.id === seg.connId);
            if (conn && conn.source_port && conn.target_port) {
                const spH = (conn.source_port === 'left' || conn.source_port === 'right');
                const tpH = (conn.target_port === 'left' || conn.target_port === 'right');
                if (spH !== tpH) {
                    // Perpendicular ports = L-route: clear waypoints
                    this.props.onUpdateConnectionWaypoints(
                        seg.connId, [], conn.source_port, conn.target_port
                    );
                }
            }
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
        if (!this.spaceHeld) {
            this.state.cursorGrab = false;
        }
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

    onStepContextMenu(ev, step) {
        if (this.props.onStepContextMenu) {
            this.props.onStepContextMenu(step.id, ev.clientX, ev.clientY);
        }
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

    isConnectionSelected(conn) {
        return this.props.selectedType === 'connection' && this.props.selectedIds.includes(conn.id);
    }

    onConnectionClick(ev, conn) {
        ev.stopPropagation();
        this.props.onSelectElement(conn.id, 'connection');
    }

    onConnectionPathMouseDown(ev, conn) {
        // Only initiate drag on already-selected connections
        if (!this.isConnectionSelected(conn)) return;
        // Find the closest segment to the mouse position
        const pos = this.screenToSvg(ev.clientX, ev.clientY);
        const points = this.getConnectionPoints(conn);
        if (points.length < 3) return;

        let bestIdx = 1; // default to first middle segment
        let bestDist = Infinity;
        for (let i = 0; i < points.length - 1; i++) {
            const a = points[i];
            const b = points[i + 1];
            // Distance from point to line segment
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const lenSq = dx * dx + dy * dy;
            let t = lenSq > 0 ? ((pos.x - a.x) * dx + (pos.y - a.y) * dy) / lenSq : 0;
            t = Math.max(0, Math.min(1, t));
            const px = a.x + t * dx;
            const py = a.y + t * dy;
            const d = (pos.x - px) ** 2 + (pos.y - py) ** 2;
            if (d < bestDist) {
                bestDist = d;
                bestIdx = i;
            }
        }

        ev.stopPropagation();
        ev.preventDefault();
        this.onSegmentHandleMouseDown(ev, conn, bestIdx);
    }

    /**
     * Returns toggle button info for a selected connection, or null if not selected.
     * Shows a small button at the midpoint of the connection to toggle L ↔ S/Z route.
     */
    getRouteToggleInfo(conn) {
        if (this.props.selectedType !== 'connection' || !this.props.selectedIds.includes(conn.id)) {
            return null;
        }
        const points = this.getConnectionPoints(conn);
        if (points.length < 3) return null;

        // Position at the midpoint of the path
        const midIdx = Math.floor(points.length / 2);
        const a = points[midIdx - 1];
        const b = points[midIdx];
        const x = (a.x + b.x) / 2;
        const y = (a.y + b.y) / 2;

        // Determine current route type
        const curSH = conn.source_port === 'left' || conn.source_port === 'right';
        const curTH = conn.target_port === 'left' || conn.target_port === 'right';
        const isL = conn.source_port && conn.target_port && (curSH !== curTH);

        return { x, y, isL };
    }

    onRouteToggle(ev, conn) {
        ev.stopPropagation();

        const source = this.props.steps.find(s => s.id === conn.source_step_id);
        const target = this.props.steps.find(s => s.id === conn.target_step_id);
        if (!source || !target) return;

        const sc = shapeCenter(source);
        const tc = shapeCenter(target);
        const dx = tc.x - sc.x;
        const dy = tc.y - sc.y;

        // Check current state
        const curSH = conn.source_port === 'left' || conn.source_port === 'right';
        const curTH = conn.target_port === 'left' || conn.target_port === 'right';
        const isCurrentlyL = conn.source_port && conn.target_port && (curSH !== curTH);

        if (isCurrentlyL) {
            // L → S/Z (opposite ports)
            let sp, tp;
            if (Math.abs(dx) > Math.abs(dy)) {
                sp = dx > 0 ? 'right' : 'left';
                tp = dx > 0 ? 'left' : 'right';
            } else {
                sp = dy > 0 ? 'bottom' : 'top';
                tp = dy > 0 ? 'top' : 'bottom';
            }
            this.props.onUpdateConnectionWaypoints(conn.id, [], sp, tp);
        } else {
            // S/Z → L: pick perpendicular port pair where ports face toward bend
            const allSides = ['top', 'right', 'bottom', 'left'];
            const candidates = [];
            for (const sp of allSides) {
                for (const tp of allSides) {
                    const spH = (sp === 'left' || sp === 'right');
                    const tpH = (tp === 'left' || tp === 'right');
                    if (spH === tpH) continue;
                    const pp1 = shapePortPoint(source, sp);
                    const pp2 = shapePortPoint(target, tp);
                    const bend = spH ? { x: pp2.x, y: pp1.y } : { x: pp1.x, y: pp2.y };
                    const srcOK = (sp === 'right' && bend.x >= pp1.x) ||
                                  (sp === 'left' && bend.x <= pp1.x) ||
                                  (sp === 'bottom' && bend.y >= pp1.y) ||
                                  (sp === 'top' && bend.y <= pp1.y);
                    const tgtOK = (tp === 'right' && bend.x >= pp2.x) ||
                                  (tp === 'left' && bend.x <= pp2.x) ||
                                  (tp === 'bottom' && bend.y >= pp2.y) ||
                                  (tp === 'top' && bend.y <= pp2.y);
                    const dist = Math.abs(pp1.x - pp2.x) + Math.abs(pp1.y - pp2.y);
                    const penalty = (srcOK ? 0 : 10000) + (tgtOK ? 0 : 10000);
                    candidates.push({ sp, tp, score: dist + penalty });
                }
            }
            candidates.sort((a, b) => a.score - b.score);
            this.props.onUpdateConnectionWaypoints(conn.id, [], candidates[0].sp, candidates[0].tp);
        }
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
        // Zoom toward cursor position
        const svg = this.svgRef.el;
        if (svg) {
            const rect = svg.getBoundingClientRect();
            const mouseX = ev.clientX - rect.left;
            const mouseY = ev.clientY - rect.top;
            const oldZoom = this.props.zoom;
            const newZoom = Math.min(3.0, Math.max(0.25, oldZoom + delta));
            const scale = newZoom / oldZoom;
            const newPanX = mouseX - (mouseX - this.props.panX) * scale;
            const newPanY = mouseY - (mouseY - this.props.panY) * scale;
            this.props.onPan(newPanX, newPanY);
            this.props.onZoom(delta);
        } else {
            this.props.onZoom(delta);
        }
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

    // --- Scrollbars ---

    _getDiagramBounds() {
        let minX = 0, minY = 0, maxX = 800, maxY = 400;
        for (const lane of this.props.lanes) {
            minY = Math.min(minY, lane.y_position);
            maxY = Math.max(maxY, lane.y_position + lane.height);
        }
        for (const step of this.props.steps) {
            const ds = defaultSize(step.step_type);
            const w = step.width || ds.w;
            const h = step.height || ds.h;
            minX = Math.min(minX, step.x_position);
            minY = Math.min(minY, step.y_position);
            maxX = Math.max(maxX, step.x_position + w);
            maxY = Math.max(maxY, step.y_position + h);
        }
        return { minX: minX - 100, minY: minY - 100, maxX: maxX + 100, maxY: maxY + 100 };
    }

    _getScrollState() {
        const svg = this.svgRef.el;
        if (!svg) return null;
        const rect = svg.getBoundingClientRect();
        const zoom = this.props.zoom;
        const viewW = rect.width / zoom;
        const viewH = rect.height / zoom;
        const viewLeft = -this.props.panX / zoom;
        const viewTop = -this.props.panY / zoom;
        const bounds = this._getDiagramBounds();
        const totalLeft = Math.min(bounds.minX, viewLeft);
        const totalTop = Math.min(bounds.minY, viewTop);
        const totalRight = Math.max(bounds.maxX, viewLeft + viewW);
        const totalBottom = Math.max(bounds.maxY, viewTop + viewH);
        const totalW = totalRight - totalLeft;
        const totalH = totalBottom - totalTop;
        return { viewLeft, viewTop, viewW, viewH, totalLeft, totalTop, totalW, totalH, zoom, domW: rect.width, domH: rect.height };
    }

    getHScrollWidth() {
        const s = this._getScrollState();
        if (!s) return 100;
        return Math.max(5, (s.viewW / s.totalW) * 100);
    }
    getHScrollLeft() {
        const s = this._getScrollState();
        if (!s) return 0;
        const range = s.totalW - s.viewW;
        if (range <= 0) return 0;
        return ((s.viewLeft - s.totalLeft) / range) * (100 - this.getHScrollWidth());
    }
    getVScrollHeight() {
        const s = this._getScrollState();
        if (!s) return 100;
        return Math.max(5, (s.viewH / s.totalH) * 100);
    }
    getVScrollTop() {
        const s = this._getScrollState();
        if (!s) return 0;
        const range = s.totalH - s.viewH;
        if (range <= 0) return 0;
        return ((s.viewTop - s.totalTop) / range) * (100 - this.getVScrollHeight());
    }

    onHThumbMouseDown(ev) {
        const track = ev.target.parentElement;
        const trackRect = track.getBoundingClientRect();
        const startX = ev.clientX;
        const startLeft = this.getHScrollLeft();
        const thumbWidth = this.getHScrollWidth();
        const s = this._getScrollState();
        if (!s) return;

        const onMove = (e) => {
            const dx = e.clientX - startX;
            const pct = dx / trackRect.width * 100;
            const newLeft = Math.max(0, Math.min(100 - thumbWidth, startLeft + pct));
            const range = s.totalW - s.viewW;
            const newViewLeft = s.totalLeft + (newLeft / (100 - thumbWidth)) * range;
            this.props.onPan(-newViewLeft * s.zoom, this.props.panY);
        };
        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    onVThumbMouseDown(ev) {
        const track = ev.target.parentElement;
        const trackRect = track.getBoundingClientRect();
        const startY = ev.clientY;
        const startTop = this.getVScrollTop();
        const thumbHeight = this.getVScrollHeight();
        const s = this._getScrollState();
        if (!s) return;

        const onMove = (e) => {
            const dy = e.clientY - startY;
            const pct = dy / trackRect.height * 100;
            const newTop = Math.max(0, Math.min(100 - thumbHeight, startTop + pct));
            const range = s.totalH - s.viewH;
            const newViewTop = s.totalTop + (newTop / (100 - thumbHeight)) * range;
            this.props.onPan(this.props.panX, -newViewTop * s.zoom);
        };
        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    onHTrackMouseDown(ev) {
        if (ev.target.classList.contains('pm-scrollbar-thumb')) return;
        const track = ev.currentTarget;
        const trackRect = track.getBoundingClientRect();
        const clickPct = (ev.clientX - trackRect.left) / trackRect.width * 100;
        const thumbWidth = this.getHScrollWidth();
        const s = this._getScrollState();
        if (!s) return;
        const newLeft = Math.max(0, Math.min(100 - thumbWidth, clickPct - thumbWidth / 2));
        const range = s.totalW - s.viewW;
        if (range <= 0) return;
        const newViewLeft = s.totalLeft + (newLeft / (100 - thumbWidth)) * range;
        this.props.onPan(-newViewLeft * s.zoom, this.props.panY);
    }

    onVTrackMouseDown(ev) {
        if (ev.target.classList.contains('pm-scrollbar-thumb')) return;
        const track = ev.currentTarget;
        const trackRect = track.getBoundingClientRect();
        const clickPct = (ev.clientY - trackRect.top) / trackRect.height * 100;
        const thumbHeight = this.getVScrollHeight();
        const s = this._getScrollState();
        if (!s) return;
        const newTop = Math.max(0, Math.min(100 - thumbHeight, clickPct - thumbHeight / 2));
        const range = s.totalH - s.viewH;
        if (range <= 0) return;
        const newViewTop = s.totalTop + (newTop / (100 - thumbHeight)) * range;
        this.props.onPan(this.props.panX, -newViewTop * s.zoom);
    }
}

// ============================================================
// Main Client Action Component
// ============================================================
class ProcessMapperClient extends Component {
    static template = "myschool_processcomposer.ProcessMapperClient";
    static components = { ProcessMapperToolbar, ProcessMapperCanvas, ProcessMapperProperties, ProcessMapperMinimap, ProcessMapperVersionPanel };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.drawioFileInput = useRef("drawioFileInput");
        this.nextTempId = -1;
        this._history = [];
        this._historyIndex = -1;
        this._clipboard = null;
        this._historyPaused = false;
        // Pending field record updates (stepId -> fieldRecords array)
        // Stored outside reactive state to avoid proxy issues
        this._pendingFieldRecords = {};

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
            lanePresets: [],
            contextMenu: { visible: false, x: 0, y: 0, stepId: null },
            rolePopover: { visible: false, x: 0, y: 0, stepId: null },
            rolePopoverQuery: '',
            requestFieldBuilder: false,
            showProperties: true,
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

    /*async loadDiagram() {
        try {
            const data = await this.orm.call("myschool.process", "get_diagram_data", [this.state.mapId]);
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
    }*/
    async loadDiagram() {
    try {
        const data = await this.orm.call("myschool.process", "get_diagram_data", [this.state.mapId]);

        // STAP 1: Maak de huidige lijnen eerst leeg (helpt tegen ghosting)
        this.state.connections = [];
        this.state.steps = [];

        // STAP 2: Vul de state met een schone kopie
        this.state.mapName = data.name;
        this.state.mapState = data.state;
        this.state.steps = data.steps.map(s => ({ ...s }));
        this.state.lanes = data.lanes.map(l => ({ ...l }));
        this.state.lanePresets = data.lane_presets || [];

        // Zorg dat waypoints van een string naar een object gaan als dat nodig is
        this.state.connections = data.connections.map(c => {
            let waypoints = c.waypoints;
            if (typeof waypoints === 'string') {
                try { waypoints = JSON.parse(waypoints); } catch(e) { waypoints = []; }
            }
            let label_offset = c.label_offset;
            if (typeof label_offset === 'string') {
                try { label_offset = JSON.parse(label_offset); } catch(e) { label_offset = {}; }
            }
            return { ...c, waypoints: waypoints || [], label_offset: label_offset || {} };
        });

        this.state.dirty = false;

        // Forceer een herberekening van de canvas als je een externe library gebruikt
        if (this.canvasEngine) {
            this.canvasEngine.render();
        }

        // Initialize history and clear pending
        this._history = [];
        this._historyIndex = -1;
        this._pendingFieldRecords = {};
        this._pushHistory();
    } catch (e) {
        this.notification.add("Failed to load diagram: " + (e.message || e), { type: "danger" });
    }
}

    async loadMapList() {
        try {
            const maps = await this.orm.searchRead("myschool.process", [], ["name", "state", "org_id"], { order: "name" });
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
        // Zorg dat alle coördinaten Integers zijn, Odoo kan struikelen over Floats uit de browser
        const pending = this._pendingFieldRecords;
        const data = {
            lanes: this.state.lanes.map(l => ({ ...l, y_position: Math.round(l.y_position) })),
            steps: this.state.steps.map(s => {
                const validTypes = ['start', 'end', 'task', 'subprocess', 'condition', 'gateway_exclusive', 'gateway_parallel'];
                const stepType = validTypes.includes(s.step_type) ? s.step_type : 'task';
                const step = { ...s, step_type: stepType, x_position: Math.round(s.x_position), y_position: Math.round(s.y_position), form_layout: s.form_layout || '' };
                // Use pending field_records if available (plain JS, no proxy)
                if (s.id in pending) {
                    step.field_records = pending[s.id];
                } else if (step.field_records) {
                    // Deep copy to strip any reactive proxy
                    step.field_records = JSON.parse(JSON.stringify(step.field_records));
                }
                return step;
            }),
            connections: this.state.connections.map(c => {
                // Extract label_offset.t explicitly to avoid reactive proxy issues
                const lo = c.label_offset;
                const labelT = (lo && typeof lo.t === 'number') ? lo.t : null;
                return {
                    id: c.id,
                    source_step_id: c.source_step_id,
                    target_step_id: c.target_step_id,
                    label: c.label || '',
                    connection_type: c.connection_type || 'sequence',
                    waypoints: c.waypoints ? JSON.parse(JSON.stringify(c.waypoints)) : [],
                    source_port: c.source_port || "",
                    target_port: c.target_port || "",
                    label_offset: labelT !== null ? { t: labelT } : {},
                };
            }),
        };

        // Let op: data is nu het tweede argument in de array []
        await this.orm.call("myschool.process", "save_diagram_data", [this.state.mapId, data]);

        // Clear pending field records after successful save
        this._pendingFieldRecords = {};

        // Optioneel: Maak de connecties even leeg voor een 'schone' hertekening
        this.state.connections = [];

        await this.loadDiagram();
        this.notification.add("Opgeslagen!", { type: "success" });
    } catch (e) {
        this.notification.add("Fout bij opslaan: " + e.message, { type: "danger" });
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
        if (this.state.contextMenu.visible) {
            this.closeContextMenu();
        }
        if (this.state.rolePopover.visible) {
            this.closeRolePopover();
        }
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
            // Clear waypoints on connected lines so they auto-route cleanly
            this._clearWaypointsForStep(stepId);
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
                // Clear waypoints on connected lines so they auto-route cleanly
                this._clearWaypointsForStep(id);
            }
        }
        this.state.dirty = true;
    }

    _clearWaypointsForStep(stepId) {
        this.state.connections = this.state.connections.map(c => {
            if (c.source_step_id === stepId || c.target_step_id === stepId) {
                // Only clear waypoints, keep stored ports so L-routes persist
                return { ...c, waypoints: [] };
            }
            return c;
        });
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

    onUpdateLabelOffset(connId, t) {
        const conn = this.state.connections.find(c => c.id === connId);
        if (conn) {
            conn.label_offset = { t };
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
            label_offset: { t: 0.5 },
        });
        this.state.dirty = true;
        this._pushHistory();
    }

    // --- Move lane (snap between other lanes) ---

    onMoveLane(laneId, newY) {
        const lanes = this.state.lanes;
        const draggedLane = lanes.find(l => l.id === laneId);
        if (!draggedLane) return;

        // Sort other lanes by current y_position
        const otherLanes = lanes.filter(l => l.id !== laneId).sort((a, b) => a.y_position - b.y_position);

        // Find insertion index based on where the dragged lane's center would be
        const dragCenter = newY + draggedLane.height / 2;
        let insertIdx = otherLanes.length; // default: at the end
        for (let i = 0; i < otherLanes.length; i++) {
            const otherCenter = otherLanes[i].y_position + otherLanes[i].height / 2;
            if (dragCenter < otherCenter) {
                insertIdx = i;
                break;
            }
        }

        // Build the new lane order
        const orderedLanes = [...otherLanes];
        orderedLanes.splice(insertIdx, 0, draggedLane);

        // Determine the starting Y (use the topmost lane's current position, or 0)
        const firstLaneY = lanes.length > 0
            ? Math.min(...lanes.map(l => l.y_position))
            : 0;
        let currentY = firstLaneY;

        // Reposition all lanes and their steps
        for (let i = 0; i < orderedLanes.length; i++) {
            const lane = orderedLanes[i];
            const oldY = lane.y_position;
            const dy = currentY - oldY;

            if (Math.abs(dy) > 0.5) {
                // Move steps inside this lane
                for (const step of this.state.steps) {
                    if (step.lane_id === lane.id) {
                        step.y_position += dy;
                    }
                }
                lane.y_position = currentY;
            }

            lane.sequence = (i + 1) * 10;
            currentY += lane.height;
        }

        this.state.dirty = true;
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

    /*onUpdateConnectionWaypoints(connId, waypoints) {
        const conn = this.state.connections.find(c => c.id === connId);
        if (conn) {
            conn.waypoints = waypoints;
            this.state.dirty = true;
        }
    }
*/
    onUpdateConnectionWaypoints(connId, waypoints, sourcePort, targetPort) {
        this.state.connections = this.state.connections.map(c => {
            if (c.id === connId) {
                const updated = { ...c, waypoints: [...waypoints] };
                if (sourcePort !== undefined) updated.source_port = sourcePort;
                if (targetPort !== undefined) updated.target_port = targetPort;
                return updated;
            }
            return c;
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
        if (field === 'preset') {
            // Look up the preset and auto-fill name + color
            const preset = this.state.lanePresets.find(p => p.id === parseInt(value));
            if (preset) {
                el.name = preset.name;
                el.color = preset.color;
            }
        } else {
            el[field] = value;
        }
        this.state.dirty = true;
        this._pushHistory();
    }

    async onCreatePreset(name, color) {
        try {
            const id = await this.orm.create("myschool.process.lane.preset", [{ name, color }]);
            const newPreset = { id: id[0] || id, name, color };
            this.state.lanePresets.push(newPreset);
            // Auto-apply the new preset to the selected lane
            const el = this.getSelectedElement();
            if (el) {
                el.name = name;
                el.color = color;
            }
            this.state.dirty = true;
            this._pushHistory();
        } catch (e) {
            this.notification.add("Failed to create preset: " + (e.message || e), { type: "danger" });
        }
    }

    async onUpdatePresetColor(presetId, newColor) {
        try {
            await this.orm.write("myschool.process.lane.preset", [presetId], { color: newColor });
            const preset = this.state.lanePresets.find(p => p.id === presetId);
            if (preset) {
                preset.color = newColor;
            }
            this.notification.add("Preset color updated", { type: "success" });
        } catch (e) {
            this.notification.add("Failed to update preset: " + (e.message || e), { type: "danger" });
        }
    }

    onFieldRecordsSave(stepId, result) {
        // Directly find step by ID and store field records as plain data
        // This bypasses OWL reactive proxy issues entirely
        if (stepId) {
            this._pendingFieldRecords[stepId] = JSON.parse(JSON.stringify(result.fieldRecords));
        }
        // Also update the step in state for display
        const el = this.getSelectedElement();
        if (el) {
            el.data_fields = result.text;
            el.field_records = result.fieldRecords;
            el.form_layout = result.formLayout;
        }
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

    // --- Context Menu ---

    onStepContextMenu(stepId, clientX, clientY) {
        // Select the step
        this.onSelectElement(stepId, 'step');
        // Close role popover if open
        if (this.state.rolePopover.visible) {
            this.closeRolePopover();
        }
        // Position relative to the pm-main container
        const main = document.querySelector('.pm-main');
        const rect = main ? main.getBoundingClientRect() : { left: 0, top: 0 };
        this.state.contextMenu = {
            visible: true,
            x: clientX - rect.left,
            y: clientY - rect.top,
            stepId,
        };
    }

    closeContextMenu() {
        this.state.contextMenu = { visible: false, x: 0, y: 0, stepId: null };
    }

    _getContextMenuStep() {
        const id = this.state.contextMenu.stepId;
        return id ? this.state.steps.find(s => s.id === id) : null;
    }

    getContextMenuItems() {
        const step = this._getContextMenuStep();
        if (!step) return [];
        return [
            {
                id: 'role',
                label: step.role_id ? 'Change Role' : 'Add Role',
                icon: 'fa-users',
            },
            {
                id: 'field_builder',
                label: 'Field Builder',
                icon: 'fa-wrench',
            },
            {
                id: 'delete',
                label: 'Delete',
                icon: 'fa-trash',
            },
        ];
    }

    getFilteredRoles() {
        const q = (this.state.rolePopoverQuery || '').toLowerCase();
        if (!q) return this.state.roles || [];
        return (this.state.roles || []).filter(r => r.name.toLowerCase().includes(q));
    }

    onContextMenuAction(itemId) {
        if (itemId === 'role') {
            // Capture position, close menu, open role popover
            const { x, y, stepId } = this.state.contextMenu;
            this.closeContextMenu();
            this.state.rolePopover = { visible: true, x, y, stepId };
            this.state.rolePopoverQuery = '';
            return;
        }
        if (itemId === 'field_builder') {
            this.closeContextMenu();
            this.state.requestFieldBuilder = true;
            return;
        }
        if (itemId === 'delete') {
            this.closeContextMenu();
            this.onDelete();
            return;
        }
    }

    onCtxSetRole(roleId) {
        const stepId = this.state.rolePopover.stepId;
        const step = stepId ? this.state.steps.find(s => s.id === stepId) : null;
        if (!step) return;
        step.role_id = roleId || false;
        const role = roleId ? this.state.roles.find(r => r.id === roleId) : null;
        step.role_name = role ? role.name : '';
        this.state.dirty = true;
        this._pushHistory();
        this.closeRolePopover();
    }

    closeRolePopover() {
        this.state.rolePopover = { visible: false, x: 0, y: 0, stepId: null };
        this.state.rolePopoverQuery = '';
    }

    onFieldBuilderOpened() {
        this.state.requestFieldBuilder = false;
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
            // Clear field record IDs so backend creates new records
            if (newStep.field_records) {
                newStep.field_records = newStep.field_records.map(fr => ({ ...fr, id: false }));
            }
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

        // Assign depth 0 to unvisited steps
        for (const s of this.state.steps) {
            if (depth[s.id] === undefined) depth[s.id] = 0;
        }

        const xSpacing = 200;
        const yPadding = 20;
        const yStepSpacing = 80;
        const startX = 100;
        const lanes = this.state.lanes;
        const hasLanes = lanes.length > 0;

        if (hasLanes) {
            // Sort lanes by y_position
            const sortedLanes = [...lanes].sort((a, b) => a.y_position - b.y_position);

            // Build a map: laneId → steps grouped by depth
            // Also collect unassigned steps (no lane or lane not found)
            const laneSteps = {};  // laneId → { depth → [step, ...] }
            const unassignedByDepth = {};
            for (const lane of sortedLanes) {
                laneSteps[lane.id] = {};
            }
            for (const s of this.state.steps) {
                const d = depth[s.id];
                if (s.lane_id && laneSteps[s.lane_id]) {
                    if (!laneSteps[s.lane_id][d]) laneSteps[s.lane_id][d] = [];
                    laneSteps[s.lane_id][d].push(s);
                } else {
                    if (!unassignedByDepth[d]) unassignedByDepth[d] = [];
                    unassignedByDepth[d].push(s);
                }
            }

            // Calculate the required height for each lane based on how many steps
            // it has at the most populated depth level
            const laneMinHeight = 100;
            for (const lane of sortedLanes) {
                const depthGroups = laneSteps[lane.id];
                let maxCount = 0;
                for (const d of Object.keys(depthGroups)) {
                    maxCount = Math.max(maxCount, depthGroups[d].length);
                }
                const needed = maxCount > 0
                    ? yPadding * 2 + maxCount * yStepSpacing
                    : laneMinHeight;
                lane.height = Math.max(lane.height, needed);
            }

            // Reflow lane y positions so they stack without gaps
            let currentY = sortedLanes[0].y_position;
            for (const lane of sortedLanes) {
                lane.y_position = currentY;
                currentY += lane.height;
            }

            // Position steps within their lane
            for (const lane of sortedLanes) {
                const depthGroups = laneSteps[lane.id];
                for (const [d, steps] of Object.entries(depthGroups)) {
                    const totalHeight = steps.length * yStepSpacing;
                    // Center the group vertically within the lane
                    const startY = lane.y_position + (lane.height - totalHeight) / 2 + yStepSpacing / 2 - 30;
                    for (let i = 0; i < steps.length; i++) {
                        steps[i].x_position = startX + parseInt(d) * xSpacing;
                        steps[i].y_position = startY + i * yStepSpacing;
                    }
                }
            }

            // Position unassigned steps below all lanes
            if (Object.keys(unassignedByDepth).length > 0) {
                const belowY = currentY + 40;
                for (const [d, steps] of Object.entries(unassignedByDepth)) {
                    for (let i = 0; i < steps.length; i++) {
                        steps[i].x_position = startX + parseInt(d) * xSpacing;
                        steps[i].y_position = belowY + i * yStepSpacing;
                    }
                }
            }
        } else {
            // No lanes: simple layout like before
            const byDepth = {};
            for (const s of this.state.steps) {
                const d = depth[s.id];
                if (!byDepth[d]) byDepth[d] = [];
                byDepth[d].push(s);
            }
            const startY = 80;
            for (const [d, steps] of Object.entries(byDepth)) {
                for (let i = 0; i < steps.length; i++) {
                    steps[i].x_position = startX + parseInt(d) * xSpacing;
                    steps[i].y_position = startY + i * yStepSpacing;
                }
            }
        }

        // Reset waypoints and compute correct ports based on new step positions
        const stepsById = {};
        for (const s of this.state.steps) stepsById[s.id] = s;
        for (const conn of this.state.connections) {
            conn.waypoints = [];
            const source = stepsById[conn.source_step_id];
            const target = stepsById[conn.target_step_id];
            if (source && target) {
                const auto = selectPorts(source, target);
                conn.source_port = auto.sourceSide;
                conn.target_port = auto.targetSide;
            } else {
                conn.source_port = false;
                conn.target_port = false;
            }
        }

        routeAroundObstacles(this.state.steps, this.state.connections);

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
            const versions = await this.orm.call("myschool.process", "get_versions", [this.state.mapId]);
            this.state.versions = versions;
        } catch {
            this.state.versions = [];
        }
    }

    async onRestoreVersion(versionId) {
        try {
            await this.orm.call("myschool.process", "restore_version", [this.state.mapId], { version_id: versionId });
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
            link.download = `${this.state.mapName || 'process_composer'}.png`;
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
        link.download = `${this.state.mapName || 'process_composer'}.svg`;
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

    // --- Export draw.io XML ---

    onExportDrawio() {
        if (this.state.steps.length === 0 && this.state.lanes.length === 0) {
            this.notification.add("Niets te exporteren — het diagram is leeg.", { type: "warning" });
            return;
        }
        const xmlStr = this._buildDrawioXml();
        const blob = new Blob([xmlStr], { type: 'application/xml;charset=utf-8' });
        const link = document.createElement('a');
        link.download = `${this.state.mapName || 'process'}.drawio`;
        link.href = URL.createObjectURL(blob);
        link.click();
        URL.revokeObjectURL(link.href);
        this.notification.add("Draw.io bestand geëxporteerd.", { type: "success" });
    }

    _buildDrawioXml() {
        const lanes = this.state.lanes;
        const steps = this.state.steps;
        const connections = this.state.connections;

        // Map our IDs → draw.io string IDs
        const idMap = {};
        let nextDioId = 2;
        for (const lane of lanes) { idMap[lane.id] = String(nextDioId++); }
        for (const step of steps) { idMap[step.id] = String(nextDioId++); }

        // Compute lane width: rightmost step edge + padding
        let maxRight = 600;
        for (const step of steps) {
            const ds = this._stepDefaults(step.step_type);
            const right = step.x_position + (step.width || ds.width);
            if (right > maxRight) maxRight = right;
        }
        const laneWidth = Math.round(maxRight + 100);

        const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

        const lines = [];
        lines.push(`<mxfile host="myschool_processcomposer" modified="${new Date().toISOString()}" type="device">`);
        lines.push(`  <diagram id="diagram_1" name="${esc(this.state.mapName || 'Process')}">`);
        lines.push(`    <mxGraphModel grid="1" gridSize="20" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" math="0" shadow="0">`);
        lines.push(`      <root>`);
        lines.push(`        <mxCell id="0"/>`);
        lines.push(`        <mxCell id="1" parent="0"/>`);

        // --- Lanes ---
        for (const lane of lanes) {
            const dioId = idMap[lane.id];
            const color = lane.color || '#E3F2FD';
            const style = `swimlane;horizontal=1;startSize=30;fillColor=${color};swimlaneLine=1;rounded=0;whiteSpace=wrap;html=1;`;
            lines.push(`        <mxCell id="${dioId}" value="${esc(lane.name)}" style="${esc(style)}" vertex="1" parent="1">`);
            lines.push(`          <mxGeometry x="0" y="${Math.round(lane.y_position)}" width="${laneWidth}" height="${Math.round(lane.height)}" as="geometry"/>`);
            lines.push(`        </mxCell>`);
        }

        // --- Steps ---
        for (const step of steps) {
            const dioId = idMap[step.id];
            const style = this._drawioStepStyle(step);
            const ds = this._stepDefaults(step.step_type);
            const w = step.width || ds.width;
            const h = step.height || ds.height;

            // If step is in a lane, use relative coordinates and lane as parent
            const lane = lanes.find(l => l.id === step.lane_id);
            let parentId = '1';
            let x = Math.round(step.x_position);
            let y = Math.round(step.y_position);
            if (lane) {
                parentId = idMap[lane.id];
                x = Math.round(step.x_position);   // lanes start at x=0
                y = Math.round(step.y_position - lane.y_position);
            }

            lines.push(`        <mxCell id="${dioId}" value="${esc(step.name)}" style="${esc(style)}" vertex="1" parent="${parentId}">`);
            lines.push(`          <mxGeometry x="${x}" y="${y}" width="${Math.round(w)}" height="${Math.round(h)}" as="geometry"/>`);
            lines.push(`        </mxCell>`);
        }

        // --- Connections ---
        for (const conn of connections) {
            const connId = String(nextDioId++);
            const srcId = idMap[conn.source_step_id];
            const tgtId = idMap[conn.target_step_id];
            if (!srcId || !tgtId) continue;

            let style = 'edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;';
            if (conn.connection_type === 'message') {
                style += 'dashed=1;dashPattern=8 4;';
            } else if (conn.connection_type === 'association') {
                style += 'dashed=1;dashPattern=2 2;strokeColor=#999999;';
            }

            const label = conn.label || '';
            lines.push(`        <mxCell id="${connId}" value="${esc(label)}" style="${esc(style)}" edge="1" source="${srcId}" target="${tgtId}" parent="1">`);
            lines.push(`          <mxGeometry relative="1" as="geometry"/>`);
            lines.push(`        </mxCell>`);
        }

        lines.push(`      </root>`);
        lines.push(`    </mxGraphModel>`);
        lines.push(`  </diagram>`);
        lines.push(`</mxfile>`);

        return lines.join('\n');
    }

    /**
     * Map a process composer step to a draw.io style string.
     */
    _drawioStepStyle(step) {
        const customColor = step.color || '';
        switch (step.step_type) {
            case 'start': {
                const fill = customColor || '#d5e8d4';
                return `ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=${fill};strokeColor=#82b366;`;
            }
            case 'end': {
                const fill = customColor || '#f8cecc';
                return `ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=${fill};strokeColor=#b85450;double=1;`;
            }
            case 'task': {
                const fill = customColor || '#dae8fc';
                return `rounded=1;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#6c8ebf;`;
            }
            case 'subprocess': {
                const fill = customColor || '#e1d5e7';
                return `shape=mxgraph.flowchart.predefined_process;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#9673a6;`;
            }
            case 'condition': {
                const fill = customColor || '#d5e8d4';
                return `rhombus;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#82b366;`;
            }
            case 'gateway_exclusive': {
                const fill = customColor || '#fff2cc';
                return `rhombus;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#d6b656;`;
            }
            case 'gateway_parallel': {
                const fill = customColor || '#fff2cc';
                return `rhombus;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#d6b656;`;
            }
            default: {
                const fill = customColor || '#dae8fc';
                return `rounded=1;whiteSpace=wrap;html=1;fillColor=${fill};strokeColor=#6c8ebf;`;
            }
        }
    }

    // --- Print ---

    onPrint() {
        window.print();
    }

    // --- Import draw.io ---

    onImportDrawio() {
        if (!this.state.mapId) {
            this.notification.add("Open een procesmap voordat je importeert.", { type: "warning" });
            return;
        }
        const input = this.drawioFileInput.el;
        if (input) {
            input.value = '';
            input.click();
        }
    }

    async _onDrawioFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;
        try {
            const content = await file.text();
            const mxXml = await this._extractMxGraphXml(content, file.name);
            if (!mxXml) {
                this.notification.add("Kon geen draw.io diagram vinden in het bestand.", { type: "danger" });
                return;
            }
            const result = this._parseDrawioCells(mxXml);
            if (result.steps.length === 0 && result.lanes.length === 0) {
                this.notification.add("Geen elementen gevonden in het diagram.", { type: "warning" });
                return;
            }
            // Replace current diagram content
            this.state.lanes = result.lanes;
            this.state.steps = result.steps;
            this.state.connections = result.connections;
            this.state.dirty = true;
            this._pushHistory();
            this.onFitView();
            const counts = [];
            if (result.lanes.length) counts.push(`${result.lanes.length} lane(s)`);
            if (result.steps.length) counts.push(`${result.steps.length} stap(pen)`);
            if (result.connections.length) counts.push(`${result.connections.length} verbinding(en)`);
            this.notification.add(`Draw.io diagram geïmporteerd: ${counts.join(', ')}`, { type: "success" });
        } catch (e) {
            this.notification.add("Import mislukt: " + (e.message || e), { type: "danger" });
        }
    }

    /**
     * Extract mxGraphModel XML from draw.io export files (XML, SVG, HTML).
     */
    async _extractMxGraphXml(content, fileName) {
        const parser = new DOMParser();
        const ext = (fileName.split('.').pop() || '').toLowerCase();

        // --- SVG: mxGraphModel is URL-encoded in the 'content' attribute of <svg> ---
        if (ext === 'svg') {
            const doc = parser.parseFromString(content, 'image/svg+xml');
            const svgEl = doc.querySelector('svg');
            if (svgEl) {
                const encoded = svgEl.getAttribute('content');
                if (encoded) {
                    try { return decodeURIComponent(encoded); } catch { return encoded; }
                }
            }
            // Fallback: look for mxGraphModel in the SVG text
            const mxMatch = content.match(/<mxGraphModel[\s\S]*?<\/mxGraphModel>/);
            if (mxMatch) return mxMatch[0];
            return null;
        }

        // --- HTML: draw.io embeds diagram in data-mxgraph JSON attribute ---
        if (ext === 'html' || ext === 'htm') {
            const dataMatch = content.match(/data-mxgraph="([^"]*)"/s);
            if (dataMatch) {
                const decoded = dataMatch[1]
                    .replace(/&quot;/g, '"').replace(/&amp;/g, '&')
                    .replace(/&lt;/g, '<').replace(/&gt;/g, '>');
                try {
                    const json = JSON.parse(decoded);
                    if (json.xml) return json.xml;
                } catch { /* fall through */ }
            }
            const mxMatch = content.match(/<mxGraphModel[\s\S]*?<\/mxGraphModel>/);
            if (mxMatch) return mxMatch[0];
            return null;
        }

        // --- XML / .drawio ---
        if (content.includes('<mxfile')) {
            const doc = parser.parseFromString(content, 'text/xml');
            const diagram = doc.querySelector('diagram');
            if (diagram) {
                // Uncompressed: inline mxGraphModel element
                const mxModel = diagram.querySelector('mxGraphModel');
                if (mxModel) {
                    return new XMLSerializer().serializeToString(mxModel);
                }
                // Compressed/encoded content inside <diagram>
                const textContent = diagram.textContent.trim();
                if (textContent) {
                    // Try URL-decode
                    try {
                        const urlDecoded = decodeURIComponent(textContent);
                        if (urlDecoded.includes('<mxGraphModel')) return urlDecoded;
                    } catch { /* fall through */ }
                    // Try base64 → deflate-raw → URL-decode (draw.io compressed format)
                    try {
                        const binary = atob(textContent);
                        const inflated = await this._inflateRaw(binary);
                        const urlDecoded = decodeURIComponent(inflated);
                        if (urlDecoded.includes('<mxGraphModel')) return urlDecoded;
                    } catch { /* fall through */ }
                    // Try base64 → URL-decode (without compression)
                    try {
                        const decoded = atob(textContent);
                        if (decoded.includes('<mxGraphModel')) return decoded;
                        const urlDecoded = decodeURIComponent(decoded);
                        if (urlDecoded.includes('<mxGraphModel')) return urlDecoded;
                    } catch { /* fall through */ }
                }
            }
        }

        // Direct mxGraphModel (no wrapper)
        if (content.includes('<mxGraphModel')) return content;

        return null;
    }

    /**
     * Inflate raw-deflated binary string using browser DecompressionStream.
     */
    async _inflateRaw(binaryString) {
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        // Try deflate-raw first (draw.io default), then fall back to deflate (zlib)
        for (const format of ['deflate-raw', 'deflate']) {
            try {
                const ds = new DecompressionStream(format);
                const writer = ds.writable.getWriter();
                writer.write(bytes);
                writer.close();
                const reader = ds.readable.getReader();
                const chunks = [];
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    chunks.push(value);
                }
                const totalLen = chunks.reduce((acc, c) => acc + c.length, 0);
                const result = new Uint8Array(totalLen);
                let offset = 0;
                for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
                return new TextDecoder().decode(result);
            } catch { /* try next format */ }
        }
        throw new Error("Decompression failed");
    }

    /**
     * Parse mxGraphModel XML into process composer lanes, steps, and connections.
     */
    _parseDrawioCells(xmlString) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlString, 'text/xml');
        const cells = doc.querySelectorAll('mxCell');

        const idMap = {};           // draw.io ID → temp ID
        const lanes = [];
        const steps = [];
        const connections = [];
        const lanePositions = {};   // draw.io lane ID → {x, y, w, h}

        // --- Pass 1: Swimlanes ---
        for (const cell of cells) {
            const id = cell.getAttribute('id');
            const style = cell.getAttribute('style') || '';
            const vertex = cell.getAttribute('vertex');
            const geom = cell.querySelector('mxGeometry');
            if (!vertex || !style.includes('swimlane')) continue;

            const tempId = this.nextTempId--;
            idMap[id] = tempId;
            const x = parseFloat(geom?.getAttribute('x') || '0');
            const y = parseFloat(geom?.getAttribute('y') || '0');
            const w = parseFloat(geom?.getAttribute('width') || '800');
            const h = parseFloat(geom?.getAttribute('height') || '150');
            lanePositions[id] = { x, y, w, h };

            const rawName = (cell.getAttribute('value') || 'Lane').replace(/<[^>]*>/g, '').trim();
            lanes.push({
                id: tempId,
                name: rawName || 'Lane',
                sequence: lanes.length * 10 + 10,
                color: this._drawioExtractColor(style, 'fillColor') || this._laneColors[lanes.length % this._laneColors.length],
                y_position: Math.round(y),
                height: Math.round(h),
                org_id: false, org_name: '',
                role_id: false, role_name: '',
            });
        }

        // --- Pass 2: Vertices (steps) ---
        for (const cell of cells) {
            const id = cell.getAttribute('id');
            const style = cell.getAttribute('style') || '';
            const vertex = cell.getAttribute('vertex');
            const parent = cell.getAttribute('parent');
            const geom = cell.querySelector('mxGeometry');
            if (!vertex || style.includes('swimlane')) continue;
            if (id === '0' || id === '1') continue;
            // Skip label-only cells (children of edges, or cells with relative geometry and no size)
            if (geom && geom.getAttribute('relative') === '1') continue;
            // Skip cells inside swimlane headers (no geometry or very small)
            const w = parseFloat(geom?.getAttribute('width') || '0');
            const h = parseFloat(geom?.getAttribute('height') || '0');
            if (w < 10 || h < 10) continue;

            const tempId = this.nextTempId--;
            idMap[id] = tempId;

            let x = parseFloat(geom?.getAttribute('x') || '0');
            let y = parseFloat(geom?.getAttribute('y') || '0');

            // Convert relative coordinates (inside swimlane parent) to absolute
            if (parent && lanePositions[parent]) {
                x += lanePositions[parent].x;
                y += lanePositions[parent].y;
            }

            const rawValue = cell.getAttribute('value') || '';
            const cleanName = rawValue.replace(/<[^>]*>/g, '').trim();
            const stepType = this._drawioDetectStepType(style, cleanName);
            const defaults = this._stepDefaults(stepType);

            steps.push({
                id: tempId,
                name: cleanName || defaults.name,
                description: '',
                step_type: stepType,
                x_position: Math.round(x),
                y_position: Math.round(y),
                width: Math.round(stepType === 'start' || stepType === 'end' ? defaults.width : w || defaults.width),
                height: Math.round(stepType === 'start' || stepType === 'end' ? defaults.height : h || defaults.height),
                lane_id: (parent && idMap[parent]) ? idMap[parent] : false,
                role_id: false, role_name: '',
                responsible: '', system_action: '',
                data_fields: '', color: '', icon: '',
                annotation: '',
                sub_process_id: false, sub_process_name: '',
            });
        }

        // Auto-assign lanes for steps not already in a lane
        if (lanes.length > 0) {
            for (const step of steps) {
                if (!step.lane_id) {
                    const lane = lanes.find(l =>
                        step.y_position >= l.y_position && step.y_position < l.y_position + l.height
                    );
                    if (lane) step.lane_id = lane.id;
                }
            }
        }

        // --- Pass 3: Edges (connections) ---
        for (const cell of cells) {
            const edge = cell.getAttribute('edge');
            const source = cell.getAttribute('source');
            const target = cell.getAttribute('target');
            if (!edge || !source || !target) continue;

            const sourceId = idMap[source];
            const targetId = idMap[target];
            if (sourceId === undefined || targetId === undefined) continue;

            const rawLabel = (cell.getAttribute('value') || '').replace(/<[^>]*>/g, '').trim();
            connections.push({
                id: this.nextTempId--,
                source_step_id: sourceId,
                target_step_id: targetId,
                label: rawLabel,
                connection_type: 'sequence',
                waypoints: [],
                source_port: false,
                target_port: false,
                label_offset: { t: 0.5 },
            });
        }

        return { lanes, steps, connections };
    }

    /**
     * Detect process composer step type from draw.io style string and label.
     */
    _drawioDetectStepType(style, label) {
        const s = style.toLowerCase();
        const v = (label || '').toLowerCase();

        // Ellipse / circle → start or end event
        if (s.includes('ellipse') || s.includes('shape=mxgraph.flowchart.terminator') ||
            s.includes('shape=mxgraph.flowchart.start')) {
            if (v.includes('end') || v.includes('einde') || v.includes('stop') ||
                s.includes('doubleellipse') || s.includes('double=1') ||
                s.includes('fillcolor=#ff') || s.includes('fillcolor=#e5')) {
                return 'end';
            }
            return 'start';
        }

        // Diamond / rhombus → gateway or condition
        if (s.includes('rhombus') || s.includes('shape=mxgraph.flowchart.decision')) {
            if (v.includes('?') || v.includes('if') || v.includes('als')) return 'condition';
            if (v.includes('+') || v.includes('and') || v.includes('parallel')) return 'gateway_parallel';
            return 'gateway_exclusive';
        }

        // Predefined process / sub-process markers
        if (s.includes('shape=mxgraph.flowchart.predefined_process') ||
            s.includes('shape=mxgraph.flowchart.subprocess') ||
            s.includes('childlayout')) {
            return 'subprocess';
        }

        // Default: task
        return 'task';
    }

    /**
     * Extract a color value from a draw.io style string.
     */
    _drawioExtractColor(style, key) {
        const re = new RegExp(key + '=(#[0-9a-fA-F]{3,8})', 'i');
        const match = style.match(re);
        return match ? match[1] : null;
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
        const margin = 20;
        this.state.panX = margin;
        if (this.state.lanes.length > 0) {
            const minY = Math.min(...this.state.lanes.map(l => l.y_position));
            this.state.panY = -(minY - margin);
        } else {
            this.state.panY = margin;
        }
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
            tag: 'processcomposer_canvas',
            name: 'Sub-Process',
            context: { active_id: mapId },
        });
    }

    // --- Keyboard ---

    _onKeydown(ev) {
        // Escape closes role popover even when input is focused
        if (ev.key === 'Escape' && this.state.rolePopover.visible) {
            ev.preventDefault();
            this.closeRolePopover();
            return;
        }
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
            res_model: 'myschool.process',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }
}

registry.category("actions").add("processcomposer_canvas", ProcessMapperClient, { force: true });
