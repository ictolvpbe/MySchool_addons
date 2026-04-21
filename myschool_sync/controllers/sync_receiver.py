# -*- coding: utf-8 -*-
"""
Sync Receiver Controller
=========================
Provides JSON-RPC endpoints on the slave instance to receive sync
payloads from the master and respond to health-check pings.

Authentication is via a shared API key validated with constant-time
comparison (``hmac.compare_digest``).
"""

from odoo import http
from odoo.http import request
import hmac
import json
import logging

_logger = logging.getLogger(__name__)


class SyncReceiverController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_api_key(self, api_key):
        """Validate the incoming API key against the configured slave key.

        Returns True if valid, False otherwise. Uses constant-time
        comparison to prevent timing attacks.
        """
        configured_key = request.env['ir.config_parameter'].sudo().get_param(
            'myschool.sync_api_key', ''
        )
        if not configured_key or not api_key:
            return False
        return hmac.compare_digest(str(configured_key), str(api_key))

    def _check_sync_role(self):
        """Return True if this instance accepts inbound sync data."""
        role = request.env['ir.config_parameter'].sudo().get_param(
            'myschool.sync_role', 'disabled'
        )
        return role in ('slave', 'both')

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @http.route('/myschool_sync/receive', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def receive(self, api_key=None, payloads=None, **kwargs):
        """Receive sync payloads from master.

        Request params::

            {
                "api_key": "shared-secret",
                "payloads": [
                    {
                        "__model": "myschool.person",
                        "__natural_key": {"sap_person_uuid": "abc-123"},
                        "__action": "sync",
                        "name": "Demeyer, Jan",
                        ...
                    },
                    ...
                ]
            }

        Response::

            {
                "results": [
                    {"model": "...", "natural_key": {...}, "action": "create", "success": true, "error": null},
                    ...
                ],
                "total": 5,
                "success_count": 4,
                "error_count": 1
            }
        """
        if not self._validate_api_key(api_key):
            _logger.warning('Sync receive: invalid API key')
            return {'error': 'Invalid API key', 'results': [], 'total': 0, 'success_count': 0, 'error_count': 0}

        if not self._check_sync_role():
            return {'error': 'This instance is not configured as a sync slave', 'results': [], 'total': 0, 'success_count': 0, 'error_count': 0}

        if not payloads or not isinstance(payloads, list):
            return {'error': 'No payloads provided', 'results': [], 'total': 0, 'success_count': 0, 'error_count': 0}

        _logger.info('Sync receive: processing %d payloads', len(payloads))

        resolver = request.env['sync.resolver'].sudo()
        sync_log = request.env['sync.log'].sudo()

        results = resolver.apply_payloads(payloads)

        # Log each result
        for r in results:
            sync_log.log_event(
                model_name=r.get('model', ''),
                natural_key=r.get('natural_key', {}),
                action=r.get('action', 'error'),
                direction='inbound',
                success=r.get('success', False),
                error_message=r.get('error'),
            )

        success_count = sum(1 for r in results if r.get('success'))
        error_count = sum(1 for r in results if not r.get('success'))

        return {
            'results': results,
            'total': len(results),
            'success_count': success_count,
            'error_count': error_count,
        }

    @http.route('/myschool_sync/ping', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def ping(self, api_key=None, **kwargs):
        """Health check endpoint.

        Returns::

            {"success": true, "role": "slave", "version": "0.1"}
        """
        if not self._validate_api_key(api_key):
            return {'success': False, 'error': 'Invalid API key'}

        role = request.env['ir.config_parameter'].sudo().get_param(
            'myschool.sync_role', 'disabled'
        )
        return {
            'success': True,
            'role': role,
            'version': '0.1',
        }
