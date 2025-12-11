# models/person_details.py
from odoo import models, fields
# myschool.person.details (PersonDetails.java)
class PersonDetails(models.Model):
    _name = 'myschool.person.details'
    _description = 'Persoon Details (JSON Data)'

    # Relatie naar Person (ManyToOne) - verplicht en met cascade delete
    person_id = fields.Many2one(
        'myschool.person',
        string='Persoon',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Detailvelden (JSON Data als TEXT)
    full_json_string = fields.Text(string='Volledige JSON String')
    addresses = fields.Text(string='Adressen (JSON)')
    emails = fields.Text(string='E-mails (JSON)')
    comnrs = fields.Text(string='Communicatienummers (JSON)')
    bank_accounts = fields.Text(string='Bankrekeningen (JSON)')
    relations = fields.Text(string='Relaties (JSON)')
    partner = fields.Text(string='Partner (JSON)')
    children = fields.Text(string='Kinderen (JSON)')
    assignments = fields.Text(string='Assignments (JSON)')

    hoofd_ambt = fields.Char(string='Hoofd Ambt')
    extra_field_1 = fields.Char(string='Extra Veld 1 / InstNr') # Mapped from extraField1 in Java