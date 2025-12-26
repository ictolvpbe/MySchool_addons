# -*- coding: utf-8 -*-
"""
Log Viewer Model
================

Provides functionality to read and tail log files in real-time.
"""

import os
import glob
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
from odoo import tools
import logging

_logger = logging.getLogger(__name__)


class LogViewer(models.TransientModel):
    """
    Transient model for viewing log files.
    Uses TransientModel so no data is stored permanently.
    """
    _name = 'myschool.log.viewer'
    _description = 'Log File Viewer'

    name = fields.Char(string='Name', default='Log Viewer')
    
    log_file = fields.Selection(
        selection='_get_available_logs',
        string='Log File',
        required=True,
        help='Select which log file to view'
    )
    
    log_content = fields.Text(
        string='Log Content',
        readonly=True,
        help='Content of the selected log file'
    )
    
    num_lines = fields.Integer(
        string='Number of Lines',
        default=100,
        help='Number of lines to display (like tail -n)'
    )
    
    filter_level = fields.Selection([
        ('all', 'All'),
        ('debug', 'DEBUG'),
        ('info', 'INFO'),
        ('warning', 'WARNING'),
        ('error', 'ERROR'),
        ('critical', 'CRITICAL'),
    ], string='Log Level Filter', default='all')
    
    search_text = fields.Char(
        string='Search',
        help='Filter log lines containing this text'
    )
    
    auto_refresh = fields.Boolean(
        string='Auto Refresh',
        default=False,
        help='Automatically refresh log content'
    )
    
    refresh_interval = fields.Integer(
        string='Refresh Interval (seconds)',
        default=5
    )
    
    last_refresh = fields.Datetime(
        string='Last Refresh',
        readonly=True
    )
    
    file_size = fields.Char(
        string='File Size',
        readonly=True
    )
    
    file_modified = fields.Datetime(
        string='Last Modified',
        readonly=True
    )

    @api.model
    def _get_log_directory(self):
        """Get the Odoo log directory."""
        # Try to get from Odoo config
        log_file = tools.config.get('logfile')
        if log_file:
            return os.path.dirname(log_file)
        
        # Default locations to check
        default_paths = [
            '/var/log/odoo',
            '/var/log/odoo19',
            '/opt/odoo/logs',
            os.path.expanduser('~/.local/share/Odoo/logs'),
            '/tmp',
        ]
        
        for path in default_paths:
            if os.path.isdir(path):
                return path
        
        return '/var/log'

    @api.model
    def _get_available_logs(self):
        """Get list of available log files."""
        self._check_admin_access()
        
        log_files = []
        
        # Get configured log file
        configured_log = tools.config.get('logfile')
        if configured_log and os.path.isfile(configured_log):
            log_files.append((configured_log, f"Odoo Log: {os.path.basename(configured_log)}"))
        
        # Search in log directory
        log_dir = self._get_log_directory()
        if os.path.isdir(log_dir):
            patterns = ['*.log', 'odoo*.log', 'server*.log']
            for pattern in patterns:
                for log_path in glob.glob(os.path.join(log_dir, pattern)):
                    if log_path not in [lf[0] for lf in log_files]:
                        log_files.append((log_path, os.path.basename(log_path)))
        
        # Add common log locations
        common_logs = [
            '/var/log/odoo/odoo-server.log',
            '/var/log/odoo/odoo.log',
            '/var/log/syslog',
            '/var/log/syslog',
        ]
        
        for log_path in common_logs:
            if os.path.isfile(log_path) and log_path not in [lf[0] for lf in log_files]:
                log_files.append((log_path, os.path.basename(log_path)))
        
        if not log_files:
            log_files.append(('none', 'No log files found'))
        
        return log_files

    def _check_admin_access(self):
        """Ensure only admins can access log files."""
        if not self.env.user.has_group('myschool_core.group_myschool_core_admin'):
            if not self.env.user.has_group('base.group_system'):
                raise AccessError(_('Only administrators can view log files.'))

    def _tail_file(self, filepath, num_lines=100):
        """
        Read the last N lines of a file (like tail -n).
        Efficient implementation for large files.
        """
        try:
            with open(filepath, 'rb') as f:
                # Go to end of file
                f.seek(0, 2)
                file_size = f.tell()
                
                if file_size == 0:
                    return ""
                
                # Read in chunks from the end
                lines = []
                chunk_size = 8192
                position = file_size
                
                while len(lines) <= num_lines and position > 0:
                    # Calculate chunk position
                    chunk_start = max(0, position - chunk_size)
                    f.seek(chunk_start)
                    chunk = f.read(position - chunk_start)
                    
                    # Decode and split into lines
                    try:
                        chunk_text = chunk.decode('utf-8', errors='replace')
                    except:
                        chunk_text = chunk.decode('latin-1', errors='replace')
                    
                    chunk_lines = chunk_text.splitlines(keepends=True)
                    
                    # Prepend to lines list
                    lines = chunk_lines + lines
                    position = chunk_start
                
                # Return last N lines
                result_lines = lines[-num_lines:] if len(lines) > num_lines else lines
                return ''.join(result_lines)
                
        except PermissionError:
            raise UserError(_('Permission denied: Cannot read log file %s') % filepath)
        except FileNotFoundError:
            raise UserError(_('Log file not found: %s') % filepath)
        except Exception as e:
            raise UserError(_('Error reading log file: %s') % str(e))

    def _filter_log_content(self, content):
        """Filter log content by level and search text."""
        if not content:
            return content
        
        lines = content.splitlines()
        filtered_lines = []
        
        level_keywords = {
            'debug': ['DEBUG'],
            'info': ['INFO'],
            'warning': ['WARNING', 'WARN'],
            'error': ['ERROR'],
            'critical': ['CRITICAL', 'FATAL'],
        }
        
        for line in lines:
            # Filter by log level
            if self.filter_level and self.filter_level != 'all':
                keywords = level_keywords.get(self.filter_level, [])
                if not any(kw in line.upper() for kw in keywords):
                    continue
            
            # Filter by search text
            if self.search_text:
                if self.search_text.lower() not in line.lower():
                    continue
            
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def _get_file_info(self, filepath):
        """Get file size and modification time."""
        try:
            stat = os.stat(filepath)
            size_bytes = stat.st_size
            
            # Format file size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
            
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            
            return size_str, mod_time
        except:
            return "Unknown", False

    @api.onchange('log_file', 'num_lines', 'filter_level', 'search_text')
    def _onchange_log_file(self):
        """Load log content when file selection changes."""
        if self.log_file and self.log_file != 'none':
            self.action_refresh()

    def action_refresh(self):
        """Refresh the log content."""
        self._check_admin_access()
        
        if not self.log_file or self.log_file == 'none':
            self.log_content = "No log file selected."
            return
        
        # Read log file
        content = self._tail_file(self.log_file, self.num_lines or 100)
        
        # Apply filters
        content = self._filter_log_content(content)
        
        self.log_content = content
        self.last_refresh = fields.Datetime.now()
        
        # Update file info
        size_str, mod_time = self._get_file_info(self.log_file)
        self.file_size = size_str
        self.file_modified = mod_time

    def action_download(self):
        """Download the current log file."""
        self._check_admin_access()
        
        if not self.log_file or self.log_file == 'none':
            raise UserError(_('No log file selected.'))
        
        # Read entire file (or last 10000 lines for large files)
        content = self._tail_file(self.log_file, 10000)
        
        # Create attachment
        filename = os.path.basename(self.log_file)
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': content.encode('utf-8'),
            'mimetype': 'text/plain',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def action_clear_filters(self):
        """Clear all filters."""
        self.filter_level = 'all'
        self.search_text = False
        self.action_refresh()

    @api.model
    def get_log_content_ajax(self, log_file, num_lines=100, filter_level='all', search_text=''):
        """
        AJAX endpoint for real-time log updates.
        Called by JavaScript for auto-refresh.
        """
        self._check_admin_access()
        
        if not log_file or log_file == 'none':
            return {'content': 'No log file selected.', 'timestamp': ''}
        
        # Create temporary record for filtering
        viewer = self.new({
            'log_file': log_file,
            'num_lines': num_lines,
            'filter_level': filter_level,
            'search_text': search_text,
        })
        
        content = viewer._tail_file(log_file, num_lines)
        content = viewer._filter_log_content(content)
        
        size_str, mod_time = viewer._get_file_info(log_file)
        
        return {
            'content': content,
            'timestamp': fields.Datetime.now().isoformat(),
            'file_size': size_str,
            'file_modified': mod_time.isoformat() if mod_time else '',
        }
