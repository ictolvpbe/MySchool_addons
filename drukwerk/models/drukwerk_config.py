from odoo import models, fields, api


class DrukwerkConfig(models.Model):
    _name = 'drukwerk.config'
    _description = 'Drukwerk Instellingen'

    name = fields.Char(default='Instellingen', readonly=True)
    prijs_per_pagina = fields.Float(
        string='Standaard prijs per pagina',
        digits=(10, 4),
        default=0.03,
    )

    @api.model
    def _get_defaults(self):
        """Get the singleton config record, create if needed."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config

    def write(self, vals):
        """Also update the ir.config_parameter when saving."""
        res = super().write(vals)
        if 'prijs_per_pagina' in vals:
            self.env['ir.config_parameter'].sudo().set_param(
                'drukwerk.prijs_per_pagina', str(vals['prijs_per_pagina']))
        return res
