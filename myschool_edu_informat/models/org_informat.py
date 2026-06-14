# -*- coding: utf-8 -*-
"""Informat-extensie op myschool.org — per-school sync-knop.

Verhuisd uit myschool_core/models/org.py (slice 3 / connector-naden):
het platform noemt geen Informat-concept meer; deze plugin levert de
"Sync this school"-actie en de bijhorende knop (org-view-extend).
"""

from odoo import models, _
from odoo.exceptions import UserError


class Org(models.Model):
    _inherit = 'myschool.org'

    def action_sync_this_school(self):
        """Run an Informat sync **for this school only**.

        Useful for debugging in isolation: the regular sync iterates
        every school with ``sap_provider=INFORMAT`` (typically 5+),
        which makes log output hard to follow. This button restricts
        the run to ``self.inst_nr`` so logs and any task-cascade
        effects are scoped to one school.

        Available on org records that:
          • have ``sap_provider=INFORMAT`` (= '1')
          • have an ``inst_nr`` set
        """
        self.ensure_one()
        if self.sap_provider != '1':
            raise UserError(_(
                'Org %s has no INFORMAT sap_provider — nothing to sync.'
            ) % self.name)
        if not self.inst_nr:
            raise UserError(_(
                'Org %s has no inst_nr set; cannot scope the Informat '
                'sync to a single school without it.') % self.name)
        service = self.env['myschool.informat.service']
        result = service.execute_sync(inst_nrs=[self.inst_nr])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informat sync — %s') % self.name,
                'message': (_('Sync completed.') if result
                            else _('Sync ended with errors. '
                                   'Check the log for details.')),
                'type': 'success' if result else 'warning',
                'sticky': not result,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
