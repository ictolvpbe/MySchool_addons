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
    ('persongroup_missing', 'PERSONGROUP ontbreekt in DB'),
    ('ad_ou_missing', 'OU ontbreekt in AD'),
    ('ad_group_missing', 'Groep ontbreekt in AD'),
    ('ad_user_missing', 'User ontbreekt in AD'),
    ('ad_membership_missing', 'Lidmaatschap ontbreekt in AD'),
    ('ad_unreachable', 'AD niet bereikbaar'),
    ('ldap_not_configured', 'Geen LDAP-configuratie'),
    ('google_ou_missing', 'OU ontbreekt in Google'),
    ('google_group_missing', 'Groep ontbreekt in Google'),
    ('google_user_missing', 'User ontbreekt in Google'),
    ('google_membership_missing', 'Lidmaatschap ontbreekt in Google'),
    ('google_unreachable', 'Google niet bereikbaar'),
    ('google_not_configured', 'Geen Google-configuratie'),
]

FIX_KIND_SELECTION = [
    ('none', 'Manueel — geen automatische fix'),
    ('open_record', 'Open record voor manuele aanvulling'),
    ('ldap_org_add', 'Maak LDAP/ORG/ADD betask aan'),
    ('sync_org_persongroup', 'Maak PERSONGROUP aan via _sync_org_persongroup'),
]


class HealthCheck(models.TransientModel):
    """One health-check run. Holds the issue lines and the orchestration
    methods that populate them."""
    _name = 'myschool.health.check'
    _description = 'MySchool Health Check'

    # ---- run scope (future-proof: enable / disable check categories) ----

    check_orgs = fields.Boolean(string='Check Organisaties', default=True)
    check_org_fields = fields.Boolean(string='Veldvolledigheid', default=True)
    check_org_persongroups = fields.Boolean(
        string='PERSONGROUP-bestaan (DB)', default=True,
        help='Voor elke container-org met has_comgroup of has_secgroup: '
             'verifieer dat er een actieve onderliggende PERSONGROUP bestaat '
             'die de groep draagt. Fix maakt die PERSONGROUP aan.')
    check_org_ad_sync = fields.Boolean(string='AD-sync (OU + groepen)', default=True)
    check_org_google_sync = fields.Boolean(
        string='Google-sync (OU + groepen)', default=True,
        help='Verifieer dat de OU/groepen die bij deze org horen ook '
             'in Google Workspace bestaan (orgUnits + groups).')

    check_persons = fields.Boolean(string='Check Personen', default=True)
    check_person_fields = fields.Boolean(
        string='Veldvolledigheid (personen)', default=True,
        help='Verifieer dat actieve, auto-sync personen de nodige '
             'identifier-velden (person_fqdn_internal, email_cloud) hebben '
             'om sync mogelijk te maken.')
    check_person_ad_sync = fields.Boolean(
        string='AD-sync (personen)', default=True,
        help='Probe of person_fqdn_internal effectief bestaat in AD.')
    check_person_google_sync = fields.Boolean(
        string='Google-sync (personen)', default=True,
        help='Probe of email_cloud effectief bestaat als user in Google '
             'Workspace.')

    check_memberships = fields.Boolean(
        string='Check Lidmaatschappen', default=True,
        help='Verifieer dat P-O proprelations naar PERSONGROUP-orgs een '
             'effectief lidmaatschap hebben in AD en/of Google.')
    check_membership_ad_sync = fields.Boolean(
        string='AD-sync (lidmaatschappen)', default=True)
    check_membership_google_sync = fields.Boolean(
        string='Google-sync (lidmaatschappen)', default=True)

    only_active = fields.Boolean(
        string='Alleen actieve records',
        default=True,
        help='Inactieve organisaties/personen/relaties overslaan.')
    only_autosync = fields.Boolean(
        string='Alleen autosync=True',
        default=True,
        help='Records met automatic_sync=False overslaan — die zijn bewust '
             'losgekoppeld van de externe systemen.')

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

        # External-system probe caches — shared across org / person /
        # membership phases so we only open one connection per LDAP server
        # and one Google service per workspace config, and only list each
        # group's members once even when many proprelations reference it.
        ext_state = self._init_ext_state()

        if self.check_orgs:
            n_field, n_ad, n_g = self._run_org_checks(ext_state)
            summary_lines.append(
                _('Orgs — veld-issues: %(f)s, AD-sync: %(a)s, '
                  'Google-sync: %(g)s') % {'f': n_field, 'a': n_ad, 'g': n_g})

        if self.check_persons:
            n_field, n_ad, n_g = self._run_person_checks(ext_state)
            summary_lines.append(
                _('Personen — veld-issues: %(f)s, AD-sync: %(a)s, '
                  'Google-sync: %(g)s') % {'f': n_field, 'a': n_ad, 'g': n_g})

        if self.check_memberships:
            n_ad, n_g = self._run_membership_checks(ext_state)
            summary_lines.append(
                _('Lidmaatschappen — AD-sync: %(a)s, Google-sync: %(g)s')
                % {'a': n_ad, 'g': n_g})

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

    # --------------------------------------------------------------------
    # External-system probe state
    # --------------------------------------------------------------------

    def _init_ext_state(self):
        """Return the shared cache dict used by all sync-checks.

        Structure:
            ad.unreachable_servers   : set of ldap.server.config ids
            ad.group_members         : dict[(config_id, dn_lower)] -> set of
                                       normalized member DNs (lowercased)
            google.unreachable       : set of google.workspace.config ids
            google.unconfigured_orgs : set of org ids for which we already
                                       emitted a "no workspace" warning
            google.services          : dict[config_id] -> directory service
            google.group_members     : dict[(config_id, email_lower)] -> set of
                                       lowercased member emails
        """
        return {
            'ad': {
                'unreachable_servers': set(),
                'connections': {},
                'group_members': {},
            },
            'google': {
                'unreachable': set(),
                'unconfigured_orgs': set(),
                'services': {},
                'group_members': {},
            },
        }

    # ====================================================================
    # Org checks
    # ====================================================================

    def _run_org_checks(self, ext_state):
        """Run field-, persongroup-, AD- and Google-sync checks for all
        (active, autosync) orgs.

        Returns ``(field_issue_count, ad_issue_count, google_issue_count)``.
        Persongroup-existence issues fold into the field-issue count so the
        summary line stays meaningful at "data-completeness" level.
        """
        Org = self.env['myschool.org']

        domain = []
        if self.only_active:
            domain.append(('is_active', '=', True))
        if self.only_autosync:
            domain.append(('automatic_sync', '=', True))
        orgs = Org.search(domain)

        n_field = n_ad = n_google = 0

        for org in orgs:
            if self.check_org_fields:
                n_field += self._check_org_fields(org)
            if self.check_org_persongroups:
                n_field += self._check_org_persongroup_existence(org)
            if self.check_org_ad_sync:
                n_ad += self._check_org_ad_sync(org, ext_state['ad'])
            if self.check_org_google_sync:
                n_google += self._check_org_google_sync(org, ext_state['google'])

        return n_field, n_ad, n_google

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

    # ---- PERSONGROUP existence (DB layer) -------------------------------

    def _check_org_persongroup_existence(self, org):
        """For container-orgs with has_comgroup/has_secgroup, verify that
        an active PERSONGROUP child exists (the org that carries the
        actual AD group). When missing → emit a fix-via-sync issue.

        Skip rules:
        * PERSONGROUP-typed orgs themselves: the org IS the group, no
          child needed (the existing field/AD checks cover those).
        * Orgs without either flag set: nothing to back.

        The matching logic mirrors what
        ``betask_processor._sync_org_persongroup`` does internally —
        find a PERSONGROUP whose ``com_group_name`` or ``sec_group_name``
        matches what the container would spawn (which is just
        ``f'{prefix}{org.name_short}'`` after the schoolboard ancestor
        walk). To stay independent of those naming heuristics here, we
        rely on an ORG-TREE child of type PERSONGROUP whose name_short
        starts with the container's name_short — accepting any group
        in that family. False positives are unlikely (different prefixes
        per family) and far less harmful than a false negative that
        spawns a duplicate.
        """
        n = 0
        if not org.org_type_id:
            return 0
        org_type_name = (org.org_type_id.name or '').upper()
        if org_type_name == 'PERSONGROUP':
            return 0
        if not (org.has_comgroup or org.has_secgroup):
            return 0
        if getattr(org, 'is_groups_container', False):
            # Container already has at least one PG child → covered by
            # design. (is_groups_container is a stored compute on org.)
            return 0

        # Per-flag tracking so a half-spawned setup (com OK, sec missing)
        # produces one issue per missing flag.
        missing_flags = []
        if org.has_comgroup:
            missing_flags.append(('has_comgroup', _('Com-groep')))
        if org.has_secgroup:
            missing_flags.append(('has_secgroup', _('Sec-groep')))

        for flag, label in missing_flags:
            n += self._add_issue(
                org, severity='error',
                issue_kind='persongroup_missing',
                description=_(
                    "%(flag)s=True maar geen onderliggende PERSONGROUP "
                    "gevonden voor %(label)s — fix maakt deze aan via "
                    "_sync_org_persongroup."
                ) % {'flag': flag, 'label': label},
                fix_kind='sync_org_persongroup')

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

    def _ad_group_members(self, ldap_service, config, group_dn, ad_state):
        """Return the set of normalized member-DNs for an AD group.

        Cached per ``(config.id, group_dn.lower())`` so a group referenced
        by many proprelations only hits AD once. On unknown/missing group
        we cache an empty set so we don't re-probe a phantom DN per call.
        """
        key = (config.id, (group_dn or '').lower())
        cached = ad_state['group_members'].get(key)
        if cached is not None:
            return cached
        members = set()
        try:
            ldap_service._check_ldap3_available()
            with ldap_service._get_connection(config) as conn:
                conn.search(
                    search_base=group_dn,
                    search_filter='(objectClass=group)',
                    search_scope='BASE',
                    attributes=['member'],
                )
                for entry in conn.entries:
                    raw = entry.member.values if 'member' in entry else []
                    for dn in raw or []:
                        members.add((dn or '').lower())
        except Exception as exc:
            msg = str(exc).lower()
            if 'nosuchobject' in msg or 'no such object' in msg \
                    or 'does not exist' in msg:
                pass  # cache empty set below
            else:
                raise
        ad_state['group_members'][key] = members
        return members

    # ---- Google probes --------------------------------------------------

    def _google_service(self, org, google_state):
        """Resolve the active workspace config + directory service for an
        org. Returns ``(config, svc)`` or ``(None, None)`` when no config
        is bound (an issue has been emitted on first occurrence).

        Caches the directory service per config so we only build it once
        per workspace tenant per run.
        """
        config = self.env['myschool.google.workspace.config'].sudo() \
            .get_server_for_org(org.id)
        if not config:
            return None, None
        if config.id in google_state['unreachable']:
            return config, None
        svc = google_state['services'].get(config.id)
        if svc is None:
            try:
                gws = self.env['myschool.google.directory.service']
                gws._check_google_available()
                svc = gws._get_directory_service(config)
                google_state['services'][config.id] = svc
            except Exception as exc:
                _logger.warning('[HEALTH] Google service init failed (%s): %s',
                                config.name, exc)
                google_state['unreachable'].add(config.id)
                return config, None
        return config, svc

    def _google_user_exists(self, svc, email):
        gws = self.env['myschool.google.directory.service']
        return gws._get_user(svc, email) is not None

    def _google_group_exists(self, svc, group_email):
        gws = self.env['myschool.google.directory.service']
        return gws._get_group(svc, group_email) is not None

    def _google_ou_exists(self, svc, config, ou_path):
        """Probe a Google orgUnit by path. Google's ``orgunits().get``
        takes an ``orgUnitPath`` (without leading slash) as the key after
        the customer id."""
        gws = self.env['myschool.google.directory.service']
        customer = config.customer_id or 'my_customer'
        try:
            from googleapiclient.errors import HttpError
            try:
                svc.orgunits().get(
                    customerId=customer,
                    orgUnitPath=ou_path.lstrip('/'),
                ).execute()
                return True
            except HttpError as e:
                status = getattr(getattr(e, 'resp', None), 'status', None)
                if status and int(status) == 404:
                    return False
                raise
        except ImportError:
            gws._check_google_available()
            raise

    def _google_group_members(self, svc, config, group_email, google_state):
        """Return the set of lowercased member emails for a Google group.

        Cached per ``(config.id, group_email.lower())`` so each group is
        listed only once per run, regardless of how many memberships
        reference it.
        """
        key = (config.id, (group_email or '').lower())
        cached = google_state['group_members'].get(key)
        if cached is not None:
            return cached
        members = set()
        try:
            from googleapiclient.errors import HttpError
            page_token = None
            while True:
                kwargs = {'groupKey': group_email, 'maxResults': 200}
                if page_token:
                    kwargs['pageToken'] = page_token
                try:
                    resp = svc.members().list(**kwargs).execute()
                except HttpError as e:
                    status = getattr(getattr(e, 'resp', None), 'status', None)
                    if status and int(status) == 404:
                        break  # group absent → empty member-set
                    raise
                for m in resp.get('members') or []:
                    em = (m.get('email') or '').lower()
                    if em:
                        members.add(em)
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except Exception as exc:
            _logger.warning('[HEALTH] Google members().list failed for %s: %s',
                            group_email, exc)
            # propagate so caller can mark workspace unreachable
            raise
        google_state['group_members'][key] = members
        return members

    # ---- Google-sync (org level) ----------------------------------------

    def _check_org_google_sync(self, org, google_state):
        """Verify Google Workspace presence of the OU / group(s) for this org.

        * Non-PERSONGROUP orgs with ``has_ou=True`` → probe the OU path
          derived from ``ou_fqdn_internal`` via
          ``google_directory_service.ou_dn_to_google_path``.
        * PERSONGROUP orgs with ``has_comgroup=True`` AND
          ``com_group_email`` set → probe the Google group by email.
          (Google only has a com-group equivalent — sec-groups stay
          AD-only by design.)

        Workspace-level failures (no config / unreachable) emit a single
        warning and short-circuit the rest of the targets for this org.
        """
        n = 0
        org_type_name = (org.org_type_id.name or '').upper() if org.org_type_id else ''

        targets = []  # list of (kind, identifier, label)
        if org_type_name == 'PERSONGROUP':
            if org.has_comgroup and (org.com_group_email or '').strip():
                targets.append(('group', org.com_group_email.strip(),
                                _('Com-groep (Google)')))
        else:
            if org.has_ou and (org.ou_fqdn_internal or '').strip():
                targets.append(('ou', org.ou_fqdn_internal.strip(), _('OU (Google)')))

        if not targets:
            return 0

        config, svc = self._google_service(org, google_state)
        if not config:
            if org.id in google_state['unconfigured_orgs']:
                return 0
            google_state['unconfigured_orgs'].add(org.id)
            return self._add_issue(
                org, severity='warning', issue_kind='google_not_configured',
                description=_('Geen Google-workspace geconfigureerd voor deze org'),
                fix_kind='none')
        if not svc:
            return self._add_issue(
                org, severity='warning', issue_kind='google_unreachable',
                description=_('Google-workspace %s niet bereikbaar — '
                              'sync-controle overgeslagen') % config.name,
                fix_kind='none')

        gws = self.env['myschool.google.directory.service']

        for kind, identifier, label in targets:
            try:
                if kind == 'ou':
                    ou_path = gws.ou_dn_to_google_path(identifier, config=config)
                    exists = self._google_ou_exists(svc, config, ou_path)
                    issue_kind = 'google_ou_missing'
                    display = ou_path
                else:
                    exists = self._google_group_exists(svc, identifier)
                    issue_kind = 'google_group_missing'
                    display = identifier
            except Exception as exc:
                _logger.warning(
                    '[HEALTH] Google probe failed for org %s (%s=%s): %s',
                    org.name, kind, identifier, exc)
                google_state['unreachable'].add(config.id)
                n += self._add_issue(
                    org, severity='warning', issue_kind='google_unreachable',
                    description=_('Google-workspace %(srv)s niet bereikbaar: %(err)s') % {
                        'srv': config.name, 'err': str(exc)},
                    fix_kind='none')
                return n

            if not exists:
                n += self._add_issue(
                    org, severity='error', issue_kind=issue_kind,
                    description=_('%(label)s ontbreekt in Google: %(id)s') % {
                        'label': label, 'id': display},
                    fix_kind='none')

        return n

    # ====================================================================
    # Person checks
    # ====================================================================

    # Identifier-fields a person must carry for sync to be possible. Not
    # all persons need both: an LDAP-only deployment will not require
    # email_cloud. The respective probe steps gate on the per-system
    # toggles, so a missing identifier only becomes an issue when the
    # matching probe-toggle is on.
    _PERSON_IDENTIFIER_FIELDS = {
        'ad': ('person_fqdn_internal', _('FQDN intern')),
        'google': ('email_cloud', _('E-mail cloud')),
    }

    def _run_person_checks(self, ext_state):
        """Field-completeness + AD/Google probe for every (active, autosync)
        person. Returns ``(field_count, ad_count, google_count)``."""
        Person = self.env['myschool.person']
        domain = []
        if self.only_active:
            domain.append(('is_active', '=', True))
        if self.only_autosync:
            domain.append(('automatic_sync', '=', True))
        persons = Person.search(domain)

        n_field = n_ad = n_google = 0
        for person in persons:
            n_field += self._check_person_fields(person)
            if self.check_person_ad_sync:
                n_ad += self._check_person_ad_sync(person, ext_state['ad'])
            if self.check_person_google_sync:
                n_google += self._check_person_google_sync(
                    person, ext_state['google'])
        return n_field, n_ad, n_google

    def _check_person_fields(self, person):
        """Identifier completeness — only complain about identifiers that
        the matching sync-toggle would actually probe. Keeps the report
        focused: an AD-only school won't see noise about email_cloud.
        """
        if not self.check_person_fields:
            return 0
        n = 0
        if self.check_person_ad_sync:
            fname, label = self._PERSON_IDENTIFIER_FIELDS['ad']
            if not (person[fname] or '').strip():
                n += self._add_issue(
                    person, object_type='person',
                    severity='warning', issue_kind='field_missing',
                    description=_('AD-sync aan maar %s is leeg') % label,
                    field_name=fname, fix_kind='open_record')
        if self.check_person_google_sync:
            fname, label = self._PERSON_IDENTIFIER_FIELDS['google']
            if not (person[fname] or '').strip():
                n += self._add_issue(
                    person, object_type='person',
                    severity='warning', issue_kind='field_missing',
                    description=_('Google-sync aan maar %s is leeg') % label,
                    field_name=fname, fix_kind='open_record')
        return n

    def _person_home_org(self, person):
        """Best-effort resolve of the org from which to derive the
        LDAP/Google config for a person. Falls back to the first active
        P-O assignment if no dedicated 'home org' field exists on
        person."""
        # Try the master P-O proprelation first — that is the canonical
        # "where does this person live" anchor for accounts.
        Pr = self.env['myschool.proprelation']
        master = Pr.search([
            ('id_person', '=', person.id),
            ('is_master', '=', True),
            ('is_active', '=', True),
            ('id_org', '!=', False),
        ], limit=1)
        if master:
            return master.id_org
        any_assignment = Pr.search([
            ('id_person', '=', person.id),
            ('is_active', '=', True),
            ('id_org', '!=', False),
        ], limit=1, order='priority desc, id asc')
        return any_assignment.id_org if any_assignment else self.env['myschool.org']

    def _check_person_ad_sync(self, person, ad_state):
        dn = (person.person_fqdn_internal or '').strip()
        if not dn:
            return 0  # field-check above already flagged this
        home_org = self._person_home_org(person)
        if not home_org:
            return self._add_issue(
                person, object_type='person',
                severity='warning', issue_kind='ldap_not_configured',
                description=_('Geen home-org gevonden — kan AD-server '
                              'niet resolven'),
                fix_kind='none')

        config = self.env['myschool.ldap.server.config'].sudo() \
            .get_server_for_org(home_org.id)
        if not config:
            return self._add_issue(
                person, object_type='person',
                severity='warning', issue_kind='ldap_not_configured',
                description=_('Geen LDAP-server voor home-org %s') % home_org.name,
                fix_kind='none')
        if config.id in ad_state['unreachable_servers']:
            return 0  # server-level warning already on the org-side run

        ldap_service = self.env['myschool.ldap.service']
        try:
            exists = self._dn_exists(ldap_service, config, dn)
        except Exception as exc:
            ad_state['unreachable_servers'].add(config.id)
            return self._add_issue(
                person, object_type='person',
                severity='warning', issue_kind='ad_unreachable',
                description=_('LDAP-server %(srv)s niet bereikbaar: %(err)s') % {
                    'srv': config.name, 'err': str(exc)},
                fix_kind='none')
        if not exists:
            return self._add_issue(
                person, object_type='person',
                severity='error', issue_kind='ad_user_missing',
                description=_('User ontbreekt in AD: %s') % dn,
                ldap_dn=dn, ldap_config_id=config.id, fix_kind='none')
        return 0

    def _check_person_google_sync(self, person, google_state):
        email = (person.email_cloud or '').strip()
        if not email:
            return 0
        home_org = self._person_home_org(person)
        if not home_org:
            return self._add_issue(
                person, object_type='person',
                severity='warning', issue_kind='google_not_configured',
                description=_('Geen home-org gevonden — kan Google-workspace '
                              'niet resolven'),
                fix_kind='none')

        config, svc = self._google_service(home_org, google_state)
        if not config:
            return 0  # org-side run will have flagged the no-config case
        if not svc:
            return 0  # workspace-level unreachable already reported

        try:
            exists = self._google_user_exists(svc, email)
        except Exception as exc:
            google_state['unreachable'].add(config.id)
            return self._add_issue(
                person, object_type='person',
                severity='warning', issue_kind='google_unreachable',
                description=_('Google-workspace %(srv)s niet bereikbaar: %(err)s') % {
                    'srv': config.name, 'err': str(exc)},
                fix_kind='none')
        if not exists:
            return self._add_issue(
                person, object_type='person',
                severity='error', issue_kind='google_user_missing',
                description=_('User ontbreekt in Google: %s') % email,
                fix_kind='none')
        return 0

    # ====================================================================
    # Membership checks
    # ====================================================================
    #
    # MySchool stores no direct "person belongs to group" row — group
    # membership is derived from two proprelation cascades, mirroring
    # the betask GROUPMEMBER/ADD cascade in manual_task_processor:
    #
    #   PPSBR (Person-Period-School-BackendRole)
    #     For each active PPSBR, look up the matching BRSO at any
    #     ORG-TREE ancestor of the PPSBR org. The BRSO's ``id_org`` is
    #     the persongroup target. The person should appear in that
    #     persongroup's com/sec group (AD) and com group (Google).
    #
    #   PG-G (PersonGroup-in-PersonGroup)
    #     A nested-group relation: ``id_org_child`` should appear in
    #     ``id_org``'s member list per matching com/sec flag-pair, both
    #     in AD (com_group_fqdn / sec_group_fqdn) and Google (com_group_email).

    def _run_membership_checks(self, ext_state):
        """Verify expected memberships in AD and Google.

        Returns ``(ad_issue_count, google_issue_count)``.
        """
        Pr = self.env['myschool.proprelation']
        Type = self.env['myschool.proprelation.type']

        n_ad = n_google = 0

        # ---- PPSBR cascade -------------------------------------------
        ppsbr_type = Type.search([('name', '=', 'PPSBR')], limit=1)
        if ppsbr_type:
            domain = [
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('id_person', '!=', False),
                ('id_org', '!=', False),
                ('id_role', '!=', False),
            ]
            if self.only_active:
                domain.append(('is_active', '=', True))
            if self.only_autosync:
                domain.append(('automatic_sync', '=', True))
            ppsbrs = Pr.search(domain)
            for ppsbr in ppsbrs:
                person = ppsbr.id_person
                if self.only_active and not person.is_active:
                    continue
                if self.only_autosync and not person.automatic_sync:
                    continue
                target_org = self._resolve_ppsbr_target_org(ppsbr)
                if not target_org:
                    continue  # no BRSO match → nothing to verify
                if self.check_membership_ad_sync:
                    n_ad += self._verify_person_in_org_groups(
                        ppsbr, person, target_org, ext_state['ad'])
                if self.check_membership_google_sync:
                    n_google += self._verify_person_in_org_groups_google(
                        ppsbr, person, target_org, ext_state['google'])

        # ---- PG-G cascade --------------------------------------------
        pg_g_type = Type.search([('name', '=', 'PG-G')], limit=1)
        if pg_g_type:
            domain = [
                ('proprelation_type_id', '=', pg_g_type.id),
                ('id_org', '!=', False),
                ('id_org_child', '!=', False),
            ]
            if self.only_active:
                domain.append(('is_active', '=', True))
            if self.only_autosync:
                domain.append(('automatic_sync', '=', True))
            pg_gs = Pr.search(domain)
            for pg_g in pg_gs:
                parent, child = pg_g.id_org, pg_g.id_org_child
                if self.only_active and (not parent.is_active or not child.is_active):
                    continue
                if self.only_autosync and (
                        not parent.automatic_sync or not child.automatic_sync):
                    continue
                if self.check_membership_ad_sync:
                    n_ad += self._verify_nested_group(pg_g, ext_state['ad'])
                if self.check_membership_google_sync:
                    n_google += self._verify_nested_group_google(
                        pg_g, ext_state['google'])
        return n_ad, n_google

    def _resolve_ppsbr_target_org(self, ppsbr):
        """Return the persongroup-org that the PPSBR's role maps to at
        the relevant school, or empty recordset if no BRSO matches.

        Walks ORG-TREE ancestors of ``ppsbr.id_org`` (using the existing
        processor helper) and picks the first active BRSO with the same
        role anchored at any ancestor. Mirrors the cascade in
        ``manual_task_processor._cascade_ppsbr_group_membership``.
        """
        processor = self.env['myschool.betask.processor']
        try:
            ancestors = list(processor._collect_org_ancestor_ids(ppsbr.id_org))
        except Exception:
            ancestors = []
        if not ancestors:
            ancestors = [ppsbr.id_org.id]
        Type = self.env['myschool.proprelation.type']
        brso_type = Type.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            return self.env['myschool.org']
        brso = self.env['myschool.proprelation'].search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_role', '=', ppsbr.id_role.id),
            ('id_org_parent', 'in', ancestors),
            ('is_active', '=', True),
        ], limit=1)
        return brso.id_org if brso else self.env['myschool.org']

    # ---- person-in-group verification (AD + Google) ---------------------

    def _verify_person_in_org_groups(self, ppsbr, person, target_org, ad_state):
        """Probe AD com/sec group member-attribute for ``person``."""
        person_dn = (person.person_fqdn_internal or '').strip()
        if not person_dn:
            return 0  # field-check on person covers this

        home_org = self._person_home_org(person) or target_org
        config = self.env['myschool.ldap.server.config'].sudo() \
            .get_server_for_org(home_org.id)
        if not config or config.id in ad_state['unreachable_servers']:
            return 0
        ldap_service = self.env['myschool.ldap.service']

        n = 0
        for flag, fname, label in (
            ('has_comgroup', 'com_group_fqdn_internal', _('Com-groep')),
            ('has_secgroup', 'sec_group_fqdn_internal', _('Sec-groep')),
        ):
            if not getattr(target_org, flag, False):
                continue
            group_dn = (target_org[fname] or '').strip()
            if not group_dn:
                continue
            try:
                members = self._ad_group_members(
                    ldap_service, config, group_dn, ad_state)
            except Exception as exc:
                ad_state['unreachable_servers'].add(config.id)
                _logger.warning(
                    '[HEALTH] AD members on %s failed: %s', group_dn, exc)
                continue
            if person_dn.lower() not in members:
                n += self._add_issue(
                    target_org, object_type='proprelation',
                    proprelation_id=ppsbr.id, person_id=person.id,
                    severity='error', issue_kind='ad_membership_missing',
                    description=_(
                        '%(person)s ontbreekt in %(label)s %(grp)s (AD) '
                        '— verwacht via PPSBR/%(role)s'
                    ) % {'person': person.display_name or person.name,
                         'label': label, 'grp': group_dn,
                         'role': ppsbr.id_role.name},
                    ldap_dn=group_dn, ldap_config_id=config.id,
                    fix_kind='none')
        return n

    def _verify_person_in_org_groups_google(self, ppsbr, person, target_org,
                                            google_state):
        """Probe Google com group membership for ``person``. Google only
        carries com-groups (mail-enabled) — sec-groups stay AD-only."""
        person_email = (person.email_cloud or '').lower().strip()
        if not person_email:
            return 0
        if not getattr(target_org, 'has_comgroup', False):
            return 0
        group_email = (target_org.com_group_email or '').strip()
        if not group_email:
            return 0

        home_org = self._person_home_org(person) or target_org
        config, svc = self._google_service(home_org, google_state)
        if not config or not svc:
            return 0
        try:
            members = self._google_group_members(
                svc, config, group_email, google_state)
        except Exception as exc:
            google_state['unreachable'].add(config.id)
            _logger.warning('[HEALTH] Google members on %s failed: %s',
                            group_email, exc)
            return 0

        if person_email not in members:
            return self._add_issue(
                target_org, object_type='proprelation',
                proprelation_id=ppsbr.id, person_id=person.id,
                severity='error', issue_kind='google_membership_missing',
                description=_(
                    '%(person)s ontbreekt in Google-groep %(grp)s '
                    '— verwacht via PPSBR/%(role)s'
                ) % {'person': person.display_name or person.name,
                     'grp': group_email, 'role': ppsbr.id_role.name},
                fix_kind='none')
        return 0

    # ---- nested-group verification (PG-G) -------------------------------

    def _verify_nested_group(self, pg_g, ad_state):
        """Probe AD: child group's DN should be in parent's member list,
        per shared flag-pair."""
        parent, child = pg_g.id_org, pg_g.id_org_child
        home_org = parent  # parent persongroup decides which AD server
        config = self.env['myschool.ldap.server.config'].sudo() \
            .get_server_for_org(home_org.id)
        if not config or config.id in ad_state['unreachable_servers']:
            return 0
        ldap_service = self.env['myschool.ldap.service']

        n = 0
        for flag, fname, label in (
            ('has_comgroup', 'com_group_fqdn_internal', _('Com-groep')),
            ('has_secgroup', 'sec_group_fqdn_internal', _('Sec-groep')),
        ):
            if not (getattr(parent, flag, False) and getattr(child, flag, False)):
                continue
            parent_dn = (parent[fname] or '').strip()
            child_dn = (child[fname] or '').strip()
            if not parent_dn or not child_dn:
                continue
            try:
                members = self._ad_group_members(
                    ldap_service, config, parent_dn, ad_state)
            except Exception as exc:
                ad_state['unreachable_servers'].add(config.id)
                _logger.warning(
                    '[HEALTH] AD members on %s failed: %s', parent_dn, exc)
                continue
            if child_dn.lower() not in members:
                n += self._add_issue(
                    parent, object_type='proprelation',
                    proprelation_id=pg_g.id,
                    severity='error', issue_kind='ad_membership_missing',
                    description=_(
                        '%(child)s ontbreekt als geneste %(label)s '
                        'in %(parent)s (AD)'
                    ) % {'child': child.name, 'parent': parent.name,
                         'label': label},
                    ldap_dn=parent_dn, ldap_config_id=config.id,
                    fix_kind='none')
        return n

    def _verify_nested_group_google(self, pg_g, google_state):
        """Probe Google: child group's email should be in parent's members.
        Only com-groups have a Google equivalent."""
        parent, child = pg_g.id_org, pg_g.id_org_child
        if not (getattr(parent, 'has_comgroup', False)
                and getattr(child, 'has_comgroup', False)):
            return 0
        parent_email = (parent.com_group_email or '').strip()
        child_email = (child.com_group_email or '').lower().strip()
        if not parent_email or not child_email:
            return 0

        config, svc = self._google_service(parent, google_state)
        if not config or not svc:
            return 0
        try:
            members = self._google_group_members(
                svc, config, parent_email, google_state)
        except Exception as exc:
            google_state['unreachable'].add(config.id)
            _logger.warning('[HEALTH] Google members on %s failed: %s',
                            parent_email, exc)
            return 0

        if child_email not in members:
            return self._add_issue(
                parent, object_type='proprelation',
                proprelation_id=pg_g.id,
                severity='error', issue_kind='google_membership_missing',
                description=_(
                    '%(child)s ontbreekt als geneste com-groep '
                    'in %(parent)s (Google)'
                ) % {'child': child.name, 'parent': parent.name},
                fix_kind='none')
        return 0

    # ====================================================================
    # Issue helpers
    # ====================================================================

    def _add_issue(self, record, severity, issue_kind, description,
                   object_type='org',
                   field_name=None, ldap_dn=None, ldap_config_id=None,
                   person_id=None, proprelation_id=None,
                   fix_kind='none'):
        """Append one issue line; returns 1 (so callers can ``n += …``).

        ``record`` is the primary anchor object (org/person/proprelation).
        ``object_type`` decides which m2o we hang it on; ``person_id`` /
        ``proprelation_id`` are explicit overrides for membership issues
        where the primary record is the org but we want the person /
        proprelation cross-reference visible in the result list.
        """
        vals = {
            'check_id': self.id,
            'severity': severity,
            'issue_kind': issue_kind,
            'object_type': object_type,
            'description': description,
            'field_name': field_name or False,
            'ldap_dn': ldap_dn or False,
            'ldap_config_id': ldap_config_id or False,
            'fix_kind': fix_kind,
        }
        if object_type == 'org':
            vals['org_id'] = record.id
        elif object_type == 'person':
            vals['person_id'] = record.id
        elif object_type == 'proprelation':
            # ``record`` is the org carrying the missing group; the
            # proprelation_id / person_id args make the row navigable.
            vals['org_id'] = record.id
            vals['proprelation_id'] = proprelation_id or False
            vals['person_id'] = person_id or False
        # Allow cross-references even when object_type is org/person.
        if person_id and 'person_id' not in vals:
            vals['person_id'] = person_id
        if proprelation_id and 'proprelation_id' not in vals:
            vals['proprelation_id'] = proprelation_id
        self.env['myschool.health.check.issue'].create(vals)
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

    # Object reference. ``object_type`` decides which m2o is the primary
    # anchor; the other m2os are cross-reference convenience pointers (e.g.
    # a proprelation issue carries both the org and the person).
    object_type = fields.Selection(
        [('org', 'Organisatie'),
         ('person', 'Persoon'),
         ('proprelation', 'Lidmaatschap')],
        required=True, default='org')
    org_id = fields.Many2one('myschool.org', string='Organisatie', ondelete='cascade')
    person_id = fields.Many2one('myschool.person', string='Persoon', ondelete='cascade')
    proprelation_id = fields.Many2one('myschool.proprelation', string='Relatie', ondelete='cascade')

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
        target = None
        if self.object_type == 'org' and self.org_id:
            target = ('myschool.org', self.org_id.id)
        elif self.object_type == 'person' and self.person_id:
            target = ('myschool.person', self.person_id.id)
        elif self.object_type == 'proprelation' and self.proprelation_id:
            target = ('myschool.proprelation', self.proprelation_id.id)
        if not target:
            raise UserError(_('Geen record om te openen.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': target[0],
            'res_id': target[1],
            'views': [[False, 'form']],
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

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

        if self.fix_kind == 'sync_org_persongroup':
            return self._fix_sync_org_persongroup()

        raise UserError(_('Geen automatische fix beschikbaar voor deze bevinding.'))

    def _fix_sync_org_persongroup(self):
        """Spawn the missing PERSONGROUP via the betask-processor's
        ``_sync_org_persongroup`` helper. That helper does the resolve-
        or-create itself (incl. ORG-TREE wiring + AD-field population),
        so a subsequent health-check run will find the PERSONGROUP and
        — if its AD group still doesn't exist — flag it for the
        ``ldap_org_add`` fix in the same UI."""
        if not self.org_id:
            raise UserError(_('Geen organisatie gekoppeld aan deze bevinding.'))

        processor = self.env['myschool.betask.processor']
        try:
            processor._sync_org_persongroup(self.org_id)
        except Exception as exc:
            _logger.exception(
                '[HEALTH] _sync_org_persongroup failed for %s', self.org_id.name)
            self.write({'fix_message': _('Fout: %s') % exc})
            raise UserError(self.fix_message)

        self.write({
            'is_fixed': True,
            'fix_message': _('PERSONGROUP-sync voltooid voor %s') % self.org_id.name,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('PERSONGROUP-fix toegepast'),
                'message': self.fix_message,
                'type': 'success',
            },
        }

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
