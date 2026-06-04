# -*- coding: utf-8 -*-
"""
SAP-sync service — orchestreert de safeguard- en review-flow.

Splits de Informat-sync in twee fasen:

  ANALYSE  : informat_service vergelijkt API-data met DB-state en roept
             record_planned_change(...) aan per geplande mutatie.
             Daarna roept de service finalise_analysis(...) — die telt,
             checkt drempels, eventueel alarmeert per mail en zet de
             run-state correct.

  COMMIT   : de admin (of bij no-breach + auto: automatisch) zet de
             goedgekeurde sync.change-records om naar betasks via
             commit_run(...). De bestaande betask-processor neemt het
             dan over.

Stale-handling: bij start van een nieuwe run worden openstaande
``planned``/``to_review_later``-changes van vorige runs gemarkeerd als
``superseded`` (per ontwerpkeuze met de gebruiker — nieuwe sync vervangt
oude pending items).
"""

import json
import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


# Default-drempels (kunnen overschreven worden in informat.service.config).
DEFAULT_THRESHOLDS = {
    'PERSON': 20.0,
    'ORG': 20.0,
    'ORGGROUP': 20.0,
    'PROPRELATION': 20.0,
}

# Objecttypes waarvoor we de safeguard-drempel toepassen.
SAFEGUARDED_TYPES = ('PERSON', 'ORG', 'ORGGROUP', 'PROPRELATION')


class SapSyncService(models.AbstractModel):
    _name = 'myschool.sap.sync.service'
    _description = 'SAP Sync Orchestration Service'

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    @api.model
    def start_run(self, trigger='manual', inst_nrs=None, phases=None,
                  require_review=False):
        """Maak een nieuwe sync.run aan en supersede openstaande items.

        :param trigger: 'cron' of 'manual'
        :param inst_nrs: list[str] of None (alle scholen)
        :param phases: dict of None
        :param require_review: bool, wizard-vlag
        :return: sync.run record
        """
        self._supersede_open_changes()

        run = self.env['myschool.sap.sync.run'].create({
            'trigger': trigger,
            'state': 'analysing',
            'inst_nrs': ','.join(inst_nrs) if inst_nrs else False,
            'phases_json': json.dumps(phases or {}),
            'require_review': bool(require_review),
        })

        self._log_event(
            'SAP-SYNC-RUN-STARTED',
            f'Run {run.name} gestart (trigger={trigger}, '
            f'require_review={require_review}, inst_nrs={inst_nrs or "all"})'
        )
        return run

    @api.model
    def _supersede_open_changes(self):
        """Markeer openstaande changes uit eerdere runs als superseded."""
        old = self.env['myschool.sap.sync.change'].search([
            ('state', 'in', ('planned', 'to_review_later', 'approved')),
            ('run_id.state', 'in', (
                'awaiting_approval', 'awaiting_review', 'analysing')),
        ])
        if old:
            old.write({'state': 'superseded'})
            _logger.info('SAP-SYNC: %d open changes gemarkeerd als '
                         'superseded bij start nieuwe run', len(old))
            # Bijhorende runs ook afsluiten als ze nu leeg zijn.
            old_runs = old.mapped('run_id')
            for r in old_runs:
                if not r.change_ids.filtered(lambda c: c.state in (
                        'planned', 'to_review_later', 'approved')):
                    r.write({
                        'state': 'cancelled',
                        'finished_at': fields.Datetime.now(),
                        'summary': (r.summary or '') +
                        '\nGeannuleerd: nieuwe sync-run gestart.',
                    })

    @api.model
    def record_planned_change(self, run, object_type, action,
                              source_key=None, display_name=None,
                              target_model=None, target_res_id=None,
                              payload_new=None, payload_old=None,
                              betask_target='DB', betask_data2=None,
                              diff_summary=None):
        """Registreer een geplande mutatie in de gegeven run.

        Aangeroepen door informat_service tijdens de analyse-fase, in
        plaats van rechtstreeks ``_create_betask``.

        :param run: sync.run record
        :param payload_new/old: dict of JSON-string
        :param betask_data2: dict of JSON-string (tweede payload voor betask)
        :return: sync.change record
        """
        def _to_json(v):
            if v is None:
                return False
            if isinstance(v, str):
                return v
            return json.dumps(v)

        return self.env['myschool.sap.sync.change'].create({
            'run_id': run.id,
            'object_type': object_type,
            'action': action,
            'source_key': source_key or '',
            'display_name': display_name or '',
            'target_model': target_model or '',
            'target_res_id': target_res_id or 0,
            'payload_new_json': _to_json(payload_new),
            'payload_old_json': _to_json(payload_old),
            'betask_target': betask_target,
            'betask_data2_json': _to_json(betask_data2),
            'diff_summary': diff_summary or '',
            'state': 'planned',
        })

    @api.model
    def finalise_analysis(self, run, auto_commit_on_no_breach=True):
        """Sluit de analyse-fase af: tel, check drempel, beslis volgende state.

        :return: dict {'state': str, 'breach': bool, 'committed': bool}
        """
        counts, breach, details = self._compute_counts_and_breach(run)

        run.write({
            'counts_json': json.dumps(counts),
            'threshold_breach': breach,
            'threshold_breach_details': '\n'.join(details) if details else False,
        })

        if breach:
            run.write({'state': 'awaiting_approval'})
            self._log_event(
                'SAP-SYNC-RUN-BREACH',
                f'Run {run.name}: drempel overschreden — wacht op '
                f'goedkeuring. Details: {"; ".join(details)}'
            )
            self._raise_safeguard_alarm(run, details)
            return {'state': 'awaiting_approval', 'breach': True,
                    'committed': False}

        if run.require_review:
            run.write({'state': 'awaiting_review'})
            self._log_event(
                'SAP-SYNC-RUN-AWAITING-REVIEW',
                f'Run {run.name}: review aangevraagd door gebruiker '
                f'({run.user_id.login or "-"}).'
            )
            return {'state': 'awaiting_review', 'breach': False,
                    'committed': False}

        if auto_commit_on_no_breach:
            self.commit_run(run.id, _auto=True)
            return {'state': run.state, 'breach': False, 'committed': True}

        run.write({'state': 'awaiting_review'})
        return {'state': 'awaiting_review', 'breach': False,
                'committed': False}

    # ------------------------------------------------------------------
    # Threshold check
    # ------------------------------------------------------------------

    @api.model
    def _get_thresholds(self):
        """Lees de drempels uit informat.service.config (met defaults)."""
        config = self.env['myschool.informat.service.config'].get_config()
        if not getattr(config, 'safeguard_enabled', True):
            return None, 0
        thresholds = {
            'PERSON': getattr(
                config, 'threshold_person_pct', DEFAULT_THRESHOLDS['PERSON']),
            'ORG': getattr(
                config, 'threshold_org_pct', DEFAULT_THRESHOLDS['ORG']),
            'ORGGROUP': getattr(
                config, 'threshold_orggroup_pct',
                DEFAULT_THRESHOLDS['ORGGROUP']),
            'PROPRELATION': getattr(
                config, 'threshold_proprelation_pct',
                DEFAULT_THRESHOLDS['PROPRELATION']),
        }
        min_changes = getattr(config, 'safeguard_min_changes', 5)
        return thresholds, min_changes

    @api.model
    def _existing_count(self, object_type):
        """Tel actieve bestaande records per type, voor de drempel-noemer."""
        if object_type == 'PERSON':
            return self.env['myschool.person'].search_count([
                ('is_active', '=', True)])
        if object_type == 'ORG':
            return self.env['myschool.org'].search_count([
                ('is_active', '=', True)])
        if object_type == 'ORGGROUP':
            # Persongroups zijn org-records met type=PERSONGROUP.
            pg_type = self.env['myschool.org.type'].search([
                ('name', '=', 'PERSONGROUP')], limit=1)
            if not pg_type:
                return 0
            return self.env['myschool.org'].search_count([
                ('is_active', '=', True),
                ('org_type_id', '=', pg_type.id)])
        if object_type == 'PROPRELATION':
            return self.env['myschool.proprelation'].search_count([
                ('is_active', '=', True)])
        # Niet-safeguarded types (ROLE, RELATION): tellen op 0 zodat ze
        # nooit een breach triggeren via deze pad.
        return 0

    @api.model
    def _compute_counts_and_breach(self, run):
        """Bereken counts per object_type + check drempel-overschrijding."""
        thresholds, min_changes = self._get_thresholds()
        counts = {}
        breach_details = []

        for ch in run.change_ids:
            ot = ch.object_type
            if ot not in counts:
                counts[ot] = {
                    'add': 0, 'upd': 0, 'deact': 0,
                    'total_existing': 0, 'pct': 0.0,
                }
            counts[ot][ch.action.lower()] = counts[ot].get(
                ch.action.lower(), 0) + 1

        breach = False
        for ot, c in counts.items():
            existing = self._existing_count(ot)
            total = c['add'] + c['upd'] + c['deact']
            c['total_existing'] = existing
            c['pct'] = round(
                (total / max(existing, 1)) * 100.0, 2) if existing else 0.0
            if (thresholds and ot in thresholds
                    and total >= min_changes
                    and c['pct'] > thresholds[ot]):
                breach = True
                breach_details.append(
                    f'{ot}: {total} wijzigingen / {existing} actief '
                    f'= {c["pct"]:.1f}% (drempel: {thresholds[ot]:.1f}%)'
                )

        return counts, breach, breach_details

    # ------------------------------------------------------------------
    # Approve / block / commit
    # ------------------------------------------------------------------

    @api.model
    def set_change_state(self, change_ids, new_state, reason=''):
        """Wijzig de status van een set sync.change-records.

        Valide overgangen vanuit ``planned``/``to_review_later``:
        approved, blocked, to_review_later. Niet vanuit eindstatussen
        (applied, superseded, cancelled).
        """
        valid_targets = ('approved', 'blocked', 'to_review_later', 'planned')
        if new_state not in valid_targets:
            raise ValueError(_('Ongeldige doel-status: %s') % new_state)

        changes = self.env['myschool.sap.sync.change'].browse(change_ids)
        editable = changes.filtered(
            lambda c: c.state in ('planned', 'approved', 'blocked',
                                  'to_review_later'))
        editable.write({
            'state': new_state,
            'state_reason': reason or False,
            'reviewer_id': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
        })

        code = {
            'approved': 'SAP-SYNC-CHANGE-APPROVED',
            'blocked': 'SAP-SYNC-CHANGE-BLOCKED',
            'to_review_later': 'SAP-SYNC-CHANGE-MARKED',
            'planned': 'SAP-SYNC-CHANGE-RESET',
        }[new_state]
        self._log_event(
            code,
            f'{len(editable)} change(s) → {new_state} '
            f'door {self.env.user.login} '
            f'(reden: {reason or "—"})'
        )
        return len(editable)

    # Volgorde voor cascade-veiligheid bij commit:
    # ORG → ORGGROUP → ROLE → PERSON → PROPRELATION
    _COMMIT_ORDER_MAP = {
        'ORG': 1, 'ORGGROUP': 2, 'ROLE': 3,
        'PERSON': 4, 'PROPRELATION': 5, 'RELATION': 6,
    }

    @api.model
    def _apply_changes_records(self, changes):
        """Lage-level helper: zet een set sync.change-records om in
        betasks, run de cascade, geeft (created, failed) terug.

        Roept geen run-state-transitie aan — dat is taak van de callers
        (commit_run finalises naar 'applied', apply_changes laat de run
        in zijn huidige state staan).
        """
        betask_service = self.env['myschool.betask.service']
        created = 0
        failed = 0

        for ch in changes.sorted(key=lambda c: (
                self._COMMIT_ORDER_MAP.get(c.object_type, 99), c.action)):
            try:
                data = ch.payload_new_json
                data2 = ch.betask_data2_json or ''
                # ORGGROUP is een safeguard-classificatie (PERSONGROUP-
                # orgs); de bestaande betask-handlers gebruiken nog
                # gewoon 'ORG' (de payload bevat org_type=PERSONGROUP).
                betask_obj = 'ORG' if ch.object_type == 'ORGGROUP' \
                    else ch.object_type
                task = betask_service.create_task(
                    target=ch.betask_target or 'DB',
                    obj=betask_obj,
                    action=ch.action,
                    data=data,
                    data2=data2,
                    auto_sync=True,
                )
                ch.write({
                    'betask_id': task.id if task else False,
                    'state': 'applied' if task else 'failed',
                    'reviewer_id': self.env.user.id,
                    'reviewed_at': fields.Datetime.now(),
                })
                if task:
                    created += 1
                else:
                    failed += 1
            except Exception as e:
                _logger.exception(
                    'SAP-SYNC commit: change %d → betask faalde', ch.id)
                ch.write({
                    'state': 'failed',
                    'state_reason': f'Betask-creation: {e}',
                })
                failed += 1

        # Cascade-fase: LDAP/CLOUD/AD/SMARTSCHOOL-betasks die door de
        # DB/* handlers werden gequeued.
        try:
            self.env['myschool.betask.processor'].process_all_pending()
        except Exception:
            _logger.exception(
                'SAP-SYNC commit: process_all_pending faalde — '
                'queue wordt door cron afgehandeld')

        return created, failed

    @api.model
    def _maybe_finalise_run(self, run):
        """Check of de run nog open changes heeft. Zo niet: state →
        'applied' + finished_at. Wordt gebruikt na partial commits zodat
        de run vanzelf afsluit zodra alles afgewerkt is."""
        still_open = run.change_ids.filtered(
            lambda c: c.state in ('planned', 'approved',
                                  'to_review_later'))
        if not still_open and run.state not in (
                'applied', 'cancelled', 'failed'):
            run.write({
                'state': 'applied',
                'finished_at': fields.Datetime.now(),
                'summary': (run.summary or '') +
                '\nRun afgesloten: alle changes afgewerkt.',
            })
            self._log_event(
                'SAP-SYNC-RUN-COMMITTED',
                f'Run {run.name}: automatisch afgesloten — alle '
                f'changes zijn afgewerkt.'
            )

    @api.model
    def apply_changes(self, change_ids):
        """Partial commit: zet geselecteerde sync.change-records nu om
        in betasks zonder te wachten op een batch-wide commit.

        Werkt op rijen in state 'planned' of 'approved'. Run blijft in
        zijn huidige state (typisch awaiting_review/awaiting_approval)
        zodat de admin verder kan reviewen. Zodra de laatste open
        change beslist is, sluit _maybe_finalise_run de run af.

        :param change_ids: lijst van sync.change IDs
        :return: dict {'created': N, 'failed': N, 'skipped': N}
        """
        changes = self.env['myschool.sap.sync.change'].browse(change_ids)
        eligible = changes.filtered(
            lambda c: c.state in ('planned', 'approved'))
        skipped = len(changes) - len(eligible)

        if not eligible:
            return {'created': 0, 'failed': 0, 'skipped': skipped}

        created, failed = self._apply_changes_records(eligible)

        self._log_event(
            'SAP-SYNC-CHANGE-APPLIED',
            f'{created} change(s) direct toegepast door '
            f'{self.env.user.login} ({failed} fout(en), '
            f'{skipped} overgeslagen).'
        )

        # Probeer per betrokken run af te sluiten als er niks meer
        # openstaat. Meestal één run, maar veilig om de set te nemen.
        for run in eligible.mapped('run_id'):
            self._maybe_finalise_run(run)

        return {'created': created, 'failed': failed, 'skipped': skipped}

    @api.model
    def commit_run(self, run_id, _auto=False):
        """Commit alle nog-eligible changes in een run en sluit hem af.

        Bij auto-commit (geen breach + auto_commit_on_no_breach):
        'planned' geldt als impliciet approved. Manueel via "Pas
        wijzigingen toe" eist expliciete approval (state='approved').
        """
        run = self.env['myschool.sap.sync.run'].browse(run_id)
        if not run.exists():
            return 0
        if run.state in ('applied', 'cancelled', 'failed'):
            return 0

        run.write({'state': 'applying'})

        eligible_states = (
            ('planned', 'approved') if _auto else ('approved',))
        eligible = run.change_ids.filtered(
            lambda c: c.state in eligible_states)

        created, failed = self._apply_changes_records(eligible)

        run.write({
            'state': 'applied',
            'finished_at': fields.Datetime.now(),
            'summary': (run.summary or '') +
            f'\nCommit: {created} betask(s) aangemaakt, {failed} fout(en).',
        })
        self._log_event(
            'SAP-SYNC-RUN-COMMITTED',
            f'Run {run.name}: {created} betask(s) aangemaakt, '
            f'{failed} fout(en).'
        )
        return created

    @api.model
    def cancel_run(self, run_id):
        """Annuleer een hele run: alle changes → cancelled, run → cancelled."""
        run = self.env['myschool.sap.sync.run'].browse(run_id)
        if not run.exists():
            return False
        if run.state in ('applied', 'cancelled', 'failed'):
            return False

        cancellable = run.change_ids.filtered(
            lambda c: c.state in ('planned', 'approved', 'blocked',
                                  'to_review_later'))
        cancellable.write({'state': 'cancelled'})
        run.write({
            'state': 'cancelled',
            'finished_at': fields.Datetime.now(),
            'summary': (run.summary or '') +
            f'\nGeannuleerd door {self.env.user.login}.',
        })
        self._log_event(
            'SAP-SYNC-RUN-CANCELLED',
            f'Run {run.name} geannuleerd door {self.env.user.login} — '
            f'{len(cancellable)} change(s) gecanceld.'
        )
        return True

    # ------------------------------------------------------------------
    # Alarm
    # ------------------------------------------------------------------

    @api.model
    def _raise_safeguard_alarm(self, run, breach_details):
        """Verstuur de drempel-alarm-mail naar de admin-groep + sys_event."""
        self._log_event(
            'SAP-SYNC-SAFEGUARD-BREACH',
            f'Drempel overschreden voor run {run.name}. '
            f'Details: {"; ".join(breach_details)}'
        )

        try:
            template = self.env.ref(
                'myschool_core.email_template_sap_safeguard',
                raise_if_not_found=False)
        except Exception:
            template = None
        if not template:
            _logger.warning(
                'SAP-SYNC: mail-template niet gevonden, geen alarm verstuurd')
            return False

        try:
            group = self.env.ref(
                'myschool_core.group_myschool_core_admin',
                raise_if_not_found=False)
        except Exception:
            group = None
        recipients = []
        if group:
            recipients = [u.email for u in group.users
                          if u.email and u.active]
        if not recipients:
            _logger.warning(
                'SAP-SYNC: geen admins met e-mail gevonden — alarm niet '
                'verstuurd (sys_event blijft staan)')
            return False

        try:
            template.with_context(
                sap_sync_recipients=','.join(recipients),
                sap_sync_breach_details='\n'.join(breach_details),
            ).send_mail(run.id, force_send=True, email_values={
                'email_to': ','.join(recipients),
            })
            _logger.info('SAP-SYNC: alarm verstuurd naar %d admin(s)',
                         len(recipients))
            return True
        except Exception as e:
            _logger.exception('SAP-SYNC: alarm-mail faalde: %s', e)
            return False

    # ------------------------------------------------------------------
    # API voor OWL2 frontend
    # ------------------------------------------------------------------

    @api.model
    def get_run_overview(self, run_id):
        """Aggregaat voor de review-UI header + tabs."""
        run = self.env['myschool.sap.sync.run'].browse(run_id)
        if not run.exists():
            return {}

        counts = run.get_counts()
        thresholds, _ = self._get_thresholds()
        thresholds = thresholds or {}

        types_info = []
        for ot in ('PERSON', 'ORG', 'ORGGROUP', 'PROPRELATION', 'ROLE',
                   'RELATION'):
            c = counts.get(ot)
            if not c:
                # Toon enkel types die effectief mutaties hebben.
                continue
            total = c['add'] + c['upd'] + c['deact']
            tr = thresholds.get(ot)
            state_color = 'ok'
            if tr is not None and c['pct'] > tr:
                state_color = 'breach'
            elif tr is not None and c['pct'] > tr * 0.6:
                state_color = 'warn'
            # Tel per state-categorie binnen dit type:
            per_state = {}
            for st in ('planned', 'approved', 'blocked', 'to_review_later',
                       'applied', 'failed', 'superseded', 'cancelled'):
                per_state[st] = run.change_ids.filtered(
                    lambda c, ot=ot, st=st: (
                        c.object_type == ot and c.state == st)).ids.__len__()
            types_info.append({
                'object_type': ot,
                'add': c['add'], 'upd': c['upd'], 'deact': c['deact'],
                'total': total,
                'existing': c['total_existing'],
                'pct': c['pct'],
                'threshold': tr,
                'state_color': state_color,
                'per_state': per_state,
            })

        return {
            'id': run.id,
            'name': run.name,
            'trigger': run.trigger,
            'state': run.state,
            'user': run.user_id.display_name or '',
            'started_at': fields.Datetime.to_string(run.started_at) or '',
            'finished_at': fields.Datetime.to_string(run.finished_at) or '',
            'inst_nrs': run.inst_nrs or '',
            'phases': run.get_phases(),
            'require_review': run.require_review,
            'threshold_breach': run.threshold_breach,
            'threshold_breach_details': run.threshold_breach_details or '',
            'error_description': run.error_description or '',
            'summary': run.summary or '',
            'types': types_info,
            'total_changes': run.change_count,
        }

    @api.model
    def get_changes(self, run_id, object_type=None, filter_state=None,
                    limit=500):
        """Lijst van changes voor de UI-tab."""
        domain = [('run_id', '=', run_id)]
        if object_type:
            domain.append(('object_type', '=', object_type))
        if filter_state:
            if isinstance(filter_state, (list, tuple)):
                domain.append(('state', 'in', list(filter_state)))
            else:
                domain.append(('state', '=', filter_state))

        changes = self.env['myschool.sap.sync.change'].search(
            domain, limit=limit)
        out = []
        for c in changes:
            out.append({
                'id': c.id,
                'object_type': c.object_type,
                'action': c.action,
                'source_key': c.source_key or '',
                'display_name': c.display_name or '',
                'diff_summary': c.diff_summary or '',
                'state': c.state,
                'state_reason': c.state_reason or '',
                'reviewer': c.reviewer_id.display_name or '',
                'reviewed_at': fields.Datetime.to_string(
                    c.reviewed_at) if c.reviewed_at else '',
                'has_old': bool(c.payload_old_json),
                'betask_id': c.betask_id.id or False,
            })
        return out

    @api.model
    def get_change_detail(self, change_id):
        """Volledige payload (oud + nieuw) voor de detail-modal."""
        c = self.env['myschool.sap.sync.change'].browse(change_id)
        if not c.exists():
            return {}
        return {
            'id': c.id,
            'object_type': c.object_type,
            'action': c.action,
            'source_key': c.source_key or '',
            'display_name': c.display_name or '',
            'diff_summary': c.diff_summary or '',
            'state': c.state,
            'state_reason': c.state_reason or '',
            'payload_new': c.get_payload_new(),
            'payload_old': c.get_payload_old(),
        }

    @api.model
    def bulk_approve_remaining(self, run_id):
        """UI-helper: alle resterende 'planned' → approved."""
        run = self.env['myschool.sap.sync.run'].browse(run_id)
        if not run.exists():
            return 0
        planned = run.change_ids.filtered(lambda c: c.state == 'planned')
        return self.set_change_state(planned.ids, 'approved',
                                     reason='Bulk-approve remaining')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _log_event(self, code, message):
        try:
            self.env['myschool.sys.event.service'].create_sys_event(
                code, message, True, source='BE')
        except Exception:
            _logger.exception('SAP-SYNC: sys_event logging faalde')

    @api.model
    def has_pending_approval_runs(self):
        """Voor _check_blocking_tasks: blokkeer nieuwe cron-runs als er
        nog goedkeuring openstaat."""
        return bool(self.env['myschool.sap.sync.run'].search_count([
            ('state', '=', 'awaiting_approval'),
        ]))
