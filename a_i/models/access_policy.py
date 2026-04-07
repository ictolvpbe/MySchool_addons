from odoo import models, fields, api


class AccessPolicy(models.Model):
    _name = 'a_i.access.policy'
    _description = 'Asset Access Policy'
    _order = 'name'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    group_id = fields.Many2one(
        'res.groups',
        string='Group',
        required=True,
        ondelete='cascade',
    )
    asset_type_category_id = fields.Many2one(
        'a_i.asset.type.category',
        string='Asset Type Category',
        help='Leave empty to apply to all categories.',
    )
    asset_type_id = fields.Many2one(
        'a_i.asset.type',
        string='Asset Type',
        help='Leave empty to apply to all types within the category.',
    )
    org_id = fields.Many2one(
        'myschool.org',
        string='Organization (School)',
        help='Leave empty to apply to all organizations.',
    )
    access_level = fields.Selection(
        [
            ('read', 'Read'),
            ('write', 'Read & Write'),
        ],
        string='Access Level',
        required=True,
        default='read',
    )

    @api.depends('group_id', 'org_id', 'asset_type_category_id', 'asset_type_id', 'access_level')
    def _compute_name(self):
        for policy in self:
            parts = [policy.group_id.name or '']
            if policy.org_id:
                parts.append(policy.org_id.name or '')
            if policy.asset_type_category_id:
                parts.append(policy.asset_type_category_id.complete_name or '')
            if policy.asset_type_id:
                parts.append(policy.asset_type_id.name or '')
            level = dict(self._fields['access_level'].selection).get(policy.access_level, '')
            parts.append(f'[{level}]')
            policy.name = ' - '.join(parts)

    def write(self, vals):
        res = super().write(vals)
        self._recompute_asset_access()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_asset_access()
        return records

    def unlink(self):
        self._recompute_asset_access()
        return super().unlink()

    def _recompute_asset_access(self):
        """Trigger recomputation of allowed groups on all assets."""
        assets = self.env['a_i.asset'].sudo().search([])
        if assets:
            self.env.add_to_compute(
                self.env['a_i.asset']._fields['allowed_group_read_ids'],
                assets,
            )
