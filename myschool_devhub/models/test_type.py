from odoo import models, fields


class DevhubTestType(models.Model):
    _name = 'devhub.test.type'
    _description = 'DevHub Test Element Type'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Test type name must be unique.'),
    ]
