# -*- coding: utf-8 -*-
"""
SAP-sync run — één record per sync-invocatie.

Houdt analyse-resultaat (geplande wijzigingen + counts per object_type) vast
voor de safeguard-flow (drempel-check, review, approve, commit).
"""

import json
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SapSyncRun(models.Model):
    _name = 'myschool.sap.sync.run'
    _description = 'SAP Sync Run'
    _order = 'started_at desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Run Name',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
    )

    trigger = fields.Selection(
        selection=[
            ('cron', 'Automatisch (cron)'),
            ('manual', 'Manueel (wizard)'),
        ],
        string='Trigger',
        required=True,
        default='manual',
        tracking=True,
    )

    state = fields.Selection(
        selection=[
            ('analysing', 'Analyseren'),
            ('awaiting_approval', 'Wacht op goedkeuring (drempel)'),
            ('awaiting_review', 'Wacht op review'),
            ('applying', 'Toepassen'),
            ('applied', 'Toegepast'),
            ('cancelled', 'Geannuleerd'),
            ('failed', 'Mislukt'),
        ],
        string='Status',
        required=True,
        default='analysing',
        tracking=True,
        index=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Aangevraagd door',
        default=lambda self: self.env.user,
        readonly=True,
    )

    started_at = fields.Datetime(
        string='Gestart',
        default=lambda self: fields.Datetime.now(),
        readonly=True,
    )
    finished_at = fields.Datetime(
        string='Klaar op',
        readonly=True,
    )

    inst_nrs = fields.Char(
        string='Scope (inst_nrs)',
        help='Komma-gescheiden lijst van inst_nrs, leeg = alle scholen met sap_provider=INFORMAT',
    )

    phases_json = fields.Text(
        string='Phases (JSON)',
        help='Welke fasen actief tijdens deze run: {"sync_roles": bool, ...}',
    )

    counts_json = fields.Text(
        string='Counts (JSON)',
        help='Per object_type: {"PERSON": {"add": N, "upd": N, "deact": N, '
             '"total_existing": N, "pct": F}, ...}',
    )

    threshold_breach = fields.Boolean(
        string='Drempel overschreden',
        readonly=True,
        index=True,
    )

    threshold_breach_details = fields.Text(
        string='Drempel-details',
        readonly=True,
    )

    summary = fields.Text(
        string='Resultaat-samenvatting',
    )

    error_description = fields.Text(
        string='Fout-beschrijving',
        readonly=True,
    )

    change_ids = fields.One2many(
        comodel_name='myschool.sap.sync.change',
        inverse_name='run_id',
        string='Geplande wijzigingen',
    )

    change_count = fields.Integer(
        string='# wijzigingen',
        compute='_compute_change_count',
        store=True,
    )

    require_review = fields.Boolean(
        string='Review verplicht (door wizard)',
        default=False,
        help='Manueel ingesteld op de wizard. Forceert de review-UI ongeacht drempel.',
    )

    active = fields.Boolean(default=True)

    @api.depends('change_ids')
    def _compute_change_count(self):
        for run in self:
            run.change_count = len(run.change_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'myschool.sap.sync.run') or _('New')
        return super().create(vals_list)

    def get_counts(self) -> dict:
        self.ensure_one()
        try:
            return json.loads(self.counts_json or '{}')
        except (ValueError, TypeError):
            return {}

    def get_phases(self) -> dict:
        self.ensure_one()
        try:
            return json.loads(self.phases_json or '{}')
        except (ValueError, TypeError):
            return {}

    def action_open_review(self):
        """Open de OWL2 review-UI voor deze run."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'myschool_sap_sync_review',
            'name': _('SAP-sync review — %s') % self.name,
            'params': {'run_id': self.id},
            'target': 'current',
        }

    def action_apply(self):
        """Server-actie: voer de approved changes uit (commit_run)."""
        self.ensure_one()
        self.env['myschool.sap.sync.service'].commit_run(self.id)
        return self.action_open_review()

    def action_cancel(self):
        """Server-actie: annuleer de hele batch."""
        self.ensure_one()
        self.env['myschool.sap.sync.service'].cancel_run(self.id)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
