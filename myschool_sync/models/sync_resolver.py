# -*- coding: utf-8 -*-
"""
Sync Resolver
=============
Receives sync payloads on the slave side and resolves natural keys to
local records. Creates or updates records with change detection and
idempotency (duplicate payloads result in ``skip``).
"""

from odoo import models, api
from . import sync_model_registry
import json
import logging

_logger = logging.getLogger(__name__)


class SyncResolver(models.AbstractModel):
    _name = 'sync.resolver'
    _description = 'Sync Resolver'

    @api.model
    def resolve_natural_key(self, model_name, natural_key):
        """Find a local record by its natural key.

        :param model_name: e.g. ``'myschool.person'``
        :param natural_key: dict, e.g. ``{'sap_person_uuid': 'abc-123'}``
        :returns: recordset (empty if not found)
        """
        Model = self.env[model_name].sudo().with_context(active_test=False)
        domain = [(k, '=', v) for k, v in natural_key.items()]
        return Model.search(domain, limit=1)

    @api.model
    def _resolve_reference(self, ref_value):
        """Resolve a ``{"__ref": "model", "key": "value"}`` to a record id.

        Returns the id of the matched record, or ``False`` if not found.
        """
        if not ref_value or not isinstance(ref_value, dict) or '__ref' not in ref_value:
            return False

        ref_model = ref_value['__ref']
        # The remaining keys (excluding __ref) form the natural key
        lookup = {k: v for k, v in ref_value.items() if k != '__ref'}
        if not lookup:
            return False

        Model = self.env[ref_model].sudo().with_context(active_test=False)
        domain = [(k, '=', v) for k, v in lookup.items()]
        record = Model.search(domain, limit=1)
        if record:
            return record.id

        _logger.warning('Sync ref not found: %s %s', ref_model, lookup)
        return False

    @api.model
    def apply_payload(self, payload):
        """Apply a single sync payload on the slave.

        Returns a result dict::

            {
                'model': str,
                'natural_key': dict,
                'action': 'create' | 'update' | 'skip' | 'error',
                'success': bool,
                'error': str | None,
            }
        """
        model_name = payload.get('__model')
        natural_key = payload.get('__natural_key')

        if not model_name or not natural_key:
            return {
                'model': model_name,
                'natural_key': natural_key,
                'action': 'error',
                'success': False,
                'error': 'Missing __model or __natural_key',
            }

        registry_entry = sync_model_registry.get_registry_by_model(model_name)
        if not registry_entry:
            return {
                'model': model_name,
                'natural_key': natural_key,
                'action': 'error',
                'success': False,
                'error': f'Model {model_name} not in sync registry',
            }

        try:
            # Build write values from payload
            write_vals = self._build_write_vals(payload, registry_entry)

            # Find existing record
            existing = self.resolve_natural_key(model_name, natural_key)

            if existing:
                # Change detection — only write if something changed
                changes = self._detect_changes(existing, write_vals)
                if not changes:
                    return {
                        'model': model_name,
                        'natural_key': natural_key,
                        'action': 'skip',
                        'success': True,
                        'error': None,
                    }
                existing.with_context(skip_sync_event=True).write(changes)
                return {
                    'model': model_name,
                    'natural_key': natural_key,
                    'action': 'update',
                    'success': True,
                    'error': None,
                }
            else:
                # Include natural key fields in create vals
                for k, v in natural_key.items():
                    if k not in write_vals:
                        write_vals[k] = v
                # Mark as auto-synced
                if 'automatic_sync' in self.env[model_name]._fields:
                    write_vals['automatic_sync'] = True

                self.env[model_name].sudo().with_context(
                    skip_sync_event=True
                ).create(write_vals)
                return {
                    'model': model_name,
                    'natural_key': natural_key,
                    'action': 'create',
                    'success': True,
                    'error': None,
                }

        except Exception as e:
            _logger.exception('Error applying sync payload for %s', model_name)
            return {
                'model': model_name,
                'natural_key': natural_key,
                'action': 'error',
                'success': False,
                'error': str(e),
            }

    @api.model
    def _build_write_vals(self, payload, registry_entry):
        """Convert a payload dict into Odoo write values.

        Resolves ``__ref`` entries to local record IDs.
        Skips meta keys (``__model``, ``__natural_key``, ``__action``).
        """
        references = registry_entry.get('references', {})
        vals = {}

        for field_name in registry_entry['fields']:
            value = payload.get(field_name)
            if value is None:
                continue

            if field_name in references:
                vals[field_name] = self._resolve_reference(value)
            else:
                vals[field_name] = value

        return vals

    @api.model
    def _detect_changes(self, record, write_vals):
        """Compare write_vals against current record values.

        Returns only the keys/values that differ (for an efficient write),
        or an empty dict if nothing changed.
        """
        changes = {}
        for field_name, new_value in write_vals.items():
            current = getattr(record, field_name, None)

            # Many2one → compare by id
            if hasattr(current, 'id'):
                current = current.id if current else False

            # Datetime → compare as string
            if hasattr(current, 'isoformat'):
                current = current.isoformat()

            if current != new_value:
                changes[field_name] = new_value

        return changes

    @api.model
    def apply_payloads(self, payloads):
        """Apply a batch of payloads, sorted by model priority.

        Returns a list of result dicts.
        """
        # Sort by priority
        def _priority(p):
            entry = sync_model_registry.get_registry_by_model(p.get('__model', ''))
            return entry['priority'] if entry else 999

        sorted_payloads = sorted(payloads, key=_priority)

        results = []
        for payload in sorted_payloads:
            result = self.apply_payload(payload)
            results.append(result)
        return results
