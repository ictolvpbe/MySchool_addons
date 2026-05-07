# -*- coding: utf-8 -*-
"""
Google Drive Service
====================

Shared-drive operations: create, rename, archive (=hide), delete, plus
permission management for membership.

Built on the Drive v3 API. Reuses the Workspace config-record from
``myschool.google.workspace.config`` for credentials but ships its own
service builder because Drive uses a different scope-set than the
Directory API.

Note: shared drives require an Editor/Manager-level subject. The
service-account impersonates the same super-admin as the Directory
service does.
"""

import json
import logging

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


class GoogleDriveService(models.AbstractModel):
    _name = 'myschool.google.drive.service'
    _description = 'Google Drive Service'

    def _check_google_available(self):
        if not GOOGLE_AVAILABLE:
            raise UserError(_(
                'google-api-python-client / google-auth not installed. '
                'Install with: pip install google-api-python-client google-auth'
            ))

    @api.model
    def _get_drive_service(self, config):
        """Build a Drive v3 client. Requires the ``drive`` scope to be
        enabled on the Workspace config (we don't quietly fall through
        to a smaller scope — admins should explicitly opt in)."""
        self._check_google_available()
        if not config.scope_drive:
            raise UserError(_(
                'Workspace config "%s" does not have the Drive scope enabled.'
            ) % config.name)
        if config.key_file_path:
            with open(config.key_file_path, 'r') as f:
                key = json.load(f)
        elif config.key_json:
            key = json.loads(config.key_json)
        else:
            raise UserError(_('No service-account key configured.'))
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_info(
            key, scopes=scopes).with_subject(config.subject_email)
        return build('drive', 'v3', credentials=creds, cache_discovery=False)

    @api.model
    def create_shared_drive(self, config, name, request_id=None,
                            dry_run=False):
        """Create a shared drive named ``name``.

        ``request_id`` is a client-supplied idempotency key — if you
        replay the same request_id you get the same drive instead of
        a duplicate. Defaults to a SHA-256 of the name (stable enough
        for retry-on-error scenarios within a betask).
        """
        self._check_google_available()
        if not request_id:
            import hashlib
            request_id = hashlib.sha256(name.encode('utf-8')).hexdigest()[:32]
        if dry_run:
            return {
                'success': True, 'id': '',
                'message': f'Dry run — would create shared drive "{name}"',
            }
        svc = self._get_drive_service(config)
        try:
            res = svc.drives().create(
                requestId=request_id,
                body={'name': name}).execute()
        except HttpError as e:
            _logger.error('drives.create failed: %s', e)
            raise UserError(_('drives.create failed: %s') % e)
        return {
            'success': True, 'id': res.get('id'),
            'message': f'Shared drive created: {name} ({res.get("id")})',
        }

    @api.model
    def update_shared_drive(self, config, drive_id, name=None, hidden=None,
                            dry_run=False):
        """Rename or hide a shared drive. Hiding archives it from the
        drive list without deleting any content."""
        self._check_google_available()
        body = {}
        if name is not None:
            body['name'] = name
        if hidden is not None:
            body['hidden'] = bool(hidden)
        if not body:
            return {'success': True, 'id': drive_id, 'message': 'No changes'}
        if dry_run:
            return {
                'success': True, 'id': drive_id,
                'message': f'Dry run — would update {drive_id}',
            }
        svc = self._get_drive_service(config)
        try:
            svc.drives().update(driveId=drive_id, body=body).execute()
        except HttpError as e:
            raise UserError(_('drives.update failed: %s') % e)
        return {
            'success': True, 'id': drive_id,
            'message': f'Shared drive updated: {drive_id}',
        }

    @api.model
    def delete_shared_drive(self, config, drive_id, dry_run=False):
        """Hard-delete the shared drive. Drive v3 only allows this when
        the drive is empty — clear or move contents first."""
        self._check_google_available()
        if dry_run:
            return {
                'success': True, 'id': drive_id,
                'message': f'Dry run — would delete {drive_id}',
            }
        svc = self._get_drive_service(config)
        try:
            svc.drives().delete(driveId=drive_id).execute()
        except HttpError as e:
            raise UserError(_('drives.delete failed: %s') % e)
        return {
            'success': True, 'id': drive_id,
            'message': f'Shared drive deleted: {drive_id}',
        }

    @api.model
    def add_drive_member(self, config, drive_id, email, role='writer',
                         dry_run=False):
        """Grant a user access to the shared drive.

        Valid roles: ``reader``, ``commenter``, ``writer``,
        ``fileOrganizer``, ``organizer``. Use ``organizer`` for
        manager-equivalent access.
        """
        self._check_google_available()
        if dry_run:
            return {
                'success': True, 'id': drive_id, 'member_id': email,
                'message': f'Dry run — would add {email} as {role}',
            }
        body = {
            'type': 'user',
            'role': role,
            'emailAddress': email,
        }
        svc = self._get_drive_service(config)
        try:
            res = svc.permissions().create(
                fileId=drive_id,
                body=body,
                supportsAllDrives=True,
                sendNotificationEmail=False).execute()
        except HttpError as e:
            raise UserError(_('permissions.create failed: %s') % e)
        return {
            'success': True, 'id': drive_id,
            'permission_id': res.get('id'),
            'message': f'Added {email} ({role}) to drive {drive_id}',
        }

    @api.model
    def remove_drive_member(self, config, drive_id, permission_id,
                            dry_run=False):
        """Revoke a member's permission on a shared drive.

        ``permission_id`` is the ID returned by ``add_drive_member``;
        looking up by email requires a separate ``permissions.list``
        call which the caller can make if needed.
        """
        self._check_google_available()
        if dry_run:
            return {
                'success': True, 'id': drive_id, 'permission_id': permission_id,
                'message': f'Dry run — would revoke {permission_id}',
            }
        svc = self._get_drive_service(config)
        try:
            svc.permissions().delete(
                fileId=drive_id,
                permissionId=permission_id,
                supportsAllDrives=True).execute()
        except HttpError as e:
            raise UserError(_('permissions.delete failed: %s') % e)
        return {
            'success': True, 'id': drive_id, 'permission_id': permission_id,
            'message': f'Revoked {permission_id} on drive {drive_id}',
        }
