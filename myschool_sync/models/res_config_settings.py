# -*- coding: utf-8 -*-
"""
MySchool Sync — Settings
========================
Contributes the **MySchool Sync** tab to the unified Settings page.

Two ir.config_parameter values drive the sync subsystem:

* ``myschool.sync_role``     — ``disabled`` / ``master`` / ``slave`` / ``both``
* ``myschool.sync_api_key``  — pre-shared key for the inbound HTTP endpoint
                                (slave-side authentication)

We expose them as ``res.config.settings`` fields with explicit
``get_values`` / ``set_values`` overrides — the standard pattern for
ir.config_parameter-backed settings.
"""

from odoo import models, fields, api


SYNC_ROLE_SELECTION = [
    ('disabled', 'Uitgeschakeld'),
    ('master', 'Master (zendt data uit)'),
    ('slave', 'Slave (ontvangt data)'),
    ('both', 'Beide (master + slave)'),
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    myschool_sync_role = fields.Selection(
        SYNC_ROLE_SELECTION,
        string='Sync-rol',
        default='disabled',
        help='Bepaalt of deze Odoo-instantie data uitstuurt (master), '
             'data ontvangt (slave), beide of geen van beide.',
    )
    myschool_sync_api_key = fields.Char(
        string='Sync API-sleutel',
        help='Pre-shared key die slave-instanties van inkomende sync-aanroepen '
             'eisen. Op een master-instantie moet dezelfde waarde via de '
             'sync.target-records geconfigureerd worden.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(
            myschool_sync_role=ICP.get_param('myschool.sync_role', 'disabled'),
            myschool_sync_api_key=ICP.get_param('myschool.sync_api_key', ''),
        )
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(
            'myschool.sync_role', self.myschool_sync_role or 'disabled')
        ICP.set_param(
            'myschool.sync_api_key', self.myschool_sync_api_key or '')

    # ------------------------------------------------------------------
    # Shortcut actions
    # ------------------------------------------------------------------

    def action_open_sync_targets(self):
        return self.env.ref('myschool_sync.action_sync_target').read()[0]

    def action_open_sync_log(self):
        return self.env.ref('myschool_sync.action_sync_log').read()[0]
