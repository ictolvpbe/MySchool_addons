# -*- coding: utf-8 -*-
"""
Task Debug Runner
=================

Transient wizard for processing pending betasks with **live log
visibility**. The regular cron / "Verwerk alle wachtende taken" menu
runs the queue silently — when a task fails it just lands in the
``error`` bucket and you have to tail the server log to find out why.
This wizard captures everything the processor logs while it runs and
shows it back in a textarea, plus tellers per status.

Three run modes:

* ``by_type``        — every pending task of a single ``betask.type``
* ``single_task``    — exactly one task (re-run a specific failure)
* ``all_priority``   — drain the whole queue in priority order

Optional ``dry_run`` flag injects ``data['dry_run']=True`` into the
payload before processing — handlers that respect it (LDAP/CLOUD
services do) make backend calls in preview mode.
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .sync_test_runner import _LogCaptureHandler, CAPTURED_LOGGERS

_logger = logging.getLogger(__name__)


class TaskDebugRunner(models.TransientModel):
    _name = 'myschool.task.debug.runner'
    _description = 'Task Debug Runner'

    # ------------------------------------------------------------------
    # Selection of what to run
    # ------------------------------------------------------------------

    mode = fields.Selection(
        selection=[
            ('by_type', 'Alle wachtende van één type'),
            ('single_task', 'Eén specifieke task'),
            ('all_priority', 'Alle wachtende (in priority-volgorde)'),
        ],
        string='Run-mode',
        default='by_type',
        required=True,
        help='Bepaalt welke set tasks de runner verwerkt.')

    task_type_id = fields.Many2one(
        comodel_name='myschool.betask.type',
        string='Task type',
        domain="[('active', '=', True)]",
        help='Vereist voor mode "Alle wachtende van één type".')

    task_id = fields.Many2one(
        comodel_name='myschool.betask',
        string='Task',
        domain="[('status', 'in', ['new', 'error'])]",
        help='Vereist voor mode "Eén specifieke task".')

    pending_count = fields.Integer(
        string='Pending nu',
        compute='_compute_pending_count',
        help='Aantal tasks met status="new" voor de huidige selectie.')

    error_count = fields.Integer(
        string='Errors nu',
        compute='_compute_pending_count',
        help='Aantal tasks met status="error" voor de huidige selectie.')

    # ------------------------------------------------------------------
    # Run options
    # ------------------------------------------------------------------

    dry_run = fields.Boolean(
        string='Dry-run',
        default=False,
        help='Forceert ``data["dry_run"]=True`` op alle verwerkte tasks. '
             'LDAP/CLOUD service-methodes respecteren dit en doen geen '
             'echte backend-mutatie. Handig om de cascade te testen '
             'zonder iets in AD/Workspace te wijzigen.')

    retry_errors = fields.Boolean(
        string='Ook errors opnieuw proberen',
        default=False,
        help='Wanneer aangevinkt, worden ook tasks met status="error" '
             'meegenomen en hun status eerst gereset naar "new".')

    log_level = fields.Selection(
        selection=[
            ('DEBUG', 'DEBUG (alles)'),
            ('INFO', 'INFO (default)'),
            ('WARNING', 'WARNING+ (alleen issues)'),
            ('ERROR', 'ERROR (alleen failures)'),
        ],
        string='Log-niveau',
        default='INFO',
        required=True)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    state = fields.Selection(
        selection=[
            ('draft', 'Klaar om te starten'),
            ('done', 'Klaar'),
        ],
        default='draft', readonly=True)

    summary = fields.Char(string='Resultaat', readonly=True)
    ok_count = fields.Integer(string='OK', readonly=True)
    err_count = fields.Integer(string='Errors', readonly=True)
    skipped_count = fields.Integer(string='Geskipt', readonly=True)
    log_output = fields.Text(string='Log output', readonly=True)

    # ==================================================================
    # Computes
    # ==================================================================

    @api.depends('mode', 'task_type_id', 'task_id', 'retry_errors')
    def _compute_pending_count(self):
        BeTask = self.env['myschool.betask']
        for wiz in self:
            if wiz.mode == 'single_task':
                wiz.pending_count = 1 if wiz.task_id else 0
                wiz.error_count = (
                    1 if wiz.task_id and wiz.task_id.status == 'error' else 0)
                continue
            domain_new = [('status', '=', 'new')]
            domain_err = [('status', '=', 'error')]
            if wiz.mode == 'by_type' and wiz.task_type_id:
                domain_new.append(('betasktype_id', '=', wiz.task_type_id.id))
                domain_err.append(('betasktype_id', '=', wiz.task_type_id.id))
            wiz.pending_count = BeTask.search_count(domain_new)
            wiz.error_count = BeTask.search_count(domain_err)

    # ==================================================================
    # Run
    # ==================================================================

    def action_run(self):
        self.ensure_one()
        BeTask = self.env['myschool.betask']
        processor = self.env['myschool.betask.processor']

        # Resolve target recordset
        if self.mode == 'single_task':
            if not self.task_id:
                raise UserError(_(
                    'Selecteer een task voor mode "Eén specifieke task".'))
            tasks = self.task_id
        elif self.mode == 'by_type':
            if not self.task_type_id:
                raise UserError(_(
                    'Selecteer een task type voor mode "Alle wachtende '
                    'van één type".'))
            statuses = ['new']
            if self.retry_errors:
                statuses.append('error')
            tasks = BeTask.search([
                ('betasktype_id', '=', self.task_type_id.id),
                ('status', 'in', statuses),
            ], order='id')
        else:  # all_priority
            statuses = ['new']
            if self.retry_errors:
                statuses.append('error')
            tasks = BeTask.search([('status', 'in', statuses)], order='id')

        if not tasks:
            self.write({
                'state': 'done',
                'summary': _('Geen tasks om te verwerken.'),
                'log_output': _('Geen wachtende tasks gevonden voor de '
                                'huidige selectie.'),
                'ok_count': 0, 'err_count': 0, 'skipped_count': 0,
            })
            return self._reload_self()

        # Reset error → new so process_single_task picks them up
        if self.retry_errors:
            error_tasks = tasks.filtered(lambda t: t.status == 'error')
            if error_tasks:
                error_tasks.write({'status': 'new', 'error_description': False})

        # Hook log capture
        log_handler = _LogCaptureHandler()
        log_handler.setLevel(getattr(logging, self.log_level))
        loggers = [logging.getLogger(n) for n in CAPTURED_LOGGERS]
        for lg in loggers:
            lg.addHandler(log_handler)

        ok = err = skipped = 0
        try:
            if self.mode == 'all_priority':
                # Use the processor's priority-aware loop
                ctx = {'dry_run_betask': True} if self.dry_run else {}
                result = processor.with_context(**ctx).process_all_pending()
                ok = result.get('successful_tasks', 0)
                err = result.get('failed_tasks', 0)
                skipped = result.get('skipped_time_limit', 0)
            else:
                for task in tasks:
                    if self.dry_run:
                        self._inject_dry_run(task)
                    if task.status not in ('new', 'error'):
                        skipped += 1
                        continue
                    try:
                        processor.process_single_task(task)
                        task.invalidate_recordset()
                        if task.status == 'completed_ok':
                            ok += 1
                        else:
                            err += 1
                    except Exception:
                        err += 1
                        _logger.exception(
                            '[TASK-DEBUG] failed to run %s', task.name)
        finally:
            for lg in loggers:
                lg.removeHandler(log_handler)

        # Render captured records
        log_text = self._format_log(log_handler.records)
        summary = _(
            '%(ok)s OK, %(err)s fouten, %(skipped)s overgeslagen '
            '(uit %(total)s)'
        ) % {'ok': ok, 'err': err, 'skipped': skipped,
             'total': len(tasks) if self.mode != 'all_priority' else (ok + err + skipped)}
        self.write({
            'state': 'done',
            'summary': summary,
            'ok_count': ok, 'err_count': err, 'skipped_count': skipped,
            'log_output': log_text,
        })
        return self._reload_self()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _inject_dry_run(self, task):
        """Add ``"dry_run": true`` to the task's data JSON.

        Saved back so re-running the task without re-clicking the
        wizard preserves the flag — admins who want to flip it off
        clear the dry_run checkbox here and re-run.
        """
        import json
        data = task.data or '{}'
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict):
                return
        except Exception:
            return
        payload['dry_run'] = True
        task.write({'data': json.dumps(payload)})

    @staticmethod
    def _format_log(records):
        """Stitch captured records into a text blob.

        Lines with exception info get the traceback appended directly
        below them so admins can see context without scrolling.
        """
        if not records:
            return '(geen log-output)'
        out = []
        for _level, line, exc in records:
            out.append(line)
            if exc:
                out.append(exc)
        return '\n'.join(out)

    def _reload_self(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_clear_log(self):
        self.ensure_one()
        self.write({
            'state': 'draft',
            'summary': False, 'log_output': False,
            'ok_count': 0, 'err_count': 0, 'skipped_count': 0,
        })
        return self._reload_self()
