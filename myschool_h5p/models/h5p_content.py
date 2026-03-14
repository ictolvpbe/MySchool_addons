from odoo import models, fields, api


class H5PContent(models.Model):
    _name = 'h5p.content'
    _description = 'H5P Content'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)

    h5p_file = fields.Binary(string='H5P File (.h5p)', attachment=True)
    h5p_filename = fields.Char(string='Filename')

    learning_path_id = fields.Many2one('h5p.learning.path', string='Learning Path',
                                        ondelete='cascade')
    content_type = fields.Selection([
        ('presentation', 'Presentation'),
        ('quiz', 'Quiz / Assessment'),
        ('interactive_video', 'Interactive Video'),
        ('drag_drop', 'Drag & Drop'),
        ('fill_blanks', 'Fill in the Blanks'),
        ('other', 'Other'),
    ], default='other', string='Content Type')

    result_ids = fields.One2many('h5p.result', 'content_id', string='Results')
    result_count = fields.Integer(compute='_compute_result_count')
    avg_score = fields.Float(compute='_compute_avg_score', string='Avg Score %')

    @api.depends('result_ids')
    def _compute_result_count(self):
        for rec in self:
            rec.result_count = len(rec.result_ids)

    @api.depends('result_ids', 'result_ids.score_percent')
    def _compute_avg_score(self):
        for rec in self:
            results = rec.result_ids.filtered(lambda r: r.max_score > 0)
            if results:
                rec.avg_score = sum(r.score_percent for r in results) / len(results)
            else:
                rec.avg_score = 0.0

    def action_preview(self):
        """Open the H5P player in a new browser tab."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/h5p/play/{self.id}',
            'target': 'new',
        }

    def action_open_results(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Results',
            'res_model': 'h5p.result',
            'view_mode': 'list,form',
            'domain': [('content_id', '=', self.id)],
        }
