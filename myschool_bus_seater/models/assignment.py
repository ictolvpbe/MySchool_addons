from odoo import models, fields, api


class BusSeatAssignment(models.Model):
    _name = 'bus_seater.assignment'
    _description = 'Bus Seat Assignment'
    _order = 'bus_id, seat_id'

    bus_id = fields.Many2one('bus_seater.bus', required=True, ondelete='cascade')
    seat_id = fields.Many2one(
        'bus_seater.seat', string='Seat',
        domain="[('bus_id', '=', bus_id), ('state', '=', 'available')]",
    )
    person_id = fields.Many2one('myschool.person', string='Persoon', required=True)
    seat_number = fields.Integer(string='Plaats nr.')

    @api.depends('person_id', 'seat_number')
    def _compute_display_name(self):
        for rec in self:
            if rec.person_id and rec.seat_number:
                rec.display_name = f'{rec.person_id.name} — Plaats {rec.seat_number}'
            elif rec.person_id:
                rec.display_name = rec.person_id.name
            else:
                rec.display_name = 'Nieuwe toewijzing'
