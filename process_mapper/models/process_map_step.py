from odoo import models, fields


class ProcessMapStep(models.Model):
    _name = 'process.map.step'
    _description = 'Process Map Step'

    STEP_TYPES = [
        ('start', 'Start Event'),
        ('end', 'End Event'),
        ('task', 'Task'),
        ('subprocess', 'Sub-Process'),
        ('condition', 'Condition (If/Else)'),
        ('gateway_exclusive', 'Exclusive Gateway'),
        ('gateway_parallel', 'Parallel Gateway'),
    ]

    name = fields.Char(string='Name', required=True, default='New Step')
    description = fields.Text(string='Description')
    step_type = fields.Selection(STEP_TYPES, string='Type', required=True, default='task')

    x_position = fields.Float(string='X Position', default=100.0)
    y_position = fields.Float(string='Y Position', default=100.0)
    width = fields.Float(string='Width', default=140.0)
    height = fields.Float(string='Height', default=60.0)

    lane_id = fields.Many2one('process.map.lane', string='Lane', ondelete='set null')
    map_id = fields.Many2one('process.map', string='Process Map', required=True, ondelete='cascade')
    role_id = fields.Many2one('myschool.role', string='Role')

    responsible = fields.Char(string='Responsible')
    system_action = fields.Char(string='System Action')
    data_fields = fields.Text(string='Data Fields',
                              help='Describe the data/fields this step needs or produces, one per line')

    color = fields.Char(string='Color', help='Custom fill color (hex) overriding the default type color')
    icon = fields.Char(string='Icon', help='FontAwesome icon class, e.g. fa-envelope')
    annotation = fields.Text(string='Annotation', help='Additional note or business rule for this step')
    sub_process_id = fields.Many2one('process.map', string='Linked Sub-Process', ondelete='set null')
