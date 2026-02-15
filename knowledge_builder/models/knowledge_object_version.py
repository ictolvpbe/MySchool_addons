import json

from odoo import models, fields


class KnowledgeObjectVersion(models.Model):
    _name = 'knowledge.object.version'
    _description = 'Knowledge Object Version'
    _order = 'version_number desc'

    knowledge_object_id = fields.Many2one(
        'knowledge.object', string='Knowledge Object',
        required=True, ondelete='cascade',
    )
    version_number = fields.Integer(string='Version', required=True)
    snapshot = fields.Text(string='Snapshot (JSON)')
    summary = fields.Char(string='Summary')
    create_date = fields.Datetime(string='Created', readonly=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)

    def get_snapshot_data(self):
        self.ensure_one()
        if self.snapshot:
            return json.loads(self.snapshot)
        return {}
