from odoo import models, fields

# myschool.period.type (PeriodType.java)
class PeriodType(models.Model):
    _name = 'myschool.period.type'
    _description = 'Periode Type'

    name = fields.Char(string='Naam', required=True)
    is_active = fields.Boolean(string='Actief', default=False)