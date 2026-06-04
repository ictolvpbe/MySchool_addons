from odoo import models, fields, api
from odoo.exceptions import ValidationError


class MyschoolProjectTask(models.Model):
    """A work item within a project (OpenProject-style 'work package').

    A single typed model covers tasks, milestones, phases, epics and bugs
    via ``item_type``, with a self-hierarchy (``parent_id``/``child_ids``)
    so items can be nested into a WBS table.
    """

    _name = 'myschool.project.task'
    _description = 'Project Work Item'
    _inherit = ['mail.thread']
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    item_type = fields.Selection([
        ('task', 'Task'),
        ('milestone', 'Milestone'),
        ('phase', 'Phase'),
        ('epic', 'Epic'),
        ('bug', 'Bug'),
    ], string='Type', default='task', required=True, tracking=True, index=True)
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

    # --- Hierarchy (WBS among work items) ---
    parent_id = fields.Many2one(
        'myschool.project.task', string='Parent',
        ondelete='set null', index=True,
        domain="[('project_id', '=', project_id), ('id', '!=', id)]",
    )
    child_ids = fields.One2many('myschool.project.task', 'parent_id', string='Sub-items')
    parent_path = fields.Char(index=True)
    child_count = fields.Integer(compute='_compute_child_count', string='Sub-item Count')

    # --- Dependencies (predecessors) ---
    depends_on_ids = fields.Many2many(
        'myschool.project.task', 'myschool_project_task_dep_rel',
        'task_id', 'depends_on_id', string='Depends On',
        help='Items that must be done before this one.',
    )
    dependent_ids = fields.Many2many(
        'myschool.project.task', 'myschool_project_task_dep_rel',
        'depends_on_id', 'task_id', string='Blocks',
    )

    @api.depends('child_ids')
    def _compute_child_count(self):
        for item in self:
            item.child_count = len(item.child_ids)

    @api.constrains('depends_on_ids')
    def _check_no_self_dependency(self):
        for item in self:
            if item in item.depends_on_ids:
                raise ValidationError("Een item kan niet van zichzelf afhangen.")

    @api.constrains('parent_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError("Een item kan niet zijn eigen voorouder zijn.")
        for item in self:
            if item.parent_id and item.parent_id.project_id != item.project_id:
                raise ValidationError(
                    "Parent en item moeten in hetzelfde project zitten."
                )
