import re

from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError


class AppfoundryRelease(models.Model):
    _name = 'appfoundry.release'
    _description = 'AppFoundry Release'
    _order = 'date_planned desc, id desc'

    name = fields.Char(required=True)
    project_id = fields.Many2one('appfoundry.project', required=True, ondelete='cascade')
    date_planned = fields.Date(string='Planned Date')
    date_released = fields.Date(string='Released Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('released', 'Released'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True)
    item_ids = fields.One2many('appfoundry.item', 'release_id', string='Items')
    notes = fields.Html(string='Release Notes')
    total_items = fields.Integer(compute='_compute_progress', string='Total Items')
    done_items = fields.Integer(compute='_compute_progress', string='Done Items')
    progress = fields.Float(compute='_compute_progress', string='Progress (%)')

    @api.model
    def _next_version_name(self, project_id):
        """Compute the next version name based on existing releases."""
        latest = self.search(
            [('project_id', '=', project_id)],
            order='id desc', limit=1,
        )
        if not latest:
            return 'v0.1.0'
        match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', latest.name)
        if match:
            major, minor, _patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f'v{major}.{minor + 1}.0'
        return ''

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        project_id = defaults.get('project_id') or self.env.context.get('default_project_id')
        if project_id and 'name' in fields_list:
            defaults['name'] = self._next_version_name(project_id)
        return defaults

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and not self.name:
            self.name = self._next_version_name(self.project_id.id)

    @api.model_create_multi
    def create(self, vals_list):
        releases = super().create(vals_list)
        for release in releases:
            release.project_id.current_release_id = release
        return releases

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
        for release in self:
            if not release.item_ids:
                raise UserError("Cannot mark as ready: no items assigned to this release.")
        self.write({'state': 'ready'})

    def action_release(self):
        for release in self:
            # Check for open bugs
            open_bugs = release.item_ids.filtered(
                lambda i: i.item_type == 'bug'
                and not i.stage_id.is_done
                and not i.stage_id.is_cancelled
            )
            if open_bugs:
                bug_names = ', '.join(open_bugs.mapped('display_name'))
                raise UserError(
                    f"Cannot release: there are open bugs that must be resolved first:\n{bug_names}"
                )
            # Check progress
            incomplete = release.item_ids.filtered(lambda i: not i.stage_id.is_done)
            if incomplete:
                raise UserError(
                    f"Cannot release: {len(incomplete)} item(s) are not yet done."
                )
        self.write({
            'state': 'released',
            'date_released': fields.Date.context_today(self),
        })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_generate_changelog(self):
        type_labels = dict(self.env['appfoundry.item']._fields['item_type'].selection)
        type_order = [key for key, _label in self.env['appfoundry.item']._fields['item_type'].selection]
        for release in self:
            sections = []
            for item_type in type_order:
                items = release.item_ids.filtered(lambda i, t=item_type: i.item_type == t)
                if not items:
                    continue
                label = type_labels[item_type]
                items_sorted = items.sorted(key=lambda i: i.sequence)
                list_items = ''.join(
                    f'<li>{i.display_name}</li>' for i in items_sorted
                )
                sections.append(f'<h3>{label}s</h3><ul>{list_items}</ul>')
            release.notes = Markup(''.join(sections)) if sections else Markup('<p>No items in this release.</p>')

    def action_add_items_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Items to Release',
            'res_model': 'appfoundry.release.add.items',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_release_id': self.id},
        }


class AppfoundryReleaseAddItems(models.TransientModel):
    _name = 'appfoundry.release.add.items'
    _description = 'Add Items to Release'

    release_id = fields.Many2one('appfoundry.release', required=True, readonly=True)
    project_id = fields.Many2one(related='release_id.project_id', string='Project')
    sprint_ids = fields.Many2many(
        'appfoundry.sprint', string='Pull from Sprints',
        domain="[('project_id', '=', project_id), ('state', '=', 'done')]",
    )
    item_ids = fields.Many2many(
        'appfoundry.item', string='Items',
        domain="[('project_id', '=', project_id), ('release_id', '=', False),"
               " ('stage_id.is_done', '=', False), ('stage_id.is_cancelled', '=', False)]",
    )

    @api.onchange('sprint_ids')
    def _onchange_sprint_ids(self):
        if self.sprint_ids:
            sprint_items = self.env['appfoundry.item'].search([
                ('sprint_id', 'in', self.sprint_ids.ids),
                ('release_id', '=', False),
                ('stage_id.is_done', '=', True),
            ])
            self.item_ids = sprint_items

    def action_add(self):
        self.item_ids.write({'release_id': self.release_id.id})
        return {'type': 'ir.actions.act_window_close'}
