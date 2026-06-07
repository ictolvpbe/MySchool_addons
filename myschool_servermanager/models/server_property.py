from odoo import models, fields, api


class MyschoolServerProperty(models.Model):
    """Herbruikbare eigenschap (capability) waaruit een server-rol is
    opgebouwd (SRVMGR-3).

    Een eigenschap is een bouwsteen die op zichzelf staat — bv.
    "draait sync-master", "host webapps", "bevat PII-data", "biedt API aan".
    Rollen verwijzen naar een set eigenschappen; servers erven hun effectieve
    eigenschappen van hun rol. Zo is een rol samenstelbaar i.p.v. een vaste
    enum.
    """

    _name = 'myschool.server.property'
    _description = 'Server Property (capability)'
    _order = 'category, sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        string='Code', required=True,
        help='Technische sleutel (uniek), gebruikt door enrollment/automatisering.')
    category = fields.Selection([
        ('hosting', 'Hosting'),
        ('data', 'Data & privacy'),
        ('sync', 'Sync / replicatie'),
        ('api', 'API'),
        ('auth', 'Authenticatie'),
        ('other', 'Overig'),
    ], default='other', required=True, index=True,
        help='Groepering van de eigenschap.')
    description = fields.Text()
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True)

    # --- Enrollment (SRVMGR-5): wat brengt deze capability mee? ---
    module_names = fields.Char(
        string='Required Modules',
        help='Komma-gescheiden technische module-namen die deze eigenschap '
             'vereist (bv. "myschool_assets,myschool_sync"). Worden bij '
             'enrollment op de server geïnstalleerd.')

    role_ids = fields.Many2many(
        'myschool.server.role',
        'myschool_server_role_property_rel', 'property_id', 'role_id',
        string='Used by Roles')
    role_count = fields.Integer(compute='_compute_role_count', string='Role Count')

    _code_unique = models.Constraint('UNIQUE(code)', 'Property code must be unique.')

    @api.depends('role_ids')
    def _compute_role_count(self):
        for prop in self:
            prop.role_count = len(prop.role_ids)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for prop in self:
            prop.display_name = f'{prop.name} [{prop.code}]' if prop.code else prop.name
