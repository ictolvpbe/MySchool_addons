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

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ------------------------------------------------------------------
    # Global safeguard mode — applies to every external integration
    # (Smartschool today; LDAP / Google Workspace can opt into the same
    # parameter later by reading ``ir.config_parameter myschool.safeguard_mode``).
    # ``live``        — per-config dry_run decides (default, backwards-compat)
    # ``dry_run_all`` — force all platforms into dry-run regardless of config
    # ``read_only``   — reject every mutating call hard
    # ------------------------------------------------------------------

    myschool_safeguard_mode = fields.Selection(
        selection=[
            ('live', 'Live — per-config dry_run decides'),
            ('dry_run_all', 'Dry run (all platforms) — simulate every mutating call'),
            ('read_only', 'Read-only — reject every mutating call'),
        ],
        string='Safeguard Mode',
        config_parameter='myschool.safeguard_mode',
        default='live',
        help='Global override that protects all external integrations '
             '(Smartschool, LDAP, Google Workspace) against unintended '
             'writes. "Live" defers to each platform\'s own dry_run flag.',
    )

    # ------------------------------------------------------------------
    # Shortcut actions — open existing tools without leaving the
    # Settings page.
    # ------------------------------------------------------------------

    def action_open_google_workspace(self):
        return self.env.ref(
            'myschool_core.action_google_workspace_config').read()[0]

    def action_open_smartschool(self):
        return self.env.ref(
            'myschool_core.action_smartschool_config').read()[0]
