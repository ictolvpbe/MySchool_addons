from odoo import models, fields


class PlannerTijdslot(models.Model):
    _name = 'planner.tijdslot'
    _description = 'Lesuur'
    _order = 'sequence'

    name = fields.Char(string='Lesuur', required=True)
    sequence = fields.Integer(string='Volgorde', default=10)
    hour_start = fields.Float(string='Begin (uur)', required=True)
    hour_end = fields.Float(string='Einde (uur)', required=True)
