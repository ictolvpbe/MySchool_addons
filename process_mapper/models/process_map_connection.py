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
    map_id = fields.Many2one('process.map', string='Process Map', required=True, ondelete='cascade')

    _sql_constraints = [
        ('no_self_connection', 'CHECK(source_step_id != target_step_id)',
         'A connection cannot link a step to itself.'),
    ]
