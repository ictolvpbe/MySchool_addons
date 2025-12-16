# -*- coding: utf-8 -*-
"""
System Event Logic
Converted from SysEventServiceImpl.java

This module contains business logic for managing system events.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SysEventLogic(models.AbstractModel):
    """
    Logic class for System Event operations
    Equivalent to SysEventServiceImpl.java
    """
    _name = 'myschool.sys.event.logic'
    _description = 'System Event Logic'
    
    @api.model
    def find_by_id(self, event_id):
        """
        Find event by ID
        Equivalent to: findById(String id)
        
        :param event_id: Event ID
        :return: Event record or empty recordset
        """
        return self.env['myschool.sys.event'].browse(event_id)
    
    @api.model
    def find_by_type_and_status(self, event_type, status):
        """
        Find events by type and status
        Equivalent to: findByTypeAndStatus(SysEventType type, String status)
        
        :param event_type: Event type record or ID
        :param status: Status string ('NEW', 'PROCESS', 'PRO_ERROR', 'CLOSED')
        :return: Recordset of matching events
        """
        if isinstance(event_type, int):
            type_id = event_type
        else:
            type_id = event_type.id if event_type else False
        
        domain = []
        if type_id:
            domain.append(('syseventtype_id', '=', type_id))
        if status:
            domain.append(('status', '=', status))
        
        return self.env['myschool.sys.event'].search(domain)
    
    @api.model
    def find_all(self):
        """
        Find all events
        Equivalent to: findAll()
        
        :return: Recordset of all events
        """
        return self.env['myschool.sys.event'].search([])
    
    @api.model
    def register_or_update_sys_event(self, event_vals):
        """
        Register a new event or update an existing one
        Equivalent to: registerOrUpdateSysEvent(SysEvent sysEvent)
        
        :param event_vals: Dictionary of event values or event record
        :return: Event record
        """
        if isinstance(event_vals, dict):
            # If it's a dict, create new event or update existing
            if 'id' in event_vals and event_vals['id']:
                # Update existing
                event = self.env['myschool.sys.event'].browse(event_vals['id'])
                event.write(event_vals)
                return event
            else:
                # Create new
                return self.env['myschool.sys.event'].create(event_vals)
        elif isinstance(event_vals, type(self.env['myschool.sys.event'])):
            # If it's already a record, just return it
            return event_vals
        else:
            raise ValidationError(_('Invalid event data provided'))
    
    @api.model
    def create_sys_event(self, event_code, data, log_to_screen=False, source='BE'):
        """
        Creates an event in the SysEvent table and shows it on screen if log_to_screen is true
        Equivalent to: createSysEvent(String pCode, String pData, Boolean pLogtoscreen)
        
        :param event_code: Event code
        :param data: Event details/data
        :param log_to_screen: If True, log event creation (uses Odoo logger)
        :param source: Source system (default: 'BE')
        :return: Created event record
        """
        try:
            # Find or create the EVENT type
            event_type = self.env['myschool.sys.event.type.logic'].get_or_create_type(
                'EVENT',
                'EVENT',
                'General system event'
            )
            
            # Create the event
            event_vals = {
                'eventcode': event_code,
                'status': 'NEW',
                'syseventtype_id': event_type.id,
                'priority': '3',  # Low priority for general events
                'data': data,
                'source': source,
            }
            
            event = self.env['myschool.sys.event'].create(event_vals)
            
            # Logging
            if log_to_screen:
                _logger.debug('SysEvent added: %s - %s', event.syseventtype_id.name, event.data)
            
            _logger.info('SysEvent added: %s - %s', event.syseventtype_id.name, event.data)
            
            return event
            
        except Exception as e:
            _logger.exception("Error creating sys event")
            # Create error event (recursive call protection)
            if event_code != 'SYSEVENT-900':
                self.create_sys_error('SYSEVENT-900', str(e), 'ERROR-NONBLOCKING', True)
            return self.env['myschool.sys.event'].browse()  # Return empty recordset
    
    @api.model
    def create_sys_error(self, error_code, error_data, error_type='ERROR-NONBLOCKING', 
                        log_to_screen=False, source='BE'):
        """
        Creates an error in the SysEvent table and shows it on screen if log_to_screen is true
        Equivalent to: createSysError(String pCode, String pData, String pType, boolean pLogtoscreen)
        
        :param error_code: Error code
        :param error_data: Error details/data
        :param error_type: 'ERROR-BLOCKING' or 'ERROR-NONBLOCKING'
        :param log_to_screen: If True, log error creation
        :param source: Source system (default: 'BE')
        :return: Created error event record
        """
        try:
            # Find or create the error type
            event_type = self.env['myschool.sys.event.type.logic'].get_or_create_type(
                error_type,
                error_type.replace('-', '_'),
                f'System error type: {error_type}'
            )
            
            # Determine priority based on error type
            # pType = ERROR-BLOCKING or ERROR-NONBLOCKING
            if 'BLOCKING' in error_type:
                priority = '1'  # High priority
            else:
                priority = '2'  # Normal priority
            
            # Create the error event
            error_vals = {
                'eventcode': error_code,
                'status': 'NEW',
                'syseventtype_id': event_type.id,
                'priority': priority,
                'data': error_data,
                'source': source,
            }
            
            error_event = self.env['myschool.sys.event'].create(error_vals)
            
            # Logging
            if log_to_screen:
                _logger.debug('SysError added: %s - %s', error_event.syseventtype_id.name, error_event.data)
            
            _logger.info('SysError added: %s - %s', error_event.syseventtype_id.name, error_event.data)
            _logger.error('ERROR: %s', error_data)
            
            return error_event
            
        except Exception as e:
            _logger.exception("Error creating sys error event")
            # Prevent infinite recursion
            if error_code != 'SYSEVENT-900':
                self.create_sys_error('SYSEVENT-900', str(e), 'ERROR-NONBLOCKING', True)
            return self.env['myschool.sys.event'].browse()  # Return empty recordset
