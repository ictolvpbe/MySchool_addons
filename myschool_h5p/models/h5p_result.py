from odoo import models, fields, api


class H5PResult(models.Model):
    _name = 'h5p.result'
    _description = 'H5P Result'
    _order = 'attempt_date desc'

    content_id = fields.Many2one('h5p.content', string='Content', required=True,
                                  ondelete='cascade')
    user_id = fields.Many2one('res.users', string='Learner', required=True,
                               default=lambda self: self.env.uid)
    score = fields.Float(string='Score')
    max_score = fields.Float(string='Max Score')
    score_percent = fields.Float(compute='_compute_score_percent', store=True,
                                  string='Score %')
    completion = fields.Boolean(string='Completed')
    duration = fields.Integer(string='Duration (s)', help='Time spent in seconds')
    attempt_date = fields.Datetime(string='Attempt Date', default=fields.Datetime.now)
    xapi_verb = fields.Char(string='xAPI Verb')
    xapi_data = fields.Text(string='Raw xAPI Statement')

    @api.depends('score', 'max_score')
    def _compute_score_percent(self):
        for rec in self:
            if rec.max_score > 0:
                rec.score_percent = (rec.score / rec.max_score) * 100
            else:
                rec.score_percent = 0.0
