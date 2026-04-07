from odoo import models, fields, api
from odoo.exceptions import UserError


class AssetType(models.Model):
    _name = 'a_i.asset.type'
    _description = 'Asset Type'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    category_id = fields.Many2one(
        'a_i.asset.type.category',
        string='Category',
        required=True,
        ondelete='restrict',
    )
    description = fields.Text(
        string='Description',
    )
    is_room = fields.Boolean(
        string='Is Room',
        help='Mark this type as a room/location type. '
             'Assets of this type can be used as location for other assets.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    asset_ids = fields.One2many(
        'a_i.asset',
        'asset_type_id',
        string='Assets',
    )
    asset_count = fields.Integer(
        string='Asset Count',
        compute='_compute_asset_count',
    )
    access_policy_ids = fields.One2many(
        'a_i.access.policy',
        'asset_type_id',
        string='Access Policies',
    )

    @api.depends('asset_ids')
    def _compute_asset_count(self):
        for record in self:
            record.asset_count = len(record.asset_ids)

    def action_safe_delete(self):
        """Archive instead of delete. Refuse if active assets still use this type."""
        for record in self:
            active_assets = record.asset_ids.filtered(lambda a: a.active)
            if active_assets:
                raise UserError(
                    f'Cannot archive asset type "{record.name}": '
                    f'{len(active_assets)} active asset(s) still use this type. '
                    f'Reassign or archive those assets first.'
                )
            record.active = False

    def action_view_assets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Assets - {self.name}',
            'res_model': 'a_i.asset',
            'view_mode': 'list,form',
            'domain': [('asset_type_id', '=', self.id)],
            'context': {'default_asset_type_id': self.id},
        }
