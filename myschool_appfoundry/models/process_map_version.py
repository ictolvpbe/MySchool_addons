from odoo import models, fields


class ProcessMapVersion(models.Model):
    _name = 'process.map.version'
    _description = 'Process Map Version Snapshot'
    _order = 'version_number desc'

    map_id = fields.Many2one('process.map', string='Process Map', required=True, ondelete='cascade')
    version_number = fields.Integer(string='Version', required=True)
    snapshot = fields.Text(string='Snapshot (JSON)', required=True)
    note = fields.Char(string='Note')
