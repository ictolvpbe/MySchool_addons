# -*- coding: utf-8 -*-
"""
Log Viewer Model
================

Provides functionality to read and tail log files in real-time.
Includes an in-memory ring buffer handler so console (stdout) logs
are always available, even when no logfile is configured.
"""

import base64
import collections
import os
import glob
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo import tools
import logging

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory ring buffer handler — captures log records from the root logger
# so the log viewer can display them even when Odoo logs to stdout only.
# ---------------------------------------------------------------------------
_CONSOLE_BUFFER_SIZE = 5000  # max records kept in memory


class _RingBufferHandler(logging.Handler):
    """Lightweight handler that stores formatted log records in a deque."""

    def __init__(self, capacity=_CONSOLE_BUFFER_SIZE):
        super().__init__()
        self.buffer = collections.deque(maxlen=capacity)
        # Reuse Odoo's default log format
        self.setFormatter(logging.Formatter(
            '%(asctime)s %(pid)s %(levelname)s %(name)s: %(message)s'
        ))

    def emit(self, record):
        try:
            self.buffer.append(self.format(record))
        except Exception:
            pass  # never break the application


# Singleton — installed once on module load
_ring_handler = _RingBufferHandler()

# Attach to root logger so we capture everything Odoo produces
_root = logging.getLogger()
if _ring_handler not in _root.handlers:
    _root.addHandler(_ring_handler)


# Virtual key used in selection / ajax calls
_CONSOLE_KEY = '__console__'


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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_log_directory(self):
        """Get the Odoo log directory."""
        log_file = tools.config.get('logfile')
        if log_file:
            return os.path.dirname(log_file)

        default_paths = [
            '/var/log/odoo',
            '/var/log/odoo19',
            '/opt/odoo/logs',
            os.path.expanduser('~/.local/share/Odoo/logs'),
            '/tmp',
        ]

        for path in default_paths:
            if os.path.isdir(path):
                # Only return if the directory actually contains log files
                if glob.glob(os.path.join(path, '*.log')):
                    return path

        return '/var/log'

    @api.model
    def _get_available_logs(self):
        """Get list of available log files.  Always includes the live
        console buffer as the first option."""
        log_files = []
        seen = set()

        # 1 — Always offer the in-memory console buffer
        log_files.append((_CONSOLE_KEY, 'Live Console (stdout)'))
        seen.add(_CONSOLE_KEY)

        # 2 — Configured logfile
        configured_log = tools.config.get('logfile')
        if configured_log and os.path.isfile(configured_log):
            log_files.append((configured_log, f"Odoo Log: {os.path.basename(configured_log)}"))
            seen.add(configured_log)

        # 3 — Search in log directory
        log_dir = self._get_log_directory()
        if os.path.isdir(log_dir):
            for pattern in ('*.log', 'odoo*.log', 'server*.log'):
                for log_path in sorted(glob.glob(os.path.join(log_dir, pattern))):
                    if log_path not in seen:
                        log_files.append((log_path, os.path.basename(log_path)))
                        seen.add(log_path)

        # 4 — Common well-known locations
        common_logs = [
            '/var/log/odoo/odoo-server.log',
            '/var/log/odoo/odoo.log',
        ]
        for log_path in common_logs:
            if os.path.isfile(log_path) and log_path not in seen:
                log_files.append((log_path, os.path.basename(log_path)))
                seen.add(log_path)

        return log_files

    @api.model
    def _has_file_logs(self):
        """Return True if at least one real log file was found (not just console)."""
        logs = self._get_available_logs()
        return any(key != _CONSOLE_KEY for key, _label in logs)

    # ------------------------------------------------------------------
    # Console buffer reader
    # ------------------------------------------------------------------

    @staticmethod
    def _read_console_buffer(num_lines=100):
        """Return the last *num_lines* entries from the ring buffer."""
        buf = _ring_handler.buffer
        entries = list(buf)[-num_lines:] if len(buf) > num_lines else list(buf)
        return '\n'.join(entries)

    # ------------------------------------------------------------------
    # File reader
    # ------------------------------------------------------------------

    def _tail_file(self, filepath, num_lines=100):
        """
        Read the last N lines of a file (like tail -n).
        Efficient implementation for large files.
        """
        try:
            with open(filepath, 'rb') as f:
                f.seek(0, 2)
                file_size = f.tell()

                if file_size == 0:
                    return ""

                lines = []
                chunk_size = 8192
                position = file_size

                while len(lines) <= num_lines and position > 0:
                    chunk_start = max(0, position - chunk_size)
                    f.seek(chunk_start)
                    chunk = f.read(position - chunk_start)

                    try:
                        chunk_text = chunk.decode('utf-8', errors='replace')
                    except Exception:
                        chunk_text = chunk.decode('latin-1', errors='replace')

                    chunk_lines = chunk_text.splitlines(keepends=True)
                    lines = chunk_lines + lines
                    position = chunk_start

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
            if self.filter_level and self.filter_level != 'all':
                keywords = level_keywords.get(self.filter_level, [])
                if not any(kw in line.upper() for kw in keywords):
                    continue
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
        except Exception:
            return "Unknown", False

    # ------------------------------------------------------------------
    # Actions (form-view, kept for backwards compat)
    # ------------------------------------------------------------------

    @api.onchange('log_file', 'num_lines', 'filter_level', 'search_text')
    def _onchange_log_file(self):
        if self.log_file and self.log_file != 'none':
            self.action_refresh()

    def action_refresh(self):
        if not self.log_file or self.log_file == 'none':
            self.log_content = "No log file selected."
            return

        if self.log_file == _CONSOLE_KEY:
            content = self._read_console_buffer(self.num_lines or 100)
        else:
            content = self._tail_file(self.log_file, self.num_lines or 100)

        content = self._filter_log_content(content)
        self.log_content = content
        self.last_refresh = fields.Datetime.now()

        if self.log_file != _CONSOLE_KEY:
            size_str, mod_time = self._get_file_info(self.log_file)
            self.file_size = size_str
            self.file_modified = mod_time

    def action_download(self):
        if not self.log_file or self.log_file == 'none':
            raise UserError(_('No log file selected.'))

        if self.log_file == _CONSOLE_KEY:
            content = self._read_console_buffer(10000)
            filename = 'console.log'
        else:
            content = self._tail_file(self.log_file, 10000)
            filename = os.path.basename(self.log_file)

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(content.encode('utf-8')),
            'mimetype': 'text/plain',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def action_clear_filters(self):
        self.filter_level = 'all'
        self.search_text = False
        self.action_refresh()

    # ------------------------------------------------------------------
    # AJAX endpoint (called by the OWL2 client action)
    # ------------------------------------------------------------------

    @api.model
    def get_log_content_ajax(self, log_file, num_lines=100, filter_level='all', search_text=''):
        """
        AJAX endpoint for real-time log updates.
        Called by JavaScript for auto-refresh.
        """
        if not log_file or log_file == 'none':
            return {
                'content': 'No log file selected.',
                'timestamp': '',
                'file_size': '',
                'file_modified': '',
                'is_console': False,
            }

        viewer = self.new({
            'log_file': log_file if log_file != _CONSOLE_KEY else False,
            'num_lines': num_lines,
            'filter_level': filter_level,
            'search_text': search_text,
        })

        is_console = (log_file == _CONSOLE_KEY)

        if is_console:
            content = self._read_console_buffer(num_lines)
        else:
            content = viewer._tail_file(log_file, num_lines)

        content = viewer._filter_log_content(content)

        if is_console:
            buf_len = len(_ring_handler.buffer)
            size_str = f"{buf_len} records (buffer)"
            mod_time_str = ''
        else:
            size_str, mod_time = viewer._get_file_info(log_file)
            mod_time_str = mod_time.isoformat() if mod_time else ''

        return {
            'content': content,
            'timestamp': fields.Datetime.now().isoformat(),
            'file_size': size_str,
            'file_modified': mod_time_str,
            'is_console': is_console,
        }

    @api.model
    def get_viewer_info(self):
        """Return metadata for the client action (available logs, config hints)."""
        logs = self._get_available_logs()
        has_logfile_config = bool(tools.config.get('logfile'))
        has_file_logs = any(key != _CONSOLE_KEY for key, _label in logs)
        return {
            'available_logs': logs,
            'has_logfile_config': has_logfile_config,
            'has_file_logs': has_file_logs,
        }
