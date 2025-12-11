from odoo import models, fields

# myschool.person.type (PersonType.java)
class PersonType(models.Model):
    _name = 'myschool.person.type'
    _description = 'Persoon Type'

    name = fields.Char(string='Naam')
    is_active = fields.Boolean(string='Actief', default=False)