# -*- coding: utf-8 -*-
"""
LDAP Server Configuration Model
================================

This model stores LDAP/Active Directory server connection settings
for multi-server support. Each server can be assigned to multiple
organizations.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class LdapServerConfig(models.Model):
    """
    LDAP Server Configuration.

    Stores connection settings for LDAP/Active Directory servers.
    Supports multiple servers for different organizations.
    """
    _name = 'myschool.ldap.server.config'
    _description = 'LDAP Server Configuration'
    _rec_name = 'name'
    _order = 'sequence, name'

    # =========================================================================
    # Basic Fields
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        help='Descriptive name for this LDAP server configuration'
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order in which servers are checked'
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this server configuration will be hidden'
    )

    # =========================================================================
    # Connection Settings
    # =========================================================================

    server_url = fields.Char(
        string='Server URL/Hostname',
        required=True,
        help='LDAP server hostname or IP address (e.g., ldap.example.com or 192.168.1.10)'
    )

    port = fields.Integer(
        string='Port',
        default=389,
        required=True,
        help='LDAP port (389 for LDAP, 636 for LDAPS)'
    )

    use_ssl = fields.Boolean(
        string='Use SSL (LDAPS)',
        default=False,
        help='Use SSL/TLS encryption (LDAPS on port 636)'
    )

    use_tls = fields.Boolean(
        string='Use StartTLS',
        default=False,
        help='Use StartTLS for encryption on standard port'
    )

    timeout = fields.Integer(
        string='Connection Timeout',
        default=30,
        help='Connection timeout in seconds'
    )

    # =========================================================================
    # Certificate Settings
    # =========================================================================

    validate_cert = fields.Boolean(
        string='Validate Certificate',
        default=True,
        help='Validate server SSL/TLS certificate. Disable only for testing with self-signed certificates.'
    )

    ca_cert_file = fields.Char(
        string='CA Certificate File',
        help='Path to CA certificate file (PEM format) for validating server certificate. '
             'Example: /etc/ssl/certs/ca-certificates.crt or /path/to/your/ca.pem'
    )

    client_cert_file = fields.Char(
        string='Client Certificate File',
        groups='base.group_system',
        help='Path to client certificate file (PEM format) for mutual TLS authentication'
    )

    client_key_file = fields.Char(
        string='Client Key File',
        groups='base.group_system',
        help='Path to client private key file (PEM format) for mutual TLS authentication'
    )

    # =========================================================================
    # Directory Settings
    # =========================================================================

    base_dn = fields.Char(
        string='Base DN',
        required=True,
        help='Base Distinguished Name for searches (e.g., DC=school,DC=local)'
    )

    user_base_dn = fields.Char(
        string='User Base DN',
        help='Base DN for user objects. If empty, uses Base DN.'
    )

    group_base_dn = fields.Char(
        string='Group Base DN',
        help='Base DN for group objects. If empty, uses Base DN.'
    )

    # =========================================================================
    # Bind Credentials (restricted)
    # =========================================================================

    bind_dn = fields.Char(
        string='Bind DN',
        required=True,
        groups='base.group_system',
        help='DN of the account used to connect (e.g., CN=ldap-bind,OU=Service Accounts,DC=school,DC=local)'
    )

    bind_password = fields.Char(
        string='Bind Password',
        required=True,
        groups='base.group_system',
        help='Password for the bind account'
    )

    # =========================================================================
    # AD-Specific Settings
    # =========================================================================

    is_active_directory = fields.Boolean(
        string='Is Active Directory',
        default=True,
        help='Check if this is a Microsoft Active Directory server'
    )

    ad_domain = fields.Char(
        string='AD Domain',
        help='Active Directory domain name (e.g., school.local)'
    )

    upn_suffix = fields.Char(
        string='UPN Suffix',
        help='User Principal Name suffix for new accounts (e.g., @school.local)'
    )

    default_user_container = fields.Char(
        string='Default User Container',
        help='Default container/OU for new users (e.g., OU=Users,OU=MySchool)'
    )

    default_group_container = fields.Char(
        string='Default Group Container',
        help='Default container/OU for new groups (e.g., OU=Groups,OU=MySchool)'
    )

    disabled_users_container = fields.Char(
        string='Disabled Users Container',
        help='Container/OU for deactivated users (e.g., OU=Disabled,OU=Users)'
    )

    # =========================================================================
    # Organization Assignments
    # =========================================================================

    org_ids = fields.Many2many(
        comodel_name='myschool.org',
        relation='ldap_server_org_rel',
        column1='ldap_server_id',
        column2='org_id',
        string='Assigned Organizations',
        help='Organizations that use this LDAP server'
    )

    org_count = fields.Integer(
        string='Organization Count',
        compute='_compute_org_count',
        store=True
    )

    # =========================================================================
    # Status Fields
    # =========================================================================

    last_test_date = fields.Datetime(
        string='Last Test Date',
        readonly=True
    )

    last_test_result = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('failed', 'Failed'),
        ],
        string='Last Test Result',
        readonly=True
    )

    last_test_message = fields.Text(
        string='Last Test Message',
        readonly=True
    )

    # =========================================================================
    # Computed Fields
    # =========================================================================

    @api.depends('org_ids')
    def _compute_org_count(self):
        for record in self:
            record.org_count = len(record.org_ids)

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains('port')
    def _check_port(self):
        for record in self:
            if record.port < 1 or record.port > 65535:
                raise ValidationError(_('Port must be between 1 and 65535'))

    @api.constrains('use_ssl', 'use_tls')
    def _check_ssl_tls(self):
        for record in self:
            if record.use_ssl and record.use_tls:
                raise ValidationError(_('Cannot use both SSL and StartTLS simultaneously'))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_effective_user_base_dn(self):
        """Get the effective user base DN."""
        self.ensure_one()
        return self.user_base_dn or self.base_dn

    def get_effective_group_base_dn(self):
        """Get the effective group base DN."""
        self.ensure_one()
        return self.group_base_dn or self.base_dn

    # =========================================================================
    # Actions
    # =========================================================================

    def action_view_organizations(self):
        """View organizations assigned to this LDAP server."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Organizations'),
            'res_model': 'myschool.org',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.org_ids.ids)],
        }

    def action_test_connection(self):
        """Test the LDAP connection."""
        self.ensure_one()

        ldap_service = self.env['myschool.ldap.service']

        try:
            result = ldap_service.test_connection(self)

            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'success' if result.get('success') else 'failed',
                'last_test_message': result.get('message', ''),
            })

            if result.get('success'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': _('Connection successful! Server info: %s') % result.get('message', 'OK'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test'),
                        'message': _('Connection failed: %s') % result.get('message', 'Unknown error'),
                        'type': 'danger',
                        'sticky': True,
                    }
                }

        except Exception as e:
            _logger.exception('LDAP connection test failed')
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': 'failed',
                'last_test_message': str(e),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': _('Connection failed: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # =========================================================================
    # Server Selection
    # =========================================================================

    @api.model
    def get_server_for_org(self, org_id):
        """
        Find the LDAP server configuration for a given organization.

        Searches through the organization's parent hierarchy to find
        a configured LDAP server.

        Args:
            org_id: Organization ID or record

        Returns:
            ldap.server.config record or empty recordset
        """
        if isinstance(org_id, int):
            org = self.env['myschool.org'].browse(org_id)
        else:
            org = org_id

        if not org:
            return self.browse()

        # Check if this org has a direct server assignment
        server = self.search([
            ('org_ids', 'in', org.id),
            ('active', '=', True),
        ], limit=1, order='sequence')

        if server:
            return server

        # Try parent orgs (using name_tree to find hierarchy)
        if org.name_tree:
            # name_tree format: "int.olvp.bawa"
            parts = org.name_tree.split('.')
            # Try parent paths: "int.olvp", "int"
            for i in range(len(parts) - 1, 0, -1):
                parent_tree = '.'.join(parts[:i])
                parent_org = self.env['myschool.org'].search([
                    ('name_tree', '=', parent_tree)
                ], limit=1)
                if parent_org:
                    server = self.search([
                        ('org_ids', 'in', parent_org.id),
                        ('active', '=', True),
                    ], limit=1, order='sequence')
                    if server:
                        return server

        # Return first active server as fallback
        return self.search([('active', '=', True)], limit=1, order='sequence')
