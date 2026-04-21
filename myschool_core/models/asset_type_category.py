from odoo import models, fields, api


class MyschoolAssetTypeCategory(models.Model):
    _name = 'myschool.asset.type.category'
    _description = 'Asset Type Category'
    _parent_name = 'parent_id'
    _parent_store = True
    _order = 'complete_name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    complete_name = fields.Char(
        string='Complete Name',
        compute='_compute_complete_name',
        recursive=True,
        store=True,
    )
    parent_id = fields.Many2one(
        'myschool.asset.type.category',
        string='Parent Category',
        ondelete='restrict',
        index=True,
    )
    parent_path = fields.Char(
        index=True,
    )
    child_ids = fields.One2many(
        'myschool.asset.type.category',
        'parent_id',
        string='Subcategories',
    )
    asset_type_ids = fields.One2many(
        'myschool.asset.type',
        'category_id',
        string='Asset Types',
    )
    description = fields.Text(
        string='Description',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = f'{category.parent_id.complete_name} / {category.name}'
            else:
                category.complete_name = category.name
