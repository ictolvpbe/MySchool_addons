# -*- coding: utf-8 -*-
"""
MySchool Core — Settings
========================
Contributes the **MySchool Core** tab to the unified Settings page.

The tab is the natural home for *integration* configuration — Google
Workspace, LDAP, Informat — because the underlying models live in
``myschool_core``. Action records for some of those views live in
``myschool_admin`` (historical accident); admin extends this tab from
its own res.config.settings view, so a freshly installed core stays
self-contained while the full admin install enriches the same tab.

A separate ``InformatServiceConfigSettings`` class exists in
``informat_service_config.py`` for legacy reasons. We reuse those
fields here through a shared ``related`` pattern so a single save on
the unified form persists both legacy and new settings.

Per-module sidebar ordering uses the ``priority`` attribute on each
ir.ui.view (lower = earlier). Core uses 10 — first in the sidebar.
"""

from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ------------------------------------------------------------------
    # Shortcut actions — open existing tools without leaving the
    # Settings page.
    # ------------------------------------------------------------------

    def action_open_google_workspace(self):
        return self.env.ref(
            'myschool_core.action_google_workspace_config').read()[0]
