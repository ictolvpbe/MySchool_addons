# -*- coding: utf-8 -*-
"""
LDAP Service
=============

AbstractModel providing LDAP/Active Directory operations using the ldap3 library.

This service handles:
- Connection management (connect, disconnect)
- DN construction from org tree
- User operations (create, update, rename, move, deactivate, delete)
- Group operations (create, update, rename, move, delete)
- Group membership (add member, remove member)
- Search operations

Uses ldap3 library (pure Python, cross-platform).
"""

from odoo import models, api, _
from odoo.exceptions import UserError
import logging
import json
from contextlib import contextmanager

_logger = logging.getLogger(__name__)

try:
    from ldap3 import (
        Server, Connection, ALL, NTLM, SIMPLE,
        SUBTREE, MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE,
        ALL_ATTRIBUTES, ALL_OPERATIONAL_ATTRIBUTES, Tls
    )
    from ldap3.core.exceptions import LDAPException, LDAPBindError, LDAPSocketOpenError
    import ssl
    LDAP3_AVAILABLE = True
except ImportError:
    LDAP3_AVAILABLE = False
    _logger.warning('ldap3 library not installed. LDAP operations will not be available.')


class LdapService(models.AbstractModel):
    """
    LDAP Service for Active Directory operations.

    This is an AbstractModel (no database table) that provides
    LDAP operations for other models and services.
    """
    _name = 'myschool.ldap.service'
    _description = 'LDAP Service'

    # =========================================================================
    # AD User Account Control Flags
    # =========================================================================

    UAC_NORMAL_ACCOUNT = 512
    UAC_DISABLED = 2
    UAC_PASSWORD_NOT_REQUIRED = 32
    UAC_PASSWORD_CANT_CHANGE = 64
    UAC_DONT_EXPIRE_PASSWORD = 65536

    # =========================================================================
    # Connection Management
    # =========================================================================

    def _check_ldap3_available(self):
        """Check if ldap3 library is available."""
        if not LDAP3_AVAILABLE:
            raise UserError(_(
                'The ldap3 Python library is not installed. '
                'Please install it with: pip install ldap3'
            ))

    @api.model
    def _create_tls_config(self, config):
        """
        Create TLS configuration for LDAP connection.

        Args:
            config: ldap.server.config record

        Returns:
            ldap3.Tls object or None
        """
        if not config.use_ssl and not config.use_tls:
            return None

        # Determine certificate validation mode
        if config.validate_cert:
            validate = ssl.CERT_REQUIRED
        else:
            validate = ssl.CERT_NONE
            _logger.warning('Certificate validation disabled for LDAP server: %s', config.name)

        # Build TLS configuration
        tls_config = Tls(
            validate=validate,
            ca_certs_file=config.ca_cert_file or None,
            local_certificate_file=config.client_cert_file or None,
            local_private_key_file=config.client_key_file or None,
        )

        return tls_config

    @api.model
    def _create_server(self, config):
        """
        Create an ldap3 Server object from configuration.

        Args:
            config: ldap.server.config record

        Returns:
            ldap3.Server object
        """
        self._check_ldap3_available()

        use_ssl = config.use_ssl
        port = config.port

        # Auto-adjust port if SSL is enabled and default port is used
        if use_ssl and port == 389:
            port = 636

        # Create TLS configuration
        tls_config = self._create_tls_config(config)

        server = Server(
            config.server_url,
            port=port,
            use_ssl=use_ssl,
            tls=tls_config,
            get_info=ALL,
            connect_timeout=config.timeout
        )

        return server

    @api.model
    def _create_connection(self, config, server=None):
        """
        Create an ldap3 Connection object.

        Args:
            config: ldap.server.config record
            server: Optional pre-created Server object

        Returns:
            ldap3.Connection object (not yet bound)
        """
        self._check_ldap3_available()

        if not server:
            server = self._create_server(config)

        # Determine authentication method
        if config.is_active_directory:
            # Use NTLM for AD if bind_dn looks like DOMAIN\user
            if '\\' in config.bind_dn:
                authentication = NTLM
            else:
                authentication = SIMPLE
        else:
            authentication = SIMPLE

        conn = Connection(
            server,
            user=config.bind_dn,
            password=config.bind_password,
            authentication=authentication,
            auto_bind=False,
            raise_exceptions=True
        )

        return conn

    @contextmanager
    def _get_connection(self, config):
        """
        Context manager for LDAP connections.

        Usage:
            with self._get_connection(config) as conn:
                conn.search(...)

        Args:
            config: ldap.server.config record

        Yields:
            Bound ldap3.Connection object
        """
        self._check_ldap3_available()

        conn = None
        try:
            conn = self._create_connection(config)
            conn.bind()

            # Apply StartTLS if configured
            if config.use_tls and not config.use_ssl:
                conn.start_tls()

            yield conn

        except LDAPBindError as e:
            _logger.error(f'LDAP bind failed: {e}')
            raise UserError(_('LDAP authentication failed: %s') % str(e))
        except LDAPSocketOpenError as e:
            _logger.error(f'LDAP connection failed: {e}')
            raise UserError(_('Cannot connect to LDAP server: %s') % str(e))
        except LDAPException as e:
            _logger.error(f'LDAP error: {e}')
            raise UserError(_('LDAP error: %s') % str(e))
        finally:
            if conn:
                try:
                    conn.unbind()
                except Exception:
                    pass

    @api.model
    def test_connection(self, config):
        """
        Test LDAP connection.

        Args:
            config: ldap.server.config record

        Returns:
            dict with 'success' (bool) and 'message' (str)
        """
        self._check_ldap3_available()

        try:
            with self._get_connection(config) as conn:
                server_info = conn.server.info
                vendor = getattr(server_info, 'vendor_name', ['Unknown'])[0] if server_info else 'Unknown'
                return {
                    'success': True,
                    'message': f'Connected to {vendor} server. Bind successful.',
                }
        except UserError as e:
            return {
                'success': False,
                'message': str(e.args[0]) if e.args else 'Connection failed',
            }
        except Exception as e:
            _logger.exception('LDAP test connection failed')
            return {
                'success': False,
                'message': str(e),
            }

    # =========================================================================
    # DN Construction
    # =========================================================================

    @api.model
    def build_ou_path_from_name_tree(self, name_tree, config):
        """
        Build OU path from organization name_tree.

        Example:
            name_tree = "int.olvp.bawa"
            → OU=bawa,OU=olvp,OU=int

        Args:
            name_tree: Organization name_tree (e.g., "int.olvp.bawa")
            config: ldap.server.config record for base DN

        Returns:
            OU path string (e.g., "OU=bawa,OU=olvp,OU=int")
        """
        if not name_tree:
            return ""

        parts = name_tree.split('.')
        # Reverse to build OU path (deepest first)
        ou_parts = [f"OU={part}" for part in reversed(parts)]
        return ','.join(ou_parts)

    @api.model
    def build_user_dn(self, cn, org, config):
        """
        Build a user DN based on organization.

        Args:
            cn: Common Name for the user
            org: myschool.org record
            config: ldap.server.config record

        Returns:
            Full DN string
        """
        dn_parts = [f"CN={cn}"]

        # Add OU path from org tree
        if org and org.name_tree:
            ou_path = self.build_ou_path_from_name_tree(org.name_tree, config)
            if ou_path:
                dn_parts.append(ou_path)

        # Add default user container if configured
        if config.default_user_container:
            dn_parts.append(config.default_user_container)

        # Add base DN
        dn_parts.append(config.base_dn)

        return ','.join(dn_parts)

    @api.model
    def build_group_dn(self, cn, org, config):
        """
        Build a group DN based on organization.

        Args:
            cn: Common Name for the group
            org: myschool.org record (optional)
            config: ldap.server.config record

        Returns:
            Full DN string
        """
        dn_parts = [f"CN={cn}"]

        # Add OU path from org tree
        if org and org.name_tree:
            ou_path = self.build_ou_path_from_name_tree(org.name_tree, config)
            if ou_path:
                dn_parts.append(ou_path)

        # Add default group container if configured
        if config.default_group_container:
            dn_parts.append(config.default_group_container)

        # Add base DN
        dn_parts.append(config.get_effective_group_base_dn())

        return ','.join(dn_parts)

    @api.model
    def escape_dn_chars(self, value):
        """
        Escape special characters in DN values.

        Args:
            value: String value to escape

        Returns:
            Escaped string
        """
        if not value:
            return value

        special_chars = {
            '\\': '\\\\',
            ',': '\\,',
            '+': '\\+',
            '"': '\\"',
            '<': '\\<',
            '>': '\\>',
            ';': '\\;',
            '=': '\\=',
            '\0': '\\00',
        }

        result = value
        for char, escaped in special_chars.items():
            result = result.replace(char, escaped)

        # Handle leading/trailing spaces
        if result.startswith(' '):
            result = '\\ ' + result[1:]
        if result.endswith(' '):
            result = result[:-1] + '\\ '

        return result

    # =========================================================================
    # User Operations
    # =========================================================================

    @api.model
    def create_user(self, config, person, org, dry_run=False):
        """
        Create a user in Active Directory.

        Args:
            config: ldap.server.config record
            person: myschool.person record
            org: myschool.org record
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        # Build CN (use abbreviation or first_name + name)
        cn = self._build_user_cn(person)
        dn = self.build_user_dn(cn, org, config)

        # Build user attributes
        attributes = self._build_user_attributes(person, config)

        _logger.info(f'Creating LDAP user: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'attributes': attributes,
                'message': 'Dry run - user would be created',
            }

        try:
            with self._get_connection(config) as conn:
                # Create the user
                result = conn.add(dn, ['user', 'person', 'organizationalPerson', 'top'], attributes)

                if result:
                    # Set password if we have one (AD requires special handling)
                    if person.odoo_user_id and person.odoo_user_id.password:
                        self._set_user_password(conn, dn, person.odoo_user_id.password)

                    # Enable the account
                    self._enable_user_account(conn, dn)

                    return {
                        'success': True,
                        'dn': dn,
                        'message': f'User created successfully: {dn}',
                    }
                else:
                    return {
                        'success': False,
                        'dn': dn,
                        'message': f'Failed to create user: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to create LDAP user: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    @api.model
    def update_user(self, config, person, org, dry_run=False):
        """
        Update a user in Active Directory.

        Args:
            config: ldap.server.config record
            person: myschool.person record
            org: myschool.org record
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        # Find the user
        dn = self._find_user_dn(config, person)
        if not dn:
            return {
                'success': False,
                'message': f'User not found in LDAP: {person.name}',
            }

        # Build updated attributes
        changes = self._build_user_changes(person, config)

        _logger.info(f'Updating LDAP user: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'changes': changes,
                'message': 'Dry run - user would be updated',
            }

        try:
            with self._get_connection(config) as conn:
                if changes:
                    result = conn.modify(dn, changes)
                    if result:
                        return {
                            'success': True,
                            'dn': dn,
                            'message': f'User updated successfully: {dn}',
                        }
                    else:
                        return {
                            'success': False,
                            'dn': dn,
                            'message': f'Failed to update user: {conn.result}',
                        }
                else:
                    return {
                        'success': True,
                        'dn': dn,
                        'message': 'No changes to apply',
                    }

        except Exception as e:
            _logger.exception(f'Failed to update LDAP user: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    @api.model
    def deactivate_user(self, config, person, dry_run=False):
        """
        Deactivate a user in Active Directory.

        This disables the account and optionally moves it to a disabled users container.

        Args:
            config: ldap.server.config record
            person: myschool.person record
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        # Find the user
        dn = self._find_user_dn(config, person)
        if not dn:
            return {
                'success': False,
                'message': f'User not found in LDAP: {person.name}',
            }

        _logger.info(f'Deactivating LDAP user: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'message': 'Dry run - user would be deactivated',
            }

        try:
            with self._get_connection(config) as conn:
                # Disable the account
                changes = {
                    'userAccountControl': [(MODIFY_REPLACE, [str(self.UAC_NORMAL_ACCOUNT | self.UAC_DISABLED)])]
                }
                result = conn.modify(dn, changes)

                if not result:
                    return {
                        'success': False,
                        'dn': dn,
                        'message': f'Failed to disable user: {conn.result}',
                    }

                # Move to disabled container if configured
                if config.disabled_users_container:
                    new_dn = self._build_disabled_user_dn(dn, config)
                    if new_dn != dn:
                        result = conn.modify_dn(dn, new_dn.split(',')[0], new_superior=','.join(new_dn.split(',')[1:]))
                        if result:
                            dn = new_dn
                        else:
                            _logger.warning(f'Failed to move disabled user: {conn.result}')

                return {
                    'success': True,
                    'dn': dn,
                    'message': f'User deactivated successfully: {dn}',
                }

        except Exception as e:
            _logger.exception(f'Failed to deactivate LDAP user: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    @api.model
    def delete_user(self, config, person, dry_run=False):
        """
        Delete a user from Active Directory.

        Args:
            config: ldap.server.config record
            person: myschool.person record
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        # Find the user
        dn = self._find_user_dn(config, person)
        if not dn:
            return {
                'success': False,
                'message': f'User not found in LDAP: {person.name}',
            }

        _logger.info(f'Deleting LDAP user: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'message': 'Dry run - user would be deleted',
            }

        try:
            with self._get_connection(config) as conn:
                result = conn.delete(dn)

                if result:
                    return {
                        'success': True,
                        'dn': dn,
                        'message': f'User deleted successfully: {dn}',
                    }
                else:
                    return {
                        'success': False,
                        'dn': dn,
                        'message': f'Failed to delete user: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to delete LDAP user: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    # =========================================================================
    # Group Operations
    # =========================================================================

    @api.model
    def create_group(self, config, group_name, org=None, description=None, dry_run=False):
        """
        Create a group in Active Directory.

        Args:
            config: ldap.server.config record
            group_name: Name of the group
            org: myschool.org record (optional)
            description: Group description
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        cn = self.escape_dn_chars(group_name)
        dn = self.build_group_dn(cn, org, config)

        attributes = {
            'cn': group_name,
            'sAMAccountName': group_name,
            'groupType': -2147483646,  # Global security group
        }
        if description:
            attributes['description'] = description

        _logger.info(f'Creating LDAP group: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'attributes': attributes,
                'message': 'Dry run - group would be created',
            }

        try:
            with self._get_connection(config) as conn:
                result = conn.add(dn, ['group', 'top'], attributes)

                if result:
                    return {
                        'success': True,
                        'dn': dn,
                        'message': f'Group created successfully: {dn}',
                    }
                else:
                    return {
                        'success': False,
                        'dn': dn,
                        'message': f'Failed to create group: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to create LDAP group: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    @api.model
    def update_group(self, config, group_dn, changes, dry_run=False):
        """
        Update a group in Active Directory.

        Args:
            config: ldap.server.config record
            group_dn: DN of the group
            changes: dict of attribute changes
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        _logger.info(f'Updating LDAP group: {group_dn}')

        if dry_run:
            return {
                'success': True,
                'dn': group_dn,
                'changes': changes,
                'message': 'Dry run - group would be updated',
            }

        try:
            with self._get_connection(config) as conn:
                # Convert changes to ldap3 format
                ldap_changes = {}
                for attr, value in changes.items():
                    ldap_changes[attr] = [(MODIFY_REPLACE, [value] if not isinstance(value, list) else value)]

                result = conn.modify(group_dn, ldap_changes)

                if result:
                    return {
                        'success': True,
                        'dn': group_dn,
                        'message': f'Group updated successfully: {group_dn}',
                    }
                else:
                    return {
                        'success': False,
                        'dn': group_dn,
                        'message': f'Failed to update group: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to update LDAP group: {group_dn}')
            return {
                'success': False,
                'dn': group_dn,
                'message': str(e),
            }

    @api.model
    def delete_group(self, config, group_dn, dry_run=False):
        """
        Delete a group from Active Directory.

        Args:
            config: ldap.server.config record
            group_dn: DN of the group
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        _logger.info(f'Deleting LDAP group: {group_dn}')

        if dry_run:
            return {
                'success': True,
                'dn': group_dn,
                'message': 'Dry run - group would be deleted',
            }

        try:
            with self._get_connection(config) as conn:
                result = conn.delete(group_dn)

                if result:
                    return {
                        'success': True,
                        'dn': group_dn,
                        'message': f'Group deleted successfully: {group_dn}',
                    }
                else:
                    return {
                        'success': False,
                        'dn': group_dn,
                        'message': f'Failed to delete group: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to delete LDAP group: {group_dn}')
            return {
                'success': False,
                'dn': group_dn,
                'message': str(e),
            }

    # =========================================================================
    # Group Membership Operations
    # =========================================================================

    @api.model
    def add_group_member(self, config, group_dn, member_dn, dry_run=False):
        """
        Add a member to a group.

        Args:
            config: ldap.server.config record
            group_dn: DN of the group
            member_dn: DN of the member to add
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        _logger.info(f'Adding member {member_dn} to group {group_dn}')

        if dry_run:
            return {
                'success': True,
                'group_dn': group_dn,
                'member_dn': member_dn,
                'message': 'Dry run - member would be added',
            }

        try:
            with self._get_connection(config) as conn:
                changes = {'member': [(MODIFY_ADD, [member_dn])]}
                result = conn.modify(group_dn, changes)

                if result:
                    return {
                        'success': True,
                        'group_dn': group_dn,
                        'member_dn': member_dn,
                        'message': f'Member added successfully',
                    }
                else:
                    # Check if already a member
                    if 'already' in str(conn.result).lower() or 'entry exists' in str(conn.result).lower():
                        return {
                            'success': True,
                            'group_dn': group_dn,
                            'member_dn': member_dn,
                            'message': 'Member already in group',
                        }
                    return {
                        'success': False,
                        'group_dn': group_dn,
                        'member_dn': member_dn,
                        'message': f'Failed to add member: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to add group member')
            return {
                'success': False,
                'group_dn': group_dn,
                'member_dn': member_dn,
                'message': str(e),
            }

    @api.model
    def remove_group_member(self, config, group_dn, member_dn, dry_run=False):
        """
        Remove a member from a group.

        Args:
            config: ldap.server.config record
            group_dn: DN of the group
            member_dn: DN of the member to remove
            dry_run: If True, only simulate the operation

        Returns:
            dict with operation result
        """
        self._check_ldap3_available()

        _logger.info(f'Removing member {member_dn} from group {group_dn}')

        if dry_run:
            return {
                'success': True,
                'group_dn': group_dn,
                'member_dn': member_dn,
                'message': 'Dry run - member would be removed',
            }

        try:
            with self._get_connection(config) as conn:
                changes = {'member': [(MODIFY_DELETE, [member_dn])]}
                result = conn.modify(group_dn, changes)

                if result:
                    return {
                        'success': True,
                        'group_dn': group_dn,
                        'member_dn': member_dn,
                        'message': f'Member removed successfully',
                    }
                else:
                    # Check if not a member
                    if 'not' in str(conn.result).lower() and 'member' in str(conn.result).lower():
                        return {
                            'success': True,
                            'group_dn': group_dn,
                            'member_dn': member_dn,
                            'message': 'Member was not in group',
                        }
                    return {
                        'success': False,
                        'group_dn': group_dn,
                        'member_dn': member_dn,
                        'message': f'Failed to remove member: {conn.result}',
                    }

        except Exception as e:
            _logger.exception(f'Failed to remove group member')
            return {
                'success': False,
                'group_dn': group_dn,
                'member_dn': member_dn,
                'message': str(e),
            }

    # =========================================================================
    # Search Operations
    # =========================================================================

    @api.model
    def search_users(self, config, search_filter=None, attributes=None, base_dn=None):
        """
        Search for users in LDAP.

        Args:
            config: ldap.server.config record
            search_filter: LDAP filter string (default: all users)
            attributes: List of attributes to return (default: all)
            base_dn: Base DN for search (default: user base DN)

        Returns:
            list of dicts with user data
        """
        self._check_ldap3_available()

        if not search_filter:
            search_filter = '(&(objectClass=user)(objectCategory=person))'

        if not base_dn:
            base_dn = config.get_effective_user_base_dn()

        if not attributes:
            attributes = ALL_ATTRIBUTES

        results = []

        try:
            with self._get_connection(config) as conn:
                conn.search(
                    base_dn,
                    search_filter,
                    search_scope=SUBTREE,
                    attributes=attributes
                )

                for entry in conn.entries:
                    results.append({
                        'dn': entry.entry_dn,
                        'attributes': dict(entry.entry_attributes_as_dict)
                    })

        except Exception as e:
            _logger.exception('LDAP user search failed')
            raise UserError(_('LDAP search failed: %s') % str(e))

        return results

    @api.model
    def search_groups(self, config, search_filter=None, attributes=None, base_dn=None):
        """
        Search for groups in LDAP.

        Args:
            config: ldap.server.config record
            search_filter: LDAP filter string (default: all groups)
            attributes: List of attributes to return (default: all)
            base_dn: Base DN for search (default: group base DN)

        Returns:
            list of dicts with group data
        """
        self._check_ldap3_available()

        if not search_filter:
            search_filter = '(objectClass=group)'

        if not base_dn:
            base_dn = config.get_effective_group_base_dn()

        if not attributes:
            attributes = ALL_ATTRIBUTES

        results = []

        try:
            with self._get_connection(config) as conn:
                conn.search(
                    base_dn,
                    search_filter,
                    search_scope=SUBTREE,
                    attributes=attributes
                )

                for entry in conn.entries:
                    results.append({
                        'dn': entry.entry_dn,
                        'attributes': dict(entry.entry_attributes_as_dict)
                    })

        except Exception as e:
            _logger.exception('LDAP group search failed')
            raise UserError(_('LDAP search failed: %s') % str(e))

        return results

    @api.model
    def find_user_by_attribute(self, config, attribute, value):
        """
        Find a user by a specific attribute.

        Args:
            config: ldap.server.config record
            attribute: Attribute name (e.g., 'sAMAccountName', 'mail')
            value: Value to search for

        Returns:
            dict with user data or None
        """
        search_filter = f'(&(objectClass=user)(objectCategory=person)({attribute}={value}))'
        results = self.search_users(config, search_filter)
        return results[0] if results else None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_user_cn(self, person):
        """Build CN for a user."""
        if person.abbreviation:
            return self.escape_dn_chars(person.abbreviation)
        elif person.first_name and person.name:
            return self.escape_dn_chars(f"{person.first_name} {person.name}")
        else:
            return self.escape_dn_chars(person.name or str(person.id))

    def _build_user_attributes(self, person, config):
        """Build user attributes for creation."""
        cn = self._build_user_cn(person)
        sam_account = person.abbreviation or f"{person.first_name[0] if person.first_name else ''}{person.name}"[:20]

        attributes = {
            'cn': cn,
            'sAMAccountName': sam_account,
            'displayName': f"{person.first_name or ''} {person.name or ''}".strip(),
            'givenName': person.first_name or '',
            'sn': person.name or '',
            'userAccountControl': str(self.UAC_NORMAL_ACCOUNT | self.UAC_DISABLED),  # Created disabled
        }

        # Add UPN if configured
        if config.upn_suffix:
            upn = f"{sam_account}{config.upn_suffix}"
            attributes['userPrincipalName'] = upn

        # Add email if available
        if hasattr(person, 'email') and person.email:
            attributes['mail'] = person.email

        return attributes

    def _build_user_changes(self, person, config):
        """Build user attribute changes for update."""
        changes = {}

        display_name = f"{person.first_name or ''} {person.name or ''}".strip()
        if display_name:
            changes['displayName'] = [(MODIFY_REPLACE, [display_name])]

        if person.first_name:
            changes['givenName'] = [(MODIFY_REPLACE, [person.first_name])]

        if person.name:
            changes['sn'] = [(MODIFY_REPLACE, [person.name])]

        if hasattr(person, 'email') and person.email:
            changes['mail'] = [(MODIFY_REPLACE, [person.email])]

        return changes

    def _find_user_dn(self, config, person):
        """Find a user's DN by various identifiers."""
        # Try by sAMAccountName (abbreviation)
        if person.abbreviation:
            result = self.find_user_by_attribute(config, 'sAMAccountName', person.abbreviation)
            if result:
                return result['dn']

        # Try by employee ID
        if person.stam_boek_nr:
            result = self.find_user_by_attribute(config, 'employeeID', person.stam_boek_nr)
            if result:
                return result['dn']

        # Try by name
        cn = self._build_user_cn(person)
        result = self.find_user_by_attribute(config, 'cn', cn)
        if result:
            return result['dn']

        return None

    def _set_user_password(self, conn, dn, password):
        """Set user password (AD uses unicodePwd attribute)."""
        # AD requires password to be in UTF-16LE with quotes
        encoded_password = f'"{password}"'.encode('utf-16-le')
        changes = {'unicodePwd': [(MODIFY_REPLACE, [encoded_password])]}
        return conn.modify(dn, changes)

    def _enable_user_account(self, conn, dn):
        """Enable a user account."""
        changes = {'userAccountControl': [(MODIFY_REPLACE, [str(self.UAC_NORMAL_ACCOUNT)])]}
        return conn.modify(dn, changes)

    def _build_disabled_user_dn(self, current_dn, config):
        """Build DN for disabled user container."""
        cn_part = current_dn.split(',')[0]  # CN=username
        if config.disabled_users_container:
            return f"{cn_part},{config.disabled_users_container},{config.base_dn}"
        return current_dn
