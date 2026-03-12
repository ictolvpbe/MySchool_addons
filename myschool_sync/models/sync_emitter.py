# -*- coding: utf-8 -*-
"""
Sync Emitter
============
Extends ``_register_task_success()`` to create follow-up ``API_*_SYNC``
betasks when a DB or MANUAL betask completes on a master instance.

The emitter is best-effort: if creating the sync betask fails it is
logged but does not fail the original task.
"""

from odoo import models, api
from . import sync_model_registry
import json
import logging

_logger = logging.getLogger(__name__)

# Maps (target, object) of completed betasks to the sync betask object
# to create. The action is always SYNC on the API target.
EMITTER_MAP = {
    # DB person tasks
    ('DB', 'PERSON'):       'PERSON',
    ('DB', 'EMPLOYEE'):     'PERSON',
    ('DB', 'STUDENT'):      'PERSON',
    # DB org tasks
    ('DB', 'ORG'):          'ORG',
    # DB role tasks
    ('DB', 'ROLE'):         'ROLE',
    # DB proprelation tasks
    ('DB', 'PROPRELATION'): 'PROPRELATION',
    ('DB', 'RELATION'):     'PROPRELATION',
    # Manual tasks
    ('MANUAL', 'PERSON'):       'PERSON',
    ('MANUAL', 'ORG'):          'ORG',
    ('MANUAL', 'PROPRELATION'): 'PROPRELATION',
}


class SyncEmitter(models.AbstractModel):
    _inherit = 'myschool.betask.processor'

    @api.model
    def _register_task_success(self, task, result_data=None, changes=None):
        """After a task completes, optionally emit a sync betask."""
        result = super()._register_task_success(task, result_data=result_data, changes=changes)

        try:
            self._maybe_emit_sync_task(task)
        except Exception:
            _logger.exception('Sync emitter failed for task %s (non-fatal)', task.name)

        return result

    @api.model
    def _maybe_emit_sync_task(self, task):
        """Create an API_*_SYNC betask if this task type triggers sync."""
        sync_role = self.env['ir.config_parameter'].sudo().get_param(
            'myschool.sync_role', 'disabled'
        )
        if sync_role not in ('master', 'both'):
            return

        # Skip if the completed task is itself a sync task
        if task.betasktype_id.target == 'API' and task.betasktype_id.action == 'SYNC':
            return

        bt_target = task.betasktype_id.target
        bt_object = task.betasktype_id.object
        sync_object = EMITTER_MAP.get((bt_target, bt_object))
        if not sync_object:
            return

        # Try to reconstruct the payload from the completed task data
        payloads = self._build_sync_payloads(task, sync_object)
        if not payloads:
            return

        betask_service = self.env['myschool.betask.service']
        data = json.dumps({'payloads': payloads})
        betask_service.create_task('API', sync_object, 'SYNC', data=data)
        _logger.info(
            'Emitted API_%s_SYNC betask after %s completed',
            sync_object, task.name,
        )

    @api.model
    def _build_sync_payloads(self, task, sync_object):
        """Attempt to build sync payloads from the completed task's data.

        The task data is typically a JSON dict with record identifiers.
        We look up the actual record and serialize it.
        """
        data = self._parse_task_data(task.data)
        if not data or not isinstance(data, dict):
            return []

        serializer = self.env['sync.serializer']
        entries = sync_model_registry.get_registry_by_betask_object(sync_object)
        if not entries:
            return []

        payloads = []

        # Determine which record was affected based on known data keys
        record = self._find_affected_record(data, sync_object)
        if record:
            # Find matching registry entry
            entry = sync_model_registry.get_registry_by_model(record._name)
            if entry:
                payload = serializer.serialize_record(record, entry)
                if payload:
                    payloads.append(payload)

        return payloads

    @api.model
    def _find_affected_record(self, data, sync_object):
        """Find the record affected by a completed task, based on task data."""
        if sync_object == 'PERSON':
            return self._find_person_from_data(data)
        elif sync_object == 'ORG':
            return self._find_org_from_data(data)
        elif sync_object == 'PROPRELATION':
            return self._find_proprelation_from_data(data)
        elif sync_object == 'ROLE':
            return self._find_role_from_data(data)
        return None

    @api.model
    def _find_person_from_data(self, data):
        Person = self.env['myschool.person'].sudo().with_context(active_test=False)
        # DB tasks use sap_person_uuid or sap_ref
        if data.get('sap_person_uuid'):
            return Person.search([('sap_person_uuid', '=', data['sap_person_uuid'])], limit=1)
        if data.get('sap_ref'):
            return Person.search([('sap_ref', '=', data['sap_ref'])], limit=1)
        # MANUAL tasks use person_id
        if data.get('person_id'):
            return Person.browse(data['person_id']).exists()
        return None

    @api.model
    def _find_org_from_data(self, data):
        Org = self.env['myschool.org'].sudo().with_context(active_test=False)
        if data.get('org_id'):
            return Org.browse(data['org_id']).exists()
        if data.get('existing_org_id'):
            return Org.browse(data['existing_org_id']).exists()
        return None

    @api.model
    def _find_proprelation_from_data(self, data):
        PR = self.env['myschool.proprelation'].sudo().with_context(active_test=False)
        if data.get('proprelation_id'):
            return PR.browse(data['proprelation_id']).exists()
        return None

    @api.model
    def _find_role_from_data(self, data):
        Role = self.env['myschool.role'].sudo().with_context(active_test=False)
        if data.get('shortname'):
            return Role.search([('shortname', '=', data['shortname'])], limit=1)
        return None
