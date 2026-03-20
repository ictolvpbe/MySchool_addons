from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    school_id = fields.Many2one('myschool.org', string='School')
    short_name = fields.Char(
        string='Korte naam',
        help='Verkorte naam voor de bedrijfskiezer (rechts bovenaan). '
             'Indien leeg wordt de volledige naam gebruikt.',
    )
