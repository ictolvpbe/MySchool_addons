from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # UI preference for the MySchool Admin OWL widgets (Organisation
    # Manager etc.). Applied as data-theme="dark" on <body> by the
    # myschool_theme JS service at webclient startup.
    myschool_theme_mode = fields.Selection(
        selection=[
            ('auto', 'Volg systeem'),
            ('light', 'Licht'),
            ('dark', 'Donker'),
        ],
        string='MySchool thema',
        default='auto',
        help='Bepaalt de visuele modus van MySchool-widgets (Organisation '
             'Manager, dashboard, …). "Volg systeem" gebruikt de '
             'voorkeur van het besturingssysteem.',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        # Users should be able to read their own theme preference so the
        # frontend can apply it at startup without admin RPC calls.
        return super().SELF_READABLE_FIELDS + ['myschool_theme_mode']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        # The toolbar toggle (Organisation Manager) writes here, so the
        # active user must be able to update their own preference.
        return super().SELF_WRITEABLE_FIELDS + ['myschool_theme_mode']
