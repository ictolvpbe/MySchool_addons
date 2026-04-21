from odoo import models, fields, api


class BusRoute(models.Model):
    _name = 'bus_seater.route'
    _description = 'Bus Route'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    bus_id = fields.Many2one('bus_seater.bus', required=True, tracking=True)
    stop_ids = fields.One2many('bus_seater.stop', 'route_id', string='Stops')
    stop_count = fields.Integer(compute='_compute_stop_count')
    is_active = fields.Boolean(default=True, tracking=True)
    note = fields.Text()

    @api.depends('stop_ids')
    def _compute_stop_count(self):
        for route in self:
            route.stop_count = len(route.stop_ids)

class BusStop(models.Model):
    _name = 'bus_seater.stop'
    _description = 'Bus Stop'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    route_id = fields.Many2one('bus_seater.route', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    address = fields.Char()
    departure_time = fields.Float(string='Departure Time', help='Time in 24h format (e.g. 7.30)')
    arrival_time = fields.Float(string='Arrival Time', help='Time in 24h format (e.g. 7.25)')

    _sql_constraints = [
        ('unique_stop_name', 'unique(route_id, name)',
         'Stop name must be unique per route.'),
    ]
