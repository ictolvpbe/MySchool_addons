# -*- coding: utf-8 -*-
"""
Org model extension - adds reverse relation to proprelations
"""

from odoo import models, fields


class OrgProprelations(models.Model):
    """Extend myschool.org to add proprelation_ids One2many field."""
    _inherit = 'myschool.org'

    # This is just a reverse link - no database change needed
    # It allows us to show proprelations in the org form
    proprelation_ids = fields.One2many(
        'myschool.proprelation', 
        'id_org', 
        string='Relations'
    )
