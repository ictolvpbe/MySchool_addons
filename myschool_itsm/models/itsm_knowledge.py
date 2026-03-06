from odoo import models, fields


class ItsmKnowledgeTag(models.Model):
    _name = 'itsm.knowledge.tag'
    _description = 'ITSM Knowledge Tag'
    _order = 'name'

    name = fields.Char(string='Name', required=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Tag name must be unique.')


class ItsmKnowledgeArticle(models.Model):
    _name = 'itsm.knowledge.article'
    _description = 'ITSM Knowledge Article'
    _inherit = ['mail.thread']
    _order = 'write_date desc'

    name = fields.Char(string='Title', required=True, tracking=True)
    content = fields.Html(string='Content', required=True)
    service_id = fields.Many2one('itsm.service', string='Service')
    article_type = fields.Selection(
        [
            ('faq', 'FAQ'),
            ('howto', 'How-To'),
            ('troubleshooting', 'Troubleshooting'),
            ('policy', 'Policy'),
        ],
        string='Type',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    author_id = fields.Many2one(
        'res.users', string='Author', default=lambda self: self.env.user,
    )
    tag_ids = fields.Many2many('itsm.knowledge.tag', string='Tags')
    views_count = fields.Integer(string='Views', default=0)
    helpful_count = fields.Integer(string='Helpful', default=0)
    related_problem_ids = fields.Many2many('itsm.problem', string='Related Problems')

    def action_publish(self):
        for article in self:
            article.state = 'published'

    def action_archive(self):
        for article in self:
            article.state = 'archived'

    def action_draft(self):
        for article in self:
            article.state = 'draft'

    def action_increment_views(self):
        for article in self:
            article.views_count += 1

    def action_mark_helpful(self):
        for article in self:
            article.helpful_count += 1
