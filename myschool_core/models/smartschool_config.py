# -*- coding: utf-8 -*-
"""
Smartschool Platform Configuration
==================================

Connection settings for a Smartschool platform — one record per school
(BAWA, BAPLE, ...). Each platform has its own API key.

Mirrors the shape of ``myschool.google.workspace.config`` and
``myschool.ldap.server.config``: ``get_server_for_org`` walks the
org-tree to resolve the right config for a person/org, so the betask
processor can dispatch ``SMARTSCHOOL/*`` tasks identically to how it
resolves CLOUD or LDAP configs today.

Unlike LDAP/Google there is NO single-active constraint — Smartschool
deploys one platform per school, so multiple active configs are normal.
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SmartschoolConfig(models.Model):
    _name = 'myschool.smartschool.config'
    _description = 'Smartschool Platform Configuration'
    _rec_name = 'name'
    _order = 'sequence, name'

    # =========================================================================
    # Identification
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        help='Descriptive name (e.g. "BAWA Smartschool")'
    )

    sequence = fields.Integer(string='Sequence', default=10)

    active = fields.Boolean(string='Active', default=True)

    # =========================================================================
    # Platform Settings
    # =========================================================================

    platform_url = fields.Char(
        string='Platform URL',
        required=True,
        help='Base URL of the Smartschool platform, e.g. '
             'https://bawa.smartschool.be (no trailing slash, no /Webservices)'
    )

    api_key = fields.Char(
        string='API Key',
        required=False,
        groups='base.group_system',
        help='Shared accesscode for the Smartschool Web Services. One key '
             'per platform — request via Smartschool support. Passed as the '
             '``accesscode`` parameter on every SOAP call.'
    )

    # =========================================================================
    # Defaults applied to user-management calls
    # =========================================================================

    default_role_teacher = fields.Char(
        string='Default Role for Teachers',
        default='Leerkracht',
        help='Smartschool role string assigned to EMPLOYEE-typed persons '
             'when no explicit mapping is defined. Must match a role that '
             'exists on the Smartschool platform (case-sensitive).'
    )

    force_password_reset = fields.Boolean(
        string='Force Password Reset on Create',
        default=True,
        help='New accounts are flagged so Smartschool prompts the user '
             'to change their password on first login.'
    )

    # =========================================================================
    # Safeguard
    # =========================================================================

    dry_run = fields.Boolean(
        string='Dry Run',
        default=False,
        help='When enabled, mutating SOAP calls (saveUser, delUser, '
             'setAccountStatus, savePassword) are simulated only — '
             'the request payload is written to myschool.sys.event '
             'instead of being sent to Smartschool. Read calls always '
             'execute. Overridden by the global Safeguard Mode setting.'
    )

    # =========================================================================
    # Org assignments
    # =========================================================================

    org_ids = fields.Many2many(
        comodel_name='myschool.org',
        relation='smartschool_config_org_rel',
        column1='config_id',
        column2='org_id',
        string='Assigned Organizations',
        help='Organizations that use this Smartschool platform. The org-tree '
             'is walked upwards if the org itself has no direct assignment.'
    )

    org_count = fields.Integer(
        string='Organization Count',
        compute='_compute_org_count',
        store=True
    )

    # =========================================================================
    # Status
    # =========================================================================

    last_test_date = fields.Datetime(string='Last Test Date', readonly=True)
    last_test_result = fields.Selection(
        selection=[('success', 'Success'), ('failed', 'Failed')],
        string='Last Test Result',
        readonly=True
    )
    last_test_message = fields.Text(string='Last Test Message', readonly=True)

    last_discovery_at = fields.Datetime(
        string='Last API Discovery', readonly=True)
    last_discovery_report = fields.Text(
        string='API Discovery Report',
        readonly=True,
        help='Output of ``Discover API``: SOAP method signatures + '
             'error-code table. Use when a saveUser/setAccountStatus/... '
             'returns an unknown code.'
    )

    # =========================================================================
    # Computed
    # =========================================================================

    @api.depends('org_ids')
    def _compute_org_count(self):
        for rec in self:
            rec.org_count = len(rec.org_ids)

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains('platform_url')
    def _check_platform_url(self):
        for rec in self:
            if not rec.platform_url:
                continue
            url = rec.platform_url.strip()
            if not url.startswith(('http://', 'https://')):
                raise ValidationError(_(
                    'Platform URL must start with http:// or https:// — got: %s'
                ) % rec.platform_url)
            if url.endswith('/'):
                raise ValidationError(_(
                    'Platform URL should not have a trailing slash — got: %s'
                ) % rec.platform_url)

    # =========================================================================
    # Helpers
    # =========================================================================

    def get_wsdl_url(self):
        """Return the full WSDL endpoint used by zeep."""
        self.ensure_one()
        return f'{self.platform_url.rstrip("/")}/Webservices/V3?wsdl'

    @api.model
    def get_server_for_org(self, org_id):
        """Find the active Smartschool config for the given org.

        Walks the org's parent chain via ``name_tree`` (same algorithm as
        ``myschool.google.workspace.config.get_server_for_org``). Returns
        empty recordset when no platform is configured for the org — the
        caller decides whether that should fail the betask or skip it.
        """
        if isinstance(org_id, int):
            org = self.env['myschool.org'].browse(org_id)
        else:
            org = org_id

        if not org:
            return self.browse()

        cfg = self.search([
            ('org_ids', 'in', [org.id]),
            ('active', '=', True),
        ], limit=1, order='sequence')
        if cfg:
            return cfg

        if org.name_tree:
            parts = org.name_tree.split('.')
            for i in range(len(parts) - 1, 0, -1):
                parent_tree = '.'.join(parts[:i])
                parent_org = self.env['myschool.org'].search(
                    [('name_tree', '=', parent_tree)], limit=1)
                if parent_org:
                    cfg = self.search([
                        ('org_ids', 'in', [parent_org.id]),
                        ('active', '=', True),
                    ], limit=1, order='sequence')
                    if cfg:
                        return cfg

        return self.browse()

    # =========================================================================
    # Actions
    # =========================================================================

    def action_view_organizations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Organizations'),
            'res_model': 'myschool.org',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.org_ids.ids)],
        }

    def action_discover_api(self):
        """Dump SOAP signatures + error-code table into last_discovery_report.

        Read-only on the Smartschool side — never blocked by safeguards.
        """
        self.ensure_one()
        _logger.info('Smartschool action_discover_api clicked for config id=%s', self.id)
        svc = self.env['myschool.smartschool.service']
        try:
            report = svc.discover_api(self)
        except Exception as e:
            _logger.exception('Smartschool discover_api failed')
            report = f'ERROR: {e}'
        self.write({
            'last_discovery_at': fields.Datetime.now(),
            'last_discovery_report': report,
        })
        self.env.cr.commit()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('API Discovery'),
                'message': _('Report opgeslagen — zie tab "API Discovery".'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            }
        }

    def action_test_connection(self):
        """Authenticate against Smartschool and probe one call.

        Delegates to ``myschool.smartschool.service.test_connection`` so
        the failure modes (bad URL, bad key, network) surface with the
        same diagnostics admins will see during real betask runs.
        """
        self.ensure_one()
        _logger.info('Smartschool action_test_connection clicked for config id=%s name=%r',
                     self.id, self.name)

        def _safe(text):
            return str(text or '').replace('\x00', ' ')

        svc = self.env['myschool.smartschool.service']
        try:
            result = svc.test_connection(self)
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'success' if result.get('success') else 'failed',
                'last_test_message': _safe(result.get('message')),
            })
        except Exception as e:
            _logger.exception('Smartschool test failed')
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'failed',
                'last_test_message': _safe(str(e)),
            })
            result = {'success': False, 'message': str(e)}

        # Commit so the user sees the result even if the page is closed
        # before the transaction would otherwise commit.
        self.env.cr.commit()

        # Notification + form reload combined: Odoo 19 does not refresh
        # the current form automatically after a client action, so the
        # ``last_test_*`` fields would stay blank visually until F5.
        # Returning a ``soft_reload`` action via ``next`` solves that.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Test'),
                'message': _safe(result.get('message') or ''),
                'type': 'success' if result.get('success') else 'danger',
                'sticky': not result.get('success'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            }
        }
