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
    # ldap3 ≤ 2.9.1 imports tagMap/typeMap from pyasn1, which were
    # renamed to TAG_MAP/TYPE_MAP in pyasn1 0.6.x. The old aliases
    # still work but emit DeprecationWarning on every Odoo startup.
    # Suppress only that specific warning during the ldap3 import —
    # narrow scope so genuine deprecation warnings elsewhere keep
    # showing up.
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore', category=DeprecationWarning,
            module=r'pyasn1\.codec\.ber\.encoder')
        from ldap3 import (
            Server, Connection, ALL, NONE as LDAP_INFO_NONE, NTLM, SIMPLE,
            SUBTREE, MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE,
            ALL_ATTRIBUTES, ALL_OPERATIONAL_ATTRIBUTES, Tls
        )
        from ldap3.core.exceptions import (
            LDAPException, LDAPBindError, LDAPSocketOpenError,
            LDAPEntryAlreadyExistsResult,
        )
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

        # get_info=NONE: don't auto-query rootDSE / schema. AD often
        # rejects pre-bind metadata queries with operationsError 000004DC,
        # which would surface as a confusing "successful bind required"
        # error even though the actual user-bind would succeed.
        server = Server(
            config.server_url,
            port=port,
            use_ssl=use_ssl,
            tls=tls_config,
            get_info=LDAP_INFO_NONE,
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
            # Lifecycle: open → start_tls → bind. Doing bind() first would
            # send credentials in plaintext, and most AD servers (LDAP
            # signing required) reset the connection in that case.
            conn.open()
            if config.use_tls and not config.use_ssl:
                conn.start_tls()

            # Refuse to silently fall through to anonymous bind: ldap3
            # turns missing user/password into an anonymous bind, after
            # which AD rejects every search with operationsError 000004DC
            # ("a successful bind must be completed").
            if not config.bind_dn or not config.bind_password:
                raise UserError(_(
                    'LDAP bind requires a bind DN and password. '
                    'For Active Directory: use either "DOMAIN\\\\user" with '
                    'NTLM (set is_active_directory and put a backslash in '
                    'the bind DN) or a UPN like "user@domain.local" with '
                    'SIMPLE authentication.'
                ))

            bound = conn.bind()
            if not bound:
                # bind() can return False without raising when the server
                # responds invalidCredentials but raise_exceptions misses
                # the path. Surface the LDAP result explicitly.
                last_result = getattr(conn, 'last_error', None) \
                    or getattr(conn, 'result', {})
                raise UserError(_(
                    'LDAP bind failed. user=%(user)s auth=%(auth)s '
                    'result=%(result)s'
                ) % {
                    'user': config.bind_dn,
                    'auth': 'NTLM' if (config.is_active_directory
                                       and '\\' in (config.bind_dn or ''))
                            else 'SIMPLE',
                    'result': last_result,
                })

            yield conn

        except LDAPBindError as e:
            _logger.error(f'LDAP bind failed: {e}')
            raise UserError(_('LDAP authentication failed: %s') % str(e))
        except LDAPSocketOpenError as e:
            _logger.error(f'LDAP connection failed: {e}')
            raise UserError(_('Cannot connect to LDAP server: %s') % str(e))
        except LDAPEntryAlreadyExistsResult:
            # Let callers decide whether to treat this as a benign
            # idempotency case (e.g. create_user re-running on an entry
            # that's already in AD) or as a real conflict.
            raise
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
                # Bind succeeded if we got here. Try the LDAP "Who Am I"
                # extended op (RFC 4532) for a friendly identity check —
                # but don't fail the test if the server doesn't support it.
                identity = ''
                try:
                    if hasattr(conn, 'extend') and conn.extend.standard.who_am_i:
                        whoami = conn.extend.standard.who_am_i()
                        if whoami:
                            identity = f' Bound as: {whoami}'
                except Exception:
                    pass

                return {
                    'success': True,
                    'message': f'Bind successful.{identity}',
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

        Top-of-tree segments that already appear as DC components in the
        configured base_dn are skipped — they're redundant with the
        domain root and would create an extra OU=test under DC=…,DC=test.

        Example:
            name_tree = "test.olvp.baple.pers"
            base_dn   = "DC=olvp,DC=test"
            → OU=pers,OU=baple,OU=olvp   (the leading 'test' matches DC=test)

        Args:
            name_tree: Organization name_tree (dot-separated, root first)
            config: ldap.server.config record for base DN

        Returns:
            OU path string with redundant DC-equivalent segments stripped
        """
        if not name_tree:
            return ""

        parts = [p for p in name_tree.split('.') if p]

        # Collect DC components from the configured base_dn so we know
        # which top-level segments to drop. base_dn looks like
        # "DC=olvp,DC=test"; we want {'olvp', 'test'} in lower-case.
        dc_values = set()
        if config and config.base_dn:
            for rdn in [r.strip() for r in config.base_dn.split(',')]:
                if rdn.lower().startswith('dc='):
                    dc_values.add(rdn[3:].strip().lower())

        # Strip leading segments that match a DC component. We only
        # strip from the *root* end (the leftmost in name_tree) — once a
        # segment doesn't match, we keep all remaining ones.
        while parts and parts[0].lower() in dc_values:
            parts.pop(0)

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

        # Build CN — uses {abbreviation}.{org.domain_internal} convention
        cn = self._build_user_cn(person, org=org)
        dn = self.build_user_dn(cn, org, config)

        # Build user attributes
        attributes = self._build_user_attributes(person, config, org=org)

        _logger.info(f'Creating LDAP user: {dn}')

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'attributes': attributes,
                'message': 'Dry run - user would be created',
            }

        # Pre-check: does this person already have an AD account under
        # *any* DN (matched by sAMAccountName / employeeID / cn)? If so
        # we skip the create entirely — never touching the password,
        # which is the contract for sync-driven re-runs against an
        # already-provisioned account. This catches the case where the
        # user lives under a different OU than the freshly computed
        # ``dn`` (e.g. moved to a new class/department) — without this
        # pre-check ``conn.add`` would raise an error that's not
        # always ``LDAPEntryAlreadyExistsResult`` (AD returns various
        # codes depending on which collision attribute trips first),
        # and we'd lose the idempotency guarantee.
        existing_dn = self._find_user_dn(config, person)
        if existing_dn:
            _logger.info(
                'LDAP user already exists at %s — skipping create '
                '(no password rotation)', existing_dn)
            return {
                'success': True,
                'dn': existing_dn,
                'message': (f'User already existed in AD: {existing_dn} '
                            f'(no change, password preserved)'),
            }

        try:
            with self._get_connection(config) as conn:
                # Ensure parent OU chain exists. AD returns noSuchObject if
                # any container in the DN path is missing — create them
                # ourselves so the user-add can succeed in fresh test
                # environments.
                self._ensure_ou_path(conn, dn)
                # Create the user
                result = conn.add(dn, ['user', 'person', 'organizationalPerson', 'top'], attributes)

                if result:
                    # Set password. Source priority:
                    # 1. ``person.password`` (plaintext, set by sync on
                    #    person creation).
                    # 2. Newly generated AD-complex password (saved back
                    #    to ``person.password``) when missing.
                    # We deliberately do NOT use ``person.odoo_user_id.password``
                    # — that is the Odoo password hash, not plaintext, and
                    # AD rejects it with "0000052D" (password complexity).
                    plaintext = (person.password or '').strip()
                    if not plaintext or not self._is_ad_complex_password(plaintext):
                        plaintext = self._generate_ad_complex_password()
                        try:
                            person.sudo().write({'password': plaintext})
                        except Exception:
                            _logger.warning(
                                'Could not persist generated password for %s',
                                person.name)
                    self._set_user_password(conn, dn, plaintext)

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

        except LDAPEntryAlreadyExistsResult:
            # Idempotent path: the user already exists in AD with this DN.
            # Treat as success so re-running the betask on a refreshed
            # session (or after a Reset & replay in the test runner)
            # doesn't fail the whole step. Subsequent USER/UPD tasks can
            # refresh attributes if needed.
            _logger.info(f'LDAP user already exists, skipping create: {dn}')
            return {
                'success': True,
                'dn': dn,
                'message': f'User already existed in AD: {dn} (no change)',
            }
        except Exception as e:
            _logger.exception(f'Failed to create LDAP user: {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

    @api.model
    def create_ou(self, config, org):
        """Ensure the OU container for ``org`` exists in AD.

        Idempotent: if the OU is already present (or any of its parents),
        nothing is added. Missing parent OUs along the path are created
        first via the existing ``_ensure_ou_path`` walker.

        Args:
            config: ldap.server.config record
            org: myschool.org record (must have ou_fqdn_internal set)

        Returns:
            dict with 'success', 'dn', and 'message'
        """
        self._check_ldap3_available()
        ou_dn = org.ou_fqdn_internal
        if not ou_dn:
            return {
                'success': False,
                'dn': '',
                'message': f'Org {org.name} has no ou_fqdn_internal — cannot create OU',
            }

        try:
            with self._get_connection(config) as conn:
                # Ensure parent path first.
                self._ensure_ou_path(conn, ou_dn)

                # Now check / create the leaf OU itself.
                try:
                    found = conn.search(
                        search_base=ou_dn, search_filter='(objectClass=*)',
                        search_scope='BASE', attributes=['distinguishedName'])
                    if found and conn.entries:
                        return {
                            'success': True,
                            'dn': ou_dn,
                            'message': f'OU already exists: {ou_dn}',
                        }
                except Exception:
                    # Most search-not-found errors land here — proceed to create.
                    pass

                # Extract the leaf RDN value (first OU=...).
                rdn = ou_dn.split(',', 1)[0]
                if not rdn.lower().startswith('ou='):
                    return {
                        'success': False,
                        'dn': ou_dn,
                        'message': f'Leaf RDN of {ou_dn!r} is not an OU — cannot create',
                    }
                ou_value = rdn.split('=', 1)[1]

                ok = conn.add(ou_dn,
                              ['organizationalUnit', 'top'],
                              {'ou': ou_value})
                if ok:
                    return {
                        'success': True,
                        'dn': ou_dn,
                        'message': f'OU created: {ou_dn}',
                    }
                return {
                    'success': False,
                    'dn': ou_dn,
                    'message': f'Failed to create OU: {conn.result}',
                }
        except Exception as e:
            _logger.exception(f'create_ou failed for {org.name}')
            return {
                'success': False,
                'dn': ou_dn,
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

    # AD groupType constants — bitmasks per
    # https://learn.microsoft.com/openspecs/windows_protocols/ms-adts/11972272
    GROUP_TYPE_GLOBAL_SECURITY = -2147483646      # 0x80000002
    GROUP_TYPE_GLOBAL_DISTRIBUTION = 2            # 0x00000002

    @api.model
    def create_group_at_dn(self, config, dn, group_name,
                           description=None, mail=None,
                           security=True, dry_run=False):
        """Create an AD group at a precomputed DN.

        Use this when the DN comes from the model (e.g. a PERSONGROUP's
        ``com_group_fqdn_internal``) rather than from the generic
        ``build_group_dn`` heuristic. Idempotent: if the DN already
        exists the call is treated as success.

        Args:
            config: ldap.server.config record
            dn: full DN where the group must live (CN=...,OU=...,DC=...)
            group_name: sAMAccountName / cn value
            description: optional description text
            mail: optional ``mail`` attribute (typical for COM groups)
            security: True → security group, False → distribution group
            dry_run: if True only simulate

        Returns dict with ``success``, ``dn``, ``message``.
        """
        self._check_ldap3_available()
        if not dn or not group_name:
            return {
                'success': False,
                'dn': dn or '',
                'message': 'create_group_at_dn requires dn and group_name',
            }

        group_type = (self.GROUP_TYPE_GLOBAL_SECURITY if security
                      else self.GROUP_TYPE_GLOBAL_DISTRIBUTION)
        attributes = {
            'cn': group_name,
            'sAMAccountName': group_name,
            'groupType': group_type,
        }
        if description:
            attributes['description'] = description
        if mail:
            attributes['mail'] = mail

        if dry_run:
            return {
                'success': True,
                'dn': dn,
                'attributes': attributes,
                'message': 'Dry run - group would be created',
            }

        try:
            with self._get_connection(config) as conn:
                # Ensure parent OU path is in place — same backfill the
                # OU-creation path uses.
                self._ensure_ou_path(conn, dn)

                # Idempotency: if the DN already resolves, we're done.
                try:
                    found = conn.search(
                        search_base=dn, search_filter='(objectClass=*)',
                        search_scope='BASE', attributes=['distinguishedName'])
                    if found and conn.entries:
                        return {
                            'success': True,
                            'dn': dn,
                            'message': f'Group already exists: {dn}',
                        }
                except Exception:
                    pass

                ok = conn.add(dn, ['group', 'top'], attributes)
                if ok:
                    return {
                        'success': True,
                        'dn': dn,
                        'message': f'Group created: {dn}',
                    }
                # ldap3 surfaces "already exists" both via exception
                # (LDAPEntryAlreadyExistsResult) and via conn.result —
                # treat both as success.
                code = (conn.result or {}).get('result')
                if code == 68:  # entryAlreadyExists
                    return {
                        'success': True,
                        'dn': dn,
                        'message': f'Group already exists: {dn}',
                    }
                return {
                    'success': False,
                    'dn': dn,
                    'message': f'Failed to create group: {conn.result}',
                }
        except LDAPEntryAlreadyExistsResult:
            return {
                'success': True,
                'dn': dn,
                'message': f'Group already exists: {dn}',
            }
        except Exception as e:
            _logger.exception(f'create_group_at_dn failed for {dn}')
            return {
                'success': False,
                'dn': dn,
                'message': str(e),
            }

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

    def _build_user_cn(self, person, org=None):
        """Build the CN (= account name) for a person.

        Resolution order:
        1. ``myschool.field.template`` matching ``field_name='cn'`` and the
           given (school, person_type). Configured from the UI under
           Integrations → Field Templates.
        2. Per-school ``anonymous_account_template`` CI (legacy path,
           limited to person types in ``anonymous_account_template_for_types``,
           default ``STUDENT``).
        3. Default ``<first_name>.<last_name>`` lower-cased, diacritics
           stripped, no spaces.
        """
        FieldTemplate = self.env['myschool.field.template']
        tpl = FieldTemplate.find_for('cn', person, org)
        if tpl:
            cn_from_tpl = tpl.evaluate(person, org)
            if cn_from_tpl:
                return self.escape_dn_chars(cn_from_tpl)

        if self._should_use_anonymous_template(person, org):
            school = self._resolve_user_cn_school(org)
            ConfigItem = self.env['myschool.config.item']
            template = ConfigItem.get_ci_value_by_org_and_name(
                school.name_short, 'anonymous_account_template')
            if template:
                cn_from_template = self._evaluate_account_template(template, person)
                if cn_from_template:
                    return self.escape_dn_chars(cn_from_template)

        # Default: firstname.lastname (cleaned)
        first = self._cn_clean(person.first_name or '')
        last = self._cn_clean(self._extract_last_name(person))
        if first and last:
            return self.escape_dn_chars(f"{first}.{last}")
        if first:
            return self.escape_dn_chars(first)
        if last:
            return self.escape_dn_chars(last)
        # Final fallback when neither name part is usable
        return self.escape_dn_chars(person.abbreviation or str(person.id))

    def _should_use_anonymous_template(self, person, org):
        """Return True when the anonymous-template CN should be used for
        this person.

        Looks at two CIs on the parent school (both optional):
        - ``anonymous_account_template``           : the template string
        - ``anonymous_account_template_for_types`` : comma-separated list
          of person-type names that the template applies to. Defaults to
          ``STUDENT`` when not set, to preserve backwards-compatible
          behaviour without ever silently anonymising employees.
        """
        if not person or not person.person_type_id:
            return False
        school = self._resolve_user_cn_school(org)
        if not school:
            return False
        ConfigItem = self.env['myschool.config.item']
        # If no template is set, no point checking the types.
        template = ConfigItem.get_ci_value_by_org_and_name(
            school.name_short, 'anonymous_account_template')
        if not template:
            return False
        types_value = ConfigItem.get_ci_value_by_org_and_name(
            school.name_short, 'anonymous_account_template_for_types')
        if types_value:
            allowed = {t.strip().upper() for t in types_value.split(',') if t.strip()}
        else:
            allowed = {'STUDENT'}
        return (person.person_type_id.name or '').upper() in allowed

    def _resolve_user_cn_school(self, org):
        """Walk up the ORG-TREE from `org` to find the first non-admin
        SCHOOL — that is the org whose CI ``anonymous_account_template``
        we look up."""
        if not org:
            return None
        # Re-use the betask_processor helper if available — same logic.
        processor = self.env.get('myschool.betask.processor')
        if processor is not None and hasattr(processor, '_resolve_parent_school_from_org'):
            try:
                return processor._resolve_parent_school_from_org(org)
            except Exception:
                pass
        # Fallback: walk via _iter_org_ancestors (defined elsewhere in
        # this module) and pick the first SCHOOL non-admin org.
        OrgType = self.env['myschool.org.type']
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)
        for ancestor in self._iter_org_ancestors(org):
            if (school_type and ancestor.org_type_id.id == school_type.id
                    and not ancestor.is_administrative):
                return ancestor
        return None

    @staticmethod
    def _cn_clean(value):
        """Lowercase, strip diacritics and spaces — same convention as the
        email-account generator in betask_processor."""
        if not value:
            return ''
        import unicodedata
        normalized = unicodedata.normalize('NFKD', value)
        ascii_only = ''.join(c for c in normalized if not unicodedata.combining(c))
        return ascii_only.replace(' ', '').lower()

    @staticmethod
    def _extract_last_name(person):
        """Return the dedicated person.last_name, falling back to parsing
        the composite person.name ('Achternaam, Voornaam') for legacy
        records that predate the last_name field."""
        if person.last_name:
            return person.last_name.strip()
        if not person.name:
            return ''
        if ',' in person.name:
            return person.name.split(',', 1)[0].strip()
        return person.name.strip()

    def _evaluate_account_template(self, template, person):
        """Tiny DSL for per-school account templates.

        Grammar (loose, & is the only operator between terms):
          expr := term ('&' term)*
          term := "'" literal "'"            (literal text, single-quoted)
                | "<" field ">" (op num)?    (field value, optional +/- N)
          op   := "+" | "-"

        Examples:
          ``'t'&<sap_ref>+1631``  →  ``t<sap_ref+1631>``
          ``<first_name>&'_'&<sap_ref>``  →  ``Mark_69``

        Non-numeric arithmetic operands are silently ignored (the field
        value falls through unchanged).
        """
        import re
        result_parts = []
        for raw_part in template.split('&'):
            part = raw_part.strip()
            if not part:
                continue
            # Literal: 'xxx'
            m = re.match(r"^'([^']*)'$", part)
            if m:
                result_parts.append(m.group(1))
                continue
            # Field with optional arithmetic: <field> [+/-N]
            m = re.match(r'^<(\w+)>\s*([+-])\s*(\d+)$', part)
            if m:
                field, op, num = m.group(1), m.group(2), int(m.group(3))
                value = getattr(person, field, '')
                try:
                    value = int(str(value).strip())
                    value = value + num if op == '+' else value - num
                except (ValueError, TypeError):
                    _logger.warning(
                        '[CN-TEMPLATE] %s.%s is not numeric, '
                        'skipping arithmetic %s%d', person._name, field, op, num)
                result_parts.append(str(value))
                continue
            # Plain field: <field>
            m = re.match(r'^<(\w+)>$', part)
            if m:
                value = getattr(person, m.group(1), '')
                result_parts.append('' if value is None else str(value))
                continue
            _logger.warning(
                '[CN-TEMPLATE] Unrecognized template segment %r in %r',
                part, template)
        return ''.join(result_parts)

    def _iter_org_ancestors(self, org):
        """Yield org plus its ORG-TREE parents until the root."""
        if not org:
            return
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        current = org
        seen = set()
        for _ in range(10):
            if not current or current.id in seen:
                break
            seen.add(current.id)
            yield current
            if not org_tree_type:
                break
            parent_rel = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org', '=', current.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            current = parent_rel.id_org_parent if parent_rel else None

    def _build_user_attributes(self, person, config, org=None):
        """Build user attributes for creation.

        Naming spec:
        - cn / sAMAccountName: see ``_build_user_cn``
        - userPrincipalName:  ``<cn>@<school.domain_internal>``
          (falls back to ``<cn><config.upn_suffix>`` when domain_internal
          is not set on any ancestor org)
        """
        cn = self._build_user_cn(person, org=org)
        sam_account = cn[:20]  # AD limit

        attributes = {
            'cn': cn,
            'sAMAccountName': sam_account,
            'displayName': f"{person.first_name or ''} {person.name or ''}".strip(),
            'givenName': person.first_name or '',
            'sn': person.name or '',
            'userAccountControl': str(self.UAC_NORMAL_ACCOUNT | self.UAC_DISABLED),
        }

        domain_internal = self._resolve_org_domain(org, 'domain_internal')
        if domain_internal:
            attributes['userPrincipalName'] = f"{cn}@{domain_internal}"
        elif config.upn_suffix:
            suffix = config.upn_suffix
            if not suffix.startswith('@'):
                suffix = '@' + suffix
            attributes['userPrincipalName'] = f"{cn}{suffix}"

        # mail = the cloud-mailbox address (myschool.person.email_cloud).
        # `person.email` doesn't exist on this model — it was a stale
        # reference that silently produced an empty mail attribute.
        if person.email_cloud:
            attributes['mail'] = person.email_cloud

        # employeeID = SAP reference. Acts as the stable cross-system
        # link to the upstream HR system; useful for downstream tooling
        # (e.g. provisioning checks, audits) that join on this attribute.
        if person.sap_ref:
            attributes['employeeID'] = str(person.sap_ref)

        return attributes

    def _resolve_org_domain(self, org, field_name):
        """Walk up the ORG-TREE looking for the first ancestor with the
        given domain field set (``domain_internal`` / ``domain_external``)."""
        if not org:
            return ''
        for ancestor in self._iter_org_ancestors(org):
            value = getattr(ancestor, field_name, None)
            if value:
                return value
        return ''

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

        if person.email_cloud:
            changes['mail'] = [(MODIFY_REPLACE, [person.email_cloud])]

        if person.sap_ref:
            changes['employeeID'] = [(MODIFY_REPLACE, [str(person.sap_ref)])]

        return changes

    def _find_user_dn(self, config, person):
        """Find a user's DN by various identifiers."""
        # Try by sAMAccountName (abbreviation)
        if person.abbreviation:
            result = self.find_user_by_attribute(config, 'sAMAccountName', person.abbreviation)
            if result:
                return result['dn']

        # Try by employeeID. The CREATE/UPD paths write sap_ref into AD's
        # `employeeID`, so prefer that. stam_boek_nr is a fallback for
        # legacy AD entries provisioned before this alignment.
        if person.sap_ref:
            result = self.find_user_by_attribute(config, 'employeeID', str(person.sap_ref))
            if result:
                return result['dn']
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

    @staticmethod
    def _is_ad_complex_password(pw):
        """Heuristic: AD's default policy requires ≥6 chars and presence
        of three of {upper, lower, digit, non-alnum}. Most domain
        configurations also require ≥8 and a non-alphanumeric. We test
        the common-strict case (8+ chars + all four classes) so a
        password that passes this is safe under any reasonable policy."""
        import string as _s
        if not pw or len(pw) < 8:
            return False
        has_upper = any(c.isupper() for c in pw)
        has_lower = any(c.islower() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_special = any(c in _s.punctuation for c in pw)
        return has_upper and has_lower and has_digit and has_special

    @staticmethod
    def _generate_ad_complex_password(length=14):
        """Random password with one guaranteed char from each AD class
        (upper, lower, digit, special), then padded with mixed chars.
        Length defaults to 14 to comfortably exceed 12-char policies."""
        import secrets as _secrets
        import string as _s
        # Pick a conservative special-char set — AD will accept any of
        # these in unicodePwd and they don't trip JSON/shell quoting in
        # log lines.
        specials = "!#$%&*+-=?@_"
        pools = [_s.ascii_uppercase, _s.ascii_lowercase, _s.digits, specials]
        required = [_secrets.choice(p) for p in pools]
        all_chars = _s.ascii_letters + _s.digits + specials
        rest = [_secrets.choice(all_chars) for _ in range(max(length - 4, 4))]
        chars = required + rest
        # Shuffle so the required chars aren't always at the front.
        _secrets.SystemRandom().shuffle(chars)
        return ''.join(chars)

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

    # =========================================================================
    # OU container management
    # =========================================================================

    def _ensure_ou_path(self, conn, leaf_dn):
        """Make sure every OU container in `leaf_dn`'s parent path exists in AD.

        Walks the parent DN of `leaf_dn` (everything after the first comma),
        from the deepest existing container outwards. For each missing
        `OU=…` segment it issues an `addRequest` with the
        `organizationalUnit` objectclass.

        Skips silently for any non-OU/DC segment (e.g. CN= containers).
        Errors during OU creation are logged but not raised — the
        subsequent user-add will surface a clear error if a needed
        container is still missing.
        """
        if not leaf_dn or ',' not in leaf_dn:
            return
        parent_dn = leaf_dn.split(',', 1)[1]

        # Split parent into RDNs, e.g. ['OU=pers', 'OU=baple', ..., 'DC=test']
        rdns = [p.strip() for p in parent_dn.split(',') if p.strip()]

        # The first DC=… segment marks the domain root — everything from
        # that point onward is assumed to exist. Find the index of the
        # first DC= rdn.
        try:
            dc_start = next(i for i, r in enumerate(rdns) if r.lower().startswith('dc='))
        except StopIteration:
            return  # No DC component, refuse to guess

        # The domain root DN itself.
        root_dn = ','.join(rdns[dc_start:])

        # Iterate from outermost OU (closest to root) to deepest,
        # creating missing ones as we go.
        for i in range(dc_start - 1, -1, -1):
            rdn = rdns[i]
            if not rdn.lower().startswith('ou='):
                continue  # only auto-create organizationalUnit segments
            ou_dn = ','.join(rdns[i:dc_start] + [root_dn])
            try:
                exists = conn.search(
                    search_base=ou_dn, search_filter='(objectClass=*)',
                    search_scope='BASE', attributes=['distinguishedName'])
                if exists and conn.entries:
                    continue
            except Exception:
                # search may raise noSuchObject for missing OUs — treat
                # that as "doesn't exist".
                pass

            ou_value = rdn.split('=', 1)[1]
            try:
                ok = conn.add(ou_dn,
                              ['organizationalUnit', 'top'],
                              {'ou': ou_value})
                if ok:
                    _logger.info('[LDAP] Auto-created missing OU: %s', ou_dn)
                else:
                    _logger.warning(
                        '[LDAP] OU add returned False for %s (result=%s)',
                        ou_dn, getattr(conn, 'result', None))
            except Exception as e:
                _logger.warning('[LDAP] Could not create OU %s: %s', ou_dn, e)
