from odoo import models, fields

# myschool.org (Org.java)
class Org(models.Model):
    _name = 'myschool.org'
    _description = 'Organisatie'
   # _inherit = 'mail.thread'

    #Tijdelijk
    OldId = fields.Char(string='OldId', required=False)

    # Aanname: SapProvider is een selection field. Vul de waarden aan indien nodig.
    SAP_PROVIDER_SELECTION = [('1', 'INFORMAT'), ('2', 'NONE')]  #TODO : get providers from database in stead of selection

    name = fields.Char(string='Naam', required=True)
    name_short = fields.Char(string='Korte Naam', required=True)
    inst_nr = fields.Char(string='Instellingsnummer', required=True, size=10)
    is_active = fields.Boolean(string='Actief', default=True, required=True)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)

    # Relatie
    org_type_id = fields.Many2one('myschool.org.type', string='Organisatie Type', ondelete='restrict')

    # Adres
    street = fields.Char(string='Straat', size=50)
    street_nr = fields.Char(string='Straatnummer', size=10)
    postal_code = fields.Char(string='Postcode', size=10)
    community = fields.Char(string='Gemeente', size=50)
    country = fields.Char(string='Land', size=30)

    # SAP & Accounts
    sap_provider = fields.Selection(SAP_PROVIDER_SELECTION, string='SAP Provider')
    sap_login = fields.Char(string='SAP Login', size=100)
    sap_password = fields.Char(string='SAP Wachtwoord', size=50, groups="base.group_system")
    is_administrative = fields.Boolean(string='Is Administratief', default=False)

    # AD/OU Velden
    domain_internal = fields.Char(string='Intern Domein')
    domain_external = fields.Char(string='Extern Domein')
    has_ou = fields.Boolean(string='Heeft OU', default=False)
    has_role = fields.Boolean(string='Heeft Role', default=False)
    has_comgroup = fields.Boolean(string='Heeft Communicatiegroep', default=False)
    has_secgroup = fields.Boolean(string='Heeft Securitygroep', default=False)
    ou_fqdn_internal = fields.Char(string='OU FQDN Intern')
    ou_fqdn_external = fields.Char(string='OU FQDN Extern')
    com_group_fqdn_internal = fields.Char(string='Com Groep FQDN Intern')
    com_group_fqdn_external = fields.Char(string='Com Groep FQDN Extern')
    sec_group_fqdn_internal = fields.Char(string='Sec Groep FQDN Intern')
    sec_group_fqdn_external = fields.Char(string='Sec Groep FQDN Extern')
    com_group_name = fields.Char(string='Com Groep Naam')
    sec_group_name = fields.Char(string='Sec Groep Naam')

    # Redundant
    orggroup_working_period = fields.Char(string='Werktijd Periode', size=30)
    richting = fields.Char(string='Richting', size=30)