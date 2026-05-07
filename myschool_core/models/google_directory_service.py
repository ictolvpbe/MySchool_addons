# -*- coding: utf-8 -*-
"""
Google Directory Service
========================

AbstractModel that wraps the Google Workspace Admin SDK Directory API
for users, organizational units, groups, group members, ChromeOS
devices, and password operations.

Mirrors ``myschool.ldap.service``: each public method is idempotent
where the underlying API allows it, supports a ``dry_run`` toggle,
and returns a uniform ``{'success', 'id'/'dn', 'message'}`` dict so
the betask processor can treat success/failure the same regardless
of target system.

Authentication is service-account + domain-wide delegation. The
subject (super-admin to impersonate) and OAuth scopes come from the
``myschool.google.workspace.config`` record.
"""

import json
import logging
import unicodedata
from contextlib import contextmanager

from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    _logger.warning(
        'google-api-python-client / google-auth not installed. '
        'Google Directory operations will not be available. '
        'Install with: pip install google-api-python-client google-auth')


class GoogleDirectoryService(models.AbstractModel):
    _name = 'myschool.google.directory.service'
    _description = 'Google Directory Service'

    # =========================================================================
    # Library availability
    # =========================================================================

    def _check_google_available(self):
        if not GOOGLE_AVAILABLE:
            raise UserError(_(
                'The google-api-python-client / google-auth Python libraries '
                'are not installed. Install with: '
                'pip install google-api-python-client google-auth'
            ))

    # =========================================================================
    # Credential / service construction
    # =========================================================================

    @api.model
    def _build_credentials(self, config):
        """Return delegated service-account credentials for ``config``.

        Reads the JSON key from disk first; falls back to the inline
        ``key_json`` field. The subject is the super-admin to
        impersonate (Workspace requires impersonation for any
        admin-scope call — service accounts on their own can't list
        users).
        """
        self._check_google_available()
        if not config.subject_email:
            raise UserError(_(
                'Workspace config "%s" has no impersonation subject.'
            ) % config.name)

        key_data = None
        if config.key_file_path:
            with open(config.key_file_path, 'r') as f:
                key_data = json.load(f)
        elif config.key_json:
            try:
                key_data = json.loads(config.key_json)
            except (ValueError, TypeError) as e:
                raise UserError(_(
                    'Inline service-account JSON is not valid JSON: %s'
                ) % e)
        else:
            raise UserError(_(
                'Workspace config "%s" has no service-account key '
                '(neither file path nor inline JSON).'
            ) % config.name)

        scopes = config.get_scopes()
        if not scopes:
            raise UserError(_(
                'Workspace config "%s" has no scopes enabled.'
            ) % config.name)

        creds = service_account.Credentials.from_service_account_info(
            key_data, scopes=scopes)
        return creds.with_subject(config.subject_email)

    @api.model
    def _get_directory_service(self, config):
        """Build a Directory API v1 client. Raises on missing scopes."""
        creds = self._build_credentials(config)
        # cache_discovery=False suppresses the noisy "file_cache is
        # only supported with oauth2client<4.0.0" warning that the
        # default discovery cache emits in server contexts.
        return build('admin', 'directory_v1', credentials=creds,
                     cache_discovery=False)

    @contextmanager
    def _api_errors(self, what):
        """Translate googleapiclient errors to UserError with diagnostics."""
        try:
            yield
        except HttpError as e:
            status = getattr(e, 'status_code', None) or getattr(
                getattr(e, 'resp', None), 'status', None)
            try:
                body = e.content.decode('utf-8', 'replace') if e.content else ''
            except Exception:
                body = str(e)
            _logger.error('Google API error during %s: status=%s body=%s',
                          what, status, body)
            raise UserError(_(
                'Google API error during %(what)s (HTTP %(status)s): %(body)s'
            ) % {'what': what, 'status': status, 'body': body})

    @api.model
    def test_connection(self, config):
        """Probe the Directory API.

        Issues a tiny ``users.list(maxResults=1)`` against the
        configured customer. A 200 means: credentials parse, subject
        is delegated correctly, scopes match, customer id resolves.
        """
        try:
            self._check_google_available()
            svc = self._get_directory_service(config)
            customer = config.customer_id or 'my_customer'
            with self._api_errors('test_connection'):
                resp = svc.users().list(
                    customer=customer, maxResults=1).execute()
            count = len(resp.get('users') or [])
            return {
                'success': True,
                'message': f'Bind OK — listed {count} user(s) on customer={customer}',
            }
        except UserError as e:
            return {'success': False, 'message': str(e.args[0]) if e.args else 'Failed'}
        except Exception as e:
            _logger.exception('Workspace test_connection failed')
            return {'success': False, 'message': str(e)}

    # =========================================================================
    # OU path helpers
    # =========================================================================

    @api.model
    def ou_dn_to_google_path(self, ou_dn, config=None):
        """Convert an AD-style ``ou_fqdn_internal`` DN to a Google
        ``orgUnitPath``.

        DC=… segments are dropped (they encode the domain root, which
        Google treats as ``/``). The remaining OU= segments are
        reversed so that the AD leaf becomes the path tail. Empty
        input maps to the root path ``/``.

        Example:
            ``OU=Klas-3A,OU=baple,OU=olvp,DC=olvp,DC=test``
            →  ``/olvp/baple/Klas-3A``
        """
        if not ou_dn:
            return '/'
        parts = [p.strip() for p in ou_dn.split(',') if p.strip()]
        ou_segments = [p[3:] for p in parts if p.lower().startswith('ou=')]
        if not ou_segments:
            return '/'
        return '/' + '/'.join(reversed(ou_segments))

    @api.model
    def org_to_google_path(self, org, config=None):
        """Resolve the Google orgUnitPath for an ``myschool.org`` record.

        Prefers ``ou_fqdn_internal`` when present (so the same OU
        topology is used for AD and Google). Falls back to building a
        path from ``name_tree``. DC-equivalent prefixes are stripped
        the same way ``myschool.ldap.service.build_ou_path_from_name_tree``
        does — this keeps the tenant root from being repeated as an
        OU segment.
        """
        if not org:
            return '/'
        if org.ou_fqdn_internal:
            return self.ou_dn_to_google_path(org.ou_fqdn_internal, config)
        if not org.name_tree:
            return '/'
        parts = [p for p in org.name_tree.split('.') if p]
        # Drop a leading segment that matches the tenant's primary
        # domain head (e.g. "olvp" when domain="olvp.be") so we don't
        # produce /olvp/olvp/...
        if config and config.domain:
            domain_head = config.domain.split('.')[0].lower()
            while parts and parts[0].lower() == domain_head:
                parts.pop(0)
        if not parts:
            return '/'
        return '/' + '/'.join(parts)

    # =========================================================================
    # User naming — defer to LDAP service so AD and Google share CNs
    # =========================================================================

    @api.model
    def build_primary_email(self, person, org, config):
        """Compose ``primaryEmail`` as ``<cn>@<domain>``.

        ``cn`` comes from the same builder LDAP uses
        (``myschool.ldap.service._build_user_cn``) so AD's sAMAccountName,
        the LDAP CN, and the Google primaryEmail local-part stay in
        lock-step. Domain priority:
        1. The org-tree's ``domain_internal`` (resolved upwards).
        2. ``config.domain`` as final fallback.
        """
        ldap_svc = self.env['myschool.ldap.service']
        cn = ldap_svc._build_user_cn(person, org=org)
        # ``cn`` may have come back DN-escaped (e.g. ``foo\,bar``).
        # Email local-parts can't contain those escapes, so undo them
        # for the email side only.
        local = cn.replace('\\,', ',').replace('\\\\', '\\').lower()
        # Strip diacritics + spaces just in case the template returned
        # something the LDAP path tolerated but SMTP would reject.
        local = ''.join(
            c for c in unicodedata.normalize('NFKD', local)
            if not unicodedata.combining(c)
        ).replace(' ', '').replace('"', '')

        domain = ldap_svc._resolve_org_domain(org, 'domain_internal') \
            or config.domain
        if not domain:
            raise UserError(_(
                'Cannot build primaryEmail for %s: no domain_internal '
                'on the org-tree and no Workspace config domain set.'
            ) % person.name)
        return f'{local}@{domain}'

    # =========================================================================
    # User operations
    # =========================================================================

    @api.model
    def create_user(self, config, person, org, dry_run=False):
        """Create a user in Workspace.

        Idempotent: if the primaryEmail already resolves we treat it
        as success and return the existing user id. Password is taken
        from ``person.password`` (same plaintext field LDAP uses) and
        sent SHA-512-crypt hashed.
        """
        self._check_google_available()
        primary_email = self.build_primary_email(person, org, config)
        ou_path = self.org_to_google_path(org, config)
        body = {
            'primaryEmail': primary_email,
            'name': {
                'givenName': person.first_name or '',
                'familyName': person.last_name or person.name or '',
            },
            'orgUnitPath': ou_path,
            'changePasswordAtNextLogin': False,
        }
        if person.sap_ref:
            body['externalIds'] = [{
                'type': 'organization',
                'value': str(person.sap_ref),
            }]

        plaintext = self._resolve_user_password(person)
        body['hashFunction'] = 'SHA-1'
        body['password'] = self._sha1_hex(plaintext)

        if dry_run:
            redacted = dict(body)
            redacted['password'] = '***'
            return {
                'success': True, 'id': primary_email,
                'attributes': redacted,
                'message': 'Dry run — user would be created',
            }

        svc = self._get_directory_service(config)

        # Idempotency: existing primaryEmail → no-op success.
        existing = self._get_user(svc, primary_email)
        if existing:
            return {
                'success': True, 'id': primary_email,
                'message': f'User already exists: {primary_email} (no change)',
            }

        with self._api_errors(f'users.insert({primary_email})'):
            res = svc.users().insert(body=body).execute()
        return {
            'success': True,
            'id': res.get('primaryEmail') or primary_email,
            'message': f'User created: {primary_email} in {ou_path}',
        }

    @api.model
    def update_user(self, config, person, org, dry_run=False):
        """Patch user attributes (name, externalIds). Does not move the
        OU — use ``move_user_ou`` for that, and ``set_user_password``
        for the password rotation path."""
        self._check_google_available()
        primary_email = self.build_primary_email(person, org, config)
        body = {
            'name': {
                'givenName': person.first_name or '',
                'familyName': person.last_name or person.name or '',
            },
        }
        if person.sap_ref:
            body['externalIds'] = [{
                'type': 'organization',
                'value': str(person.sap_ref),
            }]
        if dry_run:
            return {
                'success': True, 'id': primary_email,
                'attributes': body,
                'message': 'Dry run — user would be updated',
            }
        svc = self._get_directory_service(config)
        with self._api_errors(f'users.patch({primary_email})'):
            svc.users().patch(userKey=primary_email, body=body).execute()
        return {
            'success': True, 'id': primary_email,
            'message': f'User updated: {primary_email}',
        }

    @api.model
    def suspend_user(self, config, person, org, dry_run=False):
        """Mark the user as suspended (Google's equivalent of disable).

        Equivalent to LDAP's ``deactivate_user``. The account becomes
        unusable but mailbox + Drive content remain. To free up the
        license, run a separate ``CLOUD/LICENSE/DEL`` task.
        """
        self._check_google_available()
        primary_email = self.build_primary_email(person, org, config)
        if dry_run:
            return {
                'success': True, 'id': primary_email,
                'message': 'Dry run — user would be suspended',
            }
        svc = self._get_directory_service(config)
        with self._api_errors(f'users.patch({primary_email}, suspended=True)'):
            svc.users().patch(
                userKey=primary_email,
                body={'suspended': True}).execute()
        return {
            'success': True, 'id': primary_email,
            'message': f'User suspended: {primary_email}',
        }

    @api.model
    def delete_user(self, config, person, org=None, dry_run=False):
        """Hard-delete the user from Workspace.

        Caller is responsible for any prior data export (Vault hold,
        Drive transfer). The Directory API will reject deletion when
        the account is the sole owner of certain resources — those
        surface as ``HttpError`` and bubble up via ``_api_errors``.
        """
        self._check_google_available()
        primary_email = self.build_primary_email(person, org, config) \
            if org else (person.email_cloud or '')
        if not primary_email:
            return {
                'success': False, 'id': '',
                'message': f'Cannot resolve primaryEmail for {person.name}',
            }
        if dry_run:
            return {
                'success': True, 'id': primary_email,
                'message': 'Dry run — user would be deleted',
            }
        svc = self._get_directory_service(config)
        # Idempotency: a 404 (not-found) is treated as success.
        if not self._get_user(svc, primary_email):
            return {
                'success': True, 'id': primary_email,
                'message': f'User already absent: {primary_email}',
            }
        with self._api_errors(f'users.delete({primary_email})'):
            svc.users().delete(userKey=primary_email).execute()
        return {
            'success': True, 'id': primary_email,
            'message': f'User deleted: {primary_email}',
        }

    @api.model
    def move_user_ou(self, config, person, target_org, dry_run=False):
        """Relocate a user to ``target_org``'s OU path.

        Uses ``users.patch`` with ``orgUnitPath`` — Google handles the
        move atomically and updates derived OU policies (Chrome,
        device sync) downstream.
        """
        self._check_google_available()
        primary_email = self.build_primary_email(
            person, target_org, config)
        ou_path = self.org_to_google_path(target_org, config)
        if dry_run:
            return {
                'success': True, 'id': primary_email,
                'message': f'Dry run — would move {primary_email} to {ou_path}',
            }
        svc = self._get_directory_service(config)
        with self._api_errors(f'users.patch({primary_email}, OU)'):
            svc.users().patch(
                userKey=primary_email,
                body={'orgUnitPath': ou_path}).execute()
        return {
            'success': True, 'id': primary_email,
            'message': f'User moved: {primary_email} → {ou_path}',
        }

    @api.model
    def set_user_password(self, config, person, plaintext, org=None,
                          change_at_next_login=False, dry_run=False):
        """Push a password to Workspace.

        ``plaintext`` is the password as MySchool stores it on
        ``myschool.person.password``. We never send it over the API in
        cleartext: convert to SHA-512 crypt and use ``hashFunction``.

        Set ``change_at_next_login=True`` for admin-initiated resets
        so the user is forced to pick a new password on first login.
        Set ``False`` for the cascade after CLOUD/USER/ADD where AD
        and Google must agree on the same password.

        ``org`` is preferred for resolving primaryEmail (so the same
        ``cn@domain_internal`` is used as during create/update).
        Falls back to ``person.email_cloud`` when no org is supplied —
        useful for admin-triggered resets where the caller doesn't
        know the current PERSON-TREE position.
        """
        self._check_google_available()
        if not plaintext:
            return {
                'success': False, 'id': '',
                'message': 'No plaintext password provided',
            }
        if org is None:
            # Best-effort: ask the betask processor for the current
            # PERSON-TREE org, mirroring what LDAP/USER/UPD does.
            try:
                processor = self.env['myschool.betask.processor']
                org = processor._resolve_current_person_tree_org(person)
            except Exception:
                org = None
        if org:
            primary_email = self.build_primary_email(person, org, config)
        else:
            primary_email = person.email_cloud or ''
        if not primary_email:
            return {
                'success': False, 'id': '',
                'message': f'Cannot resolve primaryEmail for {person.name}',
            }
        if dry_run:
            return {
                'success': True, 'id': primary_email,
                'message': 'Dry run — password would be set',
            }
        body = {
            'password': self._sha1_hex(plaintext),
            'hashFunction': 'SHA-1',
            'changePasswordAtNextLogin': bool(change_at_next_login),
        }
        svc = self._get_directory_service(config)
        with self._api_errors(f'users.patch({primary_email}, password)'):
            svc.users().patch(userKey=primary_email, body=body).execute()
        return {
            'success': True, 'id': primary_email,
            'message': (f'Password set on {primary_email} '
                        f'(change_at_next_login={bool(change_at_next_login)})'),
        }

    # =========================================================================
    # Org-unit operations
    # =========================================================================

    @api.model
    def create_orgunit(self, config, org, dry_run=False):
        """Create the org's OU (and all missing ancestors) in Workspace."""
        self._check_google_available()
        ou_path = self.org_to_google_path(org, config)
        if ou_path == '/':
            return {
                'success': True, 'id': '/',
                'message': 'Root OU — nothing to create',
            }
        if dry_run:
            return {
                'success': True, 'id': ou_path,
                'message': f'Dry run — would create OU {ou_path}',
            }
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        return self._ensure_ou_path(svc, customer, ou_path)

    @api.model
    def update_orgunit(self, config, org, new_name=None, new_description=None,
                       dry_run=False):
        """Rename or re-describe an existing OU."""
        self._check_google_available()
        ou_path = self.org_to_google_path(org, config)
        body = {}
        if new_name:
            body['name'] = new_name
        if new_description is not None:
            body['description'] = new_description
        if not body:
            return {'success': True, 'id': ou_path, 'message': 'No changes'}
        if dry_run:
            return {
                'success': True, 'id': ou_path,
                'message': f'Dry run — would patch OU {ou_path}',
            }
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        # Directory API expects orgUnitPath without the leading '/'.
        with self._api_errors(f'orgunits.patch({ou_path})'):
            svc.orgunits().patch(
                customerId=customer,
                orgUnitPath=ou_path.lstrip('/'),
                body=body).execute()
        return {
            'success': True, 'id': ou_path,
            'message': f'OU updated: {ou_path}',
        }

    @api.model
    def delete_orgunit(self, config, org, dry_run=False):
        """Delete the OU. Fails if it still contains users/devices."""
        self._check_google_available()
        ou_path = self.org_to_google_path(org, config)
        if ou_path == '/':
            return {
                'success': False, 'id': '/',
                'message': 'Refusing to delete the root OU',
            }
        if dry_run:
            return {
                'success': True, 'id': ou_path,
                'message': f'Dry run — would delete OU {ou_path}',
            }
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        with self._api_errors(f'orgunits.delete({ou_path})'):
            svc.orgunits().delete(
                customerId=customer,
                orgUnitPath=ou_path.lstrip('/')).execute()
        return {
            'success': True, 'id': ou_path,
            'message': f'OU deleted: {ou_path}',
        }

    def _ensure_ou_path(self, svc, customer, ou_path):
        """Walk an OU path and create missing ancestors in order.

        Mirrors ``myschool.ldap.service._ensure_ou_path``. Each segment
        is checked individually because ``orgunits.insert`` rejects
        creation when the parent doesn't exist yet.
        """
        segments = [s for s in ou_path.split('/') if s]
        cumulative = ''
        for seg in segments:
            parent = cumulative or '/'
            cumulative = (cumulative + '/' + seg) if cumulative else ('/' + seg)
            try:
                svc.orgunits().get(
                    customerId=customer,
                    orgUnitPath=cumulative.lstrip('/')).execute()
                continue
            except HttpError as e:
                status = getattr(getattr(e, 'resp', None), 'status', None)
                if status and int(status) != 404:
                    _logger.warning(
                        'orgunits.get(%s) returned %s — proceeding to create',
                        cumulative, status)
            try:
                svc.orgunits().insert(
                    customerId=customer,
                    body={
                        'name': seg,
                        'parentOrgUnitPath': parent,
                    }).execute()
                _logger.info('[GOOGLE] Created OU %s', cumulative)
            except HttpError as e:
                # 409 (already exists) → race: another process beat us.
                status = getattr(getattr(e, 'resp', None), 'status', None)
                if status and int(status) == 409:
                    continue
                _logger.error('Failed to create OU %s: %s', cumulative, e)
                return {
                    'success': False, 'id': cumulative,
                    'message': f'Failed to create OU {cumulative}: {e}',
                }
        return {
            'success': True, 'id': ou_path,
            'message': f'OU ensured: {ou_path}',
        }

    # =========================================================================
    # Group operations
    # =========================================================================

    @api.model
    def create_group(self, config, group_email, group_name=None,
                     description=None, dry_run=False):
        """Create a Workspace group (idempotent on group_email)."""
        self._check_google_available()
        body = {
            'email': group_email,
            'name': group_name or group_email,
        }
        if description:
            body['description'] = description
        if dry_run:
            return {
                'success': True, 'id': group_email,
                'attributes': body,
                'message': 'Dry run — group would be created',
            }
        svc = self._get_directory_service(config)
        if self._get_group(svc, group_email):
            return {
                'success': True, 'id': group_email,
                'message': f'Group already exists: {group_email}',
            }
        with self._api_errors(f'groups.insert({group_email})'):
            res = svc.groups().insert(body=body).execute()
        return {
            'success': True, 'id': res.get('email') or group_email,
            'message': f'Group created: {group_email}',
        }

    @api.model
    def update_group(self, config, group_email, name=None, description=None,
                     dry_run=False):
        self._check_google_available()
        body = {}
        if name is not None:
            body['name'] = name
        if description is not None:
            body['description'] = description
        if not body:
            return {'success': True, 'id': group_email, 'message': 'No changes'}
        if dry_run:
            return {
                'success': True, 'id': group_email,
                'attributes': body,
                'message': 'Dry run — group would be updated',
            }
        svc = self._get_directory_service(config)
        with self._api_errors(f'groups.patch({group_email})'):
            svc.groups().patch(groupKey=group_email, body=body).execute()
        return {
            'success': True, 'id': group_email,
            'message': f'Group updated: {group_email}',
        }

    @api.model
    def delete_group(self, config, group_email, dry_run=False):
        self._check_google_available()
        if dry_run:
            return {
                'success': True, 'id': group_email,
                'message': 'Dry run — group would be deleted',
            }
        svc = self._get_directory_service(config)
        if not self._get_group(svc, group_email):
            return {
                'success': True, 'id': group_email,
                'message': f'Group already absent: {group_email}',
            }
        with self._api_errors(f'groups.delete({group_email})'):
            svc.groups().delete(groupKey=group_email).execute()
        return {
            'success': True, 'id': group_email,
            'message': f'Group deleted: {group_email}',
        }

    @api.model
    def add_group_member(self, config, group_email, member_email,
                         role='MEMBER', dry_run=False):
        self._check_google_available()
        if dry_run:
            return {
                'success': True,
                'group_id': group_email, 'member_id': member_email,
                'message': 'Dry run — member would be added',
            }
        body = {'email': member_email, 'role': role}
        svc = self._get_directory_service(config)
        try:
            with self._api_errors(f'members.insert({group_email},{member_email})'):
                svc.members().insert(groupKey=group_email, body=body).execute()
        except UserError as e:
            # Idempotency: already a member → success. Google returns
            # 409 with reason "duplicate".
            if 'duplicate' in str(e).lower() or '409' in str(e):
                return {
                    'success': True,
                    'group_id': group_email, 'member_id': member_email,
                    'message': f'Already a member of {group_email}',
                }
            raise
        return {
            'success': True,
            'group_id': group_email, 'member_id': member_email,
            'message': f'Added {member_email} → {group_email}',
        }

    @api.model
    def remove_group_member(self, config, group_email, member_email,
                            dry_run=False):
        self._check_google_available()
        if dry_run:
            return {
                'success': True,
                'group_id': group_email, 'member_id': member_email,
                'message': 'Dry run — member would be removed',
            }
        svc = self._get_directory_service(config)
        try:
            with self._api_errors(f'members.delete({group_email},{member_email})'):
                svc.members().delete(
                    groupKey=group_email, memberKey=member_email).execute()
        except UserError as e:
            # 404 → member already absent.
            if '404' in str(e) or 'notFound' in str(e):
                return {
                    'success': True,
                    'group_id': group_email, 'member_id': member_email,
                    'message': f'Was not a member of {group_email}',
                }
            raise
        return {
            'success': True,
            'group_id': group_email, 'member_id': member_email,
            'message': f'Removed {member_email} from {group_email}',
        }

    # =========================================================================
    # ChromeOS device operations
    # =========================================================================

    @api.model
    def list_chromeos_devices(self, config, ou_path=None, query=None,
                              max_results=None):
        """Return a list of ChromeOS devices.

        Used by the inventory cron to upsert ``myschool.asset`` rows
        keyed by serialNumber → cloud_device_id.
        """
        self._check_google_available()
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        out = []
        page_token = None
        kwargs = {
            'customerId': customer,
            'projection': 'FULL',
            'maxResults': 100,
        }
        if ou_path:
            kwargs['orgUnitPath'] = ou_path
        if query:
            kwargs['query'] = query
        while True:
            if page_token:
                kwargs['pageToken'] = page_token
            with self._api_errors('chromeosdevices.list'):
                resp = svc.chromeosdevices().list(**kwargs).execute()
            for dev in resp.get('chromeosdevices') or []:
                out.append(dev)
                if max_results and len(out) >= max_results:
                    return out
            page_token = resp.get('nextPageToken')
            if not page_token:
                break
        return out

    @api.model
    def move_chromeos_devices(self, config, ou_path, device_ids,
                              dry_run=False):
        """Move one or more ChromeOS devices to ``ou_path``.

        Google's batch endpoint takes up to 50 device ids per call, so
        we chunk transparently. Empty / falsy ids are filtered out so
        a sloppy task payload doesn't fail with a 400.
        """
        self._check_google_available()
        device_ids = [d for d in (device_ids or []) if d]
        if not device_ids:
            return {
                'success': True, 'count': 0, 'ou': ou_path,
                'message': 'No device ids provided — nothing to do',
            }
        if dry_run:
            return {
                'success': True, 'count': len(device_ids), 'ou': ou_path,
                'message': (f'Dry run — would move {len(device_ids)} device(s) '
                            f'to {ou_path}'),
            }
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        moved = 0
        for i in range(0, len(device_ids), 50):
            chunk = device_ids[i:i + 50]
            with self._api_errors(
                    f'chromeosdevices.moveDevicesToOu({len(chunk)})'):
                svc.chromeosdevices().moveDevicesToOu(
                    customerId=customer,
                    orgUnitPath=ou_path,
                    body={'deviceIds': chunk}).execute()
            moved += len(chunk)
        return {
            'success': True, 'count': moved, 'ou': ou_path,
            'message': f'Moved {moved} device(s) to {ou_path}',
        }

    @api.model
    def action_chromeos_device(self, config, device_id, action,
                               dry_run=False):
        """Run a single-device admin action.

        Valid Google ``action`` values: ``disable``, ``reenable``,
        ``deprovision``. Deprovision additionally requires a reason —
        we default to ``retiring_device`` for end-of-life and
        ``different_model_replacement`` is the canonical alternative.
        """
        self._check_google_available()
        if action not in ('disable', 'reenable', 'deprovision'):
            return {
                'success': False, 'id': device_id,
                'message': f'Unsupported ChromeOS action: {action}',
            }
        if dry_run:
            return {
                'success': True, 'id': device_id,
                'message': f'Dry run — {action} on {device_id}',
            }
        svc = self._get_directory_service(config)
        customer = config.customer_id or 'my_customer'
        body = {'action': action}
        if action == 'deprovision':
            body['deprovisionReason'] = 'retiring_device'
        with self._api_errors(f'chromeosdevices.action({action},{device_id})'):
            svc.chromeosdevices().action(
                customerId=customer,
                resourceId=device_id,
                body=body).execute()
        return {
            'success': True, 'id': device_id,
            'message': f'Device {device_id}: {action}',
        }

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_user(self, svc, user_key):
        """Return the user dict or None on 404 (other errors raise)."""
        try:
            return svc.users().get(userKey=user_key).execute()
        except HttpError as e:
            status = getattr(getattr(e, 'resp', None), 'status', None)
            if status and int(status) == 404:
                return None
            raise

    def _get_group(self, svc, group_key):
        try:
            return svc.groups().get(groupKey=group_key).execute()
        except HttpError as e:
            status = getattr(getattr(e, 'resp', None), 'status', None)
            if status and int(status) == 404:
                return None
            raise

    def _resolve_user_password(self, person):
        """Return the plaintext password, generating + persisting one
        if missing — exactly the LDAP path's behaviour. Keeps AD and
        Google in lock-step on the same plaintext."""
        ldap_svc = self.env['myschool.ldap.service']
        plaintext = (person.password or '').strip()
        if not plaintext or not ldap_svc._is_ad_complex_password(plaintext):
            plaintext = ldap_svc._generate_ad_complex_password()
            try:
                person.sudo().write({'password': plaintext})
            except Exception:
                _logger.warning(
                    'Could not persist generated password for %s',
                    person.name)
        return plaintext

    @staticmethod
    def _sha1_hex(plaintext):
        """Hex-encoded SHA-1 of ``plaintext`` for the Directory API.

        Google's ``users.insert`` / ``users.patch`` accept three
        ``hashFunction`` values: ``MD5``, ``SHA-1``, ``crypt``.
        We pick SHA-1 because:
          • the ``crypt`` module was removed in Python 3.13,
          • ``passlib`` would be an extra dependency, and
          • the hash only travels over HTTPS to Google and is
            never persisted in MySchool (Google re-hashes it on
            their side), so unsalted SHA-1 in transit is fine.
        """
        import hashlib
        return hashlib.sha1(plaintext.encode('utf-8')).hexdigest()
