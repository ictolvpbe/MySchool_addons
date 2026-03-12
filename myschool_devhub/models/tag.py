from odoo import models, fields


class DevhubTag(models.Model):
    _name = 'devhub.tag'
    _description = 'DevHub Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Tag name must be unique.'),
    ]
