from odoo import models, fields, api


class AppfoundryItem(models.Model):
    _name = 'appfoundry.item'
    _description = 'AppFoundry Item'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id desc'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(string='Number', readonly=True, copy=False)
    project_id = fields.Many2one('appfoundry.project', required=True, ondelete='cascade', tracking=True)
    item_type = fields.Selection([
        ('story', 'User Story'),
        ('bug', 'Bug'),
        ('task', 'Task'),
        ('improvement', 'Improvement'),
    ], required=True, default='story', tracking=True)
    description = fields.Html()
    stage_id = fields.Many2one(
        'appfoundry.item.stage', string='Stage',
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
    sprint_id = fields.Many2one('appfoundry.sprint', string='Sprint', tracking=True)
    release_id = fields.Many2one('appfoundry.release', string='Release', required=True)
    parent_id = fields.Many2one('appfoundry.item', string='Parent Item')
    child_ids = fields.One2many('appfoundry.item', 'parent_id', string='Sub-items')
    child_count = fields.Integer(compute='_compute_child_count', string='Sub-items')
    tag_ids = fields.Many2many('appfoundry.tag', string='Tags')
    depends_on_ids = fields.Many2many(
        'appfoundry.item', 'appfoundry_item_dependency_rel',
        'item_id', 'depends_on_id', string='Depends On',
    )
    blocked_by_ids = fields.Many2many(
        'appfoundry.item', 'appfoundry_item_dependency_rel',
        'depends_on_id', 'item_id', string='Blocked By',
    )
    process_map_ids = fields.Many2many('process.map', string='Process Maps')
    test_item_ids = fields.One2many('appfoundry.test.item', 'item_id', string='Test Items')
    test_item_count = fields.Integer(compute='_compute_test_item_count', string='Test Items')
    date_deadline = fields.Date(string='Deadline')
    kanban_color = fields.Integer(string='Color')

    def _default_stage(self):
        return self.env['appfoundry.item.stage'].search([], order='sequence', limit=1)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and not self.release_id:
            self.release_id = self.project_id.current_release_id

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

    @api.depends('child_ids')
    def _compute_child_count(self):
        for item in self:
            item.child_count = len(item.child_ids)

    @api.depends('test_item_ids')
    def _compute_test_item_count(self):
        for item in self:
            item.test_item_count = len(item.test_item_ids)

    def action_open_sub_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.display_name} - Sub-items',
            'res_model': 'appfoundry.item',
            'view_mode': 'kanban,list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {
                'default_parent_id': self.id,
                'default_project_id': self.project_id.id,
                'default_release_id': self.release_id.id,
                'default_item_type': 'task',
            },
        }

    def action_open_test_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.display_name} - Things To Test',
            'res_model': 'appfoundry.test.item',
            'view_mode': 'list,form',
            'domain': [('item_id', '=', self.id)],
            'context': {
                'default_item_id': self.id,
                'default_project_id': self.project_id.id,
                'search_default_group_view': 1,
            },
        }

    @api.model
    def _group_expand_stage_ids(self, stages, domain):
        return self.env['appfoundry.item.stage'].search([], order='sequence')
