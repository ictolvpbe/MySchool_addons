from odoo import models, fields

# ----------------------------------------------------------------------
# myschool.org.type (OrgType.java)
class OrgType(models.Model):
    _name = 'myschool.org.type'
    _description = 'Organisatie Type'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    is_active = fields.Boolean(string='Actief', default=False)