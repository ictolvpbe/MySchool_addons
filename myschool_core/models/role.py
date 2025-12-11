from odoo import models, fields

# myschool.role (Role.java)
class Role(models.Model):
    _name = 'myschool.role'
    _description = 'Rol'

    name = fields.Char(string='Naam', required=True)
    short_name = fields.Char(string='Korte Naam', required=True)

    # Let op: Java had 'priotity' (spelfout), hier gecorrigeerd naar 'priority'
    priority = fields.Integer(string='Prioriteit', help="Hoogste prioriteit bepaalt account creatie")

    # Relatie
    role_type_id = fields.Many2one('myschool.role.type', string='Rol Type', ondelete='restrict')

    has_ui_access = fields.Boolean(string='Heeft UI Toegang', default=True)
    has_group = fields.Boolean(string='Vereist Groep', default=False)
    has_accounts = fields.Boolean(string='Vereist Accounts', default=False)
    is_active = fields.Boolean(string='Actief', default=False)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)