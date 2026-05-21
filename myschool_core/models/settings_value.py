# -*- coding: utf-8 -*-
"""
Settings Value — concrete waarde voor een Settings Item op een scope

Eén record per (settings_item, scope). Scope = combinatie van
``org_id`` + ``person_id``:
- Beide leeg → globale waarde.
- ``org_id`` gezet → per-org waarde, met ``inherit_to_children`` voor
  fall-through naar sub-orgs (default True; opt-out per waarde).
- ``person_id`` gezet → per-person waarde (geen inheritance).

Combineren van org_id én person_id wordt niet ondersteund — dat zou
een 4D-matrix worden die nergens gebruikt wordt.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SettingsValue(models.Model):
    _name = 'myschool.settings.value'
    _description = 'MySchool Settings Value (waarde per scope)'
    _order = 'settings_item_id, org_id, person_id'
    _rec_name = 'display_name'

    settings_item_id = fields.Many2one(
        comodel_name='myschool.settings.item',
        string='Settings Item', required=True,
        ondelete='cascade', index=True)
    settings_key = fields.Char(
        related='settings_item_id.key', store=True, string='Sleutel',
        index=True)
    value_type = fields.Selection(
        related='settings_item_id.value_type', store=True)
    scope_kind = fields.Selection(
        related='settings_item_id.scope_kind', store=True,
        string='Scope Type')

    org_id = fields.Many2one(
        comodel_name='myschool.org', string='Organisatie',
        ondelete='cascade', index=True,
        help='Leeg = globale waarde of person-scoped.')
    person_id = fields.Many2one(
        comodel_name='myschool.person', string='Persoon',
        ondelete='cascade', index=True,
        help='Leeg = globale waarde of org-scoped.')

    # Eén kolom per waarde-type; alleen die overeenkomt met
    # settings_item_id.value_type wordt geconsumeerd door _extract_value().
    string_value = fields.Char(string='Waarde (tekst)')
    integer_value = fields.Integer(string='Waarde (getal)')
    boolean_value = fields.Boolean(string='Waarde (boolean)')

    inherit_to_children = fields.Boolean(
        string='Doorgeven aan sub-orgs', default=True,
        help='Wanneer aangevinkt geldt deze waarde ook voor alle '
             'sub-orgs die geen eigen override hebben. Default aan: '
             'opt-out per waarde, in lijn met de afspraak.')
    is_active = fields.Boolean(string='Actief', default=True, index=True)

    display_name = fields.Char(
        compute='_compute_display_name', store=True)
    value_display = fields.Char(
        compute='_compute_value_display',
        string='Effectieve waarde')
    scope_label = fields.Char(
        compute='_compute_scope_label', string='Scope')

    # Eén waarde-record per (SI, org, person)-combinatie. Met nullable
    # kolommen behandelt PostgreSQL NULL ≠ NULL, dus meerdere globale
    # waarden voor dezelfde SI worden door dit constraint NIET uitgesloten —
    # daarvoor het python-level _check_scope_unique constraint hieronder.
    _uniq_per_scope = models.Constraint(
        'UNIQUE(settings_item_id, org_id, person_id)',
        'Voor deze Settings Item bestaat al een waarde op deze scope.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('settings_item_id.key', 'org_id', 'person_id')
    def _compute_display_name(self):
        for rec in self:
            key = rec.settings_item_id.key or '?'
            if rec.person_id:
                rec.display_name = f"{key} @ persoon:{rec.person_id.display_name}"
            elif rec.org_id:
                tree = rec.org_id.name_tree or rec.org_id.name
                rec.display_name = f"{key} @ {tree}"
            else:
                rec.display_name = f"{key} (globaal)"

    @api.depends('string_value', 'integer_value', 'boolean_value',
                 'settings_item_id.value_type',
                 'settings_item_id.is_encrypted')
    def _compute_value_display(self):
        for rec in self:
            item = rec.settings_item_id
            if item.is_encrypted:
                rec.value_display = '••••••••'
                continue
            if item.value_type == 'string':
                rec.value_display = rec.string_value or ''
            elif item.value_type == 'integer':
                rec.value_display = str(rec.integer_value or 0)
            elif item.value_type == 'boolean':
                rec.value_display = 'true' if rec.boolean_value else 'false'
            else:
                rec.value_display = ''

    @api.depends('org_id', 'person_id')
    def _compute_scope_label(self):
        for rec in self:
            if rec.person_id:
                rec.scope_label = 'persoon'
            elif rec.org_id:
                rec.scope_label = 'org'
            else:
                rec.scope_label = 'globaal'

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('org_id', 'person_id', 'settings_item_id')
    def _check_scope_unique(self):
        """org_id en person_id mogen niet beide gezet zijn; en de
        gekozen scope moet kloppen met scope_kind van de SI-definitie.
        """
        for rec in self:
            if rec.org_id and rec.person_id:
                raise ValidationError(_(
                    "Een Settings Value kan niet zowel een org als "
                    "een persoon hebben — kies één scope."))
            item = rec.settings_item_id
            if not item:
                continue
            if item.scope_kind == 'global' and (rec.org_id or rec.person_id):
                raise ValidationError(_(
                    "SI '%s' is 'Alleen globaal' — een per-org of "
                    "per-person waarde is niet toegestaan."
                ) % item.key)
            if item.scope_kind == 'org' and rec.person_id:
                raise ValidationError(_(
                    "SI '%s' is 'Alleen per organisatie' — een "
                    "per-person waarde is niet toegestaan."
                ) % item.key)
            if item.scope_kind == 'person' and rec.org_id:
                raise ValidationError(_(
                    "SI '%s' is 'Alleen per persoon' — een per-org "
                    "waarde is niet toegestaan."
                ) % item.key)
            if item.scope_kind == 'both' and rec.person_id:
                raise ValidationError(_(
                    "SI '%s' is 'Globaal + per organisatie' — een "
                    "per-person waarde is niet toegestaan."
                ) % item.key)
