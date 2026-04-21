from odoo import models, fields, api


class Bus(models.Model):
    _name = 'bus_seater.bus'
    _description = 'Bus'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    license_plate = fields.Char(tracking=True)
    rows = fields.Integer(string='Number of Rows', default=10, required=True)
    seats_per_row = fields.Integer(string='Seats per Row', default=4, required=True)
    capacity = fields.Integer(compute='_compute_capacity', store=True)
    seat_ids = fields.One2many('bus_seater.seat', 'bus_id', string='Seats')
    seat_count = fields.Integer(compute='_compute_seat_count')
    is_active = fields.Boolean(default=True)
    note = fields.Text()

    @api.depends('rows', 'seats_per_row')
    def _compute_capacity(self):
        for bus in self:
            bus.capacity = bus.rows * bus.seats_per_row

    @api.depends('seat_ids')
    def _compute_seat_count(self):
        for bus in self:
            bus.seat_count = len(bus.seat_ids)

    def action_generate_seats(self):
        """Generate seats based on row/column layout."""
        for bus in self:
            bus.seat_ids.unlink()
            seat_vals = []
            for row in range(1, bus.rows + 1):
                for col in range(1, bus.seats_per_row + 1):
                    col_letter = chr(64 + col)  # A, B, C, D...
                    seat_vals.append({
                        'bus_id': bus.id,
                        'row_number': row,
                        'column_number': col,
                        'name': f'{row}{col_letter}',
                    })
            self.env['bus_seater.seat'].create(seat_vals)


class BusSeat(models.Model):
    _name = 'bus_seater.seat'
    _description = 'Bus Seat'
    _order = 'row_number, column_number'

    name = fields.Char(required=True)
    bus_id = fields.Many2one('bus_seater.bus', required=True, ondelete='cascade')
    row_number = fields.Integer(required=True)
    column_number = fields.Integer(required=True)
    state = fields.Selection([
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
    ], default='available', required=True)

    _sql_constraints = [
        ('unique_seat', 'unique(bus_id, row_number, column_number)',
         'Each seat position must be unique per bus.'),
    ]
