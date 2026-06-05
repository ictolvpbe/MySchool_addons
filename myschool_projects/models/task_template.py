from odoo import models, fields, api
from odoo.exceptions import ValidationError


class MyschoolProjectTaskTemplate(models.Model):
    """Herbruikbaar taak-blok, losgekoppeld van een project.

    Een template is een root-node (``parent_id`` leeg) met optioneel een
    subtree van sub-items. Toepassen op een project maakt er echte work
    items van (project-agnostisch: geen datums/assignee/dependencies).
    """

    _name = 'myschool.project.task.template'
    _description = 'Project Task Template'
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    item_type = fields.Selection([
        ('task', 'Task'),
        ('milestone', 'Milestone'),
        ('phase', 'Phase'),
        ('epic', 'Epic'),
        ('bug', 'Bug'),
    ], string='Type', default='task', required=True)
    description = fields.Html()
    priority = fields.Selection([
        ('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Critical'),
    ], default='1', string='Priority')
    planned_hours = fields.Float(string='Planned Hours')
    tag_ids = fields.Many2many('myschool.project.tag', string='Tags')

    parent_id = fields.Many2one(
        'myschool.project.task.template', string='Parent',
        ondelete='cascade', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'myschool.project.task.template', 'parent_id', string='Sub-items')
    child_count = fields.Integer(compute='_compute_child_count')

    @api.depends('child_ids')
    def _compute_child_count(self):
        for tmpl in self:
            tmpl.child_count = len(tmpl.child_ids)

    @api.constrains('parent_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError(
                "Een template-item kan niet zijn eigen voorouder zijn.")

    def instantiate(self, project, parent_task=False):
        """Maak echte work items van deze template-subtree onder ``project``.
        Geeft de aangemaakte root-taak terug."""
        self.ensure_one()
        Task = self.env['myschool.project.task']

        def create_node(tmpl, pid):
            task = Task.create({
                'name': tmpl.name,
                'project_id': project.id,
                'parent_id': pid,
                'item_type': tmpl.item_type,
                'sequence': tmpl.sequence,
                'priority': tmpl.priority,
                'planned_hours': tmpl.planned_hours,
                'description': tmpl.description,
                'tag_ids': [(6, 0, tmpl.tag_ids.ids)],
                'state': 'todo',
            })
            for child in tmpl.child_ids:
                create_node(child, task.id)
            return task

        return create_node(self, parent_task.id if parent_task else False)

    def action_open_apply_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Apply task template',
            'res_model': 'myschool.project.task.template.apply',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_id': self.id},
        }


class MyschoolProjectTaskTemplateApply(models.TransientModel):
    """Wizard: instantieer een taaktemplate in een project."""

    _name = 'myschool.project.task.template.apply'
    _description = 'Apply Task Template to Project'

    template_id = fields.Many2one(
        'myschool.project.task.template', string='Task Template', required=True,
        domain=[('parent_id', '=', False)])
    project_id = fields.Many2one(
        'myschool.project', string='Project', required=True)
    parent_id = fields.Many2one(
        'myschool.project.task', string='Under parent item',
        domain="[('project_id', '=', project_id)]",
        help='Optioneel: hang de template onder een bestaand work item.')

    def action_apply(self):
        self.ensure_one()
        root = self.template_id.instantiate(self.project_id, self.parent_id or False)
        return {
            'type': 'ir.actions.act_window',
            'name': self.project_id.name,
            'res_model': 'myschool.project.task',
            'res_id': root.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
        }
