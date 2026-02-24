# -*- coding: utf-8 -*-
"""
Manual Task Service
===================
Service layer that wizards and object_browser call instead of direct ORM.
Creates MANUAL betasks and either processes them immediately or queues them
for later batch processing.

Processing modes (controlled by system parameter 'myschool.manual_task_mode'):
- 'immediate' (default): Creates task → processes it in the same request
- 'queued': Creates task with automatic_sync=False → stays 'new' until batch processed
"""

from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ManualTaskService(models.AbstractModel):
    _name = 'myschool.manual.task.service'
    _description = 'Manual Task Service'

    @api.model
    def _get_mode(self):
        """Get the current manual task processing mode."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'myschool.manual_task_mode', 'immediate')

    @api.model
    def create_manual_task(self, obj, action, data):
        """Create a MANUAL betask and optionally process it immediately.

        Args:
            obj: Object type (PERSON, ORG, PROPRELATION, etc.)
            action: Action type (ADD, UPD, DEL, DEACT)
            data: Dict with operation data (will be JSON-serialized)

        Returns:
            The created betask record.

        Raises:
            UserError: If immediate processing fails.
        """
        service = self.env['myschool.betask.service']
        mode = self._get_mode()

        task = service.create_task(
            'MANUAL', obj, action,
            data=data,
            auto_sync=(mode == 'immediate'),
        )

        if mode == 'immediate':
            processor = self.env['myschool.betask.processor']
            processor.process_single_task(task)
            if task.status == 'error':
                raise UserError(
                    _('Operation failed: %s') % (task.error_description or 'Unknown error'))

        return task

    @api.model
    def process_pending_manual_tasks(self):
        """Process all queued manual tasks (called from UI button).

        Returns:
            Dict with 'ok' and 'error' counts.
        """
        tasks = self.env['myschool.betask.service'].find_manual_tasks()
        processor = self.env['myschool.betask.processor']
        results = {'ok': 0, 'error': 0}

        for task in tasks:
            processor.process_single_task(task)
            if task.status == 'completed_ok':
                results['ok'] += 1
            else:
                results['error'] += 1

        _logger.info(
            'Processed %d manual tasks: %d ok, %d errors',
            results['ok'] + results['error'], results['ok'], results['error'])

        return results
