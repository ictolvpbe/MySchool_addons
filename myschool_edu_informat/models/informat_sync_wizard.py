# -*- coding: utf-8 -*-
"""
Targeted Informat Sync Wizard
=============================

Lets admins fire a sync scoped to:
  - a chosen subset of schools (by org records, multi-select)
  - a chosen subset of phases (employees / students / classes / roles)

Vanaf v0.7 ondersteunt de wizard de safeguard-/review-flow:
  - ``require_review`` (default uit user-preference) → forceert de
    review-UI ook als de drempel niet overschreden wordt.
  - Als de run de drempel overschrijdt OF require_review aanstaat,
    redirecteren we naar de SAP-sync review-component.

Useful for debugging or for partial reruns. The persistent
``myschool.informat.service.config`` flags are NOT touched — the
overrides only apply to this single run.
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
    # Safeguard / review
    # ------------------------------------------------------------------

    require_review = fields.Boolean(
        string='Preview tonen voor commit',
        default=lambda self: self.env.user.myschool_sap_sync_always_review,
        help='Aan = na analyse wordt de review-UI getoond zodat je '
             'wijzigingen kan goedkeuren/blokkeren vooraleer ze '
             'effectief gecommit worden. Uit = onmiddellijk committen '
             'tenzij de veiligheidsdrempel overschreden is.')

    last_run_id = fields.Many2one(
        comodel_name='myschool.sap.sync.run',
        string='Laatste sync-run',
        readonly=True,
    )

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
            # execute_sync retourneert nu de sync.run-record (of False
            # bij analyse-fout). Wanneer require_review aanstaat of de
            # drempel overschreden is, gebeurt er nog GEEN commit — de
            # run blijft op awaiting_review/awaiting_approval staan.
            result = service.execute_sync(
                dev_mode=self.dev_mode,
                inst_nrs=inst_nrs,
                phases=phases,
                trigger='manual',
                require_review=self.require_review,
                auto_commit_on_no_breach=not self.require_review,
            )
        except Exception as e:
            _logger.exception('[INFORMAT-SYNC-WIZARD] sync failed')
            self.write({
                'state': 'done',
                'summary': _('Sync failed: %s') % e,
            })
            return self._reload_self()

        if not result:
            self.write({
                'state': 'done',
                'summary': _('Sync ended with errors. Check log/SysEvents.'),
            })
            return self._reload_self()

        # ``result`` is een sync.run-record.
        run = result
        self.write({
            'state': 'done',
            'last_run_id': run.id,
            'summary': self._build_summary(run),
        })

        # Bij review/breach/failed: open meteen de review-UI in plaats
        # van de draaiende-form modal. Bij 'failed' ziet de admin in de
        # UI de error_description + welke fasen wel/niet binnenkwamen.
        if run.state in ('awaiting_review', 'awaiting_approval',
                         'failed'):
            return run.action_open_review()

        return self._reload_self()

    def _build_summary(self, run):
        counts = run.get_counts()
        if not counts:
            return _('Geen wijzigingen gedetecteerd.')
        parts = []
        for ot, c in counts.items():
            total = c.get('add', 0) + c.get('upd', 0) + c.get('deact', 0)
            parts.append(
                f'{ot}: {total} (+{c.get("add", 0)}, '
                f'~{c.get("upd", 0)}, –{c.get("deact", 0)})'
            )
        state_label = dict(run._fields['state'].selection).get(
            run.state, run.state)
        return f'{run.name} → {state_label} | ' + ' | '.join(parts)

    def action_open_last_run_review(self):
        self.ensure_one()
        if not self.last_run_id:
            return False
        return self.last_run_id.action_open_review()

    def _reload_self(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
