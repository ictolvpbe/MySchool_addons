from odoo import models, fields


class KnowledgeObjectStepComment(models.Model):
    _name = 'knowledge.object.step.comment'
    _description = 'Knowledge Object Step Comment'
    _order = 'create_date desc'

    step_id = fields.Many2one(
        'knowledge.object.step', string='Step',
        required=True, ondelete='cascade',
    )
    author_id = fields.Many2one(
        'res.users', string='Author',
        default=lambda self: self.env.uid, readonly=True,
    )
    author_name = fields.Char(related='author_id.name', string='Author Name')
    body = fields.Text(string='Comment', required=True)
    create_date = fields.Datetime(string='Date', readonly=True)
