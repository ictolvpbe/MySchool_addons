# -*- coding: utf-8 -*-
"""res.config.settings-extensie voor de Informat-plugin.

Levert de knop "Beheer Informat-configuratie" op de MySchool-Core
settings-tab (verhuisd uit myschool_admin).
"""

from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def action_open_informat_config(self):
        return self.env.ref(
            'myschool_edu_informat.action_informat_service_config').read()[0]
