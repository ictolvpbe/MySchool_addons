# -*- coding: utf-8 -*-
"""
Sync Processor
==============
Extends ``myschool.betask.processor`` with handlers for ``(API, *, SYNC)``
betask tuples. Each handler deserializes the task data, dispatches the
payloads to the sync targets, and logs the results.
"""

from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class SyncProcessor(models.AbstractModel):
    _inherit = 'myschool.betask.processor'

    @api.model
    def _process_task_generic(self, task):
        target = task.betasktype_id.target
        action = task.betasktype_id.action

        if target == 'API' and action == 'SYNC':
            return self._process_sync_task(task)

        return super()._process_task_generic(task)

    # ------------------------------------------------------------------
    # Unified sync handler
    # ------------------------------------------------------------------

    @api.model
    def _process_sync_task(self, task):
        """Process an API_*_SYNC betask.

        The task data is a JSON dict with::

            {
                "sync_target_id": 123,        # optional — specific target
                "payloads": [{...}, ...],      # list of sync payloads
            }

        If ``sync_target_id`` is set, send only to that target.
        Otherwise dispatch to all active targets.
        """
        data = self._parse_task_data(task.data)
        if not data or not isinstance(data, dict):
            return {'success': False, 'error': 'Invalid or empty task data'}

        payloads = data.get('payloads', [])
        if not payloads:
            return {'success': False, 'error': 'No payloads in task data'}

        sync_role = self.env['ir.config_parameter'].sudo().get_param(
            'myschool.sync_role', 'disabled'
        )
        if sync_role not in ('master', 'both'):
            return {'success': True, 'changes': 'Sync role is not master — skipped'}

        dispatcher = self.env['sync.dispatcher']
        sync_log = self.env['sync.log']
        changes = []

        target_id = data.get('sync_target_id')
        if target_id:
            target = self.env['sync.target'].sudo().browse(target_id).exists()
            if not target or not target.is_active:
                return {'success': False, 'error': f'Target {target_id} not found or inactive'}
            dispatch_results = [(target, dispatcher.dispatch_to_target(target, payloads))]
        else:
            dispatch_results = dispatcher.dispatch_to_all_targets(payloads)

        all_success = True
        for target, result in dispatch_results:
            if result.get('success'):
                target.sudo().write({
                    'last_sync_date': fields.Datetime.now(),
                    'last_error': False,
                    'consecutive_errors': 0,
                })
                changes.append(f'{target.name}: {result.get("success_count", 0)} OK')
            else:
                all_success = False
                error_msg = result.get('error', 'Unknown error')
                target.sudo().write({
                    'last_error': error_msg,
                    'consecutive_errors': target.consecutive_errors + 1,
                })
                changes.append(f'{target.name}: FAILED — {error_msg}')

            # Log each payload result
            for payload in payloads:
                nk = payload.get('__natural_key', {})
                model = payload.get('__model', '')
                sync_log.log_event(
                    model_name=model,
                    natural_key=nk,
                    action='update' if result.get('success') else 'error',
                    direction='outbound',
                    sync_target=target,
                    payload=payload,
                    success=result.get('success', False),
                    error_message=result.get('error'),
                    betask=task,
                )

        return {
            'success': all_success,
            'changes': '\n'.join(changes),
        }
