from odoo import models, fields


class AssetCategory(models.Model):
    _name = 'asset.category'
    _description = 'Asset Category'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    parent_id = fields.Many2one(
        'asset.category',
        string='Parent Category',
        ondelete='restrict',
        index=True,
    )
    child_ids = fields.One2many(
        'asset.category',
        'parent_id',
        string='Subcategories',
    )
    asset_type = fields.Selection(
        [
            ('hardware', 'Hardware'),
            ('software', 'Software'),
            ('furniture', 'Furniture'),
            ('network', 'Network Equipment'),
            ('av_equipment', 'AV Equipment'),
            ('other', 'Other'),
        ],
        string='Asset Type',
    )
    description = fields.Text(
        string='Description',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'The category name must be unique!'),
    ]
