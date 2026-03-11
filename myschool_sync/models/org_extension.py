# -*- coding: utf-8 -*-
"""
Org Extension
=============
Adds sync_uuid field to myschool.org for natural-key based record matching
during sync. UUID4 is auto-generated on create and backfilled for existing
records via init().
"""

from odoo import models, fields, api
import uuid
import logging

_logger = logging.getLogger(__name__)


class OrgSyncExtension(models.Model):
    _inherit = 'myschool.org'

    sync_uuid = fields.Char(
        string='Sync UUID',
        size=36,
        index=True,
        copy=False,
        help='Unique identifier for cross-instance sync',
    )

    _sync_uuid_unique = models.Constraint(
        'UNIQUE(sync_uuid)',
        'Sync UUID must be unique!',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('sync_uuid'):
                vals['sync_uuid'] = str(uuid.uuid4())
        return super().create(vals_list)

    def init(self):
        """Backfill sync_uuid for existing records that lack one."""
        self.env.cr.execute("""
            UPDATE myschool_org
            SET sync_uuid = gen_random_uuid()::text
            WHERE sync_uuid IS NULL OR sync_uuid = ''
        """)
        count = self.env.cr.rowcount
        if count:
            _logger.info('Backfilled sync_uuid on %d existing org records', count)
