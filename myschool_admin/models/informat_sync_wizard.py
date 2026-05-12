# -*- coding: utf-8 -*-
"""
Targeted Informat Sync Wizard
=============================

Lets admins fire a sync scoped to:
  - a chosen subset of schools (by org records, multi-select)
  - a chosen subset of phases (employees / students / classes / roles)

Useful for debugging or for partial reruns. The persistent
``myschool.informat.service.config`` flags are NOT touched — the
overrides only apply to this single run.

The wizard delegates to ``execute_sync(inst_nrs, phases)`` so all
existing data fetch + cascade logic is reused.
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class InformatSyncWizard(models.TransientModel):
    _name = 'myschool.informat.sync.wizard'
    _description = 'Targeted Informat Sync'

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    org_ids = fields.Many2many(
        comodel_name='myschool.org',
        relation='myschool_informat_sync_wizard_org_rel',
        column1='wizard_id', column2='org_id',
        string='Schools / Schoolboards',
        domain="[('sap_provider', '=', '1'), ('inst_nr', '!=', False)]",
        help='Welke organisaties syncen. Leeg = alle schools met '
             'sap_provider=INFORMAT (het normale gedrag van de cron).')

    inst_nr_preview = fields.Char(
        string='inst_nr filter',
        compute='_compute_inst_nr_preview',
        help='De inst_nr-lijst die zo doorgegeven wordt aan execute_sync.')

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    sync_roles = fields.Boolean(
        string='Roles',
        default=False,
        help='Phase 1a: refresh BACKEND-rollen vanuit assignments.')
    sync_employees = fields.Boolean(
        string='Employees',
        default=False,
        help='Phase 1b: import/update employee-records + queue downstream tasks.')
    sync_classes = fields.Boolean(
        string='Classes',
        default=False,
        help='Phase 2a: import/update CLASSGROUP-orgs vanuit registrations.')
    sync_students = fields.Boolean(
        string='Students',
        default=False,
        help='Phase 2b: import/update student-records + queue downstream tasks.')

    dev_mode = fields.Boolean(
        string='Dev-mode',
        default=False,
        help='Lees JSON uit storage/sapimport/dev/ in plaats van de live API.')

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('done', 'Done'),
        ], default='draft', readonly=True)
    summary = fields.Char(string='Resultaat', readonly=True)

    # ==================================================================
    # Computes
    # ==================================================================

    @api.depends('org_ids')
    def _compute_inst_nr_preview(self):
        for wiz in self:
            if not wiz.org_ids:
                wiz.inst_nr_preview = '(alle scholen)'
                continue
            inst_nrs = sorted({o.inst_nr for o in wiz.org_ids if o.inst_nr})
            wiz.inst_nr_preview = ', '.join(inst_nrs) or '(geen)'

    # ==================================================================
    # Actions
    # ==================================================================

    def action_run(self):
        self.ensure_one()
        if not (self.sync_roles or self.sync_employees
                or self.sync_classes or self.sync_students):
            raise UserError(_(
                'Vink minstens één phase aan (Roles / Employees / '
                'Classes / Students).'))

        # Resolve schools — also expand SCHOOLBOARD selections to the
        # underlying schools (orgs that share the schoolboard's
        # children via ORG-TREE). For now, schoolboards are not
        # auto-expanded; admins pick the actual schools. If they pick
        # a schoolboard with sap_provider, that one's inst_nr is used.
        inst_nrs = sorted({o.inst_nr for o in self.org_ids if o.inst_nr}) \
            if self.org_ids else None

        phases = {
            'sync_roles': self.sync_roles,
            'sync_employees': self.sync_employees,
            'sync_classes': self.sync_classes,
            'sync_students': self.sync_students,
        }

        service = self.env['myschool.informat.service']
        try:
            ok = service.execute_sync(
                dev_mode=self.dev_mode,
                inst_nrs=inst_nrs,
                phases=phases,
            )
        except Exception as e:
            _logger.exception('[INFORMAT-SYNC-WIZARD] sync failed')
            self.write({
                'state': 'done',
                'summary': _('Sync failed: %s') % e,
            })
            return self._reload_self()

        self.write({
            'state': 'done',
            'summary': (_('Sync completed.') if ok
                        else _('Sync ended with errors. Check log.')),
        })
        return self._reload_self()

    def _reload_self(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
