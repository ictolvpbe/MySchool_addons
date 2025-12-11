# models/period.py
from odoo import models, fields


# myschool.period (Period.java)
class Period(models.Model):
    _name = 'myschool.period'
    _description = 'Periode'

    name = fields.Char(string='Naam', required=True)
    name_in_sap = fields.Char(string='Naam in SAP', required=True)

    # Java Date + TemporalType.TIMESTAMP vertaald naar Datetime
    start_date = fields.Datetime(string='Startdatum')

    # Relatie
    period_type_id = fields.Many2one('myschool.period.type', string='Periode Type', ondelete='restrict')

    is_active = fields.Boolean(string='Actief', default=False)