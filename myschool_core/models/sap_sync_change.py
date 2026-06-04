# -*- coding: utf-8 -*-
"""
SAP-sync change — één record per geplande mutatie binnen een run.

Wordt aangemaakt in de analyse-fase (uit ``informat_service``) en pas in
de commit-fase omgezet naar een ``myschool.betask``.
"""

import json
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


OBJECT_TYPES = [
    ('PERSON', 'Person'),
    ('ORG', 'Org (school/klas)'),
    ('ORGGROUP', 'Org-group (persongroup)'),
    ('PROPRELATION', 'Proprelation'),
    ('ROLE', 'Role'),
    ('RELATION', 'Relation (legacy)'),
]

ACTIONS = [
    ('ADD', 'ADD'),
    ('UPD', 'UPD'),
    ('DEACT', 'DEACT'),
]

CHANGE_STATES = [
    ('planned', 'Gepland'),
    ('approved', 'Goedgekeurd'),
    ('blocked', 'Geblokkeerd'),
    ('to_review_later', 'Na te kijken'),
    ('applied', 'Toegepast'),
    ('superseded', 'Vervangen door nieuwere run'),
    ('failed', 'Mislukt'),
    ('cancelled', 'Geannuleerd'),
]


class SapSyncChange(models.Model):
    _name = 'myschool.sap.sync.change'
    _description = 'SAP Sync Planned Change'
    _order = 'run_id desc, object_type, action, source_key'

    run_id = fields.Many2one(
        comodel_name='myschool.sap.sync.run',
        string='Sync run',
        required=True,
        ondelete='cascade',
        index=True,
    )

    object_type = fields.Selection(
        selection=OBJECT_TYPES,
        string='Object',
        required=True,
        index=True,
    )

    action = fields.Selection(
        selection=ACTIONS,
        string='Actie',
        required=True,
        index=True,
    )

    target_model = fields.Char(
        string='Target model',
        help='Het Odoo-model waar de betask op zou inwerken, bv. myschool.person',
    )
    target_res_id = fields.Integer(
        string='Target res_id',
        help='ID van het bestaande record (leeg voor ADD).',
    )

    source_key = fields.Char(
        string='Bron-sleutel',
        help='Stamboek / inst_nr / UUID uit Informat — voor opzoeken & uniciteit.',
        index=True,
    )

    display_name = fields.Char(
        string='Naam',
    )

    payload_new_json = fields.Text(
        string='Nieuwe payload (JSON)',
        help='De data die Informat aanlevert.',
    )
    payload_old_json = fields.Text(
        string='Oude payload (JSON)',
        help='Snapshot van DB-state op moment van analyse (voor UPD/DEACT).',
    )

    betask_target = fields.Char(
        string='Betask target',
        default='DB',
        help='Welk betask-target gebruikt wordt bij commit (default: DB).',
    )
    betask_data2_json = fields.Text(
        string='Betask data2 (JSON)',
        help='Tweede payload voor de betask (bv. diff_original bij PROPRELATION/UPD).',
    )

    diff_summary = fields.Char(
        string='Diff samenvatting',
        help='Voor UPD: een korte lijst van veranderde velden.',
    )

    state = fields.Selection(
        selection=CHANGE_STATES,
        string='Status',
        required=True,
        default='planned',
        index=True,
    )
    state_reason = fields.Char(
        string='Reden',
        help='Toelichting bij blokkeren of "na te kijken".',
    )

    betask_id = fields.Many2one(
        comodel_name='myschool.betask',
        string='Betask',
        readonly=True,
        ondelete='set null',
        help='Gevuld nadat de commit-fase een betask heeft aangemaakt.',
    )

    reviewer_id = fields.Many2one(
        comodel_name='res.users',
        string='Beoordeeld door',
        readonly=True,
    )
    reviewed_at = fields.Datetime(
        string='Beoordeeld op',
        readonly=True,
    )

    def get_payload_new(self) -> dict:
        self.ensure_one()
        try:
            return json.loads(self.payload_new_json or '{}')
        except (ValueError, TypeError):
            return {}

    def get_payload_old(self) -> dict:
        self.ensure_one()
        if not self.payload_old_json:
            return {}
        try:
            return json.loads(self.payload_old_json)
        except (ValueError, TypeError):
            return {}
