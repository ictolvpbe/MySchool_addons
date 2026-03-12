# -*- coding: utf-8 -*-
"""
Sync Dispatcher
===============
Sends sync payloads from master to slave via JSON-RPC POST.
"""

from odoo import models, api
import json
import requests
import logging

_logger = logging.getLogger(__name__)

# Timeout for HTTP requests (connect, read) in seconds
REQUEST_TIMEOUT = (10, 30)


class SyncDispatcher(models.AbstractModel):
    _name = 'sync.dispatcher'
    _description = 'Sync Dispatcher'

    @api.model
    def dispatch_to_target(self, target, payloads):
        """Send a batch of payloads to a single sync target.

        :param target: ``sync.target`` record
        :param payloads: list of payload dicts
        :returns: dict with ``success``, ``results``, ``error``
        """
        url = target.url.rstrip('/') + '/myschool_sync/receive'
        body = {
            'jsonrpc': '2.0',
            'method': 'call',
            'id': 1,
            'params': {
                'api_key': target.api_key,
                'payloads': payloads,
            },
        }

        try:
            resp = requests.post(
                url,
                json=body,
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # JSON-RPC wraps the result in {"result": ...}
            result = data.get('result', data)
            if result.get('error'):
                return {
                    'success': False,
                    'error': result['error'],
                    'results': result.get('results', []),
                }
            return {
                'success': True,
                'results': result.get('results', []),
                'total': result.get('total', 0),
                'success_count': result.get('success_count', 0),
                'error_count': result.get('error_count', 0),
            }

        except requests.ConnectionError as e:
            return {'success': False, 'error': f'Connection failed: {e}', 'results': []}
        except requests.Timeout:
            return {'success': False, 'error': 'Request timed out', 'results': []}
        except requests.HTTPError as e:
            return {'success': False, 'error': f'HTTP error: {e}', 'results': []}
        except Exception as e:
            return {'success': False, 'error': str(e), 'results': []}

    @api.model
    def ping_target(self, target):
        """Health-check a slave instance."""
        url = target.url.rstrip('/') + '/myschool_sync/ping'
        body = {
            'jsonrpc': '2.0',
            'method': 'call',
            'id': 1,
            'params': {
                'api_key': target.api_key,
            },
        }

        try:
            resp = requests.post(
                url,
                json=body,
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get('result', data)
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @api.model
    def dispatch_to_all_targets(self, payloads, betask_object=None):
        """Dispatch payloads to every active target that has the relevant
        model flag enabled.

        :param payloads: list of payload dicts
        :param betask_object: optional betask object name to filter targets
        :returns: list of (target, result) tuples
        """
        from . import sync_model_registry

        targets = self.env['sync.target'].sudo().search([('is_active', '=', True)])
        results = []

        for target in targets:
            # Filter payloads per target based on model flags
            target_payloads = []
            for p in payloads:
                entry = sync_model_registry.get_registry_by_model(p.get('__model', ''))
                if entry and getattr(target, entry['target_flag'], False):
                    target_payloads.append(p)

            if not target_payloads:
                continue

            result = self.dispatch_to_target(target, target_payloads)
            results.append((target, result))

        return results
