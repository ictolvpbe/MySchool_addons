from odoo import models, fields


class AppfoundryIconConfig(models.Model):
    _name = 'appfoundry.icon.config'
    _description = 'Icon Generator Standaardkleuren'

    name = fields.Char(default='Standaardkleuren', readonly=True)
    main_color = fields.Char(string='Hoofdkleur', default='#007d8c')
    accent_color = fields.Char(string='Accentkleur', default='#00C4D9')

    def _get_defaults(self):
        """Get the singleton config record, create if needed."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config
