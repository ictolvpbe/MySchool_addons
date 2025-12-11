# models/proprelation.py
from odoo import models, fields


# myschool.prop.relation (PropRelation.java)
class PropRelation(models.Model):
    _name = 'myschool.proprelation'
    _description = 'Persoon/Rol/Organisatie/Period Relatie'

    name = fields.Char(string='Naam')

    # Many2one Relaties (naar zichzelf of naar andere modellen)
    proprelation_type_id = fields.Many2one('myschool.proprelation.type', string='Relatie Type', ondelete='restrict')

    # Person Relaties
    id_person = fields.Many2one('myschool.person', string='Persoon')
    id_person_child = fields.Many2one('myschool.person', string='Kind Persoon')
    id_person_parent = fields.Many2one('myschool.person', string='Ouder Persoon')

    # Role Relaties
    id_role = fields.Many2one('myschool.role', string='Rol')
    id_role_parent = fields.Many2one('myschool.role', string='Ouder Rol')  # Kind Rol (idRoleChild) mist in PropRelation.java

    # Org Relaties
    id_org = fields.Many2one('myschool.org', string='Organisatie')
    id_org_parent = fields.Many2one('myschool.org', string='Ouder Organisatie')  # Kind Org (idOrgChild) mist in PropRelation.java

    # Period Relaties
    id_period = fields.Many2one('myschool.period', string='Periode')
    id_period_parent = fields.Many2one('myschool.period', string='Ouder Periode')  # Kind Periode (idPeriodChild) mist in PropRelation.java

    # Status & Datum
    is_administrative = fields.Boolean(string='Is Administratief', default=False)
    is_organisational = fields.Boolean(string='Is Organisatorisch', default=False)
    is_master = fields.Boolean(string='Is Master Relatie', default=False)
    is_active = fields.Boolean(string='Actief', default=False)
    start_date = fields.Datetime(string='Startdatum')
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)