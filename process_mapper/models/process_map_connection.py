from odoo import models, fields


class ProcessMapConnection(models.Model):
    _name = 'process.map.connection'
    _description = 'Process Map Connection'

    source_step_id = fields.Many2one('process.map.step', string='Source Step',
                                     required=True, ondelete='cascade')
    target_step_id = fields.Many2one('process.map.step', string='Target Step',
                                     required=True, ondelete='cascade')
    label = fields.Char(string='Label')
    connection_type = fields.Selection([
        ('sequence', 'Sequence Flow'),
        ('message', 'Message Flow'),
        ('association', 'Association'),
    ], string='Type', default='sequence', required=True)
    waypoints = fields.Text(string='Waypoints', default='[]',
                            help='JSON array of waypoint coordinates for orthogonal routing')
    source_port = fields.Selection([
        ('top', 'Top'), ('right', 'Right'), ('bottom', 'Bottom'), ('left', 'Left'),
    ], string='Source Port', help='Port on source shape where connection starts')
    target_port = fields.Selection([
        ('top', 'Top'), ('right', 'Right'), ('bottom', 'Bottom'), ('left', 'Left'),
    ], string='Target Port', help='Port on target shape where connection ends')
    label_offset = fields.Text(string='Label Offset', default='{}',
                               help='JSON {x, y} offset for label position')
    map_id = fields.Many2one('process.map', string='Process Map', required=True, ondelete='cascade')

    _no_self_connection = models.Constraint(
        'CHECK(source_step_id != target_step_id)',
        'A connection cannot link a step to itself.',
    )
