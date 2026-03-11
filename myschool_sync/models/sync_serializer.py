# -*- coding: utf-8 -*-
"""
Sync Serializer
===============
Converts Odoo records to JSON-serializable payloads for sync transport.
Many2one fields are resolved to ``{"__ref": "model", "key": "value"}``
references so the receiver can match by natural key.
"""

from odoo import models, api, fields as odoo_fields
from . import sync_model_registry
import logging

_logger = logging.getLogger(__name__)


class SyncSerializer(models.AbstractModel):
    _name = 'sync.serializer'
    _description = 'Sync Serializer'

    @api.model
    def serialize_record(self, record, registry_entry=None):
        """Serialize a single Odoo record to a sync payload dict.

        Returns a dict like::

            {
                "__model": "myschool.person",
                "__natural_key": {"sap_person_uuid": "abc-123"},
                "__action": "sync",
                "name": "Demeyer, Jan",
                "person_type_id": {"__ref": "myschool.person.type", "name": "EMPLOYEE"},
                "is_active": true,
            }
        """
        if not registry_entry:
            registry_entry = sync_model_registry.get_registry_by_model(record._name)
        if not registry_entry:
            _logger.warning('No sync registry entry for model %s', record._name)
            return None

        payload = {
            '__model': record._name,
            '__action': 'sync',
        }

        # Natural key
        natural_key = {}
        for key_field in registry_entry['natural_key']:
            value = getattr(record, key_field, None)
            if isinstance(value, odoo_fields.Datetime):
                value = str(value)
            natural_key[key_field] = value
        payload['__natural_key'] = natural_key

        # Syncable fields
        references = registry_entry.get('references', {})
        for field_name in registry_entry['fields']:
            if field_name in references:
                # Many2one → __ref
                ref_config = references[field_name]
                related_record = getattr(record, field_name, None)
                if related_record:
                    key_field = ref_config['key_field']
                    key_value = getattr(related_record, key_field, None)
                    payload[field_name] = {
                        '__ref': ref_config['model'],
                        key_field: key_value,
                    }
                else:
                    payload[field_name] = False
            else:
                value = getattr(record, field_name, None)
                # Convert Odoo-specific types to JSON-safe values
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                payload[field_name] = value

        return payload

    @api.model
    def serialize_records(self, records, registry_entry=None):
        """Serialize multiple records, returning a list of payloads."""
        result = []
        for record in records:
            payload = self.serialize_record(record, registry_entry)
            if payload:
                result.append(payload)
        return result
