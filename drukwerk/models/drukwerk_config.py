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
    prijs_kleur = fields.Float(
        string='Toeslag kleur (per pagina)',
        digits=(10, 4),
        default=0.05,
    )
    prijs_a3 = fields.Float(
        string='Toeslag A3 (per pagina)',
        digits=(10, 4),
        default=0.02,
    )
    prijs_dik_papier = fields.Float(
        string='Toeslag dik papier (per pagina)',
        digits=(10, 4),
        default=0.04,
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
        param = self.env['ir.config_parameter'].sudo()
        if 'prijs_per_pagina' in vals:
            param.set_param('drukwerk.prijs_per_pagina', str(vals['prijs_per_pagina']))
        if 'prijs_kleur' in vals:
            param.set_param('drukwerk.prijs_kleur', str(vals['prijs_kleur']))
        if 'prijs_a3' in vals:
            param.set_param('drukwerk.prijs_a3', str(vals['prijs_a3']))
        if 'prijs_dik_papier' in vals:
            param.set_param('drukwerk.prijs_dik_papier', str(vals['prijs_dik_papier']))
        return res
