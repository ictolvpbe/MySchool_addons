from odoo import models, fields, api


class DevhubItem(models.Model):
    _name = 'devhub.item'
    _description = 'DevHub Item'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id desc'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(string='Number', readonly=True, copy=False)
    project_id = fields.Many2one('devhub.project', required=True, ondelete='cascade', tracking=True)
    item_type = fields.Selection([
        ('story', 'User Story/Requirement'),
        ('bug', 'Bug'),
        ('task', 'Task'),
        ('improvement', 'Improvement'),
    ], required=True, default='story', tracking=True)
    description = fields.Html()
    stage_id = fields.Many2one(
        'devhub.item.stage', string='Stage',
        default=lambda self: self._default_stage(),
        group_expand='_group_expand_stage_ids',
        tracking=True,
    )
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], default='1', tracking=True)
    story_points = fields.Integer(string='Story Points')
    assigned_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    reviewer_id = fields.Many2one('res.users', string='Reviewer')
    sprint_id = fields.Many2one('devhub.sprint', string='Sprint', tracking=True)
    release_id = fields.Many2one('devhub.release', string='Release')
    parent_id = fields.Many2one('devhub.item', string='Parent Item')
    child_ids = fields.One2many('devhub.item', 'parent_id', string='Sub-items')
    tag_ids = fields.Many2many('devhub.tag', string='Tags')
    depends_on_ids = fields.Many2many(
        'devhub.item', 'devhub_item_dependency_rel',
        'item_id', 'depends_on_id', string='Depends On',
    )
    blocked_by_ids = fields.Many2many(
        'devhub.item', 'devhub_item_dependency_rel',
        'depends_on_id', 'item_id', string='Blocked By',
    )
    process_map_ids = fields.Many2many('process.map', string='Process Maps')
    date_deadline = fields.Date(string='Deadline')
    kanban_color = fields.Integer(string='Color')

    def _default_stage(self):
        return self.env['devhub.item.stage'].search([], order='sequence', limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('project_id') and not vals.get('sequence'):
                max_seq = self.search(
                    [('project_id', '=', vals['project_id'])],
                    order='sequence desc', limit=1,
                ).sequence or 0
                vals['sequence'] = max_seq + 1
        return super().create(vals_list)

    @api.depends('project_id.code', 'sequence', 'name')
    def _compute_display_name(self):
        for item in self:
            if item.project_id and item.sequence:
                item.display_name = f"{item.project_id.code}-{item.sequence} {item.name}"
            else:
                item.display_name = item.name or ''

    @api.model
    def _group_expand_stage_ids(self, stages, domain):
        return self.env['devhub.item.stage'].search([], order='sequence')
