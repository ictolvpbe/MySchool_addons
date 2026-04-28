import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Force recompute of aantal_paginas (and dependent fields) for existing records."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    records = env['drukwerk.record'].search([])
    if not records:
        return
    _logger.info('[drukwerk 2.5] recomputing aantal_paginas on %d records', len(records))
    for record in records:
        record._compute_aantal_paginas()
    records._compute_totals()
    records._compute_cost_per_student()
