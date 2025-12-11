from odoo import models, fields

class RoleType(models.Model):
    _name = 'myschool.role.type'
    _description = 'Rol Type'

    name = fields.Char(string='Naam', required=True)
    short_name = fields.Char(string='Afkorting', size=50)
    is_active = fields.Boolean(string='Actief', default=False)