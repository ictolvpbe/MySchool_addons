from odoo import models, fields, api


class DevhubProject(models.Model):
    _name = 'devhub.project'
    _description = 'DevHub Project'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Code', required=True, help='Short code used as item prefix, e.g. MSA')
    description = fields.Html()
    responsible_id = fields.Many2one('res.users', string='Project Lead')
    member_ids = fields.Many2many('res.users', string='Team Members')
    item_ids = fields.One2many('devhub.item', 'project_id', string='Items')
    sprint_ids = fields.One2many('devhub.sprint', 'project_id', string='Sprints')
    release_ids = fields.One2many('devhub.release', 'project_id', string='Releases')
    process_map_ids = fields.Many2many('process.map', string='Process Maps')
    is_active = fields.Boolean(default=True)
    item_count = fields.Integer(compute='_compute_item_count', string='Item Count')
    open_bug_count = fields.Integer(compute='_compute_open_bug_count', string='Open Bugs')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Project code must be unique.'),
    ]

    @api.depends('item_ids')
    def _compute_item_count(self):
        for project in self:
            project.item_count = len(project.item_ids)

    @api.depends('item_ids', 'item_ids.item_type', 'item_ids.stage_id',
                 'item_ids.stage_id.is_done', 'item_ids.stage_id.is_cancelled')
    def _compute_open_bug_count(self):
        for project in self:
            project.open_bug_count = len(project.item_ids.filtered(
                lambda i: i.item_type == 'bug'
                and not i.stage_id.is_done
                and not i.stage_id.is_cancelled
            ))
