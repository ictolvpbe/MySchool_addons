from odoo import models, fields, api


class H5PLearningPath(models.Model):
    _name = 'h5p.learning.path'
    _description = 'Learning Path'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    sequence = fields.Integer(default=10)
    is_published = fields.Boolean(default=False, tracking=True)
    responsible_id = fields.Many2one('res.users', string='Responsible',
                                     default=lambda self: self.env.uid)

    content_ids = fields.One2many('h5p.content', 'learning_path_id', string='Content Items')
    content_count = fields.Integer(compute='_compute_content_count')

    @api.depends('content_ids')
    def _compute_content_count(self):
        for rec in self:
            rec.content_count = len(rec.content_ids)
