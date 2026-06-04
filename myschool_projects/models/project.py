from odoo import models, fields, api
from odoo.exceptions import ValidationError


class MyschoolProject(models.Model):
    """Generic, hierarchical project for mature project management.

    Supports sub-projects (WBS) via ``parent_id``/``child_ids`` with a
    rolled-up progress. A leaf project uses its own ``progress_own``; a
    project with sub-projects shows the average of its direct children.
    """

    _name = 'myschool.project'
    _description = 'MySchool Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        string='Code',
        help='Short unique code, used for display and case-insensitive MCP lookups.',
    )
    description = fields.Html()

    # --- Hierarchy (WBS) ---
    parent_id = fields.Many2one(
        'myschool.project', string='Parent Project',
        ondelete='restrict', index=True, tracking=True,
    )
    child_ids = fields.One2many('myschool.project', 'parent_id', string='Sub-projects')
    parent_path = fields.Char(index=True)

    # --- People & planning ---
    responsible_id = fields.Many2one('res.users', string='Responsible', tracking=True)
    member_ids = fields.Many2many('res.users', string='Team Members')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    state = fields.Selection([
        ('new', 'New'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='new', required=True, tracking=True)

    # --- Progress + rollup ---
    progress_own = fields.Float(
        string='Own Progress (%)', default=0.0,
        help='Manually set progress of this project itself. '
             'Ignored when the project has sub-projects (rollup takes over).',
    )
    progress = fields.Float(
        string='Progress (%)', compute='_compute_progress',
        store=True, recursive=True,
        help='Rollup: average over direct sub-projects, or own progress for a leaf.',
    )

    child_count = fields.Integer(compute='_compute_child_count', string='Sub-project Count')
    descendant_count = fields.Integer(compute='_compute_descendant_count', string='Descendant Count')

    # --- Work items (tasks, milestones, phases, … — one typed model) ---
    task_ids = fields.One2many(
        'myschool.project.task', 'project_id', string='Work Items')
    task_count = fields.Integer(compute='_compute_task_counts', string='Task Count')
    open_task_count = fields.Integer(compute='_compute_task_counts', string='Open Tasks')
    done_task_count = fields.Integer(compute='_compute_task_counts', string='Done Tasks')

    # --- Milestones = work items of type 'milestone' ---
    milestone_ids = fields.One2many(
        'myschool.project.task', 'project_id', string='Milestones',
        domain=[('item_type', '=', 'milestone')])
    milestone_count = fields.Integer(compute='_compute_milestone_count', string='Milestone Count')

    # --- Dependencies (project-level) ---
    depends_on_ids = fields.Many2many(
        'myschool.project', 'myschool_project_dependency_rel',
        'project_id', 'depends_on_id', string='Depends On',
        help='Projects that must progress before this one (predecessors).',
    )
    dependent_ids = fields.Many2many(
        'myschool.project', 'myschool_project_dependency_rel',
        'depends_on_id', 'project_id', string='Blocks',
        help='Projects waiting on this one (successors).',
    )

    _code_unique = models.Constraint('UNIQUE(code)', 'Project code must be unique.')

    @api.depends('child_ids.progress', 'progress_own',
                 'task_ids.state', 'task_ids.item_type', 'task_ids.child_ids')
    def _compute_progress(self):
        """Drie-traps rollup:
        1. heeft sub-projecten → gewogen (gelijk) gemiddelde van hun progress;
        2. anders, heeft leaf-taken → % afgewerkte leaf-taken;
        3. anders → handmatige ``progress_own``.
        Containers (phase/epic met kinderen) en milestones tellen niet mee
        als telbaar 'werk'.
        """
        for project in self:
            children = project.child_ids
            if children:
                project.progress = sum(children.mapped('progress')) / len(children)
            else:
                tasks = project.task_ids.filtered(self._is_countable_task)
                if tasks:
                    done = len(tasks.filtered(lambda t: t.state == 'done'))
                    project.progress = done / len(tasks) * 100
                else:
                    project.progress = project.progress_own

    @staticmethod
    def _is_countable_task(t):
        """Leaf werk-item dat meetelt voor voortgang/tellers."""
        return (t.item_type != 'milestone'
                and t.state != 'cancelled'
                and not t.child_ids)

    @api.depends('child_ids')
    def _compute_child_count(self):
        for project in self:
            project.child_count = len(project.child_ids)

    @api.depends('task_ids', 'task_ids.state', 'task_ids.item_type', 'task_ids.child_ids')
    def _compute_task_counts(self):
        for project in self:
            # Telbare leaf-werkitems (milestones + containers uitgezonderd),
            # consistent met de voortgangsberekening.
            tasks = project.task_ids.filtered(self._is_countable_task)
            project.task_count = len(tasks)
            project.done_task_count = len(tasks.filtered(lambda t: t.state == 'done'))
            project.open_task_count = len(
                tasks.filtered(lambda t: t.state != 'done'))

    @api.depends('milestone_ids')
    def _compute_milestone_count(self):
        for project in self:
            project.milestone_count = len(project.milestone_ids)

    def _compute_descendant_count(self):
        for project in self:
            if project.parent_path:
                project.descendant_count = self.search_count([
                    ('parent_path', '=like', project.parent_path + '%'),
                    ('id', '!=', project.id),
                ])
            else:
                project.descendant_count = 0

    # ------------------------------------------------------------------
    # Smart-button actions — open scoped views (project as a hub)
    # ------------------------------------------------------------------

    def action_open_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Tasks',
            'res_model': 'myschool.project.task',
            'view_mode': 'kanban,list,calendar,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_open_subprojects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Sub-projects',
            'res_model': 'myschool.project',
            'view_mode': 'kanban,list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id},
        }

    def action_open_milestones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Milestones',
            'res_model': 'myschool.project.task',
            'view_mode': 'calendar,list,form',
            'domain': [('project_id', '=', self.id), ('item_type', '=', 'milestone')],
            'context': {'default_project_id': self.id, 'default_item_type': 'milestone'},
        }

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(
                "Een project kan niet zijn eigen voorouder zijn "
                "(geen recursieve sub-projecten)."
            )

    @api.constrains('depends_on_ids')
    def _check_no_self_dependency(self):
        for project in self:
            if project in project.depends_on_ids:
                raise ValidationError(
                    "Een project kan niet van zichzelf afhangen."
                )
