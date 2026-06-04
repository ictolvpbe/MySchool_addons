from odoo import models, fields


class MyschoolProjectTag(models.Model):
    """A simple colored label for work items (filter/group)."""

    _name = 'myschool.project.tag'
    _description = 'Project Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color')

    _name_unique = models.Constraint('UNIQUE(name)', 'Tag name must be unique.')
