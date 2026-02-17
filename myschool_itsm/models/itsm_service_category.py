from odoo import models, fields


class ItsmServiceCategory(models.Model):
    _name = 'itsm.service.category'
    _description = 'ITSM Service Category'
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    description = fields.Text(
        string='Description',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
