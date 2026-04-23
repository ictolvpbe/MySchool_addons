# -*- coding: utf-8 -*-
"""
SAP Sync Test Session
=====================

Persistent, stepwise runner for SAP Informat sync scenarios.

A *session* represents one end-to-end walkthrough of a numbered test-set
directory. Each subfolder becomes a *step*. The user can:

- load/edit the JSON files that each step uploads
- run one step at a time and inspect the Organisation Manager between
- re-run a step, jump back to an earlier step, or reset the session state
  (cleanup of tracked persons/classgroups + replay up to the chosen step)

Two modes:
- employees: tracks a single test person by sap_person_uuid
- students : auto-derives tracked persoonIds and classgroup klasCodes from
             the JSON files in all testset folders
"""

import glob
import json
import logging
import os
import re
import shutil

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CAPTURED_LOGGERS = (
    'odoo.addons.myschool_core.models.informat_service',
    'odoo.addons.myschool_core.models.betask_processor',
    'odoo.addons.myschool_core.models.manual_task_processor',
    'odoo.addons.myschool_core.models.manual_task_service',
    'odoo.addons.myschool_admin.models.sync_test_runner',
)


class _LogCaptureHandler(logging.Handler):
    """Collects log records emitted during a step run for display in the UI."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []
        self.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))

    def emit(self, record):
        try:
            self.records.append(self.format(record))
        except Exception:
            pass


# =============================================================================
# Session
# =============================================================================

class SyncTestSession(models.Model):
    _name = 'myschool.sync.test.session'
    _description = 'SAP Sync Test Session'
    _order = 'create_date desc'

    name = fields.Char(string='Name', required=True, default='New sync test session')
    mode = fields.Selection(
        [('employees', 'Employees'), ('students', 'Klassen & Studenten')],
        string='Mode', required=True, default='employees',
    )
    testsets_path = fields.Char(
        string='Testsets Path', required=True,
        help='Absolute path to the directory containing numbered test-set folders',
    )
    test_person_uuid = fields.Char(
        string='Test Person UUID',
        help='Employees mode: sap_person_uuid of the person to track and clean up',
    )

    tracked_persoon_ids = fields.Text(
        string='Tracked persoonIds', readonly=True,
        help='Students mode: comma-separated list of persoonIds auto-derived from the testsets',
    )
    tracked_classgroups = fields.Text(
        string='Tracked klasCodes', readonly=True,
        help='Students mode: comma-separated list of klasCodes + instnr auto-derived',
    )

    step_ids = fields.One2many('myschool.sync.test.step', 'session_id', string='Steps')
    current_step_id = fields.Many2one('myschool.sync.test.step', string='Current step')

    overall_status = fields.Selection(
        [('pending', 'Pending'),
         ('in_progress', 'In progress'),
         ('done', 'Done')],
        compute='_compute_overall_status', store=True,
    )
    last_run_at = fields.Datetime(string='Last run at', readonly=True)

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        mode = res.get('mode') or 'employees'
        res.setdefault('testsets_path', self._default_testsets_path(mode))
        if mode == 'employees':
            res.setdefault('test_person_uuid', '2dc5c533-5a7a-4b2f-9020-7372345a53bc')
        return res

    @api.onchange('mode')
    def _onchange_mode(self):
        self.testsets_path = self._default_testsets_path(self.mode)
        if self.mode == 'employees' and not self.test_person_uuid:
            self.test_person_uuid = '2dc5c533-5a7a-4b2f-9020-7372345a53bc'

    @staticmethod
    def _default_testsets_path(mode):
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        extra_addons = os.path.dirname(module_dir)
        subdir = 'employees' if mode == 'employees' else 'students'
        return os.path.join(
            extra_addons, 'myschool_core', 'storage', 'sapimport',
            'dev - testsets', subdir,
        )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    @api.depends('step_ids.status')
    def _compute_overall_status(self):
        for rec in self:
            statuses = rec.step_ids.mapped('status')
            if not statuses or all(s == 'pending' for s in statuses):
                rec.overall_status = 'pending'
            elif all(s in ('completed_ok', 'completed_errors') for s in statuses):
                rec.overall_status = 'done'
            else:
                rec.overall_status = 'in_progress'

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_refresh_steps(self):
        """(Re)load the steps from the testsets path. Preserves run results for
        steps whose folder name still matches."""
        self.ensure_one()
        if not self.testsets_path or not os.path.isdir(self.testsets_path):
            raise UserError(f'Testsets path does not exist: {self.testsets_path}')

        Step = self.env['myschool.sync.test.step']
        StepFile = self.env['myschool.sync.test.step.file']

        dirs = self._scan_testset_dirs()
        existing_by_name = {s.name: s for s in self.step_ids}
        seen = set()

        for seq, folder_name, folder_path in dirs:
            seen.add(folder_name)
            step = existing_by_name.get(folder_name)
            if not step:
                step = Step.create({
                    'session_id': self.id,
                    'sequence': seq,
                    'name': folder_name,
                    'folder_path': folder_path,
                })
            else:
                step.write({'sequence': seq, 'folder_path': folder_path})

            # (re)load file list from disk
            existing_files = {f.filename: f for f in step.file_ids}
            current_files = set()
            for fpath in sorted(glob.glob(os.path.join(folder_path, '*.json'))):
                fname = os.path.basename(fpath)
                current_files.add(fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                except OSError as e:
                    content = f'<<< read error: {e} >>>'
                if fname in existing_files:
                    # only overwrite content if the user hasn't edited it (heuristic:
                    # if persisted=True we leave the DB copy)
                    if not existing_files[fname].user_edited:
                        existing_files[fname].content = content
                else:
                    StepFile.create({
                        'step_id': step.id,
                        'filename': fname,
                        'content': content,
                    })
            # prune removed files
            for fname, frec in existing_files.items():
                if fname not in current_files:
                    frec.unlink()

        # prune removed folders
        for name, step in existing_by_name.items():
            if name not in seen:
                step.unlink()

        # students mode: auto-derive tracked persoonIds + klasCodes
        if self.mode == 'students':
            self._derive_tracked_entities_from_testsets()

        if not self.current_step_id and self.step_ids:
            self.current_step_id = self.step_ids.sorted('sequence')[:1]

        return True

    def action_cleanup_and_reset(self):
        """Remove tracked persons / classgroups, mark all steps pending."""
        self.ensure_one()
        cleanup_log = self._cleanup_tracked_entities()
        self.step_ids.write({
            'status': 'pending',
            'last_run_at': False,
            'new_betask_count': 0,
            'processed_ok_count': 0,
            'processed_err_count': 0,
            'debug_output': False,
            'sync_events': False,
        })
        if self.step_ids:
            self.current_step_id = self.step_ids.sorted('sequence')[:1]
        self.env.cr.commit()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cleanup complete',
                'message': f'{len(cleanup_log)} action(s) performed. Steps reset to pending.',
                'sticky': False,
                'type': 'success',
            },
        }

    def action_open_org_manager(self):
        """Open the Organisation Manager client action."""
        action = self.env.ref('myschool_admin.action_object_browser_client').read()[0]
        return action

    # -------------------------------------------------------------------------
    # Helpers — scanning
    # -------------------------------------------------------------------------

    def _scan_testset_dirs(self):
        """Return sorted list of (seq, name, path) for numbered subdirs."""
        out = []
        for entry in os.listdir(self.testsets_path):
            full = os.path.join(self.testsets_path, entry)
            if not os.path.isdir(full):
                continue
            m = re.match(r'^(\d+)', entry)
            if not m:
                continue
            out.append((int(m.group(1)), entry, full))
        out.sort(key=lambda x: (x[0], x[1]))
        return out

    def _derive_tracked_entities_from_testsets(self):
        """Collect every persoonId + (klasCode, instnr) that appears in any
        registration JSON across all testsets. These are the entities whose
        state we want to observe and clean up."""
        persoon_ids = set()
        klas_keys = set()   # (klasCode, instnr)

        for _seq, _name, folder in self._scan_testset_dirs():
            for fname in os.listdir(folder):
                if not fname.startswith('dev-registrations-') or not fname.endswith('.json'):
                    continue
                fpath = os.path.join(folder, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        regs = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                for reg in regs if isinstance(regs, list) else []:
                    pid = reg.get('persoonId')
                    if pid:
                        persoon_ids.add(pid)
                    inst = reg.get('instelnr', '')
                    for k in reg.get('inschrKlassen', []) or []:
                        code = k.get('klasCode')
                        if code:
                            klas_keys.add((code, inst))

        self.tracked_persoon_ids = ','.join(sorted(persoon_ids))
        self.tracked_classgroups = ','.join(
            sorted(f'{c}@{i}' for c, i in klas_keys))

    # -------------------------------------------------------------------------
    # Helpers — cleanup of tracked entities
    # -------------------------------------------------------------------------

    def _cleanup_tracked_entities(self):
        """Delete (or deactivate) only the entities tracked by this session."""
        log = []
        ManualTask = self.env['myschool.manual.task.service']

        if self.mode == 'employees':
            if not self.test_person_uuid:
                return log
            Person = self.env['myschool.person'].with_context(
                active_test=False, skip_manual_audit=True)
            person = Person.search([('sap_person_uuid', '=', self.test_person_uuid)], limit=1)
            if person:
                ManualTask.create_manual_task('PERSON', 'DEL', {'person_id': person.id})
                log.append(f'PERSON/DEL {person.name} ({self.test_person_uuid})')
            BeTask = self.env['myschool.betask']
            related = BeTask.search([('data', 'like', self.test_person_uuid)])
            if related:
                related.unlink()
                log.append(f'Removed {len(related)} related betask(s)')
            return log

        # students mode
        Person = self.env['myschool.person'].with_context(
            active_test=False, skip_manual_audit=True)
        for pid in (self.tracked_persoon_ids or '').split(','):
            pid = pid.strip()
            if not pid:
                continue
            person = Person.search([('sap_person_uuid', '=', pid)], limit=1)
            if person:
                try:
                    ManualTask.create_manual_task('PERSON', 'DEL', {'person_id': person.id})
                    log.append(f'PERSON/DEL {person.name} ({pid})')
                except Exception as e:
                    log.append(f'PERSON/DEL {pid} FAILED: {e}')

        Org = self.env['myschool.org'].with_context(active_test=False)
        OrgType = self.env['myschool.org.type']
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        for key in (self.tracked_classgroups or '').split(','):
            key = key.strip()
            if not key or '@' not in key:
                continue
            code, inst = key.split('@', 1)
            orgs = Org.search([
                ('name_short', '=', code),
                ('inst_nr', '=', inst),
                ('org_type_id', '=', cg_type.id if cg_type else False),
            ])
            for org in orgs:
                try:
                    ManualTask.create_manual_task('ORG', 'DEL', {'org_id': org.id})
                    log.append(f'ORG/DEL {org.name} (id={org.id})')
                except Exception as e:
                    log.append(f'ORG/DEL {org.name} FAILED: {e}')

        BeTask = self.env['myschool.betask']
        for pid in (self.tracked_persoon_ids or '').split(','):
            pid = pid.strip()
            if pid:
                related = BeTask.search([('data', 'like', pid)])
                if related:
                    related.unlink()
                    log.append(f'Removed {len(related)} betask(s) referencing {pid}')

        return log


# =============================================================================
# Step
# =============================================================================

class SyncTestStep(models.Model):
    _name = 'myschool.sync.test.step'
    _description = 'SAP Sync Test Step'
    _order = 'sequence, id'

    session_id = fields.Many2one(
        'myschool.sync.test.session', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='Folder name')
    folder_path = fields.Char(required=True)

    status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed_ok', 'Success'),
        ('completed_errors', 'Errors'),
    ], default='pending')

    last_run_at = fields.Datetime(string='Last run')
    new_betask_count = fields.Integer()
    processed_ok_count = fields.Integer()
    processed_err_count = fields.Integer()
    sync_result = fields.Char(help='Return value of execute_sync()')

    debug_output = fields.Html(string='Debug log')
    sync_events = fields.Html(string='Sync events & tasks')

    file_ids = fields.One2many(
        'myschool.sync.test.step.file', 'step_id', string='JSON files')

    is_current = fields.Boolean(compute='_compute_is_current')
    status_label = fields.Char(compute='_compute_status_label')

    def _compute_is_current(self):
        for rec in self:
            rec.is_current = bool(rec.session_id and rec.session_id.current_step_id == rec)

    def _compute_status_label(self):
        labels = {
            'pending': '⏸ Pending',
            'running': '▶ Running',
            'completed_ok': '✓ Success',
            'completed_errors': '✗ Errors',
        }
        for rec in self:
            rec.status_label = labels.get(rec.status, rec.status)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_jump_to(self):
        """UI-only: mark this step as current so its details show."""
        self.ensure_one()
        self.session_id.current_step_id = self
        return True

    def action_reset_to_here(self):
        """Cleanup the session and replay every earlier step, leaving this
        step as the next-to-run."""
        self.ensure_one()
        session = self.session_id
        earlier = session.step_ids.filtered(lambda s: s.sequence < self.sequence).sorted('sequence')
        session._cleanup_tracked_entities()
        session.step_ids.write({
            'status': 'pending',
            'last_run_at': False,
            'new_betask_count': 0,
            'processed_ok_count': 0,
            'processed_err_count': 0,
            'debug_output': False,
            'sync_events': False,
        })
        self.env.cr.commit()

        for step in earlier:
            step.action_run()
            if step.status != 'completed_ok':
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': f'Replay stopped at step {step.sequence}',
                        'message': f'{step.name} finished with status "{step.status}"',
                        'sticky': True,
                        'type': 'warning',
                    },
                }

        session.current_step_id = self
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Ready',
                'message': f'Replayed {len(earlier)} step(s). Step {self.sequence} is now current.',
                'sticky': False,
                'type': 'success',
            },
        }

    def action_run(self):
        """Execute this single step: write files to dev dir, sync, process tasks."""
        self.ensure_one()
        session = self.session_id
        service = self.env['myschool.informat.service']
        dev_dir = service._get_storage_path_for_students(dev_mode=True) \
            if session.mode == 'students' else service._get_storage_path(dev_mode=True)

        log_handler = _LogCaptureHandler()
        loggers = [logging.getLogger(n) for n in CAPTURED_LOGGERS]
        previous_levels = [(lg, lg.level) for lg in loggers]
        for lg in loggers:
            lg.addHandler(log_handler)
            if lg.level > logging.DEBUG or lg.level == logging.NOTSET:
                lg.setLevel(logging.DEBUG)

        started_at = fields.Datetime.now()
        debug_lines = []
        debug_lines.append(f'=== Step {self.sequence}: {self.name} ===')
        debug_lines.append(f'Mode: {session.mode}')
        debug_lines.append(f'Folder: {self.folder_path}')
        debug_lines.append(f'Dev dir: {dev_dir}')
        debug_lines.append(f'Started: {started_at}')

        self.status = 'running'
        session.current_step_id = self
        self.env.cr.commit()

        try:
            self._flush_files_to_disk(debug_lines)
            self._prepare_dev_dir(dev_dir, debug_lines, session.mode)
            self._copy_folder_to_dev(dev_dir, debug_lines)

            before_tasks = self.env['myschool.betask'].search_count([])
            debug_lines.append(f'BeTasks before sync: {before_tasks}')

            debug_lines.append('--- Running execute_sync(dev_mode=True) ---')
            try:
                sync_result = service.execute_sync(dev_mode=True)
                self.sync_result = str(sync_result)
                debug_lines.append(f'execute_sync returned: {sync_result}')
            except Exception as e:
                debug_lines.append(f'EXCEPTION in execute_sync: {e}')
                self.env.cr.rollback()
                self._finalize_step(
                    started_at, debug_lines, log_handler, status='completed_errors')
                return False

            self.env.cr.commit()

            new_tasks = self._collect_new_tasks(before_tasks)
            self.new_betask_count = len(new_tasks)
            debug_lines.append(f'New BeTasks after sync: {len(new_tasks)}')
            for t in new_tasks:
                debug_lines.append(f'  [{t.status}] {t.task_type_name or t.name} — {t.name}')

            debug_lines.append('--- Processing pending tasks ---')
            pending = self.env['myschool.betask'].search([('status', '=', 'new')])
            if pending:
                processor = self.env['myschool.betask.processor']
                try:
                    proc_result = processor.process_all_pending()
                    debug_lines.append(f'process_all_pending: {proc_result}')
                except Exception as e:
                    debug_lines.append(f'EXCEPTION in process_all_pending: {e}')
                    self.env.cr.rollback()
                    self._finalize_step(
                        started_at, debug_lines, log_handler, status='completed_errors')
                    return False
                self.env.cr.commit()

                ok, err = 0, 0
                processed = self.env['myschool.betask'].browse(pending.ids).exists()
                task_report = []
                for task in processed:
                    task.invalidate_recordset()
                    if task.status == 'completed_ok':
                        ok += 1
                        icon = '✓'
                    else:
                        err += 1
                        icon = '✗'
                    changes = (task.changes or '').splitlines()[:4]
                    task_report.append(
                        f'  {icon} [{task.status}] {task.name}' +
                        ''.join(f'\n      {line}' for line in changes))
                self.processed_ok_count = ok
                self.processed_err_count = err
                debug_lines.append(f'Processed: {ok} ok, {err} error(s)')
                debug_lines.extend(task_report)
                step_status = 'completed_ok' if err == 0 else 'completed_errors'
            else:
                debug_lines.append('No pending tasks to process.')
                self.processed_ok_count = 0
                self.processed_err_count = 0
                step_status = 'completed_ok'

            self._collect_entity_snapshot(debug_lines)
            self._finalize_step(started_at, debug_lines, log_handler, status=step_status)
            return True

        finally:
            for lg in loggers:
                lg.removeHandler(log_handler)
            for lg, lvl in previous_levels:
                lg.setLevel(lvl)

    # -------------------------------------------------------------------------
    # Run helpers
    # -------------------------------------------------------------------------

    def _flush_files_to_disk(self, debug_lines):
        debug_lines.append('--- Writing step files to disk ---')
        for frec in self.file_ids:
            path = os.path.join(self.folder_path, frec.filename)
            try:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(frec.content or '')
                debug_lines.append(f'  wrote {frec.filename} ({len(frec.content or "")} bytes)')
                frec.user_edited = False
            except OSError as e:
                debug_lines.append(f'  FAILED to write {frec.filename}: {e}')

    def _prepare_dev_dir(self, dev_dir, debug_lines, mode):
        debug_lines.append(f'--- Cleaning dev dir ({mode}) ---')
        if mode == 'employees':
            patterns = ['dev-employees-*.json', 'dev-employeeassignments-*.json']
        else:
            patterns = ['dev-students-*.json', 'dev-registrations-*.json']
        for pattern in patterns:
            for f in glob.glob(os.path.join(dev_dir, pattern)):
                try:
                    os.remove(f)
                    debug_lines.append(f'  removed {os.path.basename(f)}')
                except OSError as e:
                    debug_lines.append(f'  FAILED to remove {f}: {e}')

    def _copy_folder_to_dev(self, dev_dir, debug_lines):
        debug_lines.append(f'--- Copying testset -> {dev_dir} ---')
        for f in sorted(glob.glob(os.path.join(self.folder_path, '*.json'))):
            try:
                shutil.copy2(f, dev_dir)
                debug_lines.append(f'  copied {os.path.basename(f)}')
            except OSError as e:
                debug_lines.append(f'  FAILED to copy {f}: {e}')

    def _collect_new_tasks(self, before_count):
        BeTask = self.env['myschool.betask']
        after_count = BeTask.search_count([])
        new_count = after_count - before_count
        if new_count <= 0:
            return BeTask
        return BeTask.search([], order='id desc', limit=new_count).sorted('id')

    def _collect_entity_snapshot(self, debug_lines):
        session = self.session_id
        debug_lines.append('--- Entity snapshot ---')
        if session.mode == 'employees':
            if session.test_person_uuid:
                self._snapshot_person(session.test_person_uuid, debug_lines)
        else:
            for pid in (session.tracked_persoon_ids or '').split(','):
                pid = pid.strip()
                if pid:
                    self._snapshot_person(pid, debug_lines)
            for key in (session.tracked_classgroups or '').split(','):
                key = key.strip()
                if key and '@' in key:
                    code, inst = key.split('@', 1)
                    self._snapshot_classgroup(code, inst, debug_lines)

    def _snapshot_person(self, uuid, debug_lines):
        Person = self.env['myschool.person'].with_context(active_test=False)
        person = Person.search([('sap_person_uuid', '=', uuid)], limit=1)
        if not person:
            debug_lines.append(f'  person[{uuid}]: NOT FOUND')
            return
        details = person.person_details_set
        detail_parts = []
        for d in details:
            inst = getattr(d, 'institution_nr', None) or getattr(d, 'inst_nr', '?')
            detail_parts.append(f'{inst}(active={d.is_active})')
        debug_lines.append(
            f'  person[{uuid}]: {person.name}, is_active={person.is_active}, '
            f'details=[{", ".join(detail_parts) or "-"}]')

    def _snapshot_classgroup(self, code, inst, debug_lines):
        Org = self.env['myschool.org'].with_context(active_test=False)
        OrgType = self.env['myschool.org.type']
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        orgs = Org.search([
            ('name_short', '=', code),
            ('inst_nr', '=', inst),
            ('org_type_id', '=', cg_type.id if cg_type else False),
        ])
        if not orgs:
            debug_lines.append(f'  classgroup[{code}@{inst}]: NOT FOUND')
            return
        for o in orgs:
            debug_lines.append(
                f'  classgroup[{code}@{inst}]: {o.name}, is_active={o.is_active}')

    def _finalize_step(self, started_at, debug_lines, log_handler, status):
        self.status = status
        self.last_run_at = started_at
        sync_events_html = self._render_sync_events(started_at)
        debug_html = '<pre style="white-space:pre-wrap; font-family:monospace;">' \
            + self._escape_html('\n'.join(debug_lines)) \
            + '</pre>'
        if log_handler.records:
            debug_html += '<h5>Captured logs</h5>' \
                + '<pre style="white-space:pre-wrap; font-family:monospace; font-size:90%;">' \
                + self._escape_html('\n'.join(log_handler.records)) \
                + '</pre>'
        self.debug_output = debug_html
        self.sync_events = sync_events_html
        self.env.cr.commit()

    def _render_sync_events(self, started_at):
        SysEvent = self.env['myschool.sys.event'].with_context(active_test=False)
        events = SysEvent.search([('create_date', '>=', started_at)], order='id asc')
        rows = []
        for e in events:
            rows.append(
                f'<tr><td>{e.id}</td><td>{e.eventcode or ""}</td>'
                f'<td>{self._escape_html(e.name or "")}</td>'
                f'<td>{e.priority or ""}</td></tr>')

        BeTask = self.env['myschool.betask']
        new_tasks = BeTask.search([('create_date', '>=', started_at)], order='id asc')
        task_rows = []
        for t in new_tasks:
            changes = self._escape_html((t.changes or '').strip())[:400]
            task_rows.append(
                f'<tr><td>{t.id}</td>'
                f'<td>{t.task_type_name or ""}</td>'
                f'<td>{t.status or ""}</td>'
                f'<td>{self._escape_html(t.name or "")}</td>'
                f'<td><pre style="white-space:pre-wrap; margin:0;">{changes}</pre></td></tr>')

        html = ''
        if rows:
            html += '<h5>Sys events</h5>' \
                + '<table class="table table-sm"><thead><tr>' \
                + '<th>id</th><th>code</th><th>message</th><th>prio</th>' \
                + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        if task_rows:
            html += '<h5>BeTasks created during step</h5>' \
                + '<table class="table table-sm"><thead><tr>' \
                + '<th>id</th><th>type</th><th>status</th><th>name</th><th>changes</th>' \
                + '</tr></thead><tbody>' + ''.join(task_rows) + '</tbody></table>'
        return html or '<p><em>No sys events or betasks recorded.</em></p>'

    @staticmethod
    def _escape_html(s):
        if not s:
            return ''
        return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# =============================================================================
# Step file
# =============================================================================

class SyncTestStepFile(models.Model):
    _name = 'myschool.sync.test.step.file'
    _description = 'SAP Sync Test Step — File'
    _order = 'filename'

    step_id = fields.Many2one(
        'myschool.sync.test.step', required=True, ondelete='cascade')
    filename = fields.Char(required=True)
    content = fields.Text(string='JSON content')
    user_edited = fields.Boolean(default=False)
    size_bytes = fields.Integer(compute='_compute_size', string='Size (bytes)')

    @api.depends('content')
    def _compute_size(self):
        for rec in self:
            rec.size_bytes = len(rec.content or '')

    def write(self, vals):
        if 'content' in vals:
            vals.setdefault('user_edited', True)
        return super().write(vals)

    def action_save_to_disk(self):
        for rec in self:
            path = os.path.join(rec.step_id.folder_path, rec.filename)
            try:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(rec.content or '')
                rec.user_edited = False
            except OSError as e:
                raise UserError(f'Could not write {path}: {e}')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Saved',
                'message': f'{len(self)} file(s) written to disk.',
                'sticky': False,
                'type': 'success',
            },
        }

    def action_reload_from_disk(self):
        for rec in self:
            path = os.path.join(rec.step_id.folder_path, rec.filename)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    rec.content = fh.read()
                rec.user_edited = False
            except OSError as e:
                raise UserError(f'Could not read {path}: {e}')
        return True

    def action_validate_json(self):
        errors = []
        for rec in self:
            try:
                json.loads(rec.content or 'null')
            except json.JSONDecodeError as e:
                errors.append(f'{rec.filename}: {e}')
        if errors:
            raise UserError('JSON validation errors:\n' + '\n'.join(errors))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Valid JSON',
                'message': f'{len(self)} file(s) parsed successfully.',
                'sticky': False,
                'type': 'success',
            },
        }
