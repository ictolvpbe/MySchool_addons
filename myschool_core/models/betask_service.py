# -*- coding: utf-8 -*-
"""
Backend Task Service
Converted from BeTaskServiceImpl.java

This module provides the service layer for managing backend tasks.

Java Methods Implemented:
- findById(String id) -> find_by_id(task_id)
- findByTypeAndStatus(BeTaskType type, BeTaskStatus status) -> find_by_type_and_status(type, status)
- findAll() -> find_all()
- registerOrUpdateBeTask(BeTask beTask) -> register_or_update(vals)
- createBeTask(pTarget, pObj, pAction, pData1, pData2) -> create_task(target, obj, action, data, data2)
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import json

_logger = logging.getLogger(__name__)


class BeTaskService(models.AbstractModel):
    """
    Service class for Backend Task operations
    Equivalent to BeTaskServiceImpl.java + BeTaskDao.java
    
    Usage:
        service = self.env['myschool.betask.service']
        
        # Create a task
        task = service.create_task('DB', 'ORG', 'ADD', json_data, None)
        
        # Find tasks by type and status
        tasks = service.find_by_type_and_status(task_type, 'new')
    """
    _name = 'myschool.betask.service'
    _description = 'Backend Task Service'
    
    # =========================================================================
    # DAO Methods (from BeTaskDao.java)
    # =========================================================================
    
    @api.model
    def find_by_id(self, task_id):
        """
        Find task by ID
        Equivalent to: findBeTaskById(String id)
        
        :param task_id: Task ID
        :return: Task record or empty recordset
        """
        if not task_id:
            return self.env['myschool.betask']
        return self.env['myschool.betask'].browse(task_id).exists()
    
    @api.model
    def find_by_type_and_status(self, task_type, status):
        """
        Find tasks by type and status
        Equivalent to: findBeTasksByBetasktypeAndStatus(BeTaskType type, BeTaskStatus status)
        
        :param task_type: Task type record, ID, or name string
        :param status: Status string ('new', 'processing', 'completed_ok', 'error')
        :return: Recordset of matching tasks
        """
        domain = []
        
        # Handle task_type parameter
        if task_type:
            if isinstance(task_type, str):
                # Find by name
                type_service = self.env['myschool.betask.type.service']
                type_record = type_service.find_by_name(task_type)
                if type_record:
                    domain.append(('betasktype_id', '=', type_record.id))
            elif isinstance(task_type, int):
                domain.append(('betasktype_id', '=', task_type))
            elif hasattr(task_type, 'id'):
                domain.append(('betasktype_id', '=', task_type.id))
        
        # Handle status parameter
        if status:
            domain.append(('status', '=', status))
        
        return self.env['myschool.betask'].search(domain)
    
    @api.model
    def find_by_data_and_status(self, data, status):
        """
        Find tasks by data content and status
        Equivalent to: findBeTasksByDataAndStatus(String pData, BeTaskStatus status)
        
        :param data: Data content to search for
        :param status: Status string
        :return: Recordset of matching tasks
        """
        domain = []
        if data:
            domain.append(('data', 'ilike', data))
        if status:
            domain.append(('status', '=', status))
        
        return self.env['myschool.betask'].search(domain)
    
    @api.model
    def find_by_action_and_status(self, action, status):
        """
        Find tasks by action and status
        Equivalent to: findBeTasksByBetasktype_ActionAndStatus(String action, BeTaskStatus status)
        
        :param action: Action type (ADD, UPD, DEL, etc.)
        :param status: Status string
        :return: Recordset of matching tasks
        """
        domain = []
        if action:
            domain.append(('action', '=', action))
        if status:
            domain.append(('status', '=', status))
        
        return self.env['myschool.betask'].search(domain)
    
    @api.model
    def find_all(self):
        """
        Find all tasks
        Equivalent to: findAll()
        
        :return: Recordset of all tasks
        """
        return self.env['myschool.betask'].search([])
    
    @api.model
    def find_pending(self):
        """
        Find all pending (new) tasks
        
        :return: Recordset of pending tasks
        """
        return self.env['myschool.betask'].search([
            ('status', '=', 'new'),
            ('automatic_sync', '=', True)
        ])
    
    @api.model
    def find_errors(self):
        """
        Find all tasks in error status
        
        :return: Recordset of error tasks
        """
        return self.env['myschool.betask'].search([('status', '=', 'error')])
    
    @api.model
    def find_manual_tasks(self):
        """
        Find manual tasks that need attention
        
        :return: Recordset of manual tasks
        """
        return self.env['myschool.betask'].search([
            ('action', '=', 'MANUAL'),
            ('status', '=', 'new')
        ])
    
    # =========================================================================
    # Service Methods (from BeTaskServiceImpl.java)
    # =========================================================================
    
    @api.model
    def register_or_update(self, vals):
        """
        Register a new task or update existing one
        Equivalent to: registerOrUpdateBeTask(BeTask beTask)
        
        :param vals: Dictionary with task values or task record
        :return: Task record
        """
        BeTask = self.env['myschool.betask']
        
        if isinstance(vals, models.BaseModel):
            return vals
        
        if not isinstance(vals, dict):
            raise ValidationError(_('Invalid task data provided'))
        
        # If ID is provided, update existing
        if vals.get('id'):
            existing = BeTask.browse(vals['id']).exists()
            if existing:
                update_vals = {k: v for k, v in vals.items() if k != 'id'}
                existing.write(update_vals)
                return existing
        
        # Create new
        return BeTask.create(vals)
    
    @api.model
    def create_task(self, target, obj, action, data=None, data2=None, auto_sync=True):
        """
        Create a backend task
        Equivalent to: createBeTask(String pTarget, String pObj, String pAction, String pData1, String pData2)
        
        This is the main method for creating backend tasks.
        
        :param target: Target system (DB, AD, CLOUD, etc.)
        :param obj: Object type (ORG, PERSON, ROLE, etc.)
        :param action: Action (ADD, UPD, DEL, etc.)
        :param data: Primary data (usually JSON string)
        :param data2: Secondary data
        :param auto_sync: Whether to auto-process (default True)
        :return: Created task record
        
        Example:
            service = self.env['myschool.betask.service']
            task = service.create_task(
                'DB', 'ORG', 'ADD',
                data='{"name": "New School", "code": "SCH001"}',
                data2=None
            )
        """
        try:
            # Find the task type
            type_service = self.env['myschool.betask.type.service']
            task_type = type_service.find_by_target_object_action(target, obj, action)
            
            if not task_type:
                # Auto-create task type if it doesn't exist
                _logger.warning(f'Task type not found, creating: {target}_{obj}_{action}')
                task_type = type_service.create_task_type(target, obj, action)
            
            # Prepare data - convert dict to JSON string if needed
            if isinstance(data, dict):
                data = json.dumps(data)
            if isinstance(data2, dict):
                data2 = json.dumps(data2)
            
            # Create the task
            task_vals = {
                'betasktype_id': task_type.id,
                'status': 'new',
                'data': data,
                'data2': data2,
                'automatic_sync': auto_sync,
            }
            
            task = self.env['myschool.betask'].create(task_vals)
            
            _logger.info(f'BeTask created: [{task.name}] {task_type.name}')
            
            # Log to SysEvent
            try:
                sys_event_service = self.env['myschool.sys.event.service']
                sys_event_service.create_sys_event(
                    code='BETASK_CREATED',
                    data=f'Task {task.name} created: {task_type.name}',
                    log_to_screen=False,
                    source='BE'
                )
            except Exception:
                pass  # SysEvent logging is optional
            
            return task
            
        except Exception as e:
            _logger.exception(f"Error creating task: {target}_{obj}_{action}")
            
            # Try to log error to SysEvent
            try:
                sys_event_service = self.env['myschool.sys.event.service']
                sys_event_service.create_sys_error(
                    code='BETASK_CREATE_ERROR',
                    data=f'Failed to create task {target}_{obj}_{action}: {str(e)}',
                    error_type='ERROR-NONBLOCKING',
                    log_to_screen=True
                )
            except Exception:
                pass
            
            raise ValidationError(_('Failed to create task: %s') % str(e))
    
    @api.model
    def create_task_from_type(self, task_type, data=None, data2=None, auto_sync=True):
        """
        Create a task from an existing task type
        
        :param task_type: Task type record or ID
        :param data: Primary data
        :param data2: Secondary data
        :param auto_sync: Whether to auto-process
        :return: Created task record
        """
        if isinstance(task_type, int):
            task_type = self.env['myschool.betask.type'].browse(task_type)
        
        if not task_type:
            raise ValidationError(_('Invalid task type'))
        
        # Prepare data
        if isinstance(data, dict):
            data = json.dumps(data)
        if isinstance(data2, dict):
            data2 = json.dumps(data2)
        
        task_vals = {
            'betasktype_id': task_type.id,
            'status': 'new',
            'data': data,
            'data2': data2,
            'automatic_sync': auto_sync,
        }
        
        task = self.env['myschool.betask'].create(task_vals)
        _logger.info(f'BeTask created: [{task.name}] {task_type.name}')
        
        return task
    
    # =========================================================================
    # Bulk Operations
    # =========================================================================
    
    @api.model
    def reset_error_tasks(self, task_type=None):
        """
        Reset all error tasks to new status
        
        :param task_type: Optional task type to filter
        :return: Number of tasks reset
        """
        domain = [('status', '=', 'error')]
        if task_type:
            if isinstance(task_type, int):
                domain.append(('betasktype_id', '=', task_type))
            elif hasattr(task_type, 'id'):
                domain.append(('betasktype_id', '=', task_type.id))
        
        error_tasks = self.env['myschool.betask'].search(domain)
        
        reset_count = 0
        for task in error_tasks:
            if task.retry_count < task.max_retries:
                task.action_reset_to_new()
                reset_count += 1
        
        _logger.info(f'Reset {reset_count} error tasks to new status')
        return reset_count
    
    @api.model
    def cancel_pending_tasks(self, task_type=None):
        """
        Cancel all pending tasks (set to archived)
        
        :param task_type: Optional task type to filter
        :return: Number of tasks cancelled
        """
        domain = [('status', '=', 'new')]
        if task_type:
            if isinstance(task_type, int):
                domain.append(('betasktype_id', '=', task_type))
            elif hasattr(task_type, 'id'):
                domain.append(('betasktype_id', '=', task_type.id))
        
        pending_tasks = self.env['myschool.betask'].search(domain)
        pending_tasks.write({'active': False})
        
        _logger.info(f'Cancelled {len(pending_tasks)} pending tasks')
        return len(pending_tasks)
    
    @api.model
    def get_task_statistics(self):
        """
        Get statistics about backend tasks
        
        :return: Dictionary with task statistics
        """
        BeTask = self.env['myschool.betask']
        return {
            'total': BeTask.search_count([]),
            'new': BeTask.search_count([('status', '=', 'new')]),
            'processing': BeTask.search_count([('status', '=', 'processing')]),
            'completed': BeTask.search_count([('status', '=', 'completed_ok')]),
            'error': BeTask.search_count([('status', '=', 'error')]),
            'manual_pending': BeTask.search_count([
                ('action', '=', 'MANUAL'),
                ('status', '=', 'new')
            ]),
        }
