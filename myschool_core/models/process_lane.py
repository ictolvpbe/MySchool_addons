from odoo import models, fields


class MyschoolProcessLane(models.Model):
    _name = 'myschool.process.lane'
    _description = 'Myschool Process Swimlane'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Char(string='Color', default='#E3F2FD')
    y_position = fields.Float(string='Y Position', default=0.0)
    height = fields.Float(string='Height', default=150.0)

    org_id = fields.Many2one('myschool.org', string='Organization')
    role_id = fields.Many2one('myschool.role', string='Role')
    map_id = fields.Many2one('myschool.process', string='Process Map', required=True, ondelete='cascade')
