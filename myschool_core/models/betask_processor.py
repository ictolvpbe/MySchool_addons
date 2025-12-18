# -*- coding: utf-8 -*-
"""
Backend Task Processor
Converted from BeTaskServiceProcessorImpl.java

This module provides the processing logic for backend tasks.
It processes tasks based on their type and executes the appropriate actions.

The processor can be triggered by:
- Cron job (scheduled action)
- Manual button click
- API call

Java Methods Implemented:
- ProcesBetasks(BeTaskType pTaskType) -> process_tasks_by_type(task_type)
- RegisterTaskSuccess(BeTask pTask) -> _register_task_success(task)
- RegisterTaskError(BeTask pTask) -> _register_task_error(task, error_msg)
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
import json
import traceback

_logger = logging.getLogger(__name__)


class BeTaskProcessor(models.AbstractModel):
    """
    Processor service for Backend Tasks
    Equivalent to BeTaskServiceProcessorImpl.java
    
    This class contains the main processing logic for backend tasks.
    Tasks are processed based on their type (target/object/action).
    
    Usage:
        processor = self.env['myschool.betask.processor']
        
        # Process all tasks of a type
        result = processor.process_tasks_by_type(task_type)
        
        # Process all pending tasks
        result = processor.process_all_pending()
        
        # Process single task
        result = processor.process_single_task(task)
    """
    _name = 'myschool.betask.processor'
    _description = 'Backend Task Processor'
    
    # =========================================================================
    # Task Registration Methods
    # =========================================================================
    
    @api.model
    def _register_task_success(self, task, result_data=None):
        """
        Mark task as successfully completed
        Equivalent to: RegisterTaskSuccess(BeTask pTask)
        
        :param task: Task record
        :param result_data: Optional result data to store
        :return: True
        """
        task.action_set_completed(result_data)
        _logger.info(f'Task {task.name} completed successfully')
        return True
    
    @api.model
    def _register_task_error(self, task, error_msg=None):
        """
        Mark task as failed
        Equivalent to: RegisterTaskError(BeTask pTask)
        
        :param task: Task record
        :param error_msg: Error message to store
        :return: False
        """
        task.action_set_error(error_msg)
        _logger.error(f'Task {task.name} failed: {error_msg}')
        return False
    
    # =========================================================================
    # Main Processing Methods
    # =========================================================================
    
    @api.model
    def process_tasks_by_type(self, task_type):
        """
        Process all pending tasks of a specific type
        Equivalent to: ProcesBetasks(BeTaskType pTaskType)
        
        :param task_type: Task type record
        :return: True if all tasks processed successfully, False if any error
        """
        if not task_type:
            self._log_error('BETASK-900', 'No task type specified for processing')
            return False
        
        # Log start
        self._log_event('BETASK-002', f'START PROCESSING TASKS: {task_type.name}')
        
        # Check for manual tasks that should be processed first
        manual_tasks = self._check_manual_tasks()
        if manual_tasks:
            self._log_error(
                'BETASK-003',
                f'Found {len(manual_tasks)} manual tasks. Please process them first!'
            )
            # Continue anyway, just warn
        
        # Get tasks to process
        task_service = self.env['myschool.betask.service']
        tasks_to_process = task_service.find_by_type_and_status(task_type, 'new')
        
        if not tasks_to_process:
            _logger.info(f'No pending tasks found for type: {task_type.name}')
            return True
        
        _logger.info(f'Found {len(tasks_to_process)} tasks to process for type: {task_type.name}')
        
        all_success = True
        processed_count = 0
        error_count = 0
        
        for task in tasks_to_process:
            try:
                result = self.process_single_task(task)
                if result:
                    processed_count += 1
                else:
                    error_count += 1
                    all_success = False
            except Exception as e:
                error_count += 1
                all_success = False
                self._register_task_error(task, str(e))
                _logger.exception(f'Exception processing task {task.name}')
        
        # Log completion
        self._log_event(
            'BETASK-004',
            f'COMPLETED PROCESSING {task_type.name}: {processed_count} success, {error_count} errors'
        )
        
        return all_success
    
    @api.model
    def process_single_task(self, task):
        """
        Process a single task
        
        :param task: Task record
        :return: True if successful, False if error
        """
        if not task:
            return False
        
        if task.status not in ['new', 'error']:
            _logger.warning(f'Task {task.name} is not in processable status: {task.status}')
            return False
        
        # Mark as processing
        task.action_set_processing()
        
        try:
            # Get the processor method name from task type
            processor_method = task.betasktype_id.processor_method
            
            if processor_method and hasattr(self, processor_method):
                # Call the specific processor method
                method = getattr(self, processor_method)
                result = method(task)
            else:
                # Use generic processor based on target/object/action
                result = self._process_task_generic(task)
            
            if result:
                return self._register_task_success(task)
            else:
                return self._register_task_error(task, 'Processing returned False')
                
        except Exception as e:
            error_msg = f'{str(e)}\n{traceback.format_exc()}'
            self._log_error(
                'BETASK-500',
                f'Error processing task {task.name}: {error_msg}'
            )
            return self._register_task_error(task, str(e))
    
    @api.model
    def process_all_pending(self):
        """
        Process all pending tasks for all auto-process task types
        Called by cron job
        
        :return: Dictionary with processing results
        """
        self._log_event('BETASK-001', 'START PROCESSING ALL PENDING TASKS')
        
        # Get all auto-process task types, ordered by priority
        type_service = self.env['myschool.betask.type.service']
        task_types = type_service.find_auto_process_types()
        
        results = {
            'total_types': len(task_types),
            'processed_types': 0,
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
        }
        
        for task_type in task_types:
            # Get pending tasks for this type
            task_service = self.env['myschool.betask.service']
            pending_tasks = task_service.find_by_type_and_status(task_type, 'new')
            
            if pending_tasks:
                results['total_tasks'] += len(pending_tasks)
                
                for task in pending_tasks:
                    try:
                        if self.process_single_task(task):
                            results['successful_tasks'] += 1
                        else:
                            results['failed_tasks'] += 1
                    except Exception as e:
                        results['failed_tasks'] += 1
                        _logger.exception(f'Exception processing task {task.name}')
                
                results['processed_types'] += 1
        
        # Log completion
        self._log_event(
            'BETASK-005',
            f'COMPLETED ALL PENDING: {results["successful_tasks"]} success, {results["failed_tasks"]} errors'
        )
        
        return results
    
    # =========================================================================
    # Generic Task Processor
    # =========================================================================
    
    @api.model
    def _process_task_generic(self, task):
        """
        Generic task processor - routes to specific handlers based on type
        
        :param task: Task record
        :return: True if successful, False if error
        """
        target = task.betasktype_id.target
        obj = task.betasktype_id.object
        action = task.betasktype_id.action
        
        _logger.info(f'Processing task {task.name}: {target}_{obj}_{action}')
        
        # Parse task data
        data = self._parse_task_data(task.data)
        data2 = self._parse_task_data(task.data2)
        
        # Route to appropriate handler
        # This is where you would add specific processing logic
        # For now, we just log and return True (placeholder)
        
        _logger.info(f'Task {task.name} processed (generic handler)')
        _logger.debug(f'Data: {data}')
        _logger.debug(f'Data2: {data2}')
        
        # TODO: Implement specific handlers for each task type
        # Example:
        # if target == 'DB' and obj == 'ORG' and action == 'ADD':
        #     return self._process_db_org_add(task, data, data2)
        
        return True
    
    @api.model
    def _parse_task_data(self, data_str):
        """
        Parse task data from string (usually JSON)
        
        :param data_str: Data string
        :return: Parsed data (dict if JSON, otherwise string)
        """
        if not data_str:
            return None
        
        try:
            return json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            return data_str
    
    # =========================================================================
    # Specific Task Processors (to be extended)
    # These methods correspond to the Java ProcessTask* methods
    # =========================================================================
    
    @api.model
    def process_db_org_add(self, task):
        """
        Process DB ORG ADD task
        Equivalent to: ProcessTaskDbOrgAdd
        """
        _logger.info(f'Processing DB_ORG_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement organization creation logic
        # Example:
        # org_vals = {...}
        # self.env['myschool.org'].create(org_vals)
        
        return True
    
    @api.model
    def process_db_org_update(self, task):
        """
        Process DB ORG UPDATE task
        """
        _logger.info(f'Processing DB_ORG_UPDATE: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement organization update logic
        
        return True
    
    @api.model
    def process_db_student_add(self, task):
        """
        Process DB STUDENT ADD task
        Equivalent to: ProcessTaskDbStudentAdd
        """
        _logger.info(f'Processing DB_STUDENT_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement student creation logic
        
        return True
    
    @api.model
    def process_db_employee_add(self, task):
        """
        Process DB EMPLOYEE ADD task
        Equivalent to: ProcessTaskDbEmployeeAdd
        """
        _logger.info(f'Processing DB_EMPLOYEE_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement employee creation logic
        
        return True
    
    @api.model
    def process_db_role_add(self, task):
        """
        Process DB ROLE ADD task
        Equivalent to: ProcessTaskDbRoleAdd
        """
        _logger.info(f'Processing DB_ROLE_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement role creation logic
        
        return True
    
    @api.model
    def process_ldap_org_add(self, task):
        """
        Process LDAP ORG ADD task
        Equivalent to: ProcessTaskLdapOrgAdd
        """
        _logger.info(f'Processing LDAP_ORG_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement LDAP organization creation logic
        
        return True
    
    @api.model
    def process_ldap_employee_add(self, task):
        """
        Process LDAP EMPLOYEE ADD task
        Equivalent to: ProcessTaskLdapEmployeeAdd
        """
        _logger.info(f'Processing LDAP_EMPLOYEE_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        
        # TODO: Implement LDAP employee creation logic
        
        return True
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    @api.model
    def _check_manual_tasks(self):
        """
        Check for pending manual tasks
        
        :return: Recordset of pending manual tasks
        """
        task_service = self.env['myschool.betask.service']
        return task_service.find_manual_tasks()
    
    @api.model
    def _log_event(self, code, message):
        """
        Log event to SysEvent
        """
        try:
            sys_event_service = self.env['myschool.sys.event.service']
            sys_event_service.create_sys_event(
                code=code,
                data=message,
                log_to_screen=True,
                source='BE'
            )
        except Exception:
            _logger.info(f'SysEvent [{code}]: {message}')
    
    @api.model
    def _log_error(self, code, message, blocking=False):
        """
        Log error to SysEvent
        """
        try:
            sys_event_service = self.env['myschool.sys.event.service']
            error_type = 'ERROR-BLOCKING' if blocking else 'ERROR-NONBLOCKING'
            sys_event_service.create_sys_error(
                code=code,
                data=message,
                error_type=error_type,
                log_to_screen=True,
                source='BE'
            )
        except Exception:
            _logger.error(f'SysError [{code}]: {message}')
    
    # =========================================================================
    # Cron Job Entry Point
    # =========================================================================
    
    @api.model
    def cron_process_tasks(self):
        """
        Entry point for scheduled task processing
        Called by ir.cron
        """
        _logger.info('Cron job started: Processing backend tasks')
        
        try:
            results = self.process_all_pending()
            _logger.info(f'Cron job completed: {results}')
            return results
        except Exception as e:
            _logger.exception('Cron job failed')
            self._log_error('BETASK-999', f'Cron job failed: {str(e)}', blocking=True)
            return False
