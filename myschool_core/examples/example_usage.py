# -*- coding: utf-8 -*-
"""
Example Controller showing how to use the SysEvent service methods

This file demonstrates how to use the converted service methods in controllers,
scheduled actions, or other business logic.

To use this controller, add it to your controllers/__init__.py
"""

from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SysEventExampleController(http.Controller):
    """Example controller demonstrating SysEvent service method usage"""
    
    @http.route('/sysevent/example/create', type='json', auth='user')
    def create_example_event(self, **kwargs):
        """
        Example endpoint to create a system event
        
        Usage (from JavaScript):
        jsonrpc('/sysevent/example/create', {
            code: 'TEST_EVENT',
            data: 'Test event data'
        })
        """
        event_code = kwargs.get('code', 'DEFAULT_EVENT')
        event_data = kwargs.get('data', 'No data provided')
        
        # Create event using logic layer
        event = request.env['myschool.sys.event.logic'].create_sys_event(
            event_code,
            event_data,
            log_to_screen=True,
            source='API'
        )
        
        return {
            'success': True,
            'event_id': event.id,
            'event_name': event.name,
            'message': 'Event created successfully'
        }
    
    @http.route('/sysevent/example/error', type='json', auth='user')
    def create_example_error(self, **kwargs):
        """
        Example endpoint to create a system error event
        
        Usage (from JavaScript):
        jsonrpc('/sysevent/example/error', {
            code: 'API_ERROR',
            data: 'Error details',
            blocking: true
        })
        """
        error_code = kwargs.get('code', 'DEFAULT_ERROR')
        error_data = kwargs.get('data', 'No error data provided')
        is_blocking = kwargs.get('blocking', False)
        
        error_type = 'ERROR-BLOCKING' if is_blocking else 'ERROR-NONBLOCKING'
        
        # Create error using logic layer
        error = request.env['myschool.sys.event.logic'].create_sys_error(
            error_code,
            error_data,
            error_type=error_type,
            log_to_screen=True,
            source='API'
        )
        
        return {
            'success': True,
            'error_id': error.id,
            'error_name': error.name,
            'priority': error.priority,
            'message': 'Error event created successfully'
        }
    
    @http.route('/sysevent/example/search', type='json', auth='user')
    def search_events_example(self, **kwargs):
        """
        Example endpoint to search events by type and status
        
        Usage (from JavaScript):
        jsonrpc('/sysevent/example/search', {
            type_id: 1,
            status: 'NEW'
        })
        """
        type_id = kwargs.get('type_id')
        status = kwargs.get('status', 'NEW')
        
        # Search using logic layer
        events = request.env['myschool.sys.event.logic'].find_by_type_and_status(
            type_id,
            status
        )
        
        # Format results
        event_list = []
        for event in events:
            event_list.append({
                'id': event.id,
                'name': event.name,
                'eventcode': event.eventcode,
                'status': event.status,
                'priority': event.priority,
                'data': event.data,
                'create_date': event.create_date.isoformat() if event.create_date else None
            })
        
        return {
            'success': True,
            'count': len(events),
            'events': event_list
        }


# Example of using service methods in scheduled actions
class SysEventScheduledActions:
    """Example scheduled actions using SysEvent service methods"""
    
    @staticmethod
    def cleanup_old_events(env):
        """
        Scheduled action to close old events
        
        To set up in Odoo:
        1. Go to Settings > Technical > Automation > Scheduled Actions
        2. Create new action
        3. Set to call: model.cleanup_old_events()
        """
        import datetime
        
        # Find events older than 30 days with NEW status
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30)
        old_events = env['myschool.sys.event'].search([
            ('status', '=', 'NEW'),
            ('create_date', '<', cutoff_date)
        ])
        
        closed_count = 0
        for event in old_events:
            try:
                event.action_set_closed()
                closed_count += 1
            except Exception as e:
                _logger.error(f"Error closing event {event.id}: {e}")
        
        # Log cleanup completion
        env['myschool.sys.event.logic'].create_sys_event(
            'CLEANUP_OLD_EVENTS',
            f'Cleanup completed. Closed {closed_count} old events.',
            log_to_screen=True,
            source='CRON'
        )
        
        return closed_count
    
    @staticmethod
    def process_error_events(env):
        """
        Scheduled action to process error events
        
        Example of finding and handling error events
        """
        # Find all blocking errors that are new
        error_type = env['myschool.sys.event.type.logic'].find_by_name('ERROR-BLOCKING')
        
        if error_type:
            blocking_errors = env['myschool.sys.event.logic'].find_by_type_and_status(
                error_type,
                'NEW'
            )
            
            for error in blocking_errors:
                try:
                    # Process the error (example: send notification, retry operation, etc.)
                    _logger.info(f"Processing error: {error.eventcode} - {error.data}")
                    
                    # Mark as processing
                    error.action_set_processing()
                    
                    # TODO: Add your error handling logic here
                    
                    # If successful, close the error
                    error.action_set_closed()
                    
                except Exception as e:
                    # If processing fails, mark as error
                    error.action_set_error()
                    _logger.error(f"Failed to process error {error.id}: {e}")
        
        # Log processing completion
        env['myschool.sys.event.logic'].create_sys_event(
            'PROCESS_ERRORS_COMPLETE',
            f'Error processing completed',
            log_to_screen=True,
            source='CRON'
        )
    
    @staticmethod
    def monitor_event_statistics(env):
        """
        Scheduled action to monitor and log event statistics
        """
        # Count events by status
        new_count = env['myschool.sys.event'].search_count([('status', '=', 'NEW')])
        processing_count = env['myschool.sys.event'].search_count([('status', '=', 'PROCESS')])
        error_count = env['myschool.sys.event'].search_count([('status', '=', 'PRO_ERROR')])
        closed_count = env['myschool.sys.event'].search_count([('status', '=', 'CLOSED')])
        
        # Log statistics
        stats = f"Event Statistics - NEW: {new_count}, PROCESSING: {processing_count}, " \
                f"ERROR: {error_count}, CLOSED: {closed_count}"
        
        env['myschool.sys.event.logic'].create_sys_event(
            'EVENT_STATISTICS',
            stats,
            log_to_screen=True,
            source='CRON'
        )
        
        # If too many errors, create a warning
        if error_count > 10:
            env['myschool.sys.event.logic'].create_sys_error(
                'HIGH_ERROR_COUNT',
                f'Warning: High number of error events detected ({error_count})',
                error_type='ERROR-NONBLOCKING',
                log_to_screen=True,
                source='CRON'
            )


# Example of using service methods in a custom model
class CustomModelExample:
    """Example of using SysEvent methods in custom business logic"""
    
    @staticmethod
    def process_user_login(env, username, ip_address):
        """Handle user login event"""
        try:
            # Create login event using logic layer
            event = env['myschool.sys.event.logic'].create_sys_event(
                'USER_LOGIN_SUCCESS',
                f'User {username} logged in from IP: {ip_address}',
                log_to_screen=True,
                source='BE'
            )
            
            return True, event
            
        except Exception as e:
            # Create error if login event creation fails
            env['myschool.sys.event.logic'].create_sys_error(
                'LOGIN_EVENT_ERROR',
                f'Failed to create login event for {username}: {str(e)}',
                error_type='ERROR-NONBLOCKING',
                log_to_screen=True
            )
            return False, None
    
    @staticmethod
    def sync_external_data(env):
        """Example of external data synchronization with event logging"""
        try:
            # Start sync
            env['myschool.sys.event.logic'].create_sys_event(
                'SYNC_STARTED',
                'External data synchronization started',
                log_to_screen=True,
                source='ADSYNC'
            )
            
            # Perform sync operations
            # ... your sync logic here ...
            synced_count = 100  # Example count
            
            # Log completion
            env['myschool.sys.event.logic'].create_sys_event(
                'SYNC_COMPLETED',
                f'Successfully synchronized {synced_count} records',
                log_to_screen=True,
                source='ADSYNC'
            )
            
            return True, synced_count
            
        except Exception as e:
            # Log error
            env['myschool.sys.event.logic'].create_sys_error(
                'SYNC_ERROR',
                f'Synchronization failed: {str(e)}',
                error_type='ERROR-BLOCKING',
                log_to_screen=True,
                source='ADSYNC'
            )
            return False, 0
    
    @staticmethod
    def validate_and_log_operation(env, operation_name, data):
        """Example of validation with event logging"""
        try:
            # Validate data
            if not data:
                env['myschool.sys.event.logic'].create_sys_error(
                    'VALIDATION_ERROR',
                    f'Validation failed for {operation_name}: No data provided',
                    error_type='ERROR-NONBLOCKING',
                    log_to_screen=True
                )
                return False
            
            # Process operation
            # ... your operation logic ...
            
            # Log success
            env['myschool.sys.event.logic'].create_sys_event(
                f'{operation_name.upper()}_SUCCESS',
                f'Operation {operation_name} completed successfully',
                log_to_screen=True
            )
            
            return True
            
        except Exception as e:
            env['myschool.sys.event.logic'].create_sys_error(
                f'{operation_name.upper()}_ERROR',
                str(e),
                error_type='ERROR-BLOCKING',
                log_to_screen=True
            )
            return False


"""
USAGE IN ODOO SHELL:
--------------------

# Start Odoo shell
./odoo-bin shell -d your_database_name

# Test creating an event using LOGIC LAYER
>>> event = env['myschool.sys.event.logic'].create_sys_event('TEST', 'Test event', True)
>>> print(event.name)

# Test creating an error using LOGIC LAYER
>>> error = env['myschool.sys.event.logic'].create_sys_error('TEST_ERR', 'Test error', 'ERROR-BLOCKING', True)
>>> print(error.priority)

# Test searching using LOGIC LAYER
>>> events = env['myschool.sys.event.logic'].find_by_type_and_status(False, 'NEW')
>>> print(len(events))

# Run scheduled action examples
>>> SysEventScheduledActions.cleanup_old_events(env)
>>> SysEventScheduledActions.monitor_event_statistics(env)
"""
