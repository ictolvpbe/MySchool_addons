# -*- coding: utf-8 -*-
"""
System Event Service/Logic
Converted from SysEventService.java interface and SysEventServiceImpl.java

This module provides the service layer for managing system events,
equivalent to the Java Spring Boot service pattern.

Java Interface Methods Implemented:
- findById(String id) -> find_by_id(event_id)
- findByTypeAndStatus(SysEventType type, String status) -> find_by_type_and_status(type, status)
- findAll() -> find_all()
- createSysEvent(String pCode, String pData, Boolean pLogtoscreen) -> create_sys_event(code, data, log_to_screen)
- createSysError(String pCode, String pData, String pType, boolean pLogtoscreen) -> create_sys_error(code, data, error_type, log_to_screen)

DAO Methods (from SysEventDao.java):
- findSysEventById(String id)
- findSysEventBySysEventTypeAndStatus(SysEventType type, String status)
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class SysEventService(models.AbstractModel):
    """
    Service class for System Event operations
    Equivalent to SysEventService.java + SysEventServiceImpl.java + SysEventDao.java
    
    Usage:
        service = self.env['myschool.sys.event.service']
        
        # Create a general event
        event = service.create_sys_event('USER_LOGIN', 'User admin logged in', log_to_screen=True)
        
        # Create an error event
        error = service.create_sys_error('DB_ERROR', 'Connection failed', 'ERROR-BLOCKING', True)
        
        # Find events
        events = service.find_by_type_and_status(event_type, 'NEW')
    """
    _name = 'myschool.sys.event.service'
    _description = 'System Event Service'
    
    # =========================================================================
    # DAO Methods (from SysEventDao.java)
    # =========================================================================
    
    @api.model
    def find_by_id(self, event_id):
        """
        Find event by ID
        Equivalent to: findSysEventById(String id)
        
        :param event_id: Event ID
        :return: Event record or empty recordset
        """
        if not event_id:
            return self.env['myschool.sys.event']
        return self.env['myschool.sys.event'].browse(event_id).exists()
    
    @api.model
    def find_by_type_and_status(self, event_type, status):
        """
        Find events by type and status
        Equivalent to: findSysEventBySysEventTypeAndStatus(SysEventType type, String status)
        
        :param event_type: Event type record, ID, or name string
        :param status: Status string ('NEW', 'PROCESS', 'PRO_ERROR', 'CLOSED')
        :return: Recordset of matching events
        """
        domain = []
        
        # Handle event_type parameter
        if event_type:
            if isinstance(event_type, str):
                # Find by name
                type_record = self.env['myschool.sys.event.type.service'].find_by_name(event_type)
                if type_record:
                    domain.append(('syseventtype_id', '=', type_record.id))
            elif isinstance(event_type, int):
                domain.append(('syseventtype_id', '=', event_type))
            elif hasattr(event_type, 'id'):
                domain.append(('syseventtype_id', '=', event_type.id))
        
        # Handle status parameter
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
    def find_by_eventcode(self, eventcode):
        """
        Find events by event code
        
        :param eventcode: Event code to search for
        :return: Recordset of matching events
        """
        if not eventcode:
            return self.env['myschool.sys.event']
        return self.env['myschool.sys.event'].search([('eventcode', '=', eventcode)])
    
    @api.model
    def find_by_source(self, source):
        """
        Find events by source
        
        :param source: Source to search for (BE, ADSYNC, API, CRON, etc.)
        :return: Recordset of matching events
        """
        if not source:
            return self.env['myschool.sys.event']
        return self.env['myschool.sys.event'].search([('source', '=', source)])
    
    @api.model
    def find_open_events(self):
        """
        Find all open (non-closed) events
        
        :return: Recordset of open events
        """
        return self.env['myschool.sys.event'].search([('status', 'in', ['NEW', 'PROCESS'])])
    
    @api.model
    def find_error_events(self):
        """
        Find all events in error status
        
        :return: Recordset of error events
        """
        return self.env['myschool.sys.event'].search([('status', '=', 'PRO_ERROR')])
    
    # =========================================================================
    # Service Methods (from SysEventService.java / SysEventServiceImpl.java)
    # =========================================================================
    
    @api.model
    def register_or_update(self, event_vals):
        """
        Register a new event or update existing one
        Similar to JPA saveAndFlush behavior
        
        :param event_vals: Dictionary of event values or event record
        :return: Event record
        """
        SysEvent = self.env['myschool.sys.event']
        
        if isinstance(event_vals, models.BaseModel):
            return event_vals
        
        if not isinstance(event_vals, dict):
            raise ValidationError(_('Invalid event data provided'))
        
        # If ID is provided, update existing
        if event_vals.get('id'):
            existing = SysEvent.browse(event_vals['id']).exists()
            if existing:
                update_vals = {k: v for k, v in event_vals.items() if k != 'id'}
                existing.write(update_vals)
                return existing
        
        # Create new
        return SysEvent.create(event_vals)
    
    @api.model
    def create_sys_event(self, code, data, log_to_screen=False, source='BE'):
        """
        Creates an event in the SysEvent table and shows it on screen if log_to_screen is true
        Equivalent to: createSysEvent(String pCode, String pData, Boolean pLogtoscreen)
        
        This is the main method for logging general system events.
        
        :param code: Event code (pCode) - identifies the type of event
        :param data: Event details/data (pData) - descriptive information
        :param log_to_screen: If True, log event to console/screen (pLogtoscreen)
        :param source: Source system (default: 'BE' for Backend)
        :return: Created event record
        
        Example:
            service = self.env['myschool.sys.event.service']
            event = service.create_sys_event(
                'USER_LOGIN_SUCCESS',
                'User admin logged in from IP: 192.168.1.100',
                log_to_screen=True,
                source='BE'
            )
        """
        try:
            # Get or create the EVENT type
            type_service = self.env['myschool.sys.event.type.service']
            event_type = type_service.get_or_create(
                name='EVENT',
                code='EVENT',
                priority=3,
                description='General system event'
            )
            
            # Create the event
            event_vals = {
                'eventcode': code,
                'status': 'NEW',
                'syseventtype_id': event_type.id,
                'priority': '3',  # Low priority for general events
                'data': data,
                'source': source,
            }
            
            event = self.env['myschool.sys.event'].create(event_vals)
            
            # Logging based on pLogtoscreen parameter
            if log_to_screen:
                _logger.debug(f'SysEvent added: {event.syseventtype_id.name} - {event.data}')
            
            # Always log to info level (matching Java behavior)
            _logger.info(f'SysEvent created: [{event.name}] {code} - {data[:100]}...' if len(data or '') > 100 else f'SysEvent created: [{event.name}] {code} - {data}')
            
            return event
            
        except Exception as e:
            _logger.exception("Error creating sys event")
            # Create error event (with recursion protection)
            if code != 'SYSEVENT-900':
                self.create_sys_error(
                    'SYSEVENT-900',
                    f'Error creating event {code}: {str(e)}',
                    'ERROR-NONBLOCKING',
                    log_to_screen=True
                )
            return self.env['myschool.sys.event']  # Return empty recordset
    
    @api.model
    def create_sys_error(self, code, data, error_type='ERROR-NONBLOCKING', log_to_screen=False, source='BE'):
        """
        Creates an error in the SysEvent table and shows it on screen if log_to_screen is true
        Equivalent to: createSysError(String pCode, String pData, String pType, boolean pLogtoscreen)
        
        This is the main method for logging system errors.
        
        :param code: Error code (pCode) - identifies the type of error
        :param data: Error details/data (pData) - descriptive information
        :param error_type: 'ERROR-BLOCKING' or 'ERROR-NONBLOCKING' (pType)
        :param log_to_screen: If True, log error to console/screen (pLogtoscreen)
        :param source: Source system (default: 'BE' for Backend)
        :return: Created error event record
        
        Example:
            service = self.env['myschool.sys.event.service']
            error = service.create_sys_error(
                'DB_CONNECTION_ERROR',
                'Database connection timeout at 14:35',
                'ERROR-BLOCKING',
                log_to_screen=True,
                source='BE'
            )
        """
        try:
            # Validate error_type
            if error_type not in ['ERROR-BLOCKING', 'ERROR-NONBLOCKING']:
                _logger.warning(f'Invalid error_type "{error_type}", defaulting to ERROR-NONBLOCKING')
                error_type = 'ERROR-NONBLOCKING'
            
            # Get or create the error type
            type_service = self.env['myschool.sys.event.type.service']
            event_type = type_service.get_or_create(
                name=error_type,
                code=error_type.replace('-', '_'),
                priority=1 if 'BLOCKING' in error_type else 2,
                description=f'System error type: {error_type}'
            )
            
            # Determine priority based on error type
            # BLOCKING errors get highest priority (1), NONBLOCKING get normal (2)
            if 'BLOCKING' in error_type and 'NON' not in error_type:
                priority = '1'  # High priority
            else:
                priority = '2'  # Normal priority
            
            # Create the error event
            error_vals = {
                'eventcode': code,
                'status': 'NEW',
                'syseventtype_id': event_type.id,
                'priority': priority,
                'data': data,
                'source': source,
            }
            
            error_event = self.env['myschool.sys.event'].create(error_vals)
            
            # Logging based on pLogtoscreen parameter
            if log_to_screen:
                _logger.debug(f'SysError added: {error_event.syseventtype_id.name} - {error_event.data}')
            
            # Always log to appropriate level
            _logger.info(f'SysError created: [{error_event.name}] {error_type} - {code}')
            _logger.error(f'ERROR [{code}]: {data}')
            
            return error_event
            
        except Exception as e:
            _logger.exception("Error creating sys error event")
            # Prevent infinite recursion
            if code != 'SYSEVENT-900':
                try:
                    self.create_sys_error(
                        'SYSEVENT-900',
                        f'Error creating error event {code}: {str(e)}',
                        'ERROR-NONBLOCKING',
                        log_to_screen=True
                    )
                except Exception:
                    _logger.critical(f'Failed to create fallback error event: {str(e)}')
            return self.env['myschool.sys.event']  # Return empty recordset
    
    # =========================================================================
    # Additional Helper Methods
    # =========================================================================
    
    @api.model
    def close_event(self, event_id):
        """
        Close an event by ID
        
        :param event_id: ID of the event to close
        :return: Closed event record
        """
        event = self.find_by_id(event_id)
        if event:
            event.action_set_closed()
        return event
    
    @api.model
    def close_events_by_code(self, eventcode):
        """
        Close all events with a specific event code
        
        :param eventcode: Event code to match
        :return: Number of events closed
        """
        events = self.find_by_eventcode(eventcode).filtered(lambda e: e.status != 'CLOSED')
        for event in events:
            event.action_set_closed()
        return len(events)
    
    @api.model
    def get_event_statistics(self):
        """
        Get statistics about system events
        
        :return: Dictionary with event statistics
        """
        SysEvent = self.env['myschool.sys.event']
        return {
            'total': SysEvent.search_count([]),
            'new': SysEvent.search_count([('status', '=', 'NEW')]),
            'processing': SysEvent.search_count([('status', '=', 'PROCESS')]),
            'error': SysEvent.search_count([('status', '=', 'PRO_ERROR')]),
            'closed': SysEvent.search_count([('status', '=', 'CLOSED')]),
            'high_priority': SysEvent.search_count([('priority', '=', '1'), ('status', '!=', 'CLOSED')]),
            'blocking_errors': SysEvent.search_count([
                ('syseventtype_id.name', '=', 'ERROR-BLOCKING'),
                ('status', '!=', 'CLOSED')
            ]),
        }
    
    @api.model
    def cleanup_old_events(self, days=30, status='CLOSED'):
        """
        Archive old events (set active=False)
        
        :param days: Number of days after which to archive
        :param status: Only archive events with this status
        :return: Number of events archived
        """
        import datetime
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        
        old_events = self.env['myschool.sys.event'].search([
            ('status', '=', status),
            ('create_date', '<', cutoff_date),
            ('active', '=', True)
        ])
        
        if old_events:
            old_events.write({'active': False})
            _logger.info(f'Archived {len(old_events)} old events older than {days} days')
        
        return len(old_events)
