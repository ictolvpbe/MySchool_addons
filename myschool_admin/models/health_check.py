# -*- coding: utf-8 -*-
"""
Health Check
============
Tools-menu function that scans MySchool core objects (start: orgs) for
data-completeness and AD/LDAP sync issues, lists the necessary
corrections, and offers a per-row "Fix" action.

Architecture
------------
* ``myschool.health.check``         — transient session (one per run)
* ``myschool.health.check.issue``   — transient o2m line (one per finding)

Each issue carries enough metadata (``issue_kind``, ``fix_kind``, target
ids) to know how to fix itself; ``action_fix()`` dispatches on
``fix_kind``.

Adding new check categories later (persons, proprelations, …) means
extending ``_run_org_checks`` with a sibling routine; the model and view
are generic.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


# ---- severity / kind enums (pure strings, used by selection fields) ----

SEVERITY_SELECTION = [
    ('error', 'Error'),
    ('warning', 'Warning'),
    ('info', 'Info'),
]

ISSUE_KIND_SELECTION = [
    ('field_missing', 'Verplicht veld leeg'),
    ('flag_inconsistent', 'Flag-inconsistentie'),
    ('ad_ou_missing', 'OU ontbreekt in AD'),
    ('ad_group_missing', 'Groep ontbreekt in AD'),
    ('ad_unreachable', 'AD niet bereikbaar'),
    ('ldap_not_configured', 'Geen LDAP-configuratie'),
]

FIX_KIND_SELECTION = [
    ('none', 'Manueel — geen automatische fix'),
    ('open_record', 'Open record voor manuele aanvulling'),
    ('ldap_org_add', 'Maak LDAP/ORG/ADD betask aan'),
]


class HealthCheck(models.TransientModel):
    """One health-check run. Holds the issue lines and the orchestration
    methods that populate them."""
    _name = 'myschool.health.check'
    _description = 'MySchool Health Check'

    # ---- run scope (future-proof: enable / disable check categories) ----

    check_orgs = fields.Boolean(string='Check Organisaties', default=True)
    check_org_fields = fields.Boolean(string='Veldvolledigheid', default=True)
    check_org_ad_sync = fields.Boolean(string='AD-sync (OU + groepen)', default=True)

    only_active = fields.Boolean(
        string='Alleen actieve records',
        default=True,
        help='Inactieve organisaties overslaan.')

    # ---- results ----

    issue_ids = fields.One2many(
        'myschool.health.check.issue', 'check_id', string='Bevindingen')

    issue_count = fields.Integer(
        string='Aantal bevindingen', compute='_compute_counts')
    error_count = fields.Integer(
        string='Errors', compute='_compute_counts')
    warning_count = fields.Integer(
        string='Warnings', compute='_compute_counts')

    @api.depends('issue_ids', 'issue_ids.severity')
    def _compute_counts(self):
        for rec in self:
            rec.issue_count = len(rec.issue_ids)
            rec.error_count = len(rec.issue_ids.filtered(
                lambda i: i.severity == 'error'))
            rec.warning_count = len(rec.issue_ids.filtered(
                lambda i: i.severity == 'warning'))

    last_run_at = fields.Datetime(string='Laatste run', readonly=True)
    summary = fields.Text(string='Samenvatting', readonly=True)

    # ====================================================================
    # Run orchestration
    # ====================================================================

    def action_run(self):
        """(Re)run all enabled checks; replaces previous issues."""
        self.ensure_one()
        self.issue_ids.unlink()

        summary_lines = []

        if self.check_orgs:
            n_field, n_sync = self._run_org_checks()
            summary_lines.append(
                _('Orgs — veld-issues: %s, AD-sync issues: %s') % (n_field, n_sync))

        self.write({
            'last_run_at': fields.Datetime.now(),
            'summary': '\n'.join(summary_lines),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [[False, 'form']],
            'target': 'new',
        }

    # ====================================================================
    # Org checks
    # ====================================================================

    def _run_org_checks(self):
        """Run field- and AD-sync checks for all (active) orgs.

        Returns (field_issue_count, sync_issue_count).
        """
        Org = self.env['myschool.org']

        domain = []
        if self.only_active:
            domain.append(('is_active', '=', True))
        orgs = Org.search(domain)

        n_field = n_sync = 0

        # AD-sync: cache LDAP probes per org so a single connection per
        # configured server suffices, and skip orgs whose server cannot
        # be reached (one warning per server, not per org).
        ad_state = {
            'unreachable_servers': set(),  # ldap.server.config ids
            'connections': {},             # config_id -> Connection (lazy)
        }

        for org in orgs:
            if self.check_org_fields:
                n_field += self._check_org_fields(org)
            if self.check_org_ad_sync:
                n_sync += self._check_org_ad_sync(org, ad_state)

        return n_field, n_sync

    # ---- field-completeness ---------------------------------------------

    # All orgs: these fields should be set regardless of flags. Picked
    # by hand — `displayname` is intentionally optional (UI fallback),
    # `name_tree` is auto-computed, address fields are out-of-scope.
    _ORG_BASE_REQUIRED_FIELDS = [
        ('name', 'Naam'),
        ('name_short', 'Korte naam'),
        ('inst_nr', 'Instellingsnummer'),
        ('org_type_id', 'Organisatie-type'),
    ]

    # Only required when the corresponding flag is set:
    _ORG_FLAG_REQUIRED_FIELDS = {
        'has_ou': [
            ('ou_fqdn_internal', 'OU FQDN intern'),
            ('ou_fqdn_external', 'OU FQDN extern'),
        ],
        'has_comgroup': [
            ('com_group_name', 'Com-groep naam'),
            ('com_group_fqdn_internal', 'Com-groep FQDN intern'),
            ('com_group_fqdn_external', 'Com-groep FQDN extern'),
        ],
        'has_secgroup': [
            ('sec_group_name', 'Sec-groep naam'),
            ('sec_group_fqdn_internal', 'Sec-groep FQDN intern'),
            ('sec_group_fqdn_external', 'Sec-groep FQDN extern'),
        ],
    }

    def _check_org_fields(self, org):
        """Field-completeness checks. Returns the number of issues
        appended to ``self.issue_ids``."""
        n = 0
        org_type_name = (org.org_type_id.name or '').upper() if org.org_type_id else ''

        for fname, label in self._ORG_BASE_REQUIRED_FIELDS:
            if not org[fname]:
                n += self._add_issue(
                    org, severity='error', issue_kind='field_missing',
                    description=_('Verplicht veld leeg: %s') % label,
                    field_name=fname, fix_kind='open_record')

        for flag, fields_list in self._ORG_FLAG_REQUIRED_FIELDS.items():
            if not org[flag]:
                continue
            for fname, label in fields_list:
                if not org[fname]:
                    n += self._add_issue(
                        org, severity='error', issue_kind='field_missing',
                        description=_('%(flag)s=True maar %(field)s is leeg') % {
                            'flag': flag, 'field': label},
                        field_name=fname, fix_kind='open_record')

        # Com-group e-mail is needed once either has_comgroup flag is on
        # AND a com_group_name is present (otherwise it would just chain
        # off the previous error).
        if org.has_comgroup and org.com_group_name and not org.com_group_email:
            n += self._add_issue(
                org, severity='warning', issue_kind='field_missing',
                description=_('Com-groep e-mail ontbreekt'),
                field_name='com_group_email', fix_kind='open_record')

        # PERSONGROUP invariant: name == name_short (ensures group lookup
        # by either field returns the same record).
        if org_type_name == 'PERSONGROUP' and org.name and org.name_short \
                and org.name != org.name_short:
            n += self._add_issue(
                org, severity='warning', issue_kind='flag_inconsistent',
                description=_("PERSONGROUP-invariant geschonden: name (%s) ≠ name_short (%s)") % (
                    org.name, org.name_short),
                fix_kind='open_record')

        return n

    # ---- AD-sync --------------------------------------------------------

    def _check_org_ad_sync(self, org, ad_state):
        """Verify AD presence of the OU / group(s) this org should have.

        Strategy:
        * Resolve the LDAP config for the org via
          ``myschool.ldap.server.config.get_server_for_org``.
        * For non-PERSONGROUP orgs with ``has_ou=True`` → probe
          ``ou_fqdn_internal`` (BASE search).
        * For PERSONGROUP orgs with ``has_comgroup`` /
          ``has_secgroup``  → probe each ``*_group_fqdn_internal``.

        Each missing object yields an ``ad_*_missing`` issue with
        ``fix_kind='ldap_org_add'`` so the user can queue a single
        LDAP/ORG/ADD betask that creates the missing object.
        """
        n = 0
        org_type_name = (org.org_type_id.name or '').upper() if org.org_type_id else ''

        # Decide what should exist in AD for this org.
        targets = []  # list of (kind, dn, label)
        if org_type_name == 'PERSONGROUP':
            if org.has_comgroup and org.com_group_fqdn_internal:
                targets.append(('group', org.com_group_fqdn_internal,
                                _('Com-groep')))
            if org.has_secgroup and org.sec_group_fqdn_internal:
                targets.append(('group', org.sec_group_fqdn_internal,
                                _('Sec-groep')))
        else:
            if org.has_ou and org.ou_fqdn_internal:
                targets.append(('ou', org.ou_fqdn_internal, _('OU')))

        if not targets:
            return 0

        config = self.env['myschool.ldap.server.config'].sudo() \
            .get_server_for_org(org.id)
        if not config:
            return self._add_issue(
                org, severity='warning', issue_kind='ldap_not_configured',
                description=_('Geen LDAP-server geconfigureerd voor deze org'),
                fix_kind='none')

        if config.id in ad_state['unreachable_servers']:
            return self._add_issue(
                org, severity='warning', issue_kind='ad_unreachable',
                description=_('LDAP-server %s is niet bereikbaar — '
                              'sync-controle overgeslagen') % config.name,
                fix_kind='none')

        ldap_service = self.env['myschool.ldap.service']

        for kind, dn, label in targets:
            try:
                exists = self._dn_exists(ldap_service, config, dn)
            except Exception as exc:
                _logger.warning(
                    '[HEALTH] AD probe failed for org %s (dn=%s): %s',
                    org.name, dn, exc)
                ad_state['unreachable_servers'].add(config.id)
                n += self._add_issue(
                    org, severity='warning', issue_kind='ad_unreachable',
                    description=_('LDAP-server %(server)s niet bereikbaar: %(err)s') % {
                        'server': config.name, 'err': str(exc)},
                    fix_kind='none')
                # one server-level warning is enough — abort further probes.
                return n

            if not exists:
                issue_kind = 'ad_ou_missing' if kind == 'ou' else 'ad_group_missing'
                n += self._add_issue(
                    org, severity='error', issue_kind=issue_kind,
                    description=_('%(label)s ontbreekt in AD: %(dn)s') % {
                        'label': label, 'dn': dn},
                    ldap_dn=dn, ldap_config_id=config.id,
                    fix_kind='ldap_org_add')

        return n

    def _dn_exists(self, ldap_service, config, dn):
        """BASE-scope probe: returns True iff ``dn`` is present in AD.

        Wraps the ``ldap_service`` connection helper. Any LDAP-level
        "no such object" raises (caught in caller) — empty result set
        means absence and returns False.
        """
        ldap_service._check_ldap3_available()
        try:
            with ldap_service._get_connection(config) as conn:
                conn.search(
                    search_base=dn,
                    search_filter='(objectClass=*)',
                    search_scope='BASE',
                    attributes=['distinguishedName'],
                )
                return bool(conn.entries)
        except Exception as exc:
            # ldap3 raises LDAPNoSuchObjectResult on absent DN. We can
            # check for the message; treat all non-connection errors as
            # "absent". Re-raise on connection-level failures so the
            # caller marks the server unreachable.
            msg = str(exc).lower()
            if 'nosuchobject' in msg or 'no such object' in msg \
                    or 'does not exist' in msg:
                return False
            raise

    # ====================================================================
    # Issue helpers
    # ====================================================================

    def _add_issue(self, org, severity, issue_kind, description,
                   field_name=None, ldap_dn=None, ldap_config_id=None,
                   fix_kind='none'):
        """Append one issue line; returns 1 (so callers can ``n += …``)."""
        self.env['myschool.health.check.issue'].create({
            'check_id': self.id,
            'severity': severity,
            'issue_kind': issue_kind,
            'object_type': 'org',
            'org_id': org.id,
            'description': description,
            'field_name': field_name or False,
            'ldap_dn': ldap_dn or False,
            'ldap_config_id': ldap_config_id or False,
            'fix_kind': fix_kind,
        })
        return 1

    # ====================================================================
    # Bulk fix
    # ====================================================================

    def action_fix_all(self):
        """Apply ``action_fix`` to every issue with an automatic fix."""
        self.ensure_one()
        fixable = self.issue_ids.filtered(
            lambda i: i.fix_kind not in ('none', 'open_record') and not i.is_fixed)
        ok = err = 0
        for issue in fixable:
            try:
                issue.action_fix()
                ok += 1
            except Exception as exc:
                _logger.exception('[HEALTH] auto-fix failed for issue %s', issue.id)
                issue.write({'fix_message': str(exc)})
                err += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Health Check — fixes toegepast'),
                'message': _('%(ok)s opgelost, %(err)s mislukt.') % {
                    'ok': ok, 'err': err},
                'type': 'success' if not err else 'warning',
                'sticky': bool(err),
            },
        }


class HealthCheckIssue(models.TransientModel):
    """One row in the health-check report."""
    _name = 'myschool.health.check.issue'
    _description = 'MySchool Health Check Issue'
    _order = 'severity, object_type, id'

    check_id = fields.Many2one(
        'myschool.health.check', required=True, ondelete='cascade')

    severity = fields.Selection(SEVERITY_SELECTION, required=True, default='warning')
    issue_kind = fields.Selection(ISSUE_KIND_SELECTION, required=True)

    # Object reference. ``org_id`` for now; future check categories add
    # their own m2o (person_id, proprelation_id, …) and ``object_type``
    # tells the view which one to display.
    object_type = fields.Selection(
        [('org', 'Organisatie')], required=True, default='org')
    org_id = fields.Many2one('myschool.org', string='Organisatie', ondelete='cascade')

    description = fields.Char(string='Bevinding', required=True)

    # Optional fix metadata
    field_name = fields.Char(string='Veld')
    ldap_dn = fields.Char(string='LDAP DN')
    ldap_config_id = fields.Many2one('myschool.ldap.server.config', string='LDAP server')

    fix_kind = fields.Selection(FIX_KIND_SELECTION, default='none', required=True)
    is_fixed = fields.Boolean(string='Fix toegepast', default=False)
    fix_message = fields.Char(string='Fix-resultaat', readonly=True)

    # ---- per-row actions -----------------------------------------------

    def action_open_record(self):
        """Open the underlying record in a new modal so the user can
        complete missing fields by hand."""
        self.ensure_one()
        if self.object_type == 'org' and self.org_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'myschool.org',
                'res_id': self.org_id.id,
                'views': [[False, 'form']],
                'target': 'new',
                'context': {'form_view_initial_mode': 'edit'},
            }
        raise UserError(_('Geen record om te openen.'))

    def action_fix(self):
        """Dispatch on ``fix_kind``. Marks the issue as fixed (or stores
        the error in ``fix_message``)."""
        self.ensure_one()
        if self.is_fixed:
            return False

        if self.fix_kind == 'open_record':
            return self.action_open_record()

        if self.fix_kind == 'ldap_org_add':
            return self._fix_ldap_org_add()

        raise UserError(_('Geen automatische fix beschikbaar voor deze bevinding.'))

    def _fix_ldap_org_add(self):
        """Queue an LDAP/ORG/ADD betask. The standard processor decides
        whether to create an OU (non-persongroup) or one/both groups
        (persongroup) based on the org's flags — exactly what we need."""
        if not self.org_id:
            raise UserError(_('Geen organisatie gekoppeld aan deze bevinding.'))

        BeTaskService = self.env['myschool.betask.service']
        task = BeTaskService.create_task(
            'LDAP', 'ORG', 'ADD',
            data={'org_id': self.org_id.id},
            auto_sync=True,
        )

        # Process immediately so the user sees the result here, not on
        # the next cron tick.
        self.env['myschool.betask.processor'].process_single_task(task)

        if task.status == 'error':
            self.write({
                'fix_message': _('Betask error: %s') % (task.error_description or ''),
            })
            raise UserError(self.fix_message)

        self.write({
            'is_fixed': True,
            'fix_message': _('LDAP/ORG/ADD voltooid (betask %s)') % task.name,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AD-fix toegepast'),
                'message': self.fix_message,
                'type': 'success',
            },
        }
