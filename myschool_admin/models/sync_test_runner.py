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


# =============================================================================
# Expected outcome catalog
# =============================================================================
# Per testset folder name: the human-readable description of what the step
# should accomplish plus a list of checks that get verified against the DB
# after the step has run. See `SyncTestStep._run_expectation_checks`.
#
# Each check is a dict with a `type` and type-specific arguments:
#   - classgroup_active:   name_short   [, inst_nr]
#   - classgroup_inactive: name_short
#   - classgroup_inactive_at: name_short, inst_nr
#   - person_exists_active: uuid
#   - person_inactive_or_ended: uuid
#   - person_reg_end_empty: uuid
#   - person_active_class: uuid, klas_code
#   - person_not_in_class: uuid, klas_code
#   - person_reg_inst_nr: uuid, inst_nr
# =============================================================================

EXPECTATIONS = {
    '1 - Class add': {
        'description': (
            'Gourmand (a65d06d9…) krijgt een tweede open inschrijving: klas '
            '3NAWEa komt naast de bestaande 3NAWEb. Beide klassen moeten '
            'actief zijn in 038281.'
        ),
        'checks': [
            {'type': 'classgroup_active', 'name_short': '3NAWEb'},
            {'type': 'classgroup_active', 'name_short': '3NAWEa'},
            {'type': 'person_exists_active', 'uuid': 'a65d06d9-7250-4660-b0b1-6b319d1ca286'},
            {'type': 'person_reg_inst_nr', 'uuid': 'a65d06d9-7250-4660-b0b1-6b319d1ca286', 'inst_nr': '038281'},
        ],
    },
    '2 - Class move to other instnr': {
        'description': (
            'De klas 5BEORb (met enig lid Ouchan) verhuist van 038307 naar '
            '038281. De klas blijft bestaan (geen DEACT/ADD), enkel inst_nr '
            'wijzigt. Ouchan (b163d052…) krijgt reg_inst_nr=038281.'
        ),
        'checks': [
            {'type': 'classgroup_active', 'name_short': '5BEORb', 'inst_nr': '038281'},
            {'type': 'classgroup_inactive_at', 'name_short': '5BEORb', 'inst_nr': '038307'},
            {'type': 'person_reg_inst_nr', 'uuid': 'b163d052-d88f-4972-a74a-6ac689f8fdf0', 'inst_nr': '038281'},
            {'type': 'person_active_class', 'uuid': 'b163d052-d88f-4972-a74a-6ac689f8fdf0', 'klas_code': '5BEORb'},
        ],
    },
    '3 - class deact': {
        'description': (
            'Buysse (a90bd8f1…) verhuist van 3GRLA naar 3ECWE4. 3GRLA raakt '
            'leeg maar blijft actief (auto-deact gebeurt niet — opruiming '
            'volgt bij schooljaar-init). 3ECWE4 actief en bevat Buysse.'
        ),
        'checks': [
            {'type': 'classgroup_active', 'name_short': '3ECWE4'},
            {'type': 'person_active_class', 'uuid': 'a90bd8f1-e497-4b7a-87ba-6b27e7c6c049', 'klas_code': '3ECWE4'},
            {'type': 'person_not_in_class', 'uuid': 'a90bd8f1-e497-4b7a-87ba-6b27e7c6c049', 'klas_code': '3GRLA'},
        ],
    },
    '4 - add students': {
        'description': (
            'Twee nieuwe leerlingen — Jansen Emma in 038281/1ONTAa en '
            'De Smet Lars in 038307/3BEORb. Beide moeten bestaan en aan '
            'hun klas gekoppeld zijn.'
        ),
        'checks': [
            {'type': 'person_exists_active', 'uuid': 'c1111111-0000-4000-8000-000000000281'},
            {'type': 'person_exists_active', 'uuid': 'c2222222-0000-4000-8000-000000000307'},
            {'type': 'person_active_class', 'uuid': 'c1111111-0000-4000-8000-000000000281', 'klas_code': '1ONTAa'},
            {'type': 'person_active_class', 'uuid': 'c2222222-0000-4000-8000-000000000307', 'klas_code': '3BEORb'},
        ],
    },
    '5 - classmove-to-other-instnr': {
        'description': (
            'Karpenko (a8aac5cc…) verhuist individueel van 038307/3BEORb '
            'naar 038281/3ECWE4. Beide reg_inst_nr en klas wijzigen. '
            '3BEORb in 038307 kan leeg raken maar blijft actief.'
        ),
        'checks': [
            {'type': 'person_reg_inst_nr', 'uuid': 'a8aac5cc-2e07-4766-9228-2d7dd1d7b193', 'inst_nr': '038281'},
            {'type': 'person_active_class', 'uuid': 'a8aac5cc-2e07-4766-9228-2d7dd1d7b193', 'klas_code': '3ECWE4'},
            {'type': 'person_not_in_class', 'uuid': 'a8aac5cc-2e07-4766-9228-2d7dd1d7b193', 'klas_code': '3BEORb'},
        ],
    },
    '5 - reactivate student in other class': {
        'description': (
            'Belhaj (4c8b3375…) was uitgeschreven (reg_end_date gezet). '
            'Nieuwe JSON haalt de einddatum weg en zet hem in 3BEORb. '
            'Persoon actief, reg_end_date leeg, actieve klas=3BEORb.'
        ),
        'checks': [
            {'type': 'person_exists_active', 'uuid': '4c8b3375-c9a8-442f-b88a-c6e2fa03b786'},
            {'type': 'person_reg_end_empty', 'uuid': '4c8b3375-c9a8-442f-b88a-c6e2fa03b786'},
            {'type': 'person_active_class', 'uuid': '4c8b3375-c9a8-442f-b88a-c6e2fa03b786', 'klas_code': '3BEORb'},
        ],
    },
    '6 - classmove-in-same-instnr': {
        'description': (
            'Wagenaar (07e582c9…) verhuist binnen 038281 van 1DOEa naar 1DOEb. '
            'Actieve klas=1DOEb, niet meer als lid van 1DOEa.'
        ),
        'checks': [
            {'type': 'person_active_class', 'uuid': '07e582c9-4182-474e-9473-a0e4f6bc3ba9', 'klas_code': '1DOEb'},
            {'type': 'person_not_in_class', 'uuid': '07e582c9-4182-474e-9473-a0e4f6bc3ba9', 'klas_code': '1DOEa'},
            {'type': 'classgroup_active', 'name_short': '1DOEb'},
        ],
    },
    '7 -  deactivate student': {
        'description': (
            'Zirjaoui (6e32356f…) wordt uitgeschreven met einddatum '
            '2026-02-28. Persoon moet inactief zijn of reg_end_date '
            'gezet hebben.'
        ),
        'checks': [
            {'type': 'person_inactive_or_ended', 'uuid': '6e32356f-790a-44c8-86d4-595b8880c088'},
        ],
    },

    # =========================================================================
    # Employees-mode testset — testpersoon Mark Demeyer
    #   uuid     : 2dc5c533-5a7a-4b2f-9020-7372345a53bc
    #   instnrs  : 011007  &  143651
    # De checks volgen de nieuwe lifecycle:
    #   pending_since gezet ↔ geen actieve assignments meer
    #   account suspend gebeurt pas via cron na EmployeeSuspendPeriod
    # =========================================================================

    '1- new 1 instnr no hoofdambt': {
        'description': (
            'Nieuwe employee in 011007 zonder hoofd_ambt. Persoon wordt '
            'aangemaakt en is actief; PersonDetails voor 011007 actief; '
            'pending_since blijft leeg (assignments zijn aanwezig).'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_details_inst',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '011007'},
        ],
    },
    '2-new 2de instnr geen hoofdambt': {
        'description': (
            'Tweede instnr 143651 wordt toegevoegd (zonder hoofd_ambt). '
            'PersonDetails voor 011007 én 143651 staan actief.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_details_inst',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '011007'},
            {'type': 'person_details_inst',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '143651'},
        ],
    },
    '3>-1ste+ 2de  instnr +hoofdambt': {
        'description': (
            'Beide instnrs krijgen een hoofd_ambt: 011007=00000255 '
            '(ict-coordinator), 143651=00000007 (Leraar). Persoon actief '
            'met active proprelations.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_hoofd_ambt',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '011007', 'code': '00000255'},
            {'type': 'person_hoofd_ambt',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '143651', 'code': '00000007'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '4-2de instnr +hoofdambt wijzigt': {
        'description': (
            'inst 143651 hoofd_ambt verandert van 00000007 (Leraar) naar '
            '00000255 (ict-coordinator). Nieuwe actieve PersonDetails-versie '
            'voor 143651 met de nieuwe code.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_hoofd_ambt',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '143651', 'code': '00000255'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '5-change extradata': {
        'description': (
            'Wijziging van bank/iban/adres-extradata zonder impact op '
            'lifecycle. Persoon blijft actief, geen suspend.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '6-change Persondata': {
        'description': (
            'Wijziging van persoonsdata (initialen, geboortedatum, hoofdAmbt '
            'naam …). Persoon blijft actief; PersonDetails-versies vernieuwd.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '7-change Persondata + persondata': {
        'description': (
            'Combineerde wijziging persoonsdata + iban. Persoon blijft '
            'actief en buiten de suspend-pipeline.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '8-change inst1 hoofdambt': {
        'description': (
            'inst 011007 hoofd_ambt verandert naar 00000007 (Leraar). '
            'Persoon actief, PersonDetails voor 011007 toont nieuwe code.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_hoofd_ambt',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc',
             'inst_nr': '011007', 'code': '00000007'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '9-inst1 assignment weg': {
        'description': (
            'inst 011007 verliest zijn assignment (lege assignmentsfile). '
            'inst 143651 heeft nog wel assignments → cross-instnr check ziet '
            'actieve assignments → pending_since blijft leeg, persoon actief, '
            'minstens 1 actieve proprelation.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_has_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '10-inst2 assignment weg': {
        'description': (
            'Nu vallen ook de inst 143651 assignments weg → géén actieve '
            'assignments meer. pending_since=today, alle proprelations '
            'inactief, maar account zelf blijft actief (suspend-grace).'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_set',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_no_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '11-inst1 + inst2 assignment terug': {
        'description': (
            'Beide instnrs hebben opnieuw assignments → suspend-clock stopt '
            '(pending_since geleegd). Phase 2 herstelt PPSBR-proprelations.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_has_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '12-inst1 + inst2 pensioendatum niet in toekomst': {
        'description': (
            'Beide instnrs krijgen een pensioendatum in het verleden '
            '(2024-12-01). should_deactivate_instnr triggert per inst → '
            'PROPRELATION/DEACT tasks. Na de post-sync sweep zit de persoon '
            'in de suspend-pipeline (account nog actief, alle proprelations '
            'inactief, pending_since gezet).'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_set',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_no_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '13 -  inst1 + 2 pensioendatum weg': {
        'description': (
            'Pensioendatum gewist op beide instnrs. Persoon is nooit '
            'gedeactiveerd geweest (zat enkel in suspend), should_deactivate '
            'triggert niet meer; pending_since wordt gewist; Phase 2 herstelt '
            'PPSBR-proprelations vanuit de assignments.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_empty',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_has_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
    '14 -  inst1 + 2 isactive false': {
        'description': (
            'Beide instnrs krijgen isActive=false. should_deactivate_instnr '
            'triggert → PROPRELATION/DEACT tasks. Post-sync sweep zet de '
            'suspend-clock; account zelf blijft actief tot de cron na '
            'EmployeeSuspendPeriod.'
        ),
        'checks': [
            {'type': 'person_exists_active',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_pending_since_set',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
            {'type': 'person_no_active_proprelations',
             'uuid': '2dc5c533-5a7a-4b2f-9020-7372345a53bc'},
        ],
    },
}


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
        help='Students mode: comma-separated list of klasCode@instnr auto-derived',
    )

    skip_ldap_processing = fields.Boolean(
        string='Skip LDAP processing', default=True,
        help='When checked, LDAP/AD tasks generated by the sync are marked as '
             'skipped (completed_ok, no action). Useful to test purely against '
             'the local database without an LDAP server configured.',
    )

    step_ids = fields.One2many('myschool.sync.test.step', 'session_id', string='Steps')
    current_step_id = fields.Many2one('myschool.sync.test.step', string='Current step')

    overall_status = fields.Selection(
        [('pending', 'Pending'),
         ('in_progress', 'In progress'),
         ('done', 'Done')],
        default='pending',
    )
    last_run_at = fields.Datetime(string='Last run at', readonly=True)

    cleanup_log = fields.Html(
        string='Last cleanup log', readonly=True, sanitize=False,
        help='Per-record outcome of the most recent Cleanup & Reset run.')

    # ---- Tree-position diagnose -----------------------------------------
    diag_person_id = fields.Many2one(
        'myschool.person', string='Diagnose person',
        help='Pick the person to inspect: PPSBR / role priority / BRSO / SR-BR.')
    diag_report_html = fields.Html(
        string='Diagnose report', readonly=True, sanitize=False,
        help='Output of the last "Diagnose tree position" run.')
    diag_target_org = fields.Char(
        string='Resolved target org', readonly=True,
        help='What target org the current PERSON-TREE logic picks.')

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
    # Actions
    # -------------------------------------------------------------------------

    def action_refresh_steps(self):
        """(Re)load the steps from the testsets path. Preserves run results
        for steps whose folder name still matches."""
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
            spec = EXPECTATIONS.get(folder_name)
            summary_html = self._render_expectations_summary(folder_name, spec)
            step = existing_by_name.get(folder_name)
            if not step:
                step = Step.create({
                    'session_id': self.id,
                    'sequence': seq,
                    'name': folder_name,
                    'folder_path': folder_path,
                    'expectations_summary': summary_html,
                })
            else:
                step.write({
                    'sequence': seq,
                    'folder_path': folder_path,
                    'expectations_summary': summary_html,
                })

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
                    if not existing_files[fname].user_edited:
                        existing_files[fname].content = content
                else:
                    StepFile.create({
                        'step_id': step.id,
                        'filename': fname,
                        'content': content,
                    })
            for fname, frec in existing_files.items():
                if fname not in current_files:
                    frec.unlink()

        for name, step in existing_by_name.items():
            if name not in seen:
                step.unlink()

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
            'expectations_result': False,
            'expectations_pass_count': 0,
            'expectations_fail_count': 0,
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
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_open_org_manager(self):
        """Open the Organisation Manager client action."""
        action = self.env.ref('myschool_admin.action_object_browser_client').read()[0]
        return action

    def action_recompute_person_tree(self):
        """Trigger ``betask_processor._update_person_tree_position`` for the
        diagnose person directly. Bypasses the sync — useful to verify
        the resolver works given the current PPSBRs/BRSOs without having
        to re-run a whole testset."""
        self.ensure_one()
        person = self._resolve_diag_person()
        if not person:
            return self._diag_notify(
                'No person', 'Pick a person (or set Test Person UUID).',
                'warning')
        processor = self.env['myschool.betask.processor']
        ok = processor._update_person_tree_position(person)
        # Re-render the diagnose so the user sees the new state.
        self.action_diagnose_tree_position()
        return self._diag_notify(
            'PERSON-TREE recompute',
            f'Recomputed tree for {person.name} — '
            f'{"OK" if ok else "returned False (check sys-events for PROPREL-900)"}.',
            'success' if ok else 'warning')

    def action_migrate_group_flags(self):
        """One-shot migration: roll legacy BRSO/role group-flags up into
        ``org.has_comgroup`` / ``has_secgroup`` / ``has_odoo_group`` plus
        ``odoo_group_ids``. Idempotent."""
        self.ensure_one()
        Org = self.env['myschool.org']
        result = Org._migrate_group_flags_from_legacy()
        return self._diag_notify(
            'Group flags migration',
            f"Updated {result.get('orgs_updated', 0)} org(s); "
            f"flags set: {result.get('flags_set', {})}.",
            'success')

    def action_force_reload_from_disk(self):
        """Re-read every step file from disk into the DB, regardless of
        the per-file ``user_edited`` flag. Use after editing testset
        files outside the UI (e.g. shell-based bulk update) — otherwise
        ``_flush_files_to_disk`` would overwrite your disk changes with
        the (now-stale) DB content on the next run."""
        self.ensure_one()
        reloaded = skipped = 0
        for step in self.step_ids:
            for frec in step.file_ids:
                path = os.path.join(step.folder_path, frec.filename)
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        disk = fh.read()
                except OSError:
                    skipped += 1
                    continue
                if frec.content != disk:
                    # super().write to skip the user_edited side effect.
                    super(SyncTestStepFile, frec).write({
                        'content': disk,
                        'user_edited': False,
                    })
                    reloaded += 1
                else:
                    # Make sure the flag is honest even when content matches.
                    if frec.user_edited:
                        super(SyncTestStepFile, frec).write({'user_edited': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Force reload from disk',
                'message': f'Reloaded {reloaded} file(s), skipped {skipped} unreadable.',
                'type': 'success' if reloaded or not skipped else 'warning',
                'sticky': False,
            },
        }

    # =====================================================================
    # PERSON-TREE diagnose
    # =====================================================================

    def action_diagnose_tree_position(self):
        """Inspect what `_update_person_tree_position` would do for a
        chosen person. Renders an HTML report covering:
        - active PPSBR rows (role + effective priority + org)
        - SR-BR mappings for every distinct role on those PPSBRs
        - active BRSO rows for every distinct role
        - the role / target_org the selection would produce now
        - the current active PERSON-TREE row (if any)
        """
        self.ensure_one()
        person = self._resolve_diag_person()
        if not person:
            return self._diag_notify(
                'No person', 'Pick a person (or set Test Person UUID).',
                'warning')

        PropRelationType = self.env['myschool.proprelation.type']
        PropRelation = self.env['myschool.proprelation']
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        sr_br_type = PropRelationType.search([('name', '=', 'SRBR')], limit=1)
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)

        ppsbrs = PropRelation.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id', '=', ppsbr_type.id if ppsbr_type else 0),
            ('is_active', '=', True),
        ]) if ppsbr_type else PropRelation.browse()

        sections = []
        sections.append(self._diag_render_header(person))
        sections.append(self._diag_render_ppsbr_table(ppsbrs))

        # Pick winner using the same logic as _update_person_tree_position.
        winner = self._diag_pick_winner(ppsbrs)
        sections.append(self._diag_render_selection(winner, ppsbrs))

        # Pull SAP roles from the person's stored assignments JSON so the
        # SRBR section also covers roles that aren't on a PPSBR yet (the
        # exact case when PPSBR-creation failed earlier).
        sap_roles_from_assignments = self._diag_collect_sap_roles_from_assignments(person)

        # SRBR mappings for: roles on PPSBR ∪ SAP roles in assignments.
        sections.append(self._diag_render_sr_br(
            ppsbrs, sr_br_type, PropRelation,
            extra_role_ids=sap_roles_from_assignments))

        # All active SRBRs (independent of role-set) — lets the user see
        # whether the records are stored with the convention the lookups
        # expect (SAP in id_role or id_role_child, Backend in id_role_parent).
        sections.append(self._diag_render_all_sr_br(sr_br_type, PropRelation))

        # BRSOs per role.
        sections.append(self._diag_render_brso(
            ppsbrs, brso_type, PropRelation, person))

        # Result: target_org if the algorithm ran now.
        target_org, target_log = self._diag_compute_target_org(
            winner, brso_type, PropRelation)
        sections.append(self._diag_render_target(target_org, target_log))

        # Current PERSON-TREE row.
        current_tree = PropRelation.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id', '=', person_tree_type.id if person_tree_type else 0),
            ('is_active', '=', True),
        ]) if person_tree_type else PropRelation.browse()
        sections.append(self._diag_render_current_tree(current_tree))

        # Persongroup memberships and per-target persongroup status.
        sections.append(self._diag_render_persongroup_state(person))

        # Recent betasks for this person (helps spot failed PPSBR-ADDs).
        sections.append(self._diag_render_recent_betasks(person))

        # Recent sys-events touching this person — Phase 2 logs explicit
        # BETASK-DEBUG events per active employee that confirm whether
        # the assignments-loop ran for them.
        sections.append(self._diag_render_recent_sys_events(person))

        self.diag_report_html = '\n'.join(sections)
        self.diag_target_org = (target_org.name if target_org else '(none)')
        return False

    def _resolve_diag_person(self):
        if self.diag_person_id:
            return self.diag_person_id
        if self.test_person_uuid:
            person = self.env['myschool.person'].search(
                [('sap_person_uuid', '=', self.test_person_uuid)], limit=1)
            if person:
                self.diag_person_id = person
                return person
        return None

    def _diag_notify(self, title, message, kind='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': False},
        }

    @staticmethod
    def _diag_eff_priority(role):
        """Mirror the rule in betask_processor._update_person_tree_position
        line ~3281: priority = role.priority if role.priority else 9999."""
        return role.priority if role and role.priority else 9999

    def _diag_pick_winner(self, ppsbrs):
        """Pick the (ppsbr, role, eff_priority) the same way
        _update_person_tree_position does (master overrides priority)."""
        master = next((p for p in ppsbrs if p.is_master), None)
        if master:
            return (master, master.id_role,
                    self._diag_eff_priority(master.id_role), 'master')
        seen = {}
        for p in ppsbrs:
            if not p.id_role:
                continue
            if p.id_role.id in seen:
                continue
            seen[p.id_role.id] = (p, p.id_role,
                                  self._diag_eff_priority(p.id_role), 'priority')
        if not seen:
            return None
        return min(seen.values(), key=lambda v: v[2])

    def _diag_compute_target_org(self, winner, brso_type, PropRelation):
        """Replicate Step-4 of _update_person_tree_position."""
        if not winner:
            return None, ['No PPSBR with a role — algorithm returns early.']
        ppsbr, role, prio, _ = winner
        log = []

        processor = self.env.get('myschool.betask.processor')
        ppsbr_school = ppsbr.id_org_parent or ppsbr.id_org
        if ppsbr_school and processor is not None and \
                hasattr(processor, '_resolve_school_org'):
            try:
                ppsbr_school = processor._resolve_school_org(ppsbr_school)
            except Exception as e:
                log.append(f'_resolve_school_org failed: {e}')

        log.append(
            f'Lookup school for BRSO: '
            f'{ppsbr_school.name if ppsbr_school else "(none)"} '
            f'(ID={ppsbr_school.id if ppsbr_school else "-"})')

        target_org = None
        if brso_type:
            domain = [
                ('id_role', '=', role.id),
                ('proprelation_type_id', '=', brso_type.id),
                ('is_active', '=', True),
                ('id_org', '!=', False),
            ]
            if ppsbr_school:
                domain.append(('id_org_parent', '=', ppsbr_school.id))
            brso = PropRelation.search(domain, limit=1)
            if brso:
                target_org = brso.id_org
                log.append(
                    f'BRSO match → id={brso.id}, name={brso.name}, '
                    f'target id_org={target_org.name} (id={target_org.id})')
            else:
                log.append('No BRSO match for role + school')

        if not target_org and ppsbr.id_org:
            target_org = ppsbr.id_org
            log.append(
                f'FALLBACK to PPSBR.id_org = {target_org.name} '
                f'(id={target_org.id})')

        if target_org and target_org.is_administrative \
                and processor is not None \
                and hasattr(processor, '_find_non_administrative_parent_org'):
            try:
                resolved = processor._find_non_administrative_parent_org(target_org)
                if resolved:
                    log.append(
                        f'target_org admin → resolved to '
                        f'{resolved.name} (id={resolved.id})')
                    target_org = resolved
            except Exception as e:
                log.append(f'_find_non_administrative_parent_org failed: {e}')

        return target_org, log

    # ----- Renderers ---------------------------------------------------------

    @staticmethod
    def _diag_html_escape(value):
        if value is None:
            return ''
        s = str(value)
        return (s.replace('&', '&amp;').replace('<', '&lt;')
                 .replace('>', '&gt;').replace('"', '&quot;'))

    def _diag_render_header(self, person):
        e = self._diag_html_escape
        school = ''
        if hasattr(person, 'id_school_org') and person.id_school_org:
            school = f' · School: {e(person.id_school_org.name)}'
        return (
            f'<h3 class="mt-0">Diagnose: {e(person.name)} '
            f'<small class="text-muted">(id={person.id}, '
            f'uuid={e(person.sap_person_uuid or "")})</small></h3>'
            f'<p class="text-muted mb-2">person_type: '
            f'{e(person.person_type_id.name) if person.person_type_id else "(none)"}'
            f'{school}</p>')

    def _diag_render_ppsbr_table(self, ppsbrs):
        e = self._diag_html_escape
        if not ppsbrs:
            return ('<h4>Active PPSBRs</h4>'
                    '<p class="text-warning">No active PPSBRs.</p>')
        rows = []
        for p in ppsbrs:
            role = p.id_role
            eff = self._diag_eff_priority(role)
            raw = role.priority if role else ''
            rows.append(
                f'<tr><td>{p.id}</td>'
                f'<td>{e(role.name) if role else "<i>none</i>"}</td>'
                f'<td>{e(role.id) if role else ""}</td>'
                f'<td>{e(raw)}</td>'
                f'<td><b>{e(eff)}</b></td>'
                f'<td>{e(p.id_org.name) if p.id_org else ""}</td>'
                f'<td>{e(p.id_org_parent.name) if p.id_org_parent else ""}</td>'
                f'<td>{"✓" if p.is_master else ""}</td>'
                f'<td>{"auto" if p.automatic_sync else "manual"}</td></tr>')
        return (
            '<h4>Active PPSBRs</h4>'
            '<table class="table table-sm table-striped">'
            '<thead><tr>'
            '<th>id</th><th>role</th><th>role.id</th>'
            '<th>raw priority</th><th>effective</th>'
            '<th>id_org</th><th>id_org_parent</th>'
            '<th>master?</th><th>sync</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table>'
            '<p class="text-muted mb-2"><small>'
            'Effective priority follows '
            '<code>role.priority if role.priority else 9999</code> '
            '(0/unset → 9999, lowest rank).'
            '</small></p>')

    def _diag_render_selection(self, winner, ppsbrs):
        if not winner:
            return ('<h4>Selection</h4>'
                    '<p class="text-warning">No selectable PPSBR.</p>')
        ppsbr, role, prio, reason = winner
        e = self._diag_html_escape
        return (
            '<h4>Selection</h4>'
            f'<p>Winner: <b>{e(role.name) if role else "(none)"}</b> '
            f'(role.id={e(role.id) if role else "-"}, '
            f'effective priority=<b>{e(prio)}</b>, '
            f'via <code>{reason}</code>) — '
            f'PPSBR id={ppsbr.id}</p>')

    def _diag_collect_sap_roles_from_assignments(self, person):
        """Parse `assignments` JSON on the person's PersonDetails rows and
        return the SAP-role ids matched by `ambtCode` shortname. Helps the
        diagnose see roles that should map but have no PPSBR yet."""
        Details = self.env['myschool.person.details']
        Role = self.env['myschool.role']
        details = Details.search([('person_id', '=', person.id)])
        codes = set()
        for d in details:
            raw = d.assignments or ''
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                parsed = [parsed]
            if not isinstance(parsed, list):
                continue
            for a in parsed:
                if isinstance(a, dict):
                    code = a.get('ambtCode') or a.get('ambt_code')
                    if code:
                        codes.add(str(code).strip())
        if not codes:
            return []
        roles = Role.search([('shortname', 'in', list(codes))])
        return roles.ids

    def _diag_render_sr_br(self, ppsbrs, sr_br_type, PropRelation,
                           extra_role_ids=None):
        """Show SR-BR rows whose `id_role` / `id_role_child` / `id_role_parent`
        touches any of the person's PPSBR roles. The canonical creator
        (`proprelation_service.create_sr_br`) sets only `id_role_child`
        (SAP) and `id_role_parent` (Backend) — `id_role` is left empty.
        Both informat_service and the betask processor also do SR-BR
        lookups; if conventions diverge between callers, the SAP→Backend
        mapping silently breaks. The three role columns make any such
        mismatch obvious."""
        e = self._diag_html_escape
        if not sr_br_type:
            return '<h4>SRBR mappings</h4><p class="text-muted">No SRBR type defined.</p>'
        role_ids = {p.id_role.id for p in ppsbrs if p.id_role}
        role_ids.update(extra_role_ids or [])
        role_ids = list(role_ids)
        if not role_ids:
            return '<h4>SRBR mappings</h4><p class="text-muted">No roles to map (no PPSBR roles, no assignments-derived SAP roles).</p>'
        rels = PropRelation.search([
            ('proprelation_type_id', '=', sr_br_type.id),
            ('is_active', '=', True),
            '|', '|',
            ('id_role', 'in', role_ids),
            ('id_role_child', 'in', role_ids),
            ('id_role_parent', 'in', role_ids),
        ])
        Role = self.env['myschool.role']
        role_recs = Role.browse(role_ids)
        role_summary = ', '.join(
            f'{r.name} <small>(id={r.id}, sn={r.shortname or "—"})</small>'
            for r in role_recs)
        if not rels:
            return (
                '<h4>SRBR mappings</h4>'
                '<p class="text-warning">No active SRBR row touches any of '
                'the inspected roles.</p>'
                f'<p class="text-muted"><small>Inspected role-ids: {role_summary}<br/>'
                'Lookup tested across <code>id_role</code>, '
                '<code>id_role_child</code>, <code>id_role_parent</code>.</small></p>')

        def cell(role):
            if not role:
                return '<span class="text-muted">—</span>'
            return f'{e(role.name)} <small>(id={role.id}, p={e(role.priority)})</small>'

        rows = []
        for r in rels:
            warn = ''
            if not r.id_role_parent:
                warn = (' <span class="badge text-bg-danger">'
                        'id_role_parent empty — betask processor '
                        '<code>process_db_proprelation_add</code> will '
                        'reject this mapping</span>')
            rows.append(
                f'<tr><td>{r.id}</td>'
                f'<td>{cell(r.id_role)}</td>'
                f'<td>{cell(r.id_role_child)}</td>'
                f'<td>{cell(r.id_role_parent)}{warn}</td>'
                f'<td>{e(r.name)}</td></tr>')
        return (
            '<h4>SRBR mappings</h4>'
            f'<p class="text-muted"><small>Inspected role-ids: {role_summary}</small></p>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>id</th>'
            '<th>id_role</th><th>id_role_child (SAP)</th>'
            '<th>id_role_parent (Backend)</th><th>name</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
            '<p class="text-muted mb-2"><small>'
            'Canonical: SAP role lives in <code>id_role_child</code>, '
            'Backend role in <code>id_role_parent</code>.<br/>'
            '<code>informat_service._sync_employee_proprelations</code> only '
            'matches on <code>id_role = SAP</code>; the betask processor '
            'matches on <code>id_role OR id_role_child = SAP</code>. '
            'A canonically-created SRBR is invisible to informat (be_role '
            'becomes None → fallback path), but the betask processor still '
            'resolves it correctly via <code>id_role_child</code>.'
            '</small></p>')

    def _diag_render_all_sr_br(self, sr_br_type, PropRelation):
        """Show every active SRBR row with its three role-fields and a
        per-row classification of the field convention used. The user can
        immediately see if records are stored in a way the lookups will
        not pick up."""
        e = self._diag_html_escape
        if not sr_br_type:
            return ''
        rels = PropRelation.search([
            ('proprelation_type_id', '=', sr_br_type.id),
            ('is_active', '=', True),
        ], limit=200)
        if not rels:
            return ('<h4>All active SRBR rows</h4>'
                    '<p class="text-warning">No active SRBR rows in the DB. '
                    'You need to create them — one per SAP-ambt that maps '
                    'to a backend role.</p>')

        def cell(role):
            if not role:
                return '<span class="text-muted">—</span>'
            return f'{e(role.name)} <small>(id={role.id})</small>'

        def classify(r):
            """Return a label + bootstrap class for the convention used."""
            ir = r.id_role
            irc = r.id_role_child
            irp = r.id_role_parent
            if ir and irp and not irc:
                return ('id_role=SAP, id_role_parent=Backend',
                        'text-bg-success')
            if irc and irp and not ir:
                return ('id_role_child=SAP, id_role_parent=Backend (canonical)',
                        'text-bg-success')
            if ir and irc and irp:
                return ('all three set — works but redundant',
                        'text-bg-info')
            if not irp:
                return ('id_role_parent EMPTY — betask processor will reject',
                        'text-bg-danger')
            return ('unusual layout — verify manually', 'text-bg-warning')

        rows = []
        for r in rels:
            label, cls = classify(r)
            rows.append(
                f'<tr><td>{r.id}</td>'
                f'<td>{cell(r.id_role)}</td>'
                f'<td>{cell(r.id_role_child)}</td>'
                f'<td>{cell(r.id_role_parent)}</td>'
                f'<td><span class="badge {cls}">{e(label)}</span></td>'
                f'<td>{e(r.name)}</td></tr>')
        return (
            '<h4>All active SRBR rows</h4>'
            f'<p class="text-muted"><small>{len(rels)} active SRBR row(s).</small></p>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>id</th><th>id_role</th><th>id_role_child</th>'
            '<th>id_role_parent</th><th>convention</th><th>name</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')

    def _diag_render_persongroup_state(self, person):
        """For every BRSO target_org reachable from the person's PPSBRs,
        show: target org, has_comgroup flag, the linked persongroup org
        (under the school's OuForGroups), the persongroup's PG-P member
        count, and whether the *person* is in it.

        Pinpoints the difference between "AD-side wel toegevoegd" and
        "DB-persongroup PG-P leeg" — the user sees per-target-org which
        side worked and which didn't."""
        e = self._diag_html_escape
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']
        ConfigItem = self.env['myschool.config.item']
        processor = self.env['myschool.betask.processor']

        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        pg_p_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        pg_org_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)

        if not ppsbr_type or not brso_type:
            return ''

        # Collect target orgs from BRSOs matching the person's PPSBRs
        # (with the same ORG-TREE+inst_nr expansion the cascade uses).
        ppsbrs = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', person.id),
            ('is_active', '=', True),
            ('id_role', '!=', False),
            ('id_org', '!=', False),
        ])
        targets = Org.browse()
        for ppsbr in ppsbrs:
            ancestors = set(processor._collect_org_ancestor_ids(ppsbr.id_org)) \
                if hasattr(processor, '_collect_org_ancestor_ids') else {ppsbr.id_org.id}
            inst_nrs = {o.inst_nr for o in Org.browse(list(ancestors))
                        if o.inst_nr}
            if inst_nrs:
                same_inst = Org.search([
                    ('inst_nr', 'in', list(inst_nrs)),
                    ('is_active', '=', True),
                ])
                ancestors.update(same_inst.ids)
            brsos = PropRelation.search([
                ('proprelation_type_id', '=', brso_type.id),
                ('id_role', '=', ppsbr.id_role.id),
                ('id_org_parent', 'in', list(ancestors)),
                ('is_active', '=', True),
                ('id_org', '!=', False),
            ])
            targets |= brsos.mapped('id_org')

        # Also include the active PERSON-TREE org as a target (placement
        # contributes to its persongroup separately).
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if pt_type:
            pt_rel = PropRelation.search([
                ('proprelation_type_id', '=', pt_type.id),
                ('id_person', '=', person.id),
                ('is_active', '=', True),
                ('id_org', '!=', False),
            ], limit=1)
            if pt_rel and pt_rel.id_org:
                targets |= pt_rel.id_org

        if not targets:
            return ('<h4>Persongroup memberships</h4>'
                    '<p class="text-muted">No target orgs reachable from this person.</p>')

        rows = []
        for t in targets:
            school = None
            if hasattr(processor, '_resolve_parent_school_from_org'):
                try:
                    school = processor._resolve_parent_school_from_org(t)
                except Exception:
                    school = None
            ouforgroups = None
            ou_org = None
            if school and hasattr(processor, '_resolve_ou_for_groups_org'):
                try:
                    ouforgroups, ou_org = processor._resolve_ou_for_groups_org(school)
                except Exception:
                    ouforgroups, ou_org = None, None
            persongroup = None
            pgp_count = 0
            person_in_pg = False
            if pg_org_type and ou_org and org_tree_type:
                # Find every PERSONGROUP under the resolved OuForGroups
                # org (via ORG-TREE), then match against the target org's
                # com_group_name OR the persongroup's own name_short.
                child_rels = PropRelation.search([
                    ('proprelation_type_id', '=', org_tree_type.id),
                    ('id_org_parent', '=', ou_org.id),
                    ('is_active', '=', True),
                ])
                child_ids = [r.id_org.id for r in child_rels if r.id_org]
                if child_ids:
                    candidates = Org.search([
                        ('id', 'in', child_ids),
                        ('org_type_id', '=', pg_org_type.id),
                        ('is_active', '=', True),
                    ])
                    target_cgn = (t.com_group_name or '').strip().lower()
                    target_short = (t.name_short or '').strip().lower()
                    school_short = (school.name_short or '').strip().lower() if school else ''
                    # Also try the canonical formula in case the
                    # target's com_group_name hasn't been computed yet.
                    formula_pgname = (
                        f'grp-{target_short}-{school_short}'
                        if target_short and school_short else '')
                    for cand in candidates:
                        cand_short = (cand.name_short or '').strip().lower()
                        cand_cgn = (cand.com_group_name or '').strip().lower()
                        if target_cgn and (cand_short == target_cgn or cand_cgn == target_cgn):
                            persongroup = cand
                            break
                        if formula_pgname and (cand_short == formula_pgname
                                               or cand_cgn == formula_pgname):
                            persongroup = cand
                            break
                        # Last-ditch fuzzy match: target's short name as
                        # substring (e.g. target 'pers' matches 'grp-pers-so').
                        if target_short and (target_short in cand_short
                                             or target_short in cand_cgn):
                            persongroup = cand
                            break
            if persongroup and pg_p_type:
                pgp_rels = PropRelation.search([
                    ('proprelation_type_id', '=', pg_p_type.id),
                    ('id_org', '=', persongroup.id),
                    ('is_active', '=', True),
                    ('id_person', '!=', False),
                ])
                pgp_count = len(pgp_rels)
                person_in_pg = person.id in pgp_rels.mapped('id_person').ids

            warn_cls = ''
            if t.has_comgroup and persongroup and not person_in_pg:
                warn_cls = 'text-bg-warning'

            pg_cell = (e(persongroup.name_short) if persongroup
                       else '<span class="badge text-bg-danger">missing</span>')
            school_cell = e(school.name) if school else '<i>?</i>'
            badge_cls = warn_cls or (
                'text-bg-success' if person_in_pg else 'text-bg-secondary')
            badge_text = '✓ in PG' if person_in_pg else '— not in PG'
            rows.append(
                f'<tr><td>{t.id}</td>'
                f'<td>{e(t.name)}</td>'
                f'<td>{"✓" if t.has_comgroup else ""}</td>'
                f'<td>{school_cell}</td>'
                f'<td>{pg_cell}</td>'
                f'<td>{pgp_count}</td>'
                f'<td><span class="badge {badge_cls}">{badge_text}</span></td></tr>')

        return (
            '<h4>Persongroup memberships</h4>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>target id</th><th>target org</th>'
            '<th>has_comgroup</th><th>resolved school</th>'
            '<th>persongroup (name_short)</th><th>total PG-P</th>'
            '<th>person in PG?</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table>'
            '<p class="text-muted mb-0"><small>'
            'For each target org reachable from the person\'s PPSBRs '
            '(plus the active PERSON-TREE org): does the persongroup '
            'exist under the resolved school\'s OuForGroups, how many '
            'PG-P members it has, and whether the person is among them. '
            'A red "missing" persongroup means the school could not be '
            'resolved (e.g. target sits under a non-SCHOOL parent).'
            '</small></p>')

    def _diag_render_recent_sys_events(self, person):
        """Pull sys-events from the last hour that mention the person's
        name or UUID. Phase 2 of the sync writes explicit BETASK-DEBUG
        events per active employee — their presence/absence reveals if
        Phase 2 saw this person and what assignments it found."""
        e = self._diag_html_escape
        SysEvent = self.env.get('myschool.sys.event')
        if SysEvent is None:
            return ''
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=2)
        leaves = []
        if person.name:
            leaves.append(('data', 'ilike', person.name))
        if person.sap_person_uuid:
            leaves.append(('data', 'ilike', person.sap_person_uuid))
        # Also surface any "Phase 2" / "Processing N active employees"
        # markers — they tell us whether Phase 2 even started.
        leaves.append(('data', 'ilike', 'Phase 2'))
        leaves.append(('data', 'ilike', 'active employees'))
        if not leaves:
            return ''
        domain = ['|'] * (len(leaves) - 1) + leaves
        domain = [('create_date', '>=', since.strftime('%Y-%m-%d %H:%M:%S'))] + domain
        events = SysEvent.search(domain, order='create_date desc', limit=50)
        if not events:
            return ('<h4>Recent sys-events (last 2h)</h4>'
                    '<p class="text-muted">No matching sys-events.</p>')
        rows = []
        for ev in events:
            code = ev.eventcode or ''
            cls = ('text-bg-danger' if 'ERROR' in (ev.event_type_name or '').upper()
                   or code.startswith('BETASK-9') else
                   'text-bg-warning' if code == 'PPSBR-ROLE-MISMATCH' else
                   'text-bg-info' if code == 'BETASK-DEBUG' else
                   'text-bg-secondary')
            data_short = (ev.data or '').strip().replace('\n', ' ')
            if len(data_short) > 220:
                data_short = data_short[:217] + '…'
            rows.append(
                f'<tr><td>{ev.id}</td>'
                f'<td><small>{e(ev.create_date)}</small></td>'
                f'<td><span class="badge {cls}">{e(code)}</span></td>'
                f'<td><small>{e(data_short)}</small></td></tr>')
        return (
            '<h4>Recent sys-events (last 2h)</h4>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>id</th><th>created</th><th>code</th>'
            '<th>data</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table>'
            '<p class="text-muted mb-0"><small>'
            'Look for: <code>Phase 2: Syncing PPSBR PropRelation objects</code> '
            '(Phase 2 started), <code>Processing N active employees</code> '
            '(active_employees count), and per-person '
            '<code>Person {name} @ inst_nr X: N assignments</code>. '
            'Absence of the per-person line means the person was filtered '
            'out of <code>active_employees</code>.'
            '</small></p>')

    def _diag_render_recent_betasks(self, person):
        """Pull the most recent PROPRELATION/ROLE/PERSON betasks tied to
        the person (via the data JSON) so a failed PPSBR-ADD surfaces."""
        e = self._diag_html_escape
        BeTask = self.env['myschool.betask']
        # Use the person's id and uuid as substring matches on data.
        person_id_str = str(person.id)
        person_uuid = person.sap_person_uuid or ''
        leaves = [
            ('data', 'ilike', f'"person_db_id": {person_id_str}'),
            ('data', 'ilike', f'"person_db_id":{person_id_str}'),
        ]
        if person_uuid:
            leaves.append(('data', 'ilike', person_uuid))
        # N leaves OR'd together need (N-1) leading `|` operators.
        domain = ['|'] * (len(leaves) - 1) + leaves
        tasks = BeTask.search(domain, order='create_date desc', limit=15)
        if not tasks:
            return ('<h4>Recent BeTasks for this person</h4>'
                    '<p class="text-muted">No matching betasks found.</p>')
        rows = []
        for t in tasks:
            status_cls = (
                'text-bg-success' if t.status == 'completed_ok' else
                'text-bg-danger' if t.status in ('completed_errors', 'failed') else
                'text-bg-warning' if t.status == 'new' else 'text-bg-secondary')
            changes_short = (t.changes or '').strip()
            if len(changes_short) > 240:
                changes_short = changes_short[:237] + '…'
            rows.append(
                f'<tr><td>{t.id}</td>'
                f'<td><small>{e(t.create_date)}</small></td>'
                f'<td>{e(t.task_type_name or "")}</td>'
                f'<td><span class="badge {status_cls}">{e(t.status)}</span></td>'
                f'<td>{e(t.name or "")}</td>'
                f'<td><small>{e(changes_short)}</small></td></tr>')
        return (
            '<h4>Recent BeTasks for this person</h4>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>id</th><th>created</th><th>type</th>'
            '<th>status</th><th>name</th><th>changes / error</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
            '<p class="text-muted mb-0"><small>'
            'Look for failed <code>DB/PROPRELATION/ADD</code> tasks — those '
            'are the PPSBR-creators. A failure with "BETASK-703" means SR-BR '
            'lookup failed.'
            '</small></p>')

    def _diag_render_brso(self, ppsbrs, brso_type, PropRelation, person):
        e = self._diag_html_escape
        if not brso_type:
            return '<h4>BRSO entries</h4><p class="text-muted">No BRSO type defined.</p>'
        role_ids = list({p.id_role.id for p in ppsbrs if p.id_role})
        if not role_ids:
            return '<h4>BRSO entries</h4><p class="text-muted">No roles to look up.</p>'
        brsos = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('is_active', '=', True),
            ('id_role', 'in', role_ids),
        ])
        if not brsos:
            return ('<h4>BRSO entries</h4>'
                    '<p class="text-warning">No active BRSO for any of the '
                    'PPSBR roles.</p>')
        rows = []
        for b in brsos:
            rows.append(
                f'<tr><td>{b.id}</td>'
                f'<td>{e(b.id_role.name) if b.id_role else ""} '
                f'<small>(id={e(b.id_role.id) if b.id_role else ""})</small></td>'
                f'<td>{e(b.id_org_parent.name) if b.id_org_parent else "—"} '
                f'<small>(id={e(b.id_org_parent.id) if b.id_org_parent else "-"})</small></td>'
                f'<td>{e(b.id_org.name) if b.id_org else ""} '
                f'<small>(id={e(b.id_org.id) if b.id_org else "-"})</small></td>'
                f'<td>{"✓" if b.id_org and b.id_org.has_comgroup else ""}</td>'
                f'<td>{"✓" if b.id_org and b.id_org.has_secgroup else ""}</td>'
                f'<td>{"✓" if b.id_org and b.id_org.has_odoo_group else ""}</td></tr>')
        return ('<h4>BRSO entries</h4>'
                '<p class="text-muted"><small>'
                'Group flags shown are read from the BRSO\'s '
                '<b>target org</b> (single source of truth).'
                '</small></p>'
                '<table class="table table-sm table-striped">'
                '<thead><tr><th>id</th><th>role</th>'
                '<th>id_org_parent (school)</th><th>id_org (target)</th>'
                '<th>target.has_comgroup</th><th>target.has_secgroup</th><th>target.has_odoo_group</th>'
                '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')

    def _diag_render_target(self, target_org, log):
        e = self._diag_html_escape
        log_html = ''.join(f'<li>{e(line)}</li>' for line in log)
        if target_org:
            return (
                '<h4>Resolved target org</h4>'
                f'<p class="alert alert-success mb-1">→ <b>{e(target_org.name)}</b> '
                f'<small>(id={target_org.id})</small></p>'
                f'<ul class="text-muted"><small>{log_html}</small></ul>')
        return (
            '<h4>Resolved target org</h4>'
            '<p class="alert alert-warning mb-1">No target org could be '
            'resolved.</p>'
            f'<ul class="text-muted"><small>{log_html}</small></ul>')

    def _diag_render_current_tree(self, current_tree):
        e = self._diag_html_escape
        if not current_tree:
            return ('<h4>Current PERSON-TREE</h4>'
                    '<p class="text-muted">No active PERSON-TREE record.</p>')
        rows = []
        for t in current_tree:
            rows.append(
                f'<tr><td>{t.id}</td>'
                f'<td>{e(t.id_role.name) if t.id_role else ""}</td>'
                f'<td>{e(t.id_org.name) if t.id_org else ""}</td>'
                f'<td>{e(t.priority)}</td>'
                f'<td>{"auto" if t.automatic_sync else "manual"}</td></tr>')
        return (
            '<h4>Current PERSON-TREE</h4>'
            '<table class="table table-sm table-striped">'
            '<thead><tr><th>id</th><th>role</th><th>org</th>'
            '<th>priority</th><th>sync</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table>')

    # -------------------------------------------------------------------------
    # Helpers — expectation rendering
    # -------------------------------------------------------------------------

    @staticmethod
    def _escape(s):
        return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _render_expectations_summary(self, folder_name, spec):
        if not spec:
            return ('<p><em>Geen gekende verwachtingen voor '
                    f'"{self._escape(folder_name)}". Voeg een entry toe aan '
                    'EXPECTATIONS in sync_test_runner.py voor automatische '
                    'verificatie.</em></p>')
        desc = self._escape(spec.get('description', ''))
        bullets = ''.join(
            f'<li>{self._escape(self._format_check(c))}</li>'
            for c in spec.get('checks', []))
        return f'<p>{desc}</p>' + (f'<ul>{bullets}</ul>' if bullets else '')

    @staticmethod
    def _format_check(check):
        t = check.get('type', '?')
        if t == 'classgroup_active':
            extra = f" in {check['inst_nr']}" if check.get('inst_nr') else ''
            return f"Klasgroep '{check['name_short']}' is actief{extra}"
        if t == 'classgroup_inactive':
            return f"Klasgroep '{check['name_short']}' is inactief"
        if t == 'classgroup_inactive_at':
            return f"Klasgroep '{check['name_short']}' in instnr {check['inst_nr']} is inactief / verplaatst"
        if t == 'person_exists_active':
            return f"Persoon [{check['uuid'][:8]}…] bestaat en is actief"
        if t == 'person_inactive_or_ended':
            return f"Persoon [{check['uuid'][:8]}…] is gedeactiveerd of heeft reg_end_date"
        if t == 'person_reg_end_empty':
            return f"Persoon [{check['uuid'][:8]}…] heeft reg_end_date leeg (gereactiveerd)"
        if t == 'person_active_class':
            return f"Persoon [{check['uuid'][:8]}…] heeft actieve klas '{check['klas_code']}'"
        if t == 'person_not_in_class':
            return f"Persoon [{check['uuid'][:8]}…] hoort niet meer bij klas '{check['klas_code']}'"
        if t == 'person_reg_inst_nr':
            return f"Persoon [{check['uuid'][:8]}…] heeft reg_inst_nr={check['inst_nr']}"
        if t == 'person_pending_since_set':
            return (f"Persoon [{check['uuid'][:8]}…] heeft "
                    f"deactivation_pending_since gezet (in suspend-pipeline)")
        if t == 'person_pending_since_empty':
            return (f"Persoon [{check['uuid'][:8]}…] heeft "
                    f"deactivation_pending_since leeg (niet in suspend)")
        if t == 'person_no_active_proprelations':
            return f"Persoon [{check['uuid'][:8]}…] heeft géén actieve proprelations"
        if t == 'person_has_active_proprelations':
            return f"Persoon [{check['uuid'][:8]}…] heeft minstens 1 actieve proprelation"
        if t == 'person_details_inst':
            return (f"Persoon [{check['uuid'][:8]}…] heeft actieve "
                    f"PersonDetails voor instnr {check['inst_nr']}")
        if t == 'person_no_details_inst':
            return (f"Persoon [{check['uuid'][:8]}…] heeft géén actieve "
                    f"PersonDetails voor instnr {check['inst_nr']}")
        if t == 'person_hoofd_ambt':
            return (f"Persoon [{check['uuid'][:8]}…] @ {check['inst_nr']}: "
                    f"hoofd_ambt={check['code']}")
        return f"{t} {check}"

    # -------------------------------------------------------------------------
    # Helpers — scanning
    # -------------------------------------------------------------------------

    def _scan_testset_dirs(self):
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
        persoon_ids = set()
        klas_keys = set()
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

    def _cleanup_orphan_persongroups(self, log, ctx, purge_proprelations, try_unlink):
        """Delete PERSONGROUP orgs that have no active PG-P member after
        the test person was removed.

        Why this exists: the sync auto-creates a PERSONGROUP per role
        (and per BRSO with com/sec flags). Those orgs are not tracked
        per session, so the regular employee-mode cleanup left them
        behind — including the loop-bug detritus (``grp-grp-ict-bawa-bawa``,
        ``grp-grp-grp-…`` …). Removing them after the person is gone
        keeps the test runner reproducible across runs.

        Conservative: only deletes PERSONGROUPs that (a) have no active
        PG-P member, and (b) hold no PERSON-TREE entries pointing at
        them. PG-P/ORG-TREE/PT references on those orgs are wiped first.
        """
        Org = self.env['myschool.org'].with_context(**ctx)
        OrgType = self.env['myschool.org.type']
        PropRelation = self.env['myschool.proprelation'].with_context(**ctx)
        PropRelationType = self.env['myschool.proprelation.type']

        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        if not pg_type:
            return

        pg_p_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)

        all_pgs = Org.search([
            ('org_type_id', '=', pg_type.id),
        ])
        if not all_pgs:
            return

        orphans = Org.browse()
        for pg in all_pgs:
            has_member = False
            if pg_p_type:
                has_member = bool(PropRelation.search_count([
                    ('proprelation_type_id', '=', pg_p_type.id),
                    ('id_org', '=', pg.id),
                    ('is_active', '=', True),
                    ('id_person', '!=', False),
                ]))
            if has_member:
                continue
            if pt_type:
                has_tree_member = bool(PropRelation.search_count([
                    ('proprelation_type_id', '=', pt_type.id),
                    ('id_org', '=', pg.id),
                    ('is_active', '=', True),
                    ('id_person', '!=', False),
                ]))
                if has_tree_member:
                    continue
            orphans |= pg

        if not orphans:
            log.append('PERSONGROUP cleanup: no orphans found')
            return

        # Wipe references first (PG-P, ORG-TREE, PERSON-TREE) so unlink
        # doesn't trip on FK constraints.
        purge_proprelations(self.env['myschool.person'].browse(),
                            orphans, self.env['myschool.role'].browse())

        # Persongroups created by the loop bug get noisy names — surface
        # a few in the log so the operator sees what was swept.
        sample = ', '.join(o.name_short or o.name or str(o.id) for o in orphans[:10])
        if len(orphans) > 10:
            sample += f', … (+{len(orphans) - 10})'
        try_unlink(orphans, f'PERSONGROUP (orphan)')
        log.append(f'PERSONGROUP cleanup: candidates were {sample}')

    def _cleanup_tracked_entities(self):
        """Delete only the entities tracked by this session.

        Direct unlink (with skip_manual_audit context) instead of the
        MANUAL/ORG/DEL pipeline: this is an admin reset for tests, not a
        business mutation, and the pipeline-cascade was occasionally
        leaving classgroup orgs behind when a downstream LDAP cascade
        raised. Same approach as the Reset Auto-Sync Data wizard.
        """
        log = []
        ctx = {'active_test': False, 'skip_manual_audit': True,
               'skip_pg_flag_handling': True}

        def _purge_proprelations_for(persons, orgs, roles):
            """Drop every proprelation referencing any of the targets."""
            PropRelation = self.env['myschool.proprelation'].with_context(**ctx)
            sub_domains = []
            if persons:
                sub_domains += [
                    [('id_person', 'in', persons.ids)],
                    [('id_person_parent', 'in', persons.ids)],
                    [('id_person_child', 'in', persons.ids)],
                ]
            if orgs:
                sub_domains += [
                    [('id_org', 'in', orgs.ids)],
                    [('id_org_parent', 'in', orgs.ids)],
                    [('id_org_child', 'in', orgs.ids)],
                ]
            if roles:
                sub_domains += [
                    [('id_role', 'in', roles.ids)],
                    [('id_role_parent', 'in', roles.ids)],
                    [('id_role_child', 'in', roles.ids)],
                ]
            if not sub_domains:
                return 0
            domain = ['|'] * (len(sub_domains) - 1)
            for sd in sub_domains:
                domain += sd
            rels = PropRelation.search(domain)
            n = len(rels)
            if n:
                rels.unlink()
            return n

        def _try_unlink(records, label):
            if not records:
                return
            n = len(records)
            names = ', '.join((r.name or str(r.id)) for r in records[:5])
            if n > 5:
                names += f', … (+{n - 5})'
            try:
                records.with_context(**ctx).unlink()
                self.env.cr.commit()
                log.append(f'{label}: deleted {n} ({names})')
            except Exception as e:
                self.env.cr.rollback()
                log.append(f'{label}: FAILED ({n} record(s)) — {e}')

        if self.mode == 'employees':
            if not self.test_person_uuid:
                self.cleanup_log = ''
                return log
            Person = self.env['myschool.person'].with_context(**ctx)
            person = Person.search(
                [('sap_person_uuid', '=', self.test_person_uuid)], limit=1)
            if person:
                # Detach Odoo user/employee links first to avoid write-protect.
                person.write({'odoo_user_id': False, 'odoo_employee_id': False})
                _purge_proprelations_for(person, person.browse(), person.browse())
                _try_unlink(person, 'PERSON')
            BeTask = self.env['myschool.betask']
            related = BeTask.search([('data', 'like', self.test_person_uuid)])
            if related:
                n = len(related)
                related.unlink()
                log.append(f'BETASK: removed {n} reference(s) to {self.test_person_uuid}')
            # Sweep up persongroup orgs auto-created by the sync. After
            # the test person is gone, any PERSONGROUP whose PG-P member
            # set is empty is orphaned. Matches the loop-bug detritus
            # (`grp-grp-ict-bawa-bawa`, …) plus the regular auto-spawned
            # ones for the test's roles.
            self._cleanup_orphan_persongroups(log, ctx, _purge_proprelations_for, _try_unlink)
            self._save_cleanup_log(log)
            return log

        # students mode -----------------------------------------------------
        Person = self.env['myschool.person'].with_context(**ctx)
        Org = self.env['myschool.org'].with_context(**ctx)
        OrgType = self.env['myschool.org.type']
        Role = self.env['myschool.role'].with_context(**ctx)

        # Resolve tracked persons.
        person_uuids = [p.strip() for p in (self.tracked_persoon_ids or '').split(',') if p.strip()]
        persons = (Person.search([('sap_person_uuid', 'in', person_uuids)])
                   if person_uuids else Person.browse())

        # Resolve tracked orgs by (name_short, inst_nr) pairs from the
        # tracked-classgroups field. We look at CLASSGROUP and PERSONGROUP
        # types because both can be auto-created during student sync.
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        type_ids = [t.id for t in (cg_type, pg_type) if t]

        org_keys = []
        for key in (self.tracked_classgroups or '').split(','):
            key = key.strip()
            if not key or '@' not in key:
                continue
            code, inst = key.split('@', 1)
            org_keys.append((code, inst))

        orgs = Org.browse()
        missing_keys = []
        for code, inst in org_keys:
            domain = [('name_short', '=ilike', code)]
            if inst:
                domain += ['|', ('inst_nr', '=', inst), ('inst_nr', '=', False)]
            if type_ids:
                domain.append(('org_type_id', 'in', type_ids))
            found = Org.search(domain)
            if found:
                orgs |= found
            else:
                missing_keys.append(f'{code}@{inst}')

        if missing_keys:
            log.append(
                'ORG: no match for ' + ', '.join(missing_keys[:10])
                + (f' (+{len(missing_keys) - 10})' if len(missing_keys) > 10 else ''))

        # Backend roles named after the tracked org full names.
        roles = Role.browse()
        if orgs:
            full_names = list({o.name for o in orgs if o.name})
            if full_names:
                roles = Role.search([('name', 'in', full_names)])

        # Detach persons from Odoo links before unlink.
        if persons:
            persons.write({'odoo_user_id': False, 'odoo_employee_id': False})

        # Drop everything that references any of these targets in one shot.
        n_rels = _purge_proprelations_for(persons, orgs, roles)
        if n_rels:
            log.append(f'PROPRELATION: deleted {n_rels}')

        _try_unlink(persons, 'PERSON')
        _try_unlink(roles, 'ROLE')
        _try_unlink(orgs, 'ORG')

        # Drop betasks referencing any tracked person UUID — they store the
        # uuid in their JSON data field.
        BeTask = self.env['myschool.betask']
        for pid in person_uuids:
            related = BeTask.search([('data', 'like', pid)])
            if related:
                n = len(related)
                related.unlink()
                log.append(f'BETASK: removed {n} reference(s) to {pid}')

        self._save_cleanup_log(log)
        return log

    def _save_cleanup_log(self, log):
        """Render the cleanup log as HTML into the session field."""
        if not log:
            self.cleanup_log = '<p><em>Nothing matched the tracked entities.</em></p>'
            return
        rows = ''.join(
            f'<li>{(line or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</li>'
            for line in log)
        self.cleanup_log = (
            f'<p><strong>{len(log)} action(s):</strong></p>'
            f'<ul style="margin:0;padding-left:18px;">{rows}</ul>')


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

    expectations_summary = fields.Html(string='Expected changes')
    expectations_result = fields.Html(string='Verification')
    expectations_pass_count = fields.Integer(readonly=True)
    expectations_fail_count = fields.Integer(readonly=True)

    file_ids = fields.One2many(
        'myschool.sync.test.step.file', 'step_id', string='JSON files')

    status_label = fields.Char(compute='_compute_status_label')

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
    # Step actions
    # -------------------------------------------------------------------------

    def action_jump_to(self):
        self.ensure_one()
        self.session_id.current_step_id = self
        return True

    def action_reset_to_here(self):
        """Cleanup the session and replay all earlier steps. After this the
        chosen step is the next-to-run."""
        self.ensure_one()
        session = self.session_id
        earlier = session.step_ids.filtered(
            lambda s: s.sequence < self.sequence).sorted('sequence')
        session._cleanup_tracked_entities()
        session.step_ids.write({
            'status': 'pending', 'last_run_at': False,
            'new_betask_count': 0, 'processed_ok_count': 0, 'processed_err_count': 0,
            'debug_output': False, 'sync_events': False, 'expectations_result': False,
            'expectations_pass_count': 0, 'expectations_fail_count': 0,
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
                        'message': f'{step.name} finished with "{step.status}"',
                        'sticky': True, 'type': 'warning',
                        'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                    },
                }
        session.current_step_id = self
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Ready',
                'message': f'Replayed {len(earlier)} step(s). Step {self.sequence} now current.',
                'sticky': False, 'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_run(self):
        """Execute this single step: write files, sync, process tasks, verify."""
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

        config_saved_flags = self._force_sync_flags_for_mode(session.mode)

        started_at = fields.Datetime.now()
        debug_lines = [
            f'=== Step {self.sequence}: {self.name} ===',
            f'Mode: {session.mode}',
            f'Folder: {self.folder_path}',
            f'Dev dir: {dev_dir}',
            f'Started: {started_at}',
        ]
        if config_saved_flags and config_saved_flags.get('forced'):
            debug_lines.append(
                f'Sync flags forced for run: {config_saved_flags["forced"]}')

        self.status = 'running'
        session.current_step_id = self
        self.env.cr.commit()

        try:
            self._flush_files_to_disk(debug_lines)
            self._prepare_dev_dir(dev_dir, debug_lines, session.mode)
            self._copy_folder_to_dev(dev_dir, debug_lines)

            BeTask = self.env['myschool.betask']
            before = BeTask.search_count([])
            debug_lines.append(f'BeTasks before sync: {before}')
            debug_lines.append('--- Running execute_sync(dev_mode=True) ---')
            try:
                sync_result = service.execute_sync(dev_mode=True)
                self.sync_result = str(sync_result)
                debug_lines.append(f'execute_sync returned: {sync_result}')
            except Exception as e:
                debug_lines.append(f'EXCEPTION in execute_sync: {e}')
                self.env.cr.rollback()
                self._finalize_step(started_at, debug_lines, log_handler, 'completed_errors')
                return False
            self.env.cr.commit()

            new_tasks = self._collect_new_tasks(before)
            self.new_betask_count = len(new_tasks)
            debug_lines.append(f'New BeTasks after sync: {len(new_tasks)}')
            for t in new_tasks:
                debug_lines.append(f'  [{t.status}] {t.task_type_name or t.name} — {t.name}')

            if session.skip_ldap_processing:
                skipped = self._skip_ldap_tasks()
                if skipped:
                    debug_lines.append(
                        f'--- Skipped {len(skipped)} LDAP/AD task(s) ---')
                    for t in skipped:
                        debug_lines.append(f'  ⏭ [{t.target}] {t.name}')

            debug_lines.append('--- Processing pending tasks ---')
            pending = BeTask.search([('status', '=', 'new')])
            if pending:
                processor = self.env['myschool.betask.processor']
                try:
                    proc_result = processor.process_all_pending()
                    debug_lines.append(f'process_all_pending: {proc_result}')
                except Exception as e:
                    debug_lines.append(f'EXCEPTION in process_all_pending: {e}')
                    self.env.cr.rollback()
                    self._finalize_step(started_at, debug_lines, log_handler, 'completed_errors')
                    return False
                self.env.cr.commit()

                ok = err = 0
                for task in pending.exists():
                    task.invalidate_recordset()
                    if task.status == 'completed_ok':
                        ok += 1
                        icon = '✓'
                    else:
                        err += 1
                        icon = '✗'
                    changes = (task.changes or '').splitlines()[:4]
                    debug_lines.append(
                        f'  {icon} [{task.status}] {task.name}'
                        + ''.join(f'\n      {line}' for line in changes))
                self.processed_ok_count = ok
                self.processed_err_count = err
                debug_lines.append(f'Processed: {ok} ok, {err} error(s)')
                step_status = 'completed_ok' if err == 0 else 'completed_errors'
            else:
                debug_lines.append('No pending tasks to process.')
                self.processed_ok_count = 0
                self.processed_err_count = 0
                step_status = 'completed_ok'

            self._collect_entity_snapshot(debug_lines)
            verification = self._run_expectation_checks(debug_lines)
            if verification == 'failed' and step_status == 'completed_ok':
                step_status = 'completed_errors'
            self._finalize_step(started_at, debug_lines, log_handler, step_status)
            return True

        finally:
            for lg in loggers:
                lg.removeHandler(log_handler)
            for lg, lvl in previous_levels:
                lg.setLevel(lvl)
            if config_saved_flags:
                self._restore_sync_flags(config_saved_flags)

    def _force_sync_flags_for_mode(self, mode):
        Config = self.env['myschool.informat.service.config']
        config = Config.search([], limit=1)
        if not config:
            return None
        if mode == 'students':
            needed = ('sync_classes', 'sync_students')
        else:
            needed = ('sync_employees', 'sync_roles')
        previous = {f: bool(config[f]) for f in needed}
        forced = [f for f in needed if not previous[f]]
        if forced:
            config.write({f: True for f in forced})
            self.env.cr.commit()
        return {'config_id': config.id, 'previous': previous, 'forced': forced}

    def _restore_sync_flags(self, saved):
        Config = self.env['myschool.informat.service.config']
        config = Config.browse(saved['config_id']).exists()
        if not config or not saved.get('forced'):
            return
        config.write({f: saved['previous'][f] for f in saved['forced']})
        self.env.cr.commit()

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
        """Clean dev dir but ONLY remove the file types this step provides.

        Files of a type the step doesn't provide (e.g. step 6 has only
        registrations) are left in place so the sync still finds the
        previously-loaded data — preventing student records being created
        with empty naam/voornaam from registration-only data.
        """
        step_files = {
            os.path.basename(f)
            for f in glob.glob(os.path.join(self.folder_path, '*.json'))
        }
        debug_lines.append(
            f'--- Cleaning dev dir ({mode}): step provides {len(step_files)} file(s) ---')
        if mode == 'employees':
            patterns = ['dev-employees-*.json', 'dev-employeeassignments-*.json']
        else:
            patterns = ['dev-students-*.json', 'dev-registrations-*.json']
        for pattern in patterns:
            step_has = any(glob.fnmatch.fnmatch(n, pattern) for n in step_files)
            if not step_has:
                debug_lines.append(
                    f'  keeping existing {pattern} (not provided by this step)')
                continue
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

    def _skip_ldap_tasks(self):
        BeTask = self.env['myschool.betask']
        ldap_tasks = BeTask.search([
            ('status', '=', 'new'),
            ('target', 'in', ('LDAP', 'AD')),
        ])
        if not ldap_tasks:
            return ldap_tasks
        ldap_tasks.write({
            'status': 'completed_ok',
            'changes': 'Skipped by sync test runner (skip_ldap_processing=True)',
        })
        return ldap_tasks

    def _collect_new_tasks(self, before_count):
        BeTask = self.env['myschool.betask']
        after = BeTask.search_count([])
        new = after - before_count
        if new <= 0:
            return BeTask
        return BeTask.search([], order='id desc', limit=new).sorted('id')

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
            debug_lines.append(f'  person[{uuid[:8]}…]: NOT FOUND')
            return
        details = person.person_details_set
        detail_parts = [
            f"{getattr(d, 'institution_nr', None) or getattr(d, 'inst_nr', '?')}"
            f"(active={d.is_active})"
            for d in details
        ]
        debug_lines.append(
            f'  person[{uuid[:8]}…]: {person.name}, is_active={person.is_active}, '
            f'reg_inst_nr={person.reg_inst_nr or "-"}, '
            f'details=[{", ".join(detail_parts) or "-"}]')

    def _snapshot_classgroup(self, code, inst, debug_lines):
        Org = self.env['myschool.org'].with_context(active_test=False)
        OrgType = self.env['myschool.org.type']
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        orgs = Org.search([
            ('name_short', '=ilike', code),
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
        debug_html = (
            '<pre style="white-space:pre-wrap;font-family:monospace;">'
            + self._escape_html('\n'.join(debug_lines))
            + '</pre>')
        if log_handler.records:
            debug_html += (
                '<h5>Captured logs</h5>'
                '<pre style="white-space:pre-wrap;font-family:monospace;font-size:90%;">'
                + self._escape_html('\n'.join(log_handler.records))
                + '</pre>')
        self.debug_output = debug_html
        self.sync_events = self._render_sync_events(started_at)
        # update overall_status on session
        statuses = self.session_id.step_ids.mapped('status')
        if not statuses or all(s == 'pending' for s in statuses):
            self.session_id.overall_status = 'pending'
        elif all(s in ('completed_ok', 'completed_errors') for s in statuses):
            self.session_id.overall_status = 'done'
        else:
            self.session_id.overall_status = 'in_progress'
        self.session_id.last_run_at = started_at
        self.env.cr.commit()

    def _render_sync_events(self, started_at):
        SysEvent = self.env['myschool.sys.event'].with_context(active_test=False)
        events = SysEvent.search([('create_date', '>=', started_at)], order='id asc')
        rows = ''.join(
            f'<tr><td>{e.id}</td><td>{e.eventcode or ""}</td>'
            f'<td>{self._escape_html(e.name or "")}</td>'
            f'<td>{e.priority or ""}</td></tr>'
            for e in events)

        BeTask = self.env['myschool.betask']
        new_tasks = BeTask.search([('create_date', '>=', started_at)], order='id asc')
        task_rows = ''.join(
            f'<tr><td>{t.id}</td><td>{t.task_type_name or ""}</td>'
            f'<td>{t.status or ""}</td>'
            f'<td>{self._escape_html(t.name or "")}</td>'
            f'<td><pre style="white-space:pre-wrap;margin:0;">'
            f'{self._escape_html((t.changes or "").strip())[:400]}</pre></td></tr>'
            for t in new_tasks)

        html = ''
        if rows:
            html += ('<h5>Sys events</h5>'
                     '<table class="table table-sm"><thead><tr>'
                     '<th>id</th><th>code</th><th>message</th><th>prio</th>'
                     f'</tr></thead><tbody>{rows}</tbody></table>')
        if task_rows:
            html += ('<h5>BeTasks created during step</h5>'
                     '<table class="table table-sm"><thead><tr>'
                     '<th>id</th><th>type</th><th>status</th><th>name</th><th>changes</th>'
                     f'</tr></thead><tbody>{task_rows}</tbody></table>')
        return html or '<p><em>No sys events or betasks recorded.</em></p>'

    @staticmethod
    def _escape_html(s):
        if not s:
            return ''
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # -------------------------------------------------------------------------
    # Expectation checks
    # -------------------------------------------------------------------------

    def _run_expectation_checks(self, debug_lines):
        spec = EXPECTATIONS.get(self.name)
        if not spec:
            self.expectations_result = (
                '<p><em>Geen verwachtingen gedefinieerd voor deze folder — '
                'verificatie overgeslagen.</em></p>')
            self.expectations_pass_count = 0
            self.expectations_fail_count = 0
            debug_lines.append('--- Expectation checks: SKIPPED (no catalog) ---')
            return 'skipped'

        rows = []
        pass_count = fail_count = 0
        for check in spec.get('checks', []):
            ok, detail = self._run_single_check(check)
            icon = '✓' if ok else '✗'
            color = '#2ea043' if ok else '#d32f2f'
            rows.append(
                f'<tr><td style="color:{color};font-weight:bold;width:2em;">{icon}</td>'
                f'<td>{self.session_id._escape(self.session_id._format_check(check))}</td>'
                f'<td><code>{self.session_id._escape(detail)}</code></td></tr>')
            if ok:
                pass_count += 1
            else:
                fail_count += 1

        self.expectations_pass_count = pass_count
        self.expectations_fail_count = fail_count
        header_color = '#2ea043' if fail_count == 0 else '#d32f2f'
        header = (f'<p style="color:{header_color};font-weight:bold;">'
                  f'{pass_count} passed, {fail_count} failed '
                  f'({pass_count + fail_count} checks total)</p>')
        table = ('<table class="table table-sm"><thead><tr>'
                 '<th></th><th>Check</th><th>DB state</th></tr></thead>'
                 f'<tbody>{"".join(rows)}</tbody></table>')
        self.expectations_result = header + table

        debug_lines.append(
            f'--- Expectation checks: {pass_count} passed, {fail_count} failed ---')
        return 'passed' if fail_count == 0 else 'failed'

    def _run_single_check(self, check):
        try:
            t = check.get('type', '')
            if t == 'classgroup_active':
                return self._check_classgroup_active(check['name_short'], check.get('inst_nr'))
            if t == 'classgroup_inactive':
                return self._check_classgroup_inactive(check['name_short'])
            if t == 'classgroup_inactive_at':
                return self._check_classgroup_inactive_at(check['name_short'], check['inst_nr'])
            if t == 'person_exists_active':
                return self._check_person_active(check['uuid'])
            if t == 'person_inactive_or_ended':
                return self._check_person_inactive_or_ended(check['uuid'])
            if t == 'person_reg_end_empty':
                return self._check_person_reg_end_empty(check['uuid'])
            if t == 'person_active_class':
                return self._check_person_active_class(check['uuid'], check['klas_code'])
            if t == 'person_not_in_class':
                return self._check_person_not_in_class(check['uuid'], check['klas_code'])
            if t == 'person_reg_inst_nr':
                return self._check_person_reg_inst_nr(check['uuid'], check['inst_nr'])
            # New employee-lifecycle check types
            if t == 'person_pending_since_set':
                return self._check_person_pending_since_set(check['uuid'])
            if t == 'person_pending_since_empty':
                return self._check_person_pending_since_empty(check['uuid'])
            if t == 'person_no_active_proprelations':
                return self._check_person_no_active_proprelations(check['uuid'])
            if t == 'person_has_active_proprelations':
                return self._check_person_has_active_proprelations(check['uuid'])
            if t == 'person_details_inst':
                return self._check_person_details_inst(check['uuid'], check['inst_nr'])
            if t == 'person_no_details_inst':
                return self._check_person_no_details_inst(check['uuid'], check['inst_nr'])
            if t == 'person_hoofd_ambt':
                return self._check_person_hoofd_ambt(
                    check['uuid'], check['inst_nr'], check['code'])
            return (False, f'unknown check type: {t}')
        except Exception as e:
            _logger.exception('expectation check raised')
            return (False, f'exception: {e}')

    # ------------------------------------------------------------------
    # Employee-lifecycle check helpers
    # ------------------------------------------------------------------

    def _check_person_pending_since_set(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        if not p.deactivation_pending_since:
            return (False, f'{p.name}: deactivation_pending_since is empty')
        return (True,
                f'{p.name}: pending_since={p.deactivation_pending_since}, '
                f'due={p.account_deactivation_due_date}')

    def _check_person_pending_since_empty(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        if p.deactivation_pending_since:
            return (False,
                    f'{p.name}: pending_since={p.deactivation_pending_since} '
                    f'(should be empty)')
        return (True, f'{p.name}: pending_since empty')

    def _check_person_no_active_proprelations(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        active = self._active_proprelations_count(p)
        if active == 0:
            return (True, f'{p.name}: 0 active proprelations')
        return (False, f'{p.name}: still {active} active proprelation(s)')

    def _check_person_has_active_proprelations(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        active = self._active_proprelations_count(p)
        if active > 0:
            return (True, f'{p.name}: {active} active proprelation(s)')
        return (False, f'{p.name}: no active proprelations')

    def _active_proprelations_count(self, person):
        PropRelation = self.env['myschool.proprelation']
        return PropRelation.search_count([
            '|', '|',
            ('id_person', '=', person.id),
            ('id_person_parent', '=', person.id),
            ('id_person_child', '=', person.id),
            ('is_active', '=', True),
        ])

    def _check_person_details_inst(self, uuid, inst_nr):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        Details = self.env['myschool.person.details']
        d = Details.search([
            ('person_id', '=', p.id),
            ('extra_field_1', '=', inst_nr),
            ('is_active', '=', True),
        ], limit=1)
        if d:
            return (True, f'{p.name}: PersonDetails active for inst {inst_nr} (id={d.id})')
        return (False, f'{p.name}: no active PersonDetails for inst {inst_nr}')

    def _check_person_no_details_inst(self, uuid, inst_nr):
        p = self._find_person(uuid)
        if not p:
            return (True, 'person not found')
        Details = self.env['myschool.person.details']
        d = Details.search([
            ('person_id', '=', p.id),
            ('extra_field_1', '=', inst_nr),
            ('is_active', '=', True),
        ], limit=1)
        if d:
            return (False, f'{p.name}: still has active PersonDetails for inst {inst_nr}')
        return (True, f'{p.name}: no active PersonDetails for inst {inst_nr}')

    def _check_person_hoofd_ambt(self, uuid, inst_nr, code):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        Details = self.env['myschool.person.details']
        d = Details.search([
            ('person_id', '=', p.id),
            ('extra_field_1', '=', inst_nr),
            ('is_active', '=', True),
        ], limit=1)
        if not d:
            return (False, f'no active PersonDetails for inst {inst_nr}')
        actual = d.hoofd_ambt or ''
        if actual == code:
            return (True, f'{p.name} @ {inst_nr}: hoofd_ambt={actual}')
        return (False,
                f'{p.name} @ {inst_nr}: hoofd_ambt={actual!r} expected {code!r}')

    def _find_classgroup(self, name_short, inst_nr=None):
        Org = self.env['myschool.org'].with_context(active_test=False)
        OrgType = self.env['myschool.org.type']
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        domain = [('name_short', '=ilike', name_short)]
        if cg_type:
            domain.append(('org_type_id', '=', cg_type.id))
        if inst_nr:
            domain.append(('inst_nr', '=', inst_nr))
        return Org.search(domain)

    def _check_classgroup_active(self, name_short, inst_nr=None):
        orgs = self._find_classgroup(name_short, inst_nr)
        active = orgs.filtered(lambda o: o.is_active)
        if active:
            return (True, f'{len(active)} active: '
                    + ', '.join(f'{o.name}[id={o.id},inst={o.inst_nr}]' for o in active))
        if orgs:
            return (False, 'only inactive: '
                    + ', '.join(f'{o.name}[id={o.id}]' for o in orgs))
        return (False, 'no classgroup found')

    def _check_classgroup_inactive(self, name_short):
        orgs = self._find_classgroup(name_short)
        if not orgs:
            return (True, 'no classgroup found (considered inactive)')
        active = orgs.filtered(lambda o: o.is_active)
        if not active:
            return (True, f'all {len(orgs)} records inactive')
        return (False, f'still {len(active)} active: '
                + ', '.join(f'{o.name}[id={o.id}]' for o in active))

    def _check_classgroup_inactive_at(self, name_short, inst_nr):
        orgs = self._find_classgroup(name_short, inst_nr)
        if not orgs:
            return (True, f'no classgroup at inst_nr={inst_nr}')
        active = orgs.filtered(lambda o: o.is_active)
        if not active:
            return (True, f'classgroup at {inst_nr} is inactive')
        return (False, 'still active: '
                + ', '.join(f'{o.name}[id={o.id}]' for o in active))

    def _find_person(self, uuid):
        Person = self.env['myschool.person'].with_context(active_test=False)
        return Person.search([('sap_person_uuid', '=', uuid)], limit=1)

    def _check_person_active(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        if not p.is_active:
            return (False, f'{p.name} exists but is_active=False')
        return (True, f'{p.name} (id={p.id})')

    def _check_person_inactive_or_ended(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (True, 'person not found (considered deactivated)')
        if not p.is_active:
            return (True, f'{p.name} is_active=False')
        if p.reg_end_date:
            return (True, f'{p.name} reg_end_date={p.reg_end_date}')
        return (False, f'{p.name} still active without reg_end_date')

    def _check_person_reg_end_empty(self, uuid):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        if p.reg_end_date:
            return (False, f'reg_end_date={p.reg_end_date}')
        if not p.is_active:
            return (False, 'person not active')
        return (True, f'{p.name} active, reg_end_date empty')

    def _active_classes_of_person(self, person):
        if not person:
            return self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        cg_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        if not pt_type:
            return self.env['myschool.org']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_person', '=', person.id),
            ('is_active', '=', True),
            ('id_org', '!=', False),
        ])
        orgs = rels.mapped('id_org')
        if cg_type:
            orgs = orgs.filtered(lambda o: o.org_type_id.id == cg_type.id)
        return orgs

    def _check_person_active_class(self, uuid, klas_code):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        orgs = self._active_classes_of_person(p)
        match = orgs.filtered(lambda o: (o.name_short or '').lower() == klas_code.lower())
        if match:
            return (True, f'{p.name} -> '
                    + ', '.join(f'{o.name}[id={o.id}]' for o in match))
        return (False, f'{p.name} active classes: '
                + (', '.join(o.name_short or o.name for o in orgs) or '(none)'))

    def _check_person_not_in_class(self, uuid, klas_code):
        p = self._find_person(uuid)
        if not p:
            return (True, 'person not found')
        orgs = self._active_classes_of_person(p)
        match = orgs.filtered(lambda o: (o.name_short or '').lower() == klas_code.lower())
        if not match:
            return (True, f'{p.name} not linked to {klas_code}')
        return (False, 'still linked: '
                + ', '.join(f'{o.name}[id={o.id}]' for o in match))

    def _check_person_reg_inst_nr(self, uuid, inst_nr):
        p = self._find_person(uuid)
        if not p:
            return (False, 'person not found')
        actual = p.reg_inst_nr or ''
        if actual == inst_nr:
            return (True, f'{p.name} reg_inst_nr={actual}')
        return (False, f'{p.name} reg_inst_nr={actual!r} expected {inst_nr!r}')


# =============================================================================
# Step file
# =============================================================================

class SyncTestStepFile(models.Model):
    _name = 'myschool.sync.test.step.file'
    _description = 'SAP Sync Test Step — File'
    _order = 'filename'

    step_id = fields.Many2one('myschool.sync.test.step', required=True, ondelete='cascade')
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
            'params': {'title': 'Saved',
                       'message': f'{len(self)} file(s) written.',
                       'type': 'success'},
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
            'params': {'title': 'Valid JSON',
                       'message': f'{len(self)} file(s) parsed successfully.',
                       'type': 'success'},
        }
