# -*- coding: utf-8 -*-
"""Migration 0.3 → 0.4 — clean up legacy duplicates that block UNIQUE indexes.

Two cleanups, both **pre-schema-sync** so Odoo's index creation in
the same upgrade succeeds:

1. ``myschool_role.shortname == '0'``
   An older import path wrote literal ``"0"`` for empty SAP-shortnames
   on BACKEND roles. The UNIQUE(shortname) constraint blocks the
   index from being created on the second one. Convert to NULL —
   PostgreSQL allows multiple NULLs in a UNIQUE column.

2. ``myschool_sys_event_type`` orphan duplicates
   Earlier deployments programmatically created multiple rows per
   (code, name) via ``sys_event_type_service.create_event_type``.
   Some carry an XML-id (canonical from myschool_core or
   myschool_admin) and some don't (orphans). We:
   - Pick a canonical row per ``code`` — preferring the row tied to
     ``myschool_core``'s XML-id, falling back to the lowest id.
   - Redirect every FK reference from non-canonical rows to the
     canonical row (currently: ``myschool_sys_event.syseventtype_id``).
   - Delete the non-canonical rows.

Both steps are idempotent and no-ops when no offending rows exist.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _normalise_role_shortname(cr)
    _dedupe_sys_event_type(cr)
    _drop_orphan_process_map_views(cr)


# ---------------------------------------------------------------------------
# 1. myschool_role.shortname normalisation
# ---------------------------------------------------------------------------

def _normalise_role_shortname(cr):
    cr.execute("""
        UPDATE myschool_role
           SET shortname = NULL
         WHERE shortname = '0'
    """)
    if cr.rowcount:
        _logger.info(
            '[MIGRATE 0.4] myschool_role.shortname: %d row(s) "0" → NULL',
            cr.rowcount)


# ---------------------------------------------------------------------------
# 2. myschool_sys_event_type dedupe
# ---------------------------------------------------------------------------

def _dedupe_sys_event_type(cr):
    """For each duplicate ``code`` group, keep one canonical row and
    redirect / drop the rest.

    Canonical-row selection priority:
      1. Row with an ``ir_model_data`` entry where ``module='myschool_core'``
      2. Row with any ``ir_model_data`` entry (admin module's seed)
      3. Lowest ``id``

    Side-effects:
      - Updates ``myschool_sys_event.syseventtype_id`` to point to
        the canonical row before deleting the duplicates.
      - Releases ``ir_model_data`` rows that pointed to the
        non-canonical rows (so the next install can re-bind cleanly).
    """
    cr.execute("""
        SELECT code, array_agg(id ORDER BY id) AS ids
          FROM myschool_sys_event_type
         WHERE code IS NOT NULL
         GROUP BY code
        HAVING count(*) > 1
    """)
    duplicate_groups = cr.fetchall()
    if not duplicate_groups:
        return

    total_dropped = 0
    total_redirected = 0
    for code, ids in duplicate_groups:
        # Resolve canonical id — prefer myschool_core's XML-id row.
        canonical = _pick_canonical(cr, ids)
        losers = [i for i in ids if i != canonical]
        if not losers:
            continue

        # Redirect FK references on myschool_sys_event.
        cr.execute("""
            UPDATE myschool_sys_event
               SET syseventtype_id = %s
             WHERE syseventtype_id IN %s
        """, (canonical, tuple(losers)))
        redirected = cr.rowcount or 0
        total_redirected += redirected

        # Drop ir_model_data rows that bound to losers — leaves the
        # canonical XML-id intact.
        cr.execute("""
            DELETE FROM ir_model_data
             WHERE model = 'myschool.sys.event.type'
               AND res_id IN %s
        """, (tuple(losers),))

        # Drop the losing rows themselves.
        cr.execute("""
            DELETE FROM myschool_sys_event_type
             WHERE id IN %s
        """, (tuple(losers),))
        total_dropped += len(losers)

        _logger.info(
            '[MIGRATE 0.4] sys_event_type code=%s: kept id=%s, '
            'dropped ids=%s, redirected %d sys_event row(s)',
            code, canonical, losers, redirected)

    if total_dropped:
        _logger.info(
            '[MIGRATE 0.4] sys_event_type dedupe: dropped %d row(s), '
            'redirected %d sys_event reference(s)',
            total_dropped, total_redirected)


# ---------------------------------------------------------------------------
# 3. Orphan process.map views from a removed process_mapper module
# ---------------------------------------------------------------------------

def _drop_orphan_process_map_views(cr):
    """Remove leftover ``ir.ui.view`` rows for ``process.map`` that
    have no ``ir_model_data`` binding.

    Background: an earlier deployment had the process-map UI in a
    standalone ``process_mapper`` module. The current source lives in
    ``myschool_appfoundry`` (with a renamed group). Uninstalling the
    old module dropped the registration but left the view rows behind,
    so the form view at the old DB-id still references the
    long-gone ``process_mapper.group_process_mapper_manager`` group —
    Odoo logs a warning on every startup.

    Only orphan rows (no ir_model_data) for ``model='process.map'``
    are removed. The current ``myschool_appfoundry.view_process_map_*``
    views are untouched.
    """
    cr.execute("""
        SELECT v.id
          FROM ir_ui_view v
         WHERE v.model = 'process.map'
           AND NOT EXISTS (
             SELECT 1 FROM ir_model_data imd
              WHERE imd.model = 'ir.ui.view' AND imd.res_id = v.id)
    """)
    orphan_ids = [r[0] for r in cr.fetchall()]
    if not orphan_ids:
        return
    cr.execute(
        "DELETE FROM ir_ui_view WHERE id = ANY(%s)", (orphan_ids,))
    _logger.info(
        '[MIGRATE 0.4] dropped %d orphan process.map view(s) '
        '(ids=%s) — leftover from removed process_mapper module',
        len(orphan_ids), orphan_ids)


def _pick_canonical(cr, ids):
    """Choose the canonical id from a list of duplicates.

    Preference order:
      1. Row with ir_model_data.module='myschool_core'
      2. Row with any ir_model_data row
      3. Lowest id
    """
    # 1) myschool_core wins
    cr.execute("""
        SELECT res_id
          FROM ir_model_data
         WHERE model = 'myschool.sys.event.type'
           AND module = 'myschool_core'
           AND res_id IN %s
         ORDER BY res_id
         LIMIT 1
    """, (tuple(ids),))
    row = cr.fetchone()
    if row:
        return row[0]
    # 2) any ir_model_data row
    cr.execute("""
        SELECT res_id
          FROM ir_model_data
         WHERE model = 'myschool.sys.event.type'
           AND res_id IN %s
         ORDER BY (CASE WHEN module = 'myschool_admin' THEN 0 ELSE 1 END),
                  res_id
         LIMIT 1
    """, (tuple(ids),))
    row = cr.fetchone()
    if row:
        return row[0]
    # 3) lowest id
    return min(ids)
