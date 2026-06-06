from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MyschoolServer(models.Model):
    """Register van een Odoo-instance / server (SRVMGR-2).

    Houdt per server de netwerk- & connectiegegevens, FQDN, environment,
    db/instance-id en de toegekende rol bij. De effectieve eigenschappen
    (capabilities) worden geërfd van de rol (SRVMGR-3).
    """

    _name = 'myschool.server'
    _description = 'MySchool Server / Instance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'environment, name'

    name = fields.Char(
        string='Name', required=True, tracking=True,
        help='Korte, herkenbare naam/label (bv. srvv-odoo-01).')
    code = fields.Char(
        string='Code',
        help='Korte unieke code voor weergave en automatisering.')
    active = fields.Boolean(default=True)

    # --- Netwerk- & connectiegegevens ---
    fqdn = fields.Char(
        string='FQDN', tracking=True,
        help='Fully Qualified Domain Name (bv. myschool-ict.olvp.be).')
    ip_address = fields.Char(string='IP Address')
    ssh_port = fields.Integer(string='SSH Port', default=22)
    http_port = fields.Integer(string='HTTP Port', default=8069)
    api_endpoint = fields.Char(
        string='API Endpoint',
        help='Basis-URL voor API-calls naar deze server (bv. https://host/jsonrpc).')

    # --- Identiteit / environment ---
    environment = fields.Selection([
        ('prod', 'Production'),
        ('test', 'Test'),
        ('dev', 'Development'),
    ], string='Environment', required=True, default='dev', tracking=True, index=True)
    db_name = fields.Char(
        string='Database', help='Naam van de Odoo-database op deze server.')
    instance_id = fields.Char(
        string='Instance ID',
        help='Welk instance-/server-id gebruikt wordt (bv. addons-channel, slot).')

    # --- Rol & effectieve eigenschappen (SRVMGR-3) ---
    role_id = fields.Many2one(
        'myschool.server.role', string='Role', tracking=True, index=True,
        ondelete='restrict',
        help='De rol typeert de server en bundelt de eigenschappen.')
    property_ids = fields.Many2many(
        'myschool.server.property', string='Effective Properties',
        compute='_compute_property_ids', store=False,
        help='Eigenschappen geërfd van de rol.')

    # --- People ---
    responsible_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        default=lambda self: self.env.user)

    description = fields.Html()

    _code_unique = models.Constraint('UNIQUE(code)', 'Server code must be unique.')
    _fqdn_unique = models.Constraint('UNIQUE(fqdn)', 'FQDN must be unique.')

    @api.depends('role_id', 'role_id.property_ids')
    def _compute_property_ids(self):
        for server in self:
            server.property_ids = server.role_id.property_ids

    @api.constrains('ssh_port', 'http_port')
    def _check_ports(self):
        for server in self:
            for port in (server.ssh_port, server.http_port):
                if port and not (0 < port < 65536):
                    raise ValidationError(_(
                        "Poortnummer moet tussen 1 en 65535 liggen."))
