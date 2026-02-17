from odoo import models, fields


class ItsmService(models.Model):
    _name = 'itsm.service'
    _description = 'ITSM Service'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    category_id = fields.Many2one(
        'itsm.service.category',
        string='Category',
    )
    description = fields.Html(
        string='Description',
    )
    owner_id = fields.Many2one(
        'res.users',
        string='Service Owner',
        tracking=True,
    )
    state = fields.Selection(
        [
            ('design', 'Design'),
            ('operational', 'Operational'),
            ('retired', 'Retired'),
        ],
        string='State',
        default='design',
        tracking=True,
    )
    support_hours = fields.Char(
        string='Support Hours',
        help='e.g. Mon-Fri 8:00-17:00',
    )
    sla_ids = fields.One2many(
        'itsm.sla',
        'service_id',
        string='SLA Definitions',
    )
    ci_ids = fields.Many2many(
        'itsm.ci',
        string='Configuration Items',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
