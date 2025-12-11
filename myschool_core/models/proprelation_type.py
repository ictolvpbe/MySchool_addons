from odoo import models, fields

# myschool.proprelation.type (PropRelationType.java)
class PropRelationType(models.Model):
    _name = 'myschool.proprelation.type'
    _description = 'Relatie Eigenschap Type'

    name = fields.Char(string='Naam', required=True)
    usage = fields.Char(string='Gebruik', size=150)
    is_active = fields.Boolean(string='Actief', default=False)