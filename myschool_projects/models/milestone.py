from odoo import models, fields


class MyschoolProjectMilestone(models.Model):
    """A dated checkpoint within a project (e.g. 'Netwerk opgeleverd')."""

    _name = 'myschool.project.milestone'
    _description = 'Project Milestone'
    _order = 'date, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(
        'myschool.project', string='Project',
        required=True, ondelete='cascade', index=True,
    )
    date = fields.Date(string='Target Date')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('reached', 'Reached'),
        ('missed', 'Missed'),
    ], default='pending', required=True)
    description = fields.Text()
