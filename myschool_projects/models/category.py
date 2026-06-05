from odoo import models, fields


class MyschoolProjectCategory(models.Model):
    """A category to classify projects (e.g. ICT, Infra, Onderwijs)."""

    _name = 'myschool.project.category'
    _description = 'Project Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color')
    description = fields.Text()
    project_count = fields.Integer(compute='_compute_project_count', string='Projects')

    _name_unique = models.Constraint('UNIQUE(name)', 'Category name must be unique.')

    def _compute_project_count(self):
        groups = self.env['myschool.project']._read_group(
            [('category_id', 'in', self.ids)], ['category_id'], ['__count'])
        counts = {cat.id: cnt for cat, cnt in groups}
        for category in self:
            category.project_count = counts.get(category.id, 0)
