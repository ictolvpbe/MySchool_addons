from odoo import models, fields


class MyschoolProcessVersion(models.Model):
    _name = 'myschool.process.version'
    _description = 'Myschool Process Version Snapshot'
    _order = 'version_number desc'

    map_id = fields.Many2one('myschool.process', string='Process Map', required=True, ondelete='cascade')
    version_number = fields.Integer(string='Version', required=True)
    snapshot = fields.Text(string='Snapshot (JSON)', required=True)
    note = fields.Char(string='Note')
