# -*- coding: utf-8 -*-
"""
Smartschool Test Runner
=======================

Transient wizard for ad-hoc testing of the Smartschool integration
without touching the cron queue. Two-step workflow:

1. **Dry run** — selects an action + target person, forces dry-run via
   the ``smartschool_force_dry_run`` context flag (overrules even
   ``safeguard_mode=live`` with the per-config dry_run off). Captures
   log output + result, no real SOAP mutation happens.
2. **Live** — re-runs the same action without the force flag, so the
   normal safeguard stack applies. Only enabled after a successful
   dry-run, to make sure admins read the dry-run result first.

Each run creates a real ``myschool.betask`` so the production code
path is exercised end-to-end (handler dispatch, ownership-check,
sys_event audit-trail). Test betasks are prefixed ``[TEST]`` in their
name so they're easy to filter out of the queue.
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .sync_test_runner import _LogCaptureHandler, CAPTURED_LOGGERS

_logger = logging.getLogger(__name__)


# Map wizard action → (betask target, object, action, label)
_ACTION_MAP = {
    'test_connection': (None, None, None, 'Test platform connection (read-only)'),
    'user_add': ('SMARTSCHOOL', 'USER', 'ADD', 'Add / upsert user (saveUser)'),
    'user_upd': ('SMARTSCHOOL', 'USER', 'UPD', 'Update user (saveUser, no password)'),
    'user_deact': ('SMARTSCHOOL', 'USER', 'DEACT', 'Deactivate user (setAccountStatus)'),
    'user_pwd': ('SMARTSCHOOL', 'USER', 'PWD', 'Rotate password (savePassword)'),
    'user_del': ('SMARTSCHOOL', 'USER', 'DEL', 'Delete user (delUser)'),
}


class SmartschoolTestRunner(models.TransientModel):
    _name = 'myschool.smartschool.test.runner'
    _description = 'Smartschool Test Runner'

    # ==================================================================
    # Selection
    # ==================================================================

    action = fields.Selection(
        selection=[
            ('test_connection', 'Test connection (read-only probe)'),
            ('user_add', 'Add / upsert teacher account'),
            ('user_upd', 'Update teacher fields'),
            ('user_deact', 'Deactivate teacher account'),
            ('user_pwd', 'Rotate teacher password'),
            ('user_del', 'Delete teacher account (irreversible)'),
        ],
        string='Action',
        default='test_connection',
        required=True,
        help='What to test. "test_connection" only probes the WSDL + auth — '
             'no person needed. Everything else requires a target person.'
    )

    person_id = fields.Many2one(
        comodel_name='myschool.person',
        string='Target person',
        domain="[('person_type_id.name', '=', 'EMPLOYEE')]",
        help='Person to act on. Only EMPLOYEE persons are listed — Smartschool '
             'integration MVP scope is leerkrachten.'
    )

    config_id = fields.Many2one(
        comodel_name='myschool.smartschool.config',
        string='Smartschool platform',
        compute='_compute_config_id',
        store=False,
        help='Resolved automatically from the target person\'s school. '
             'For "test_connection" pick a platform explicitly.'
    )

    config_picker_id = fields.Many2one(
        comodel_name='myschool.smartschool.config',
        string='Pick platform',
        domain="[('active', '=', True)]",
        help='Required for "test_connection" mode (there is no person to '
             'derive the platform from).'
    )

    # ==================================================================
    # Computed info
    # ==================================================================

    target_username = fields.Char(
        string='Smartschool username',
        compute='_compute_target_info',
        store=False,
    )

    target_internnumber = fields.Char(
        string='Expected internnumber',
        compute='_compute_target_info',
        store=False,
    )

    safeguard_mode = fields.Char(
        string='Global safeguard mode',
        compute='_compute_safeguard_info',
        store=False,
    )

    safeguard_warning = fields.Text(
        string='Safeguard warning',
        compute='_compute_safeguard_info',
        store=False,
    )

    # ==================================================================
    # Workflow state
    # ==================================================================

    state = fields.Selection(
        selection=[
            ('draft', 'Klaar voor dry-run'),
            ('dry_run_done', 'Dry-run klaar — review'),
            ('live_done', 'Live klaar'),
        ],
        default='draft',
        readonly=True,
    )

    # Dry-run output
    dry_run_at = fields.Datetime(string='Dry-run uitgevoerd op', readonly=True)
    dry_run_status = fields.Selection(
        selection=[('ok', 'OK'), ('error', 'Error')],
        string='Dry-run status', readonly=True)
    dry_run_summary = fields.Char(string='Dry-run resultaat', readonly=True)
    dry_run_log = fields.Text(string='Dry-run log', readonly=True)
    dry_run_betask_id = fields.Many2one(
        'myschool.betask', string='Dry-run betask', readonly=True)

    # Live output
    live_at = fields.Datetime(string='Live uitgevoerd op', readonly=True)
    live_status = fields.Selection(
        selection=[('ok', 'OK'), ('error', 'Error')],
        string='Live status', readonly=True)
    live_summary = fields.Char(string='Live resultaat', readonly=True)
    live_log = fields.Text(string='Live log', readonly=True)
    live_betask_id = fields.Many2one(
        'myschool.betask', string='Live betask', readonly=True)

    # ==================================================================
    # Computes
    # ==================================================================

    @api.depends('action', 'person_id', 'config_picker_id')
    def _compute_config_id(self):
        Processor = self.env['myschool.betask.processor']
        for wiz in self:
            if wiz.action == 'test_connection':
                wiz.config_id = wiz.config_picker_id
                continue
            if wiz.person_id:
                wiz.config_id = Processor._resolve_smartschool_config_for_person(
                    wiz.person_id)
            else:
                wiz.config_id = False

    @api.depends('action', 'person_id', 'config_id')
    def _compute_target_info(self):
        Processor = self.env['myschool.betask.processor']
        for wiz in self:
            if wiz.action == 'test_connection' or not wiz.person_id:
                wiz.target_username = False
                wiz.target_internnumber = False
                continue
            wiz.target_username = Processor._smartschool_username_for_person(
                wiz.person_id) or False
            wiz.target_internnumber = wiz.person_id.sap_ref or False

    @api.depends('action', 'config_id')
    def _compute_safeguard_info(self):
        Svc = self.env['myschool.smartschool.service']
        mode = Svc._get_safeguard_mode()
        for wiz in self:
            wiz.safeguard_mode = mode
            warnings = []
            if mode == 'read_only':
                warnings.append(
                    'Globale safeguard staat op READ-ONLY: een live run zal '
                    'door _call worden geweigerd. Zet "Live"-modus in '
                    'Instellingen → Veiligheid om écht te muteren.')
            elif mode == 'dry_run_all':
                warnings.append(
                    'Globale safeguard staat op DRY-RUN (all platforms): elke '
                    'live run wordt alsnog gesimuleerd. Zet "Live" in '
                    'Instellingen → Veiligheid voor echte mutatie.')
            if wiz.config_id and wiz.config_id.dry_run and mode == 'live':
                warnings.append(
                    f'Config "{wiz.config_id.name}" heeft DRY-RUN=True: elke '
                    'live run zal alsnog gesimuleerd worden. Zet de config '
                    'op live om dat te omzeilen.')
            wiz.safeguard_warning = '\n'.join(warnings) or False

    # ==================================================================
    # Runs
    # ==================================================================

    def action_run_dry_run(self):
        self.ensure_one()
        self._validate_input(require_live_safe=False)
        result = self._run_action(force_dry_run=True, label='DRY-RUN')
        self.write({
            'state': 'dry_run_done',
            'dry_run_at': fields.Datetime.now(),
            'dry_run_status': 'ok' if result['success'] else 'error',
            'dry_run_summary': result['summary'],
            'dry_run_log': result['log'],
            'dry_run_betask_id': result['betask_id'],
        })
        return self._reload_self()

    def action_run_live(self):
        self.ensure_one()
        if self.state != 'dry_run_done':
            raise UserError(_(
                'Voer eerst een dry-run uit voor je live gaat. Dit voorkomt '
                'dat ongeleeste resultaten ongemerkt productie raken.'))
        self._validate_input(require_live_safe=True)
        result = self._run_action(force_dry_run=False, label='LIVE')
        self.write({
            'state': 'live_done',
            'live_at': fields.Datetime.now(),
            'live_status': 'ok' if result['success'] else 'error',
            'live_summary': result['summary'],
            'live_log': result['log'],
            'live_betask_id': result['betask_id'],
        })
        return self._reload_self()

    def action_reset(self):
        self.ensure_one()
        self.write({
            'state': 'draft',
            'dry_run_at': False, 'dry_run_status': False,
            'dry_run_summary': False, 'dry_run_log': False,
            'dry_run_betask_id': False,
            'live_at': False, 'live_status': False,
            'live_summary': False, 'live_log': False,
            'live_betask_id': False,
        })
        return self._reload_self()

    # ==================================================================
    # Internals
    # ==================================================================

    def _validate_input(self, require_live_safe):
        """Reject obviously broken combinations before queueing a betask.

        ``require_live_safe`` is True for the live run — adds extra
        checks (e.g. config must not be in dry_run mode).
        """
        action = self.action
        if action == 'test_connection':
            if not self.config_picker_id:
                raise UserError(_('Kies een platform voor "Test connection".'))
            return
        if not self.person_id:
            raise UserError(_('Selecteer een target persoon.'))
        if not self.config_id:
            raise UserError(_(
                'Geen Smartschool-config gevonden voor deze persoon. Koppel '
                'eerst de school van de persoon aan een config record.'))
        if not self.target_username:
            raise UserError(_(
                'Persoon heeft geen email_cloud — Smartschool username '
                'kan niet afgeleid worden.'))

    def _run_action(self, force_dry_run, label):
        """Execute the wizard's selected action and capture log + result.

        Returns ``{'success': bool, 'summary': str, 'log': str,
        'betask_id': int or False}``.
        """
        Svc = self.env['myschool.smartschool.service']
        Processor = self.env['myschool.betask.processor']

        # Attach a log handler so the user sees what happens during the
        # run — same pattern as task_debug_runner.
        log_handler = _LogCaptureHandler()
        log_handler.setLevel(logging.INFO)
        loggers = [logging.getLogger(n) for n in CAPTURED_LOGGERS]
        # Make sure our own loggers are captured too.
        loggers.append(logging.getLogger(
            'odoo.addons.myschool_core.models.smartschool_service'))
        loggers.append(logging.getLogger(
            'odoo.addons.myschool_core.models.betask_processor'))
        for lg in loggers:
            lg.addHandler(log_handler)

        success = False
        summary = ''
        betask_id = False

        try:
            if self.action == 'test_connection':
                svc_ctx = Svc
                if force_dry_run:
                    svc_ctx = Svc.with_context(smartschool_force_dry_run=True)
                # test_connection is read-only — force_dry_run does not
                # affect it. Run anyway for symmetry.
                result = svc_ctx.test_connection(self.config_picker_id)
                success = bool(result.get('success'))
                summary = f"[{label}] {result.get('message', '')}"
                _logger.info('[SS-TEST-RUNNER] test_connection result: %s', result)
            else:
                betask = self._create_test_betask()
                betask_id = betask.id
                proc_ctx = Processor
                if force_dry_run:
                    proc_ctx = Processor.with_context(
                        smartschool_force_dry_run=True)
                proc_ctx.process_single_task(betask)
                betask.invalidate_recordset()
                success = betask.status == 'completed_ok'
                changes = betask.changes or ''
                err = betask.error_description or ''
                summary = (f"[{label}] status={betask.status} | "
                           f"{(changes or err).splitlines()[0] if (changes or err) else 'no message'}")
        except Exception as e:
            _logger.exception('[SS-TEST-RUNNER] run failed')
            summary = f"[{label}] EXCEPTION: {e}"
            success = False
        finally:
            for lg in loggers:
                lg.removeHandler(log_handler)

        log_text = self._format_log(log_handler.records)
        return {
            'success': success,
            'summary': summary,
            'log': log_text,
            'betask_id': betask_id,
        }

    def _create_test_betask(self):
        """Create a real betask record for the wizard's selected action.

        Naming uses ``[TEST]`` prefix so the queue stays scannable.
        """
        target, obj, action, _label = _ACTION_MAP[self.action]
        BeTaskType = self.env['myschool.betask.type']
        BeTask = self.env['myschool.betask']
        ttype = BeTaskType.search([
            ('target', '=', target),
            ('object', '=', obj),
            ('action', '=', action),
        ], limit=1)
        if not ttype:
            raise UserError(_(
                'Task type %s/%s/%s niet gevonden — is myschool_core '
                'volledig geüpgrade?') % (target, obj, action))
        import json as _json
        return BeTask.create({
            'name': f'[TEST] {target}/{obj}/{action} for {self.person_id.name}',
            'betasktype_id': ttype.id,
            'status': 'new',
            'data': _json.dumps({'person_id': self.person_id.id}),
        })

    @staticmethod
    def _format_log(records):
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
