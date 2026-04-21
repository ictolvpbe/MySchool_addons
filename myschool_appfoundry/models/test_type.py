from odoo import models, fields


class AppfoundryTestType(models.Model):
    _name = 'appfoundry.test.type'
    _description = 'AppFoundry Test Element Type'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    color = fields.Integer(string='Color Index')

    _name_unique = models.Constraint('UNIQUE(name)', 'Test type name must be unique.')
