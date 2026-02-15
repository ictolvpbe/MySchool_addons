from odoo import models, fields


class KnowledgeObjectStep(models.Model):
    _name = 'knowledge.object.step'
    _description = 'Knowledge Object Step'
    _order = 'sequence, id'

    name = fields.Char(string='Title', required=True, default='New Step')
    text = fields.Html(string='Text')
    image = fields.Binary(string='Picture', attachment=True)
    sequence = fields.Integer(string='Sequence', default=10)
    knowledge_object_id = fields.Many2one(
        'knowledge.object', string='Knowledge Object',
        required=True, ondelete='cascade',
    )
