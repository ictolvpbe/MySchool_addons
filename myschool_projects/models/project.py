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
    _inherit = ['mail.thread']
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
    parent_path = fields.Char(index=True, unaccent=False)

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

    # --- Milestones ---
    milestone_ids = fields.One2many(
        'myschool.project.milestone', 'project_id', string='Milestones')
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

    @api.depends('child_ids.progress', 'progress_own')
    def _compute_progress(self):
        for project in self:
            children = project.child_ids
            if children:
                # v1: gelijk gewogen gemiddelde van directe sub-projecten.
                # Later eventueel wegen op effort/story_points.
                project.progress = sum(children.mapped('progress')) / len(children)
            else:
                project.progress = project.progress_own

    @api.depends('child_ids')
    def _compute_child_count(self):
        for project in self:
            project.child_count = len(project.child_ids)

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
