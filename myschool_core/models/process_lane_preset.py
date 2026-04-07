from odoo import models, fields


class MyschoolProcessLanePreset(models.Model):
    _name = 'myschool.process.lane.preset'
    _description = 'Lane Preset'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Char(default='#E3F2FD')
