# -*- coding: utf-8 -*-
"""
Google License Manager Service
==============================

Per-user license assignment via the Enterprise License Manager API.

Useful for:
    • Granting/removing Google Workspace for Education Plus, Workspace
      Business, etc. on a per-user basis instead of relying on
      OU-level auto-assignment.
    • Reporting on who has which SKU.

A productId / skuId pair identifies the license. Common ones (current
at time of writing — verify against the SKU reference if Google
re-numbers them):

    Google-Apps                / 1010020027  (Workspace for Education Plus)
    Google-Apps                / Google-Apps-For-Business  (legacy)
    Google-Apps                / Google-Apps-Lite          (Education Fundamentals)
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


class GoogleLicenseService(models.AbstractModel):
    _name = 'myschool.google.license.service'
    _description = 'Google License Service'

    def _check_google_available(self):
        if not GOOGLE_AVAILABLE:
            raise UserError(_(
                'google-api-python-client / google-auth not installed.'
            ))

    @api.model
    def _get_licensing_service(self, config):
        self._check_google_available()
        if not config.scope_licensing:
            raise UserError(_(
                'Workspace config "%s" does not have the Licensing scope enabled.'
            ) % config.name)
        if config.key_file_path:
            with open(config.key_file_path, 'r') as f:
                key = json.load(f)
        elif config.key_json:
            key = json.loads(config.key_json)
        else:
            raise UserError(_('No service-account key configured.'))
        scopes = ['https://www.googleapis.com/auth/apps.licensing']
        creds = service_account.Credentials.from_service_account_info(
            key, scopes=scopes).with_subject(config.subject_email)
        return build('licensing', 'v1', credentials=creds,
                     cache_discovery=False)

    @api.model
    def assign_license(self, config, product_id, sku_id, user_email,
                       dry_run=False):
        """Assign ``sku_id`` of ``product_id`` to ``user_email``.

        Idempotent: if the assignment already exists Google returns
        409, which we treat as success.
        """
        if dry_run:
            return {
                'success': True, 'id': user_email,
                'message': (f'Dry run — would assign '
                            f'{product_id}/{sku_id} to {user_email}'),
            }
        svc = self._get_licensing_service(config)
        try:
            svc.licenseAssignments().insert(
                productId=product_id, skuId=sku_id,
                body={'userId': user_email}).execute()
        except HttpError as e:
            status = getattr(getattr(e, 'resp', None), 'status', None)
            if status and int(status) == 409:
                return {
                    'success': True, 'id': user_email,
                    'message': (f'License already assigned: '
                                f'{product_id}/{sku_id} → {user_email}'),
                }
            raise UserError(_('licenseAssignments.insert failed: %s') % e)
        return {
            'success': True, 'id': user_email,
            'message': f'Assigned {product_id}/{sku_id} → {user_email}',
        }

    @api.model
    def reassign_license(self, config, product_id, old_sku_id, new_sku_id,
                         user_email, dry_run=False):
        """Move a user from one SKU to another within the same product."""
        if dry_run:
            return {
                'success': True, 'id': user_email,
                'message': (f'Dry run — would reassign {user_email}: '
                            f'{old_sku_id} → {new_sku_id}'),
            }
        svc = self._get_licensing_service(config)
        try:
            svc.licenseAssignments().patch(
                productId=product_id, skuId=old_sku_id, userId=user_email,
                body={'skuId': new_sku_id}).execute()
        except HttpError as e:
            raise UserError(_('licenseAssignments.patch failed: %s') % e)
        return {
            'success': True, 'id': user_email,
            'message': (f'Reassigned {user_email} on {product_id}: '
                        f'{old_sku_id} → {new_sku_id}'),
        }

    @api.model
    def revoke_license(self, config, product_id, sku_id, user_email,
                       dry_run=False):
        """Remove a license assignment. 404 (already absent) → success."""
        if dry_run:
            return {
                'success': True, 'id': user_email,
                'message': (f'Dry run — would revoke '
                            f'{product_id}/{sku_id} from {user_email}'),
            }
        svc = self._get_licensing_service(config)
        try:
            svc.licenseAssignments().delete(
                productId=product_id, skuId=sku_id,
                userId=user_email).execute()
        except HttpError as e:
            status = getattr(getattr(e, 'resp', None), 'status', None)
            if status and int(status) == 404:
                return {
                    'success': True, 'id': user_email,
                    'message': (f'License already absent: '
                                f'{product_id}/{sku_id} for {user_email}'),
                }
            raise UserError(_('licenseAssignments.delete failed: %s') % e)
        return {
            'success': True, 'id': user_email,
            'message': f'Revoked {product_id}/{sku_id} from {user_email}',
        }

    @api.model
    def list_licenses_for_user(self, config, user_email, product_id=None):
        """Return the list of license assignments for a user.

        Useful for auditing or computing the diff before reassignment.
        ``product_id`` narrows the scan.
        """
        svc = self._get_licensing_service(config)
        out = []
        try:
            # The licenseAssignments collection requires productId to
            # list; without it we'd need to enumerate all known SKUs
            # ourselves. Caller-supplied product_id keeps this simple.
            if not product_id:
                raise UserError(_(
                    'list_licenses_for_user requires a product_id'))
            page_token = None
            while True:
                kwargs = {
                    'productId': product_id,
                    'customerId': config.domain,
                    'maxResults': 100,
                }
                if page_token:
                    kwargs['pageToken'] = page_token
                resp = svc.licenseAssignments().listForProduct(
                    **kwargs).execute()
                for item in resp.get('items') or []:
                    if item.get('userId', '').lower() == user_email.lower():
                        out.append(item)
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except HttpError as e:
            raise UserError(_('listForProduct failed: %s') % e)
        return out
