from odoo import models, fields


class AppfoundryTestType(models.Model):
    _name = 'appfoundry.test.type'
    _description = 'AppFoundry Test Element Type'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Test type name must be unique.'),
    ]
