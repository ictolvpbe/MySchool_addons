# -*- coding: utf-8 -*-
"""
Google Workspace Configuration
==============================

Connection settings for the Google Workspace tenant: service-account
JSON key, customer id, default domain, and the super-admin to
impersonate via domain-wide delegation.

Mirrors the shape of ``myschool.ldap.server.config`` (single-active
constraint, org assignment, ``get_server_for_org`` resolver,
``action_test_connection``) so the betask processor can resolve a
config the same way for ``CLOUD/*`` tasks as it does for ``LDAP/*``.
"""

import logging
import os

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GoogleWorkspaceConfig(models.Model):
    _name = 'myschool.google.workspace.config'
    _description = 'Google Workspace Configuration'
    _rec_name = 'name'
    _order = 'sequence, name'

    # =========================================================================
    # Identification
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        help='Descriptive name for this Workspace tenant configuration'
    )

    sequence = fields.Integer(string='Sequence', default=10)

    active = fields.Boolean(string='Active', default=True)

    # =========================================================================
    # Tenant Settings
    # =========================================================================

    customer_id = fields.Char(
        string='Customer ID',
        default='my_customer',
        required=True,
        help='Google Workspace customer id. "my_customer" resolves to the '
             'tenant the service-account belongs to and is correct for most '
             'single-tenant setups.'
    )

    domain = fields.Char(
        string='Primary Domain',
        required=True,
        help='Primary domain of the Workspace tenant (e.g. olvp.be)'
    )

    subject_email = fields.Char(
        string='Impersonation Subject',
        required=True,
        groups='base.group_system',
        help='Email of a Workspace super-admin that the service account '
             'impersonates via domain-wide delegation. Must be granted in '
             'the Workspace admin console under Security → API Controls → '
             'Domain-wide Delegation, with the scopes listed below.'
    )

    # =========================================================================
    # Service-account credentials
    # =========================================================================
    #
    # Two storage modes — pick one:
    #   • key_file_path     : filesystem path to JSON file (recommended;
    #                         keeps secrets out of database backups)
    #   • key_json          : raw JSON contents (fallback for setups
    #                         where the filesystem is not writable)
    # =========================================================================

    key_file_path = fields.Char(
        string='Service Account JSON Path',
        groups='base.group_system',
        help='Filesystem path to the service-account JSON key file.'
    )

    key_json = fields.Text(
        string='Service Account JSON (inline)',
        groups='base.group_system',
        help='Inline JSON contents of the service-account key. Used only '
             'when no file path is configured. Stored encrypted at rest is '
             'a non-goal here — prefer the file-path option.'
    )

    # =========================================================================
    # Scope configuration
    # =========================================================================

    scope_directory_user = fields.Boolean(
        string='Directory: Users',
        default=True,
        help='Grant admin.directory.user scope (manage users, passwords, OUs).'
    )
    scope_directory_group = fields.Boolean(
        string='Directory: Groups',
        default=True,
        help='Grant admin.directory.group scope (manage groups + members).'
    )
    scope_directory_orgunit = fields.Boolean(
        string='Directory: OrgUnits',
        default=True,
        help='Grant admin.directory.orgunit scope (manage OUs).'
    )
    scope_directory_device = fields.Boolean(
        string='Directory: ChromeOS Devices',
        default=True,
        help='Grant admin.directory.device.chromeos scope (manage Chromebooks).'
    )
    scope_drive = fields.Boolean(
        string='Drive (Shared Drives)',
        default=False,
        help='Grant drive scope (manage shared drives + permissions).'
    )
    scope_classroom = fields.Boolean(
        string='Classroom',
        default=False,
        help='Grant classroom.courses + .rosters scopes.'
    )
    scope_licensing = fields.Boolean(
        string='License Manager',
        default=False,
        help='Grant apps.licensing scope (manage license assignments).'
    )

    # =========================================================================
    # Org assignments
    # =========================================================================

    org_ids = fields.Many2many(
        comodel_name='myschool.org',
        relation='google_workspace_org_rel',
        column1='workspace_id',
        column2='org_id',
        string='Assigned Organizations',
        help='Organizations that use this Workspace tenant. The org-tree is '
             'walked upwards if the org itself has no direct assignment.'
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

    @api.constrains('active')
    def _check_single_active(self):
        if self.search_count([('active', '=', True)]) > 1:
            raise ValidationError(_(
                'Only one Google Workspace configuration can be active at '
                'a time. Archive the others first.'
            ))

    @api.constrains('key_file_path', 'key_json')
    def _check_credentials(self):
        for rec in self:
            if not rec.key_file_path and not rec.key_json:
                # Allow empty credentials on draft records — only enforce
                # at test/connection time. This lets admins create the
                # record first and paste the key after.
                continue
            if rec.key_file_path and not os.path.isfile(rec.key_file_path):
                raise ValidationError(_(
                    'Service-account key file not found: %s'
                ) % rec.key_file_path)

    # =========================================================================
    # Overrides — single active record
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('active', True) for vals in vals_list):
            self.search([('active', '=', True)]).write({'active': False})
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('active') is True:
            others = self.search([
                ('active', '=', True),
                ('id', 'not in', self.ids or [0]),
            ])
            if others:
                super(type(self), others).write({'active': False})
        return super().write(vals)

    # =========================================================================
    # Helpers
    # =========================================================================

    def get_scopes(self):
        """Return the OAuth scope list selected for this tenant."""
        self.ensure_one()
        scopes = []
        if self.scope_directory_user:
            scopes.append('https://www.googleapis.com/auth/admin.directory.user')
        if self.scope_directory_group:
            scopes.append('https://www.googleapis.com/auth/admin.directory.group')
            scopes.append(
                'https://www.googleapis.com/auth/admin.directory.group.member')
        if self.scope_directory_orgunit:
            scopes.append('https://www.googleapis.com/auth/admin.directory.orgunit')
        if self.scope_directory_device:
            scopes.append(
                'https://www.googleapis.com/auth/admin.directory.device.chromeos')
        if self.scope_drive:
            scopes.append('https://www.googleapis.com/auth/drive')
        if self.scope_classroom:
            scopes.append('https://www.googleapis.com/auth/classroom.courses')
            scopes.append('https://www.googleapis.com/auth/classroom.rosters')
        if self.scope_licensing:
            scopes.append('https://www.googleapis.com/auth/apps.licensing')
        return scopes

    @api.model
    def get_server_for_org(self, org_id):
        """Find the active workspace config for the given org.

        Walks the org's parent chain via ``name_tree`` (same algorithm as
        ``myschool.ldap.server.config.get_server_for_org``) and falls
        back to the single active record when no explicit assignment is
        found.
        """
        if isinstance(org_id, int):
            org = self.env['myschool.org'].browse(org_id)
        else:
            org = org_id

        if not org:
            return self.browse()

        cfg = self.search([
            ('org_ids', 'in', org.id),
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
                        ('org_ids', 'in', parent_org.id),
                        ('active', '=', True),
                    ], limit=1, order='sequence')
                    if cfg:
                        return cfg

        return self.search([('active', '=', True)], limit=1, order='sequence')

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

    def action_test_connection(self):
        """Authenticate against Workspace and probe one Directory call.

        Uses the directory service's ``test_connection`` so the failure
        modes (missing scopes, wrong subject, expired key) surface with
        the same diagnostics admins will see during real betask runs.
        """
        self.ensure_one()

        def _safe(text):
            return str(text or '').replace('\x00', ' ')

        svc = self.env['myschool.google.directory.service']
        try:
            result = svc.test_connection(self)
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'success' if result.get('success') else 'failed',
                'last_test_message': _safe(result.get('message')),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': _safe(result.get('message') or ''),
                    'type': 'success' if result.get('success') else 'danger',
                    'sticky': not result.get('success'),
                }
            }
        except Exception as e:
            _logger.exception('Google Workspace test failed')
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'failed',
                'last_test_message': _safe(str(e)),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
