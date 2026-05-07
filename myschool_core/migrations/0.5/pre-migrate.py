# -*- coding: utf-8 -*-
"""Migration 0.4 → 0.5 — drop obsolete letter report wrapper.

Background: 0.3 introduced the letter-template feature backed by an
``ir.actions.report`` (xmlid ``myschool_core.action_report_letter_template``)
plus a QWeb wrapper view (xmlid ``myschool_core.report_letter_document``).
We rendered to PDF via wkhtmltopdf through that action.

In 0.5 the rendering moved to WeasyPrint — pure Python, called
directly from ``letter_template.render_pdf``. The action.report and
the wrapper view are no longer reachable from any code path. Their
``ir_model_data`` entries got orphaned the moment we removed the XML
file from the manifest. This migration deletes them so we don't
ship dead records.

Idempotent: running on a DB that never had the records is a no-op.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _drop_legacy_letter_report(cr)


def _drop_legacy_letter_report(cr):
    """Remove the legacy ir.actions.report and QWeb view + their
    ir_model_data bindings.

    Order matters: report-action references the view via report_name,
    so drop the action first to avoid FK / cascade weirdness.
    """
    # 1. ir.actions.report (xmlid: myschool_core.action_report_letter_template)
    cr.execute("""
        DELETE FROM ir_act_report_xml
         WHERE id IN (
             SELECT res_id FROM ir_model_data
              WHERE module='myschool_core'
                AND name='action_report_letter_template'
                AND model='ir.actions.report')
    """)
    if cr.rowcount:
        _logger.info(
            '[MIGRATE 0.5] dropped %d obsolete ir.actions.report row(s)',
            cr.rowcount)
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module='myschool_core'
           AND name='action_report_letter_template'
    """)

    # 2. QWeb wrapper view (xmlid: myschool_core.report_letter_document)
    cr.execute("""
        DELETE FROM ir_ui_view
         WHERE id IN (
             SELECT res_id FROM ir_model_data
              WHERE module='myschool_core'
                AND name='report_letter_document'
                AND model='ir.ui.view')
    """)
    if cr.rowcount:
        _logger.info(
            '[MIGRATE 0.5] dropped %d obsolete QWeb wrapper view(s)',
            cr.rowcount)
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module='myschool_core'
           AND name='report_letter_document'
    """)
