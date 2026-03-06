from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    school_ids = fields.Many2many('myschool.org', string='Scholen')
