# -*- coding: utf-8 -*-
"""
MCP Configuration — `res.config.settings`-tab voor de MCP server.

Houdt rate-limit + provider-toggles bij. Geen aparte config-model
nodig: alles via ir.config_parameter (sleutel-prefix ``myschool_mcp.``).
"""

from odoo import api, fields, models

from .mcp_registry import get_rate_limiter


class McpConfigSettings(models.TransientModel):
    _name = 'myschool.mcp.config'
    _inherit = 'res.config.settings'
    _description = 'MCP Server Settings'

    mcp_rate_limit_calls = fields.Integer(
        string='Rate limit (calls)',
        default=60,
        config_parameter='myschool_mcp.rate_limit_calls',
        help='Maximaal aantal MCP tool-calls per venster per gebruiker. '
             'Stop runaway-loops; geen security-laag.',
    )
    mcp_rate_limit_window = fields.Integer(
        string='Rate limit-venster (sec)',
        default=60,
        config_parameter='myschool_mcp.rate_limit_window',
    )
    mcp_provider_appfoundry = fields.Boolean(
        string='AppFoundry provider',
        default=True,
        config_parameter='myschool_mcp.provider_appfoundry',
        help='Schakel uit om alle appfoundry_* tools tijdelijk te '
             'verbergen voor de MCP-clients.',
    )

    @api.model
    def set_values(self):
        super().set_values()
        # Configureer de in-memory rate-limiter zodat wijzigingen
        # onmiddellijk effect hebben (geen restart nodig).
        calls = int(self.env['ir.config_parameter'].sudo().get_param(
            'myschool_mcp.rate_limit_calls', 60))
        window = int(self.env['ir.config_parameter'].sudo().get_param(
            'myschool_mcp.rate_limit_window', 60))
        get_rate_limiter().configure(max_calls=calls, window_seconds=window)

    @api.model
    def _load_rate_limit_at_startup(self):
        """Lees ir.config_parameter en push naar de in-memory limiter.
        Wordt aangeroepen door de controller op de eerste request."""
        ICP = self.env['ir.config_parameter'].sudo()
        calls = int(ICP.get_param('myschool_mcp.rate_limit_calls', 60))
        window = int(ICP.get_param('myschool_mcp.rate_limit_window', 60))
        get_rate_limiter().configure(max_calls=calls, window_seconds=window)
