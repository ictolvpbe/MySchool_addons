from odoo import models, fields, api


class ActiviteitenConfig(models.Model):
    _name = 'activiteiten.config'
    _description = 'Activiteiten Instellingen'

    name = fields.Char(default='Instellingen', readonly=True)
    verzekering_pct = fields.Float(
        string='Verzekeringspercentage (%)',
        digits=(10, 4),
        default=2.0,
        help='Percentage verzekering dat wordt berekend op de kosten van een activiteit.',
    )

    @api.model
    def _get_defaults(self):
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        param = self.env['ir.config_parameter'].sudo()
        for record in records:
            param.set_param('activiteiten.verzekering_pct', str(record.verzekering_pct))
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'verzekering_pct' in vals:
            self.env['ir.config_parameter'].sudo().set_param(
                'activiteiten.verzekering_pct', str(vals['verzekering_pct']))
        return res
