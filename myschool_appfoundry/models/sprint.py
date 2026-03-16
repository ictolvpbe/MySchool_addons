from odoo import models, fields, api


class AppfoundrySprint(models.Model):
    _name = 'appfoundry.sprint'
    _description = 'AppFoundry Sprint'
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True)
    project_id = fields.Many2one('appfoundry.project', required=True, ondelete='cascade')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    goal = fields.Text(string='Sprint Goal')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('done', 'Done'),
    ], default='draft', required=True)
    item_ids = fields.One2many('appfoundry.item', 'sprint_id', string='Items')
    total_points = fields.Integer(compute='_compute_points', string='Total Points')
    completed_points = fields.Integer(compute='_compute_points', string='Completed Points')
    velocity = fields.Float(compute='_compute_points', string='Velocity (%)')
    item_count = fields.Integer(compute='_compute_points', string='Item Count')

    @api.depends('item_ids', 'item_ids.story_points', 'item_ids.stage_id',
                 'item_ids.stage_id.is_done')
    def _compute_points(self):
        for sprint in self:
            items = sprint.item_ids
            sprint.item_count = len(items)
            sprint.total_points = sum(items.mapped('story_points'))
            sprint.completed_points = sum(
                items.filtered(lambda i: i.stage_id.is_done).mapped('story_points')
            )
            sprint.velocity = (
                (sprint.completed_points / sprint.total_points * 100)
                if sprint.total_points else 0.0
            )

    def action_start(self):
        for sprint in self:
            vals = {'state': 'active'}
            if not sprint.date_start:
                vals['date_start'] = fields.Date.context_today(self)
            sprint.write(vals)

    def action_complete(self):
        for sprint in self:
            sprint.write({'state': 'done'})
