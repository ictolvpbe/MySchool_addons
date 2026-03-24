from odoo import models, fields


class ProcessMapLanePreset(models.Model):
    _name = 'process.map.lane.preset'
    _description = 'Lane Preset'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Char(default='#E3F2FD')
