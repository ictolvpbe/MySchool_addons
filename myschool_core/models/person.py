# models/person.py
from odoo import models, fields


# myschool.person (Person.java)
class Person(models.Model):
    _name = 'myschool.person'
    _description = 'Persoon'
    #_inherit = 'mail.thread'

    # Naamgegevens
    name = fields.Char(string='Naam', size=100)
    first_name = fields.Char(string='Voornaam')
    short_name = fields.Char(string='Roepnaam')
    abbreviation = fields.Char(string='Initialen/Afkorting', help="Enkel voor personeel")

    # Unieke Referenties (Required in Java)
    sap_ref = fields.Char(string='SAP Referentie (pPersoon)', size=10)
    sap_person_uuid = fields.Char(string='SAP Persoon UUID', size=40)
    stam_boek_nr = fields.Char(string='Stamboeknummer', size=20)

    # Relatie naar PersonType
    person_type_id = fields.Many2one('myschool.person.type', string='Type Persoon', ondelete='set null', tracking=True)

    # Basis Gegevens
    gender = fields.Char(string='Geslacht', size=5)
    insz = fields.Char(string='Rijksregisternummer (INSZ)', size=20)
    birth_date = fields.Datetime(string='Geboortedatum')

    # Registratiegegevens (opgeslagen als String in Java)
    reg_start_date = fields.Char(string='Registratie Startdatum', size=50)
    reg_end_date = fields.Char(string='Registratie Einddatum', size=50)
    reg_inst_nr = fields.Char(string='Instellingsnummer', size=10)
    reg_group_code = fields.Char(string='Klascode', size=10)

    # Accounts
    email_cloud = fields.Char(string='E-mail Cloud')
    password = fields.Char(string='Wachtwoord', help="Enkel voor kinderen lagere school", groups="base.group_system")

    # One2many naar PersonDetails (zie PersonDetails.java)
    person_details_set = fields.One2many(
        'myschool.person.details',
        'person_id',
        string='Persoonsdetails'
    )

    is_active = fields.Boolean(string='Is Actief', default=False, tracking=True)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)

    _sql_constraints = [
        ('sap_ref_unique', 'unique(sap_ref)', 'De SAP Referentie moet uniek zijn!'),
        ('sap_uuid_unique', 'unique(sap_person_uuid)', 'De SAP Persoon UUID moet uniek zijn!'),
    ]