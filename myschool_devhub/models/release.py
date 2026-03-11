from odoo import models, fields, api


class DevhubRelease(models.Model):
    _name = 'devhub.release'
    _description = 'DevHub Release'
    _order = 'date_planned desc, id desc'

    name = fields.Char(required=True)
    project_id = fields.Many2one('devhub.project', required=True, ondelete='cascade')
    date_planned = fields.Date(string='Planned Date')
    date_released = fields.Date(string='Released Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('released', 'Released'),
    ], default='draft', required=True)
    item_ids = fields.One2many('devhub.item', 'release_id', string='Items')
    notes = fields.Html(string='Release Notes')
    total_items = fields.Integer(compute='_compute_progress', string='Total Items')
    done_items = fields.Integer(compute='_compute_progress', string='Done Items')
    progress = fields.Float(compute='_compute_progress', string='Progress (%)')

    @api.depends('item_ids', 'item_ids.stage_id', 'item_ids.stage_id.is_done')
    def _compute_progress(self):
        for release in self:
            items = release.item_ids
            release.total_items = len(items)
            release.done_items = len(items.filtered(lambda i: i.stage_id.is_done))
            release.progress = (
                (release.done_items / release.total_items * 100)
                if release.total_items else 0.0
            )

    def action_ready(self):
        self.write({'state': 'ready'})

    def action_release(self):
        self.write({
            'state': 'released',
            'date_released': fields.Date.context_today(self),
        })
