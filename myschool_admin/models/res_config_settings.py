# -*- coding: utf-8 -*-
"""
MySchool Admin — Settings
=========================
Contributes the **MySchool Admin** tab to the unified Settings page.

The tab is intentionally light on stored fields: most of what lives in
``myschool_admin`` is operational tooling (Health Check, AD-Takeover,
benchmarks, log viewer). The Settings page surfaces those as shortcut
buttons so an administrator finds *everything* about a sub-system in one
place, even when the actual tool is a wizard living elsewhere in the
menu tree.

Per-module Settings sidebar ordering is controlled by the ``priority``
attribute on each contributing ir.ui.view record (lower = earlier in the
sidebar). See ``views/res_config_settings_views.xml`` — admin uses 20,
which sits right after myschool_core (10) and before any alphabetical
module-blocks.
"""

from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ------------------------------------------------------------------
    # Shortcut actions — open existing tools without leaving the
    # Settings page. Each method returns an ir.actions.act_window dict;
    # no state is touched, so set_values()/get_values() do not need to
    # be overridden for the admin block.
    # ------------------------------------------------------------------

    def action_open_health_check(self):
        return self.env.ref('myschool_admin.action_health_check').read()[0]

    def action_open_ad_takeover(self):
        return self.env.ref('myschool_admin.action_ad_takeover_session').read()[0]

    def action_open_server_benchmark(self):
        return self.env.ref('myschool_admin.action_server_benchmark').read()[0]

    def action_open_log_viewer(self):
        return self.env.ref('myschool_admin.action_log_viewer').read()[0]

    def action_open_cron_tasks(self):
        return self.env.ref('myschool_admin.action_myschool_ir_cron').read()[0]

    def action_open_domain_rename(self):
        return self.env.ref('myschool_admin.action_domain_rename_wizard').read()[0]

    # ------------------------------------------------------------------
    # Shortcuts contributed to the MySchool Core tab — these actions
    # historically live in myschool_admin (LDAP/Informat/ConfigItem
    # views) even though the underlying models are in myschool_core,
    # so the button methods belong here.
    # ------------------------------------------------------------------

    def action_open_ldap_servers(self):
        return self.env.ref('myschool_admin.action_ldap_server_config').read()[0]

    def action_open_informat_config(self):
        return self.env.ref('myschool_admin.action_informat_service_config').read()[0]

    def action_open_config_items(self):
        return self.env.ref('myschool_admin.action_config_item').read()[0]

    def action_open_ci_relations(self):
        return self.env.ref('myschool_admin.action_ci_relation').read()[0]

    def action_open_settings_global(self):
        """Open het beheer van Globale Settings Values.

        Opent de list-action ``action_settings_value_global`` met
        domain ``org_id=False, person_id=False`` zodat enkel echte
        globale waarden getoond worden.
        """
        return self.env.ref(
            'myschool_admin.action_settings_value_global').read()[0]

    def action_open_settings_catalog(self):
        """Open de Settings Items catalogus (definities)."""
        return self.env.ref(
            'myschool_admin.action_settings_item').read()[0]

    def action_open_settings_values_all(self):
        """Open de platte lijst van ALLE Settings Values (admin-tool)."""
        return self.env.ref(
            'myschool_admin.action_settings_value').read()[0]
