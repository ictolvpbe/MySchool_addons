# -*- coding: utf-8 -*-
"""Migration 0.2 → 0.3 — split deactivation_date semantic.

The old ``myschool.person.deactivation_date`` column was used as
"date when the assignments dropped to zero". From 0.3 that semantic
moves to ``deactivation_pending_since``; the existing column gets a
new meaning ("date is_active was actually flipped to False").

This migration:
  - Copies any existing ``deactivation_date`` value into the new
    ``deactivation_pending_since`` column for active employees
    (= they're still in suspend-pipeline).
  - Clears ``deactivation_date`` for those records (it doesn't yet
    represent a real deactivation).
  - Leaves inactive persons alone — for them deactivation_date *is*
    the actual deactivation date, which matches the new semantic.

Idempotent: runs only when the new column is empty for a row.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Ensure both columns exist (the new one was added by the model).
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'myschool_person'
          AND column_name IN ('deactivation_date', 'deactivation_pending_since')
    """)
    cols = {r[0] for r in cr.fetchall()}
    if 'deactivation_date' not in cols or 'deactivation_pending_since' not in cols:
        _logger.info(
            '[MIGRATE-0.3] columns not both present; nothing to migrate '
            '(have: %s)', cols)
        return

    # 1) Active employees with deactivation_date set — push it into the
    #    new pending-since column and clear the old one.
    cr.execute("""
        UPDATE myschool_person
           SET deactivation_pending_since = deactivation_date,
               deactivation_date = NULL
         WHERE is_active = TRUE
           AND deactivation_date IS NOT NULL
           AND deactivation_pending_since IS NULL
    """)
    moved = cr.rowcount
    _logger.info(
        '[MIGRATE-0.3] active persons: moved deactivation_date → '
        'deactivation_pending_since for %d row(s)', moved)

    # 2) Inactive persons: deactivation_date stays — its meaning aligns
    #    with the new semantic ("actually flipped to False"). Nothing
    #    to do for them.
