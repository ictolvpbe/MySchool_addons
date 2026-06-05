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
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
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
    tag_ids = fields.Many2many('myschool.project.tag', string='Tags')

    # --- Hierarchy (WBS among work items) ---
    parent_id = fields.Many2one(
        'myschool.project.task', string='Parent',
        ondelete='cascade', index=True,
        domain="[('project_id', '=', project_id), ('id', '!=', id)]",
    )
    child_ids = fields.One2many('myschool.project.task', 'parent_id', string='Sub-items')
    parent_path = fields.Char(index=True)
    child_count = fields.Integer(compute='_compute_child_count', string='Sub-item Count')

    # --- Milestone anchor (organize work toward a milestone) ---
    milestone_id = fields.Many2one(
        'myschool.project.task', string='Milestone',
        domain="[('item_type', '=', 'milestone'), ('project_id', '=', project_id)]",
        index=True,
        help='Target milestone this item works toward (same project).',
    )
    milestone_item_ids = fields.One2many(
        'myschool.project.task', 'milestone_id', string='Items for this milestone')
    milestone_progress = fields.Float(
        compute='_compute_milestone_progress', string='Milestone Progress',
        help='For a milestone: % of its linked leaf items that are done.')

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

    def action_save_as_task_template(self):
        """Bewaar deze taak (+ subtree) als herbruikbare taaktemplate."""
        self.ensure_one()
        Template = self.env['myschool.project.task.template']

        def copy_node(task, pid):
            tmpl = Template.create({
                'name': task.name,
                'parent_id': pid,
                'item_type': task.item_type,
                'sequence': task.sequence,
                'priority': task.priority,
                'planned_hours': task.planned_hours,
                'description': task.description,
                'tag_ids': [(6, 0, task.tag_ids.ids)],
            })
            for child in task.child_ids:
                copy_node(child, tmpl.id)
            return tmpl

        root = copy_node(self, False)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Task Template',
            'res_model': 'myschool.project.task.template',
            'res_id': root.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
        }

    def write(self, vals):
        res = super().write(vals)
        # Archiveren/de-archiveren cascadeert naar de sub-items.
        if 'active' in vals:
            active = vals['active']
            Task = self.env['myschool.project.task'].with_context(active_test=False)
            for item in self:
                kids = Task.search([('parent_id', '=', item.id), ('active', '!=', active)])
                if kids:
                    kids.write({'active': active})
        return res

    @api.depends('child_ids')
    def _compute_child_count(self):
        for item in self:
            item.child_count = len(item.child_ids)

    @api.depends('item_type', 'milestone_item_ids.state',
                 'milestone_item_ids.item_type', 'milestone_item_ids.child_ids')
    def _compute_milestone_progress(self):
        for item in self:
            if item.item_type != 'milestone':
                item.milestone_progress = 0.0
                continue
            leaves = item.milestone_item_ids.filtered(
                lambda t: t.item_type != 'milestone'
                and t.state != 'cancelled' and not t.child_ids)
            if leaves:
                done = len(leaves.filtered(lambda t: t.state == 'done'))
                item.milestone_progress = done / len(leaves) * 100
            else:
                item.milestone_progress = 0.0

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

    @api.constrains('milestone_id')
    def _check_milestone(self):
        for item in self:
            m = item.milestone_id
            if not m:
                continue
            if m.id == item.id:
                raise ValidationError("Een item kan niet zijn eigen milestone zijn.")
            if m.item_type != 'milestone':
                raise ValidationError("Het doel moet van type 'milestone' zijn.")
            if m.project_id != item.project_id:
                raise ValidationError("Doel-milestone moet in hetzelfde project zitten.")
