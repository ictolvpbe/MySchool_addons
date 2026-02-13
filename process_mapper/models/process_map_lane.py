from odoo import models, fields


class ProcessMapLane(models.Model):
    _name = 'process.map.lane'
    _description = 'Process Map Swimlane'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Char(string='Color', default='#E3F2FD')
    y_position = fields.Float(string='Y Position', default=0.0)
    height = fields.Float(string='Height', default=150.0)

    org_id = fields.Many2one('myschool.org', string='Organization')
    role_id = fields.Many2one('myschool.role', string='Role')
    map_id = fields.Many2one('process.map', string='Process Map', required=True, ondelete='cascade')
