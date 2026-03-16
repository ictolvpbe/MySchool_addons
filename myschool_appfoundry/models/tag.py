from odoo import models, fields


class AppfoundryTag(models.Model):
    _name = 'appfoundry.tag'
    _description = 'AppFoundry Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Tag name must be unique.'),
    ]
