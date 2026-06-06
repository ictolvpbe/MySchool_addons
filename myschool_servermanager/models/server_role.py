from odoo import models, fields, api


class MyschoolServerRole(models.Model):
    """Rol die een server typeert (account-server, webapps-server, ...),
    samengesteld uit eigenschappen (SRVMGR-3).

    Een rol bundelt een set herbruikbare ``myschool.server.property``-records.
    Wijzig je een eigenschap, dan erven alle rollen die ze gebruiken (en de
    servers met die rol) de wijziging automatisch.
    """

    _name = 'myschool.server.role'
    _description = 'Server Role'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True, translate=True)
    code = fields.Char(
        string='Code',
        help='Korte unieke code voor weergave en automatisering.')
    description = fields.Html()
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True, tracking=True)

    property_ids = fields.Many2many(
        'myschool.server.property',
        'myschool_server_role_property_rel', 'role_id', 'property_id',
        string='Properties', tracking=True,
        help='Eigenschappen waaruit deze rol is opgebouwd.')
    property_count = fields.Integer(
        compute='_compute_property_count', string='Property Count')

    server_ids = fields.One2many('myschool.server', 'role_id', string='Servers')
    server_count = fields.Integer(
        compute='_compute_server_count', string='Server Count')

    _code_unique = models.Constraint('UNIQUE(code)', 'Role code must be unique.')

    @api.depends('property_ids')
    def _compute_property_count(self):
        for role in self:
            role.property_count = len(role.property_ids)

    @api.depends('server_ids')
    def _compute_server_count(self):
        for role in self:
            role.server_count = len(role.server_ids)

    def action_open_servers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Servers',
            'res_model': 'myschool.server',
            'view_mode': 'list,form',
            'domain': [('role_id', '=', self.id)],
            'context': {'default_role_id': self.id},
        }
