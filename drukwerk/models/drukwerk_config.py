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

    # --- Count-e export ---
    count_e_artikel = fields.Char(
        string='Count-e artikel (zwart-wit)',
        default='KOPIES',
        help='Artikelcode in Count-e voor zwart-wit kopies',
    )
    count_e_artikel_kleur = fields.Char(
        string='Count-e artikel (kleur)',
        default='KOPIES',
        help='Artikelcode in Count-e voor kleur kopies (mag dezelfde zijn als zwart-wit)',
    )
    count_e_analytisch = fields.Char(
        string='Count-e analytische code',
        help='Optionele analytische code (kolom Analytisch1 in de export)',
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
        if 'count_e_artikel' in vals:
            param.set_param('drukwerk.count_e_artikel', vals['count_e_artikel'] or '')
        if 'count_e_artikel_kleur' in vals:
            param.set_param('drukwerk.count_e_artikel_kleur', vals['count_e_artikel_kleur'] or '')
        if 'count_e_analytisch' in vals:
            param.set_param('drukwerk.count_e_analytisch', vals['count_e_analytisch'] or '')
        return res
