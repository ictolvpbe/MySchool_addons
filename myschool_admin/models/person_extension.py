# -*- coding: utf-8 -*-
"""
Person model extension - adds computed org fields for list view display.
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PersonExtension(models.Model):
    """Extend myschool.person with computed org fields from PERSON-TREE."""
    _inherit = 'myschool.person'

    tree_org_id = fields.Many2one(
        'myschool.org',
        string='Organization',
        compute='_compute_tree_org',
        store=True,
        compute_sudo=True,
    )

    tree_org_name_tree = fields.Char(
        related='tree_org_id.name_tree',
        string='Org Tree Path',
        store=True,
    )

    @api.depends('proprelation_ids', 'proprelation_ids.is_active',
                 'proprelation_ids.proprelation_type_id',
                 'proprelation_ids.id_org')
    def _compute_tree_org(self):
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for rec in self:
            if person_tree_type:
                tree_rel = self.env['myschool.proprelation'].search([
                    ('id_person', '=', rec.id),
                    ('proprelation_type_id', '=', person_tree_type.id),
                    ('is_active', '=', True),
                ], limit=1)
                rec.tree_org_id = tree_rel.id_org.id if tree_rel and tree_rel.id_org else False
            else:
                rec.tree_org_id = False
