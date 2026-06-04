from odoo import models, fields, api
from odoo.exceptions import ValidationError


class MyschoolProjectTask(models.Model):
    """A unit of work within a project (the WBS leaf level)."""

    _name = 'myschool.project.task'
    _description = 'Project Task'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(
        'myschool.project', string='Project',
        required=True, ondelete='cascade', index=True, tracking=True,
    )
    description = fields.Html()
    assigned_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    state = fields.Selection([
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='todo', required=True, tracking=True, index=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], default='1', string='Priority')
    date_start = fields.Date(string='Start Date')
    date_deadline = fields.Date(string='Deadline')
    planned_hours = fields.Float(string='Planned Hours')

    # Task-level dependencies (predecessors).
    depends_on_ids = fields.Many2many(
        'myschool.project.task', 'myschool_project_task_dep_rel',
        'task_id', 'depends_on_id', string='Depends On',
        help='Tasks that must be done before this one.',
    )
    dependent_ids = fields.Many2many(
        'myschool.project.task', 'myschool_project_task_dep_rel',
        'depends_on_id', 'task_id', string='Blocks',
    )

    @api.constrains('depends_on_ids')
    def _check_no_self_dependency(self):
        for task in self:
            if task in task.depends_on_ids:
                raise ValidationError("Een taak kan niet van zichzelf afhangen.")
