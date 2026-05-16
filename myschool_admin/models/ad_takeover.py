# -*- coding: utf-8 -*-
"""AD Takeover — one-time migration assistant.

Discovers AD-objects (OU / group / user) under a chosen scope,
matches them against MySchool DB records, and lets an admin decide
per-finding what to do:

  * ``investigate``            — keep researching (default)
  * ``delete_after_migration`` — flag for later cleanup (user/group only)
  * ``takeover_pending``       — sync from AD → DB; admin reviews
                                 proposed parent/type/role first
  * ``takeover_done``          — DB record created
  * ``ignored``                — explicitly accepted as out-of-scope
  * ``matched``                — DB already has this object
  * ``delete_done``            — AD object removed at end of migration

Reads from AD only during discovery + takeover. The only AD-write happens
in ``apply_pending_deletes`` (cleanup phase), through the existing LDAP
delete helpers. All DB mutations (org/person creates) go through the
betask pipeline (MANUAL/ORG/ADD, MANUAL/PERSON/ADD,
MANUAL/PROPRELATION/ADD) per the architectural rule.
"""

import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


KIND_SELECTION = [('ou', 'OU'), ('group', 'Group'), ('user', 'User')]
MATCH_SELECTION = [
    ('unmatched', 'Niet in DB'),
    ('matched_in_db', 'Reeds in DB'),
]
STATUS_SELECTION = [
    ('investigate', 'Te onderzoeken'),
    ('delete_after_migration', 'Verwijder na migratie'),
    ('takeover_pending', 'Takeover gepland'),
    ('takeover_done', 'Takeover voltooid'),
    ('matched', 'Match in DB'),
    ('ignored', 'Genegeerd'),
    ('delete_done', 'Verwijderd in AD'),
]

# Phase A: new identity/state model. The old STATUS_SELECTION above
# still drives the existing action_scan / action_apply_pending_*
# code paths; phase B switches those to STATE_SELECTION and removes
# the legacy fields.
SOURCE_SELECTION = [
    ('ad',          'Active Directory'),
    ('cloud',       'Google Workspace'),
    ('smartschool', 'Smartschool'),
]
PROPOSAL_KIND_SELECTION = [
    ('link_only',      'Koppel — DB-record maken, bron ongewijzigd'),
    ('stamp_id',       'Schrijf sap_ref naar bron'),
    ('rename',         'Hernoem in bron'),
    ('move',           'Verplaats in bron'),
    ('membership_add', 'Voeg toe aan groep'),
    ('delete_after',   'Verwijder na migratie'),
    ('ignore',         'Negeer'),
]
STATE_SELECTION = [
    ('discovered',        'Ontdekt'),
    ('proposed',          'Voorstel klaar'),
    ('approved',          'Goedgekeurd'),
    ('applied_pilot',     'Pilot uitgevoerd'),
    ('verified',          'Geverifieerd'),
    ('done',              'Voltooid'),
    ('rolled_back',       'Teruggedraaid'),
    ('identity_conflict', 'Identity-conflict'),
    ('ignored',           'Genegeerd'),
]
RISK_SELECTION = [
    ('low',    'Laag'),
    ('medium', 'Medium'),
    ('high',   'Hoog'),
]
ENVIRONMENT_SELECTION = [
    ('prod', 'Productie'),
    ('test', 'Test'),
]
PHASE_SELECTION = [
    ('preflight', '1. Pre-flight — identity fixen'),
    ('link',      '2. Koppelen — DB-records aanmaken'),
    ('normalise', '3. Normaliseren — rename / move'),
    ('cleanup',   '4. Cleanup — verwijderen'),
    ('done',      '5. Voltooid'),
]

# Mapping for the post-init migration of existing rows. Maps the
# legacy ``status`` to (new ``state``, new ``proposal_kind``).
LEGACY_STATUS_MIGRATION = {
    'investigate':            ('discovered', None),
    'takeover_pending':       ('proposed',   'link_only'),
    'takeover_done':          ('done',       'link_only'),
    'delete_after_migration': ('proposed',   'delete_after'),
    'delete_done':            ('done',       'delete_after'),
    'matched':                ('done',       None),
    'ignored':                ('ignored',    'ignore'),
}


class AdTakeoverSession(models.Model):
    _name = 'myschool.ad.takeover.session'
    _description = 'AD Takeover Session'
    _order = 'create_date desc'

    name = fields.Char(required=True, default='Nieuwe AD-takeover sessie')
    # Fase B: ldap_config_id is no longer strictly required — a session
    # can scan AD, Cloud, or both. At least one source must be selected
    # (enforced via _check_at_least_one_source).
    ldap_config_id = fields.Many2one(
        'myschool.ldap.server.config',
        string='LDAP-server (AD)',
        domain="[('active', '=', True)]",
        help='Bronnetje voor de AD-scan. Leeg laten als deze sessie '
             'alleen Cloud (Google Workspace) wil scannen.')
    google_workspace_config_id = fields.Many2one(
        'myschool.google.workspace.config',
        string='Google Workspace',
        domain="[('active', '=', True)]",
        help='Bronnetje voor de Cloud-scan. Leeg laten als deze sessie '
             'alleen AD wil scannen. Zoals bij LDAP filtert de UI op de '
             'sessie-environment.')
    scope_org_id = fields.Many2one(
        'myschool.org', required=True, string='Scope (SCHOOL/SCHOOLBOARD)',
        domain="[('org_type_id.name', 'in', ['SCHOOL', 'SCHOOLBOARD'])]",
        help='Scan-scope is SUBTREE onder ou_fqdn_internal van deze org '
             '(AD) en orgUnitPath (Cloud). Strikt — geen scan buiten '
             'deze tak.')
    base_dn = fields.Char(
        compute='_compute_base_dn', store=True, readonly=True)
    cloud_ou_path = fields.Char(
        compute='_compute_cloud_ou_path', store=True, readonly=True,
        string='Cloud orgUnitPath')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('discovered', 'Gediscoverd'),
        ('in_progress', 'Bezig'),
        ('completed', 'Voltooid'),
    ], default='draft', required=True)

    # ---- Phase A: environment binding + wizard phase ----
    environment = fields.Selection(
        ENVIRONMENT_SELECTION,
        required=True,
        default='test',
        index=True,
        string='Omgeving',
        help='Sessies starten safe-by-default op test. Pas na verify op de '
             'test-omgeving wordt de sessie via "Promoot naar prod" naar '
             'productie overgezet.'
    )
    current_phase = fields.Selection(
        PHASE_SELECTION,
        default='preflight',
        required=True,
        index=True,
        string='Fase',
        help='Een sessie doorloopt vier fasen: eerst identity fixen '
             '(STAMP_ID + identity_conflict), dan DB-records koppelen, '
             'dan normaliseren (rename/move), tenslotte cleanup van '
             'leftover AD-objecten.'
    )
    role_filter_preflight = fields.Selection(
        selection=[
            ('employees_only', 'Alleen werknemers'),
            ('all',            'Iedereen'),
        ],
        default='employees_only',
        string='Pre-flight scope',
        help='Tijdens de pre-flight-fase: filter findings op rol. Standaard '
             '"alleen werknemers" — kleinere set, hoger-risico, beste '
             'pilot-kandidaten. Schakel naar "iedereen" zodra het patroon '
             'op werknemers bevestigd is.'
    )

    last_scan_at = fields.Datetime(readonly=True)
    scan_summary = fields.Text(readonly=True)
    finding_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id')
    finding_ou_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('kind', '=', 'ou')])
    finding_group_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('kind', '=', 'group')])
    finding_user_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('kind', '=', 'user')])

    # Phase-filtered finding lists. Used by the per-phase notebook tabs
    # in the new UI (commit 4) so the admin only sees findings relevant
    # to the current phase.
    finding_preflight_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=['|', ('proposal_kind', '=', 'stamp_id'),
                     ('state', '=', 'identity_conflict')],
        string='Pre-flight findings')
    finding_link_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('proposal_kind', '=', 'link_only')],
        string='Koppel-findings')
    finding_normalise_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('proposal_kind', 'in', ('rename', 'move', 'membership_add'))],
        string='Normaliseer-findings')
    finding_cleanup_ids = fields.One2many(
        'myschool.ad.takeover.finding', 'session_id',
        domain=[('proposal_kind', '=', 'delete_after')],
        string='Cleanup-findings')

    # Pre-flight report — populated by action_preflight_report. Rendered
    # in the form-view as a HTML field; not stored beyond the latest
    # report (a new run overwrites).
    preflight_report_html = fields.Html(
        readonly=True, sanitize=False,
        string='Pre-flight rapport')
    preflight_report_at = fields.Datetime(readonly=True)

    # Counters for the UI header.
    # Legacy counters (investigate_count etc.) are kept so the current
    # XML view continues to work; they're recomputed from the new state
    # machine in `_compute_counts`. Commit 4 replaces the view fields
    # with the *_count_v2 set.
    finding_count          = fields.Integer(compute='_compute_counts')
    investigate_count      = fields.Integer(compute='_compute_counts')
    delete_after_count     = fields.Integer(compute='_compute_counts')
    takeover_pending_count = fields.Integer(compute='_compute_counts')
    takeover_done_count    = fields.Integer(compute='_compute_counts')
    matched_count          = fields.Integer(compute='_compute_counts')

    # New state-based counters (Fase A).
    discovered_count       = fields.Integer(compute='_compute_counts')
    proposed_count         = fields.Integer(compute='_compute_counts')
    approved_count         = fields.Integer(compute='_compute_counts')
    applied_pilot_count    = fields.Integer(
        compute='_compute_counts',
        help='Voorstellen die piloot-uitgevoerd zijn maar nog niet '
             'geverifieerd. Wachten op admin-actie (verify of rollback).')
    done_count             = fields.Integer(compute='_compute_counts')
    conflict_count         = fields.Integer(compute='_compute_counts')
    stamp_id_pending_count = fields.Integer(
        compute='_compute_counts',
        help='STAMP_ID-voorstellen die nog wachten op approve/apply — '
             'blokkeren de overgang van pre-flight naar de koppel-fase.')

    @api.depends('scope_org_id.ou_fqdn_internal')
    def _compute_base_dn(self):
        for rec in self:
            rec.base_dn = (rec.scope_org_id.ou_fqdn_internal or '').strip()

    @api.depends('scope_org_id', 'google_workspace_config_id')
    def _compute_cloud_ou_path(self):
        for rec in self:
            if not rec.scope_org_id or not rec.google_workspace_config_id:
                rec.cloud_ou_path = False
                continue
            svc = self.env['myschool.google.directory.service']
            rec.cloud_ou_path = svc.org_to_google_path(
                rec.scope_org_id, rec.google_workspace_config_id)

    @api.constrains('ldap_config_id', 'google_workspace_config_id',
                    'environment')
    def _check_environment_consistency(self):
        for s in self:
            if s.ldap_config_id:
                cfg_env = getattr(s.ldap_config_id, 'environment', 'prod')
                if cfg_env != s.environment:
                    raise ValidationError(_(
                        'LDAP-config "%(cfg)s" is gemarkeerd als omgeving '
                        '"%(cfg_env)s"; deze sessie staat op "%(sess_env)s". '
                        'Kies een LDAP-config met dezelfde omgeving, of pas '
                        'de sessie-omgeving aan.'
                    ) % {
                        'cfg': s.ldap_config_id.name,
                        'cfg_env': cfg_env,
                        'sess_env': s.environment,
                    })
            if s.google_workspace_config_id:
                cfg_env = getattr(s.google_workspace_config_id,
                                  'environment', 'prod')
                if cfg_env != s.environment:
                    raise ValidationError(_(
                        'Google-config "%(cfg)s" is gemarkeerd als omgeving '
                        '"%(cfg_env)s"; deze sessie staat op "%(sess_env)s".'
                    ) % {
                        'cfg': s.google_workspace_config_id.name,
                        'cfg_env': cfg_env,
                        'sess_env': s.environment,
                    })

    @api.constrains('ldap_config_id', 'google_workspace_config_id')
    def _check_at_least_one_source(self):
        for s in self:
            if not s.ldap_config_id and not s.google_workspace_config_id:
                raise ValidationError(_(
                    'Kies minstens één bron: een LDAP-server of een '
                    'Google Workspace tenant (of beide). Een sessie '
                    'zonder bron kan niets scannen.'))

    @api.model_create_multi
    def create(self, vals_list):
        # @api.constrains only fires on changed fields; when both
        # source-fields are absent from vals (admin clicked "Create"
        # without picking either), the constraint silently passes.
        # Explicit post-create invocation closes that gap.
        records = super().create(vals_list)
        records._check_at_least_one_source()
        return records

    @api.depends('finding_ids', 'finding_ids.state', 'finding_ids.proposal_kind')
    def _compute_counts(self):
        for rec in self:
            f = rec.finding_ids
            rec.finding_count = len(f)

            # New state-based counters
            rec.discovered_count = len(f.filtered(lambda x: x.state == 'discovered'))
            rec.proposed_count   = len(f.filtered(lambda x: x.state == 'proposed'))
            rec.approved_count   = len(f.filtered(lambda x: x.state == 'approved'))
            rec.applied_pilot_count = len(
                f.filtered(lambda x: x.state == 'applied_pilot'))
            rec.done_count       = len(f.filtered(lambda x: x.state == 'done'))
            rec.conflict_count   = len(f.filtered(
                lambda x: x.state == 'identity_conflict'))
            rec.stamp_id_pending_count = len(f.filtered(
                lambda x: x.proposal_kind == 'stamp_id'
                          and x.state in ('discovered', 'proposed', 'approved')))

            # Legacy aliases mapped from the new state. Preserved so the
            # current XML view keeps rendering header counts during the
            # Fase A transition; commit 4 removes these.
            rec.investigate_count = rec.discovered_count
            rec.takeover_pending_count = rec.proposed_count + rec.approved_count
            rec.takeover_done_count = len(f.filtered(
                lambda x: x.state == 'done' and x.proposal_kind == 'link_only'))
            rec.delete_after_count = len(f.filtered(
                lambda x: x.proposal_kind == 'delete_after'
                          and x.state in ('proposed', 'approved')))
            rec.matched_count = len(f.filtered(
                lambda x: x.state == 'done' and not x.proposal_kind))

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def action_scan(self):
        """Orchestrator that runs every configured source-scanner.

        Configured sources:
          * ldap_config_id            → ``_scan_ad``
          * google_workspace_config_id → ``_scan_cloud``  (Fase B2)
          * (Fase B-future) smartschool_config_id → ``_scan_smartschool``

        Each scanner returns ``(new_findings, summary)``. The
        orchestrator wipes pre-existing ``discovered`` rows (no human
        decision yet), runs every scanner, creates the collected
        findings, and writes the combined summary.
        """
        self.ensure_one()
        if not self.ldap_config_id and not self.google_workspace_config_id:
            raise UserError(_(
                'Geen bron geconfigureerd. Kies minstens een LDAP-server '
                'of een Google Workspace tenant.'))
        if self.ldap_config_id and not self.base_dn:
            raise UserError(_(
                'Scope org "%s" heeft geen ou_fqdn_internal — kan geen '
                'AD base_dn afleiden.') % self.scope_org_id.name)

        index = self._build_db_index()

        # Wipe ``discovered`` rows (no admin decision yet) so a rescan
        # cleanly rebuilds from the source. Everything past discovered
        # represents human-made progress and survives.
        self.finding_ids.filtered(
            lambda r: r.state == 'discovered').unlink()

        existing_by_extid = {
            (f.source, self._norm_dn(f.external_id or f.ad_dn)): f
            for f in self.finding_ids
        }

        all_new = []
        summaries = []

        if self.ldap_config_id:
            new, summary = self._scan_ad(index, existing_by_extid)
            all_new.extend(new)
            summaries.append(summary)
        if self.google_workspace_config_id:
            new, summary = self._scan_cloud(index, existing_by_extid)
            all_new.extend(new)
            summaries.append(summary)

        if all_new:
            self.env['myschool.ad.takeover.finding'].create(all_new)

        # Cross-source linker — only meaningful when >1 source ran.
        cross_summary = ''
        if len(summaries) > 1:
            siblings, drift = self._link_cross_source()
            cross_summary = (
                f'\n\nCross-source linker:\n'
                f'  {siblings} user-finding(s) gekoppeld als siblings\n'
                f'  {drift} cross-source identity-conflict(en) gemarkeerd')

        scan_summary = '\n\n'.join(summaries) + cross_summary
        self.write({
            'state': 'discovered' if self.state == 'draft' else 'in_progress',
            'last_scan_at': fields.Datetime.now(),
            'scan_summary': scan_summary,
        })
        return self._notify(
            _('Scan voltooid'), scan_summary or _('Geen findings.'),
            kind='success')

    # ------------------------------------------------------------------
    # Cross-source linker
    # ------------------------------------------------------------------

    def _link_cross_source(self):
        """Populate sibling_ids on user-findings that share a sap_ref
        across sources (AD + Cloud). Escalate to identity_conflict
        when sibling-findings disagree on which DB-person they match.

        Runs after every scanner has produced findings, so this single
        pass sees the full multi-source state at once.
        """
        self.ensure_one()
        user_findings = self.finding_ids.filtered(
            lambda f: f.kind == 'user' and f.sap_ref)
        by_sap_ref = {}
        for f in user_findings:
            key = (f.sap_ref or '').strip()
            if not key:
                continue
            by_sap_ref.setdefault(key, []).append(f)

        siblings_set = 0
        drift_set = 0
        for sap_ref, fs in by_sap_ref.items():
            if len(fs) < 2:
                # Reset any stale sibling-link from a previous scan when
                # the counterpart has disappeared.
                fs[0].sibling_ids = [(5, 0, 0)]
                continue
            # Connect each finding to all the others
            ids = [f.id for f in fs]
            for f in fs:
                others = [oid for oid in ids if oid != f.id]
                f.sibling_ids = [(6, 0, others)]
            siblings_set += len(fs)

            # Cross-source drift: matched-person disagreement.
            matched_ids = {f.matched_person_id.id
                           for f in fs if f.matched_person_id}
            if len(matched_ids) > 1:
                for f in fs:
                    f.state = 'identity_conflict'
                    f.status = 'investigate'
                    f.risk_level = 'high'
                    existing = (f.conflict_reason or '').strip()
                    cross_note = (
                        f'Cross-source conflict: bronnen koppelen sap_ref='
                        f'{sap_ref} aan verschillende DB-persons '
                        f'(IDs: {sorted(matched_ids)}).')
                    f.conflict_reason = (
                        f'{existing}\n{cross_note}' if existing
                        else cross_note)
                drift_set += len(fs)

        return siblings_set, drift_set

    # ------------------------------------------------------------------
    # AD scanner
    # ------------------------------------------------------------------

    def _scan_ad(self, index, existing_by_extid):
        """Scan LDAP under ``base_dn``. Returns (list_of_finding_vals, summary).

        Identity-linker:
          1. employeeID (sap_ref) match → state=done OR identity_conflict
          2. mail / login fallback → STAMP_ID proposal
          3. orphan → LINK_ONLY proposal
        """
        self.ensure_one()
        ldap_service = self.env['myschool.ldap.service']
        ldap_service._check_ldap3_available()

        ou_rows = []
        group_rows = []
        user_rows = []
        try:
            with ldap_service._get_connection(self.ldap_config_id) as conn:
                conn.search(
                    search_base=self.base_dn,
                    search_filter='(objectClass=organizationalUnit)',
                    search_scope='SUBTREE',
                    attributes=['distinguishedName', 'ou', 'description'])
                ou_rows = list(conn.entries)
                conn.search(
                    search_base=self.base_dn,
                    search_filter='(objectClass=group)',
                    search_scope='SUBTREE',
                    attributes=['distinguishedName', 'cn', 'sAMAccountName',
                                'mail', 'description'])
                group_rows = list(conn.entries)
                # Users — exclude computer objects (share the user class).
                # employeeID is the cross-source identity key; userAccountControl
                # surfaces disabled accounts so the linker can flag drift.
                conn.search(
                    search_base=self.base_dn,
                    search_filter='(&(objectClass=user)(!(objectClass=computer)))',
                    search_scope='SUBTREE',
                    attributes=['distinguishedName', 'cn', 'sAMAccountName',
                                'mail', 'givenName', 'sn',
                                'employeeID', 'userAccountControl'])
                user_rows = list(conn.entries)
        except Exception as e:
            _logger.exception('[AD-TAKEOVER] LDAP scan failed')
            raise UserError(_('LDAP-scan mislukt: %s') % e)

        # Wipe + existing_by_extid construction now happen in the
        # orchestrator (action_scan), shared across all source-scanners.
        ou_total = ou_match = 0
        gr_total = gr_match = 0
        us_total = us_match = us_conflict = us_stamp = us_orphan = 0
        new_findings = []

        # ---------- OUs ----------
        for entry in ou_rows:
            ou_total += 1
            dn = self._entry_str(entry, 'distinguishedName')
            if not dn:
                continue
            dn_norm = self._norm_dn(dn)
            if ('ad', dn_norm) in existing_by_extid:
                continue
            matched_org_id = index['ou_dn_to_org'].get(dn_norm)
            if matched_org_id:
                ou_match += 1
                continue
            proposed = self._guess_ou_takeover(dn)
            new_findings.append({
                'session_id': self.id,
                'source': 'ad',
                'external_id': dn,
                'kind': 'ou',
                'ad_dn': dn,
                'ad_cn': self._entry_str(entry, 'ou'),
                'ad_attributes_json': self._entry_to_json(entry),
                'match_kind': 'unmatched',
                'status': 'investigate',           # legacy mirror
                'state': 'proposed',
                'proposal_kind': 'link_only',
                'risk_level': 'low',
                'proposed_parent_org_id': proposed.get('parent_id'),
                'proposed_org_type_id': proposed.get('type_id'),
            })

        # ---------- Groups ----------
        for entry in group_rows:
            gr_total += 1
            dn = self._entry_str(entry, 'distinguishedName')
            if not dn:
                continue
            dn_norm = self._norm_dn(dn)
            if ('ad', dn_norm) in existing_by_extid:
                continue
            matched_org_id = index['group_dn_to_org'].get(dn_norm)
            if matched_org_id:
                gr_match += 1
                continue
            cn   = self._entry_str(entry, 'cn')
            sam  = self._entry_str(entry, 'sAMAccountName')
            mail = self._entry_str(entry, 'mail')
            parent = self._guess_group_parent(dn)
            new_findings.append({
                'session_id': self.id,
                'source': 'ad',
                'external_id': dn,
                'kind': 'group',
                'ad_dn': dn,
                'ad_cn': cn,
                'ad_sam': sam,
                'ad_mail': mail,
                'ad_attributes_json': self._entry_to_json(entry),
                'match_kind': 'unmatched',
                'status': 'investigate',
                'state': 'proposed',
                'proposal_kind': 'link_only',
                'risk_level': 'low',
                'proposed_parent_org_id': parent.id if parent else False,
            })

        # ---------- Users — deterministic linker ----------
        Person = self.env['myschool.person']
        for entry in user_rows:
            us_total += 1
            dn = self._entry_str(entry, 'distinguishedName')
            if not dn:
                continue
            dn_norm = self._norm_dn(dn)
            if ('ad', dn_norm) in existing_by_extid:
                continue

            cn   = self._entry_str(entry, 'cn')
            sam  = self._entry_str(entry, 'sAMAccountName')
            mail = self._entry_str(entry, 'mail')
            given = self._entry_str(entry, 'givenName')
            sn    = self._entry_str(entry, 'sn')
            emp   = self._entry_str(entry, 'employeeID')
            parent_org = self._guess_user_parent(dn)

            vals = {
                'session_id': self.id,
                'source': 'ad',
                'external_id': dn,
                'kind': 'user',
                'ad_dn': dn,
                'ad_cn': cn,
                'ad_sam': sam,
                'ad_mail': mail,
                'ad_givenname': given,
                'ad_sn': sn,
                'ad_attributes_json': self._entry_to_json(entry),
                'match_kind': 'unmatched',
                'sap_ref': emp or False,
                'proposed_parent_org_id': parent_org.id if parent_org else False,
                'proposed_person_role_id': (
                    self._guess_role(parent_org).id
                    if parent_org and self._guess_role(parent_org)
                    else False),
            }

            # 1) Strongest signal: employeeID == person.sap_ref
            person_id = index['sap_ref_to_person'].get(emp.strip()) if emp else None
            if person_id:
                person = Person.browse(person_id)
                existing_dn = (person.person_fqdn_internal or '').strip()
                if existing_dn and self._norm_dn(existing_dn) != dn_norm:
                    # Same sap_ref claimed at two different DNs → conflict.
                    vals.update({
                        'state': 'identity_conflict',
                        'status': 'investigate',           # legacy mirror
                        'matched_person_id': person.id,
                        'risk_level': 'high',
                        'conflict_reason': (
                            f'AD-user met employeeID={emp} hangt op DN '
                            f'{dn}, maar DB.person.person_fqdn_internal '
                            f'wijst naar {existing_dn}.'),
                    })
                    us_conflict += 1
                else:
                    # Match + consistent → already linked.
                    vals.update({
                        'state': 'done',
                        'status': 'matched',
                        'matched_person_id': person.id,
                        'match_kind': 'matched_in_db',
                        'risk_level': 'low',
                    })
                    us_match += 1
                new_findings.append(vals)
                continue

            # 2) No employeeID → look for a candidate via mail / login.
            person_id = None
            via = None
            if mail and mail.lower() in index['user_mail_to_person']:
                person_id = index['user_mail_to_person'][mail.lower()]
                via = 'email_cloud'
            elif sam and sam.lower() in index['login_to_person']:
                person_id = index['login_to_person'][sam.lower()]
                via = 'odoo_user.login'

            if person_id:
                person = Person.browse(person_id)
                vals.update({
                    'state': 'proposed',
                    'status': 'investigate',
                    'matched_person_id': person.id,
                    'proposal_kind': 'stamp_id',
                    'proposal_payload_json': json.dumps({
                        'target_attribute': 'employeeID',
                        'value': str(person.sap_ref or ''),
                        'matched_via': via,
                    }),
                    'risk_level': 'low',
                    'notes': (
                        f'AD-user mist employeeID; gematcht via {via}. '
                        f'Voorstel schrijft sap_ref={person.sap_ref} '
                        f'naar AD employeeID. Geen wijziging in DN, '
                        f'sAMAccountName of wachtwoord.'),
                })
                us_stamp += 1
                new_findings.append(vals)
                continue

            # 3) Genuine orphan — admin decides.
            vals.update({
                'state': 'proposed',
                'status': 'investigate',
                'proposal_kind': 'link_only',
                'risk_level': 'medium',
                'notes': (
                    'Geen DB-match op employeeID, mail of login. '
                    'Mogelijk een extern account of een persoon die '
                    'nog niet in Informat zit. Beslis: importeren of '
                    'negeren.'),
            })
            us_orphan += 1
            new_findings.append(vals)

        summary = (
            f'AD-scan:\n'
            f'  OUs: {ou_total} gevonden — {ou_match} al gelinkt, '
            f'{ou_total - ou_match} nieuw.\n'
            f'  Groups: {gr_total} gevonden — {gr_match} al gelinkt, '
            f'{gr_total - gr_match} nieuw.\n'
            f'  Users: {us_total} gevonden — {us_match} al gelinkt, '
            f'{us_stamp} STAMP_ID, {us_orphan} orphan, '
            f'{us_conflict} identity-conflict.'
        )
        return new_findings, summary

    # ------------------------------------------------------------------
    # Cloud scanner
    # ------------------------------------------------------------------

    def _scan_cloud(self, index, existing_by_extid):
        """Scan Google Workspace OUs / groups / users under
        ``cloud_ou_path``. Returns (new_findings, summary).

        Identity-linker per kind:
          * OU    → match via cloud_path_to_org
          * Group → match via cloud_group_email_to_org (com_group_email)
          * User  → externalIds (sap_ref) primary, primaryEmail
                    fallback; otherwise orphan
        """
        self.ensure_one()
        if not self.cloud_ou_path:
            return [], _(
                'Cloud-scan: scope-org "%s" levert geen Google-pad op '
                '(geen ou_fqdn_internal of name_tree).'
            ) % self.scope_org_id.name

        gsvc = self.env['myschool.google.directory.service']
        gsvc._check_google_available()
        config = self.google_workspace_config_id
        customer_id = config.customer_id or 'my_customer'
        api = gsvc._get_directory_service(config)

        ou_rows = self._cloud_fetch_ous(api, customer_id, self.cloud_ou_path)
        user_rows = self._cloud_fetch_users(api, customer_id, self.cloud_ou_path)
        group_rows = self._cloud_fetch_groups(api, customer_id, config.domain)

        Person = self.env['myschool.person']
        new_findings = []
        ou_total = ou_match = 0
        gr_total = gr_match = 0
        us_total = us_match = us_conflict = us_stamp = us_orphan = 0

        # ---------- OUs ----------
        for entry in ou_rows:
            ou_total += 1
            path = (entry.get('orgUnitPath') or '').strip()
            ou_id = entry.get('orgUnitId') or path
            if not path:
                continue
            key = ('cloud', path.lower())
            if key in existing_by_extid:
                continue
            if index['cloud_path_to_org'].get(path.lower()):
                ou_match += 1
                continue
            new_findings.append({
                'session_id': self.id,
                'source': 'cloud',
                'external_id': ou_id,
                'kind': 'ou',
                'ad_dn': path,        # use ad_dn column to hold the path
                'ad_cn': entry.get('name') or path.rsplit('/', 1)[-1],
                'ad_attributes_json': json.dumps(entry, default=str)[:8000],
                'match_kind': 'unmatched',
                'status': 'investigate',
                'state': 'proposed',
                'proposal_kind': 'link_only',
                'risk_level': 'low',
            })

        # ---------- Groups ----------
        for entry in group_rows:
            gr_total += 1
            email = (entry.get('email') or '').strip().lower()
            gid = entry.get('id') or email
            if not email:
                continue
            key = ('cloud', gid.lower())
            if key in existing_by_extid:
                continue
            if index['cloud_group_email_to_org'].get(email):
                gr_match += 1
                continue
            new_findings.append({
                'session_id': self.id,
                'source': 'cloud',
                'external_id': gid,
                'kind': 'group',
                'ad_dn': email,
                'ad_cn': entry.get('name') or email,
                'ad_mail': entry.get('email') or False,
                'ad_attributes_json': json.dumps(entry, default=str)[:8000],
                'match_kind': 'unmatched',
                'status': 'investigate',
                'state': 'proposed',
                'proposal_kind': 'link_only',
                'risk_level': 'low',
            })

        # ---------- Users — deterministic linker ----------
        for entry in user_rows:
            us_total += 1
            uid = entry.get('id') or ''
            email = (entry.get('primaryEmail') or '').strip().lower()
            if not uid:
                continue
            key = ('cloud', uid.lower())
            if key in existing_by_extid:
                continue

            # externalIds is a list of {'type': '...', 'value': '...'}.
            # google_directory_service.create_user writes sap_ref with
            # type='organization', so match that first; fall back to
            # any externalId whose value parses as a sap_ref.
            sap_ref = ''
            for eid in entry.get('externalIds') or []:
                if eid.get('type') == 'organization' and eid.get('value'):
                    sap_ref = str(eid['value']).strip()
                    break
            if not sap_ref:
                for eid in entry.get('externalIds') or []:
                    val = (eid.get('value') or '').strip()
                    if val and val.isdigit():
                        sap_ref = val
                        break

            name_obj = entry.get('name') or {}
            given = name_obj.get('givenName', '') if isinstance(name_obj, dict) else ''
            family = name_obj.get('familyName', '') if isinstance(name_obj, dict) else ''
            full = name_obj.get('fullName', '') if isinstance(name_obj, dict) else ''

            vals = {
                'session_id': self.id,
                'source': 'cloud',
                'external_id': uid,
                'kind': 'user',
                'ad_dn': email,           # store primary email in ad_dn column
                'ad_cn': full or f'{given} {family}'.strip() or email,
                'ad_mail': email or False,
                'ad_givenname': given or False,
                'ad_sn': family or False,
                'sap_ref': sap_ref or False,
                'ad_attributes_json': json.dumps(entry, default=str)[:8000],
                'match_kind': 'unmatched',
            }

            # 1) externalIds → sap_ref match
            person_id = (index['sap_ref_to_person'].get(sap_ref)
                         if sap_ref else None)
            if person_id:
                person = Person.browse(person_id)
                db_email = (person.email_cloud or '').strip().lower()
                if db_email and email and db_email != email:
                    vals.update({
                        'state': 'identity_conflict',
                        'status': 'investigate',
                        'matched_person_id': person.id,
                        'risk_level': 'high',
                        'conflict_reason': (
                            f'Cloud-user met externalIds={sap_ref} heeft '
                            f'primaryEmail={email}, maar DB.person.'
                            f'email_cloud={person.email_cloud}.'),
                    })
                    us_conflict += 1
                else:
                    vals.update({
                        'state': 'done',
                        'status': 'matched',
                        'matched_person_id': person.id,
                        'match_kind': 'matched_in_db',
                        'risk_level': 'low',
                    })
                    us_match += 1
                new_findings.append(vals)
                continue

            # 2) primaryEmail fallback → STAMP_ID voorstel
            if email and email in index['user_mail_to_person']:
                person = Person.browse(index['user_mail_to_person'][email])
                vals.update({
                    'state': 'proposed',
                    'status': 'investigate',
                    'matched_person_id': person.id,
                    'proposal_kind': 'stamp_id',
                    'proposal_payload_json': json.dumps({
                        'target_attribute': 'externalIds',
                        'value': str(person.sap_ref or ''),
                        'matched_via': 'email_cloud',
                    }),
                    'risk_level': 'low',
                    'notes': (
                        f'Cloud-user mist externalIds; gematcht via '
                        f'primaryEmail. Voorstel schrijft sap_ref='
                        f'{person.sap_ref} naar Cloud externalIds. '
                        f'Geen wijziging in primaryEmail, naam of OU.'),
                })
                us_stamp += 1
                new_findings.append(vals)
                continue

            # 3) Orphan
            vals.update({
                'state': 'proposed',
                'status': 'investigate',
                'proposal_kind': 'link_only',
                'risk_level': 'medium',
                'notes': (
                    'Geen DB-match op externalIds of email_cloud. '
                    'Mogelijk een extern account of een persoon die '
                    'nog niet in Informat zit.'),
            })
            us_orphan += 1
            new_findings.append(vals)

        summary = (
            f'Cloud-scan:\n'
            f'  OUs: {ou_total} gevonden — {ou_match} al gelinkt, '
            f'{ou_total - ou_match} nieuw.\n'
            f'  Groups: {gr_total} gevonden — {gr_match} al gelinkt, '
            f'{gr_total - gr_match} nieuw.\n'
            f'  Users: {us_total} gevonden — {us_match} al gelinkt, '
            f'{us_stamp} STAMP_ID, {us_orphan} orphan, '
            f'{us_conflict} identity-conflict.'
        )
        return new_findings, summary

    # ---------- Cloud paginated fetch helpers ----------

    def _cloud_fetch_ous(self, api, customer_id, root_path):
        """List OUs under root_path. type='all' returns the whole subtree
        including descendants, root excluded."""
        try:
            resp = api.orgunits().list(
                customerId=customer_id,
                orgUnitPath=root_path,
                type='all',
            ).execute()
            return resp.get('organizationUnits', []) or []
        except Exception as e:
            _logger.exception('[AD-TAKEOVER] Cloud orgunits.list failed')
            raise UserError(_('Cloud OUs ophalen mislukt: %s') % e)

    def _cloud_fetch_users(self, api, customer_id, ou_path):
        """List users under ou_path. Wildcard query catches descendants;
        admin reviews unexpected matches."""
        users = []
        page_token = None
        # The colon-form supports wildcard prefix matching.
        query = f"orgUnitPath:'{ou_path}*'"
        try:
            while True:
                resp = api.users().list(
                    customer=customer_id,
                    query=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute()
                users.extend(resp.get('users', []) or [])
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except Exception as e:
            _logger.exception('[AD-TAKEOVER] Cloud users.list failed')
            raise UserError(_('Cloud users ophalen mislukt: %s') % e)
        return users

    def _cloud_fetch_groups(self, api, customer_id, domain_filter=None):
        """List all groups in the tenant, optionally filtered by
        primaryEmail domain. Google Workspace groups are tenant-flat
        (no OU concept), so the domain filter is the only way to
        narrow before download.
        """
        groups = []
        page_token = None
        suffix = f'@{domain_filter}' if domain_filter else None
        try:
            while True:
                resp = api.groups().list(
                    customer=customer_id,
                    maxResults=200,
                    pageToken=page_token,
                ).execute()
                for g in resp.get('groups', []) or []:
                    email = (g.get('email') or '').lower()
                    if suffix is None or email.endswith(suffix):
                        groups.append(g)
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except Exception as e:
            _logger.exception('[AD-TAKEOVER] Cloud groups.list failed')
            raise UserError(_('Cloud groups ophalen mislukt: %s') % e)
        return groups

    # ------------------------------------------------------------------
    # Bulk apply
    # ------------------------------------------------------------------

    def action_apply_approved(self):
        """Apply every finding in state=approved, routing by proposal_kind.

        Fase A actively executes:
          * link_only    — existing DB-create flow (unchanged behaviour)
          * stamp_id     — write sap_ref into AD.employeeID
          * delete_after — LDAP delete (user/group only)

        rename / move / membership_add are accepted in the state-machine
        but raise NotImplementedError when executed — Fase C lands them.
        """
        self.ensure_one()
        approved = self.finding_ids.filtered(lambda r: r.state == 'approved')
        if not approved:
            raise UserError(_('Geen goedgekeurde voorstellen in deze sessie.'))
        # Order matters on a blanco DB: OUs must exist before groups/users
        # claim them as proposed_parent_org_id. Sort by kind so OUs run
        # first, then groups, then users — and stable-by-DN within each
        # kind so parent-OUs land before their children.
        kind_order = {'ou': 0, 'group': 1, 'user': 2}
        approved = approved.sorted(
            key=lambda r: (kind_order.get(r.kind, 99), r.ad_dn or ''))
        ok = err = 0
        for f in approved:
            try:
                f.action_takeover()
                ok += 1
            except Exception as e:
                _logger.exception('[AD-TAKEOVER] apply failed for %s', f.ad_dn)
                f.write({'action_message': str(e)})
                err += 1
        return self._notify(_('Goedgekeurde voorstellen toegepast'),
                            f'OK: {ok}, Fouten: {err}',
                            kind='success' if err == 0 else 'warning')

    # Backwards-compat alias — the existing XML view still binds the
    # button to this name. Re-targets the same state set internally
    # ('proposed' status='takeover_pending' was approve+apply combined).
    def action_apply_pending_takeovers(self):
        self.ensure_one()
        legacy_pending = self.finding_ids.filtered(
            lambda r: r.state in ('proposed', 'approved')
                      and r.proposal_kind in ('link_only', 'stamp_id'))
        if not legacy_pending:
            raise UserError(_(
                'Geen openstaande voorstellen. Markeer eerst items als '
                '"goedgekeurd" of gebruik de directe takeover-knop per rij.'))
        # Same dependency-order as action_apply_approved.
        kind_order = {'ou': 0, 'group': 1, 'user': 2}
        legacy_pending = legacy_pending.sorted(
            key=lambda r: (kind_order.get(r.kind, 99), r.ad_dn or ''))
        ok = err = 0
        for f in legacy_pending:
            try:
                f.action_takeover()
                ok += 1
            except Exception as e:
                _logger.exception('[AD-TAKEOVER] apply failed for %s', f.ad_dn)
                f.write({'action_message': str(e)})
                err += 1
        return self._notify(_('Voorstellen toegepast'),
                            f'OK: {ok}, Fouten: {err}',
                            kind='success' if err == 0 else 'warning')

    def action_apply_pending_deletes(self):
        """Cleanup-phase: actually delete in AD what was flagged
        ``proposal_kind=delete_after`` and approved by the admin.

        Triggered only after the admin has worked through pre-flight,
        link, and normalise — typically from the "Cleanup" tab.
        """
        self.ensure_one()
        flagged = self.finding_ids.filtered(
            lambda r: r.proposal_kind == 'delete_after'
                      and r.state in ('approved', 'proposed'))
        if not flagged:
            raise UserError(_(
                'Geen items met voorstel "Verwijder na migratie". '
                'Markeer eerst rijen via "Verwijder na migratie" + '
                '"Goedkeuren" voordat je deze knop gebruikt.'))

        ldap_service = self.env['myschool.ldap.service']
        ok = err = skip = 0
        for f in flagged:
            try:
                if f.kind == 'user':
                    res = ldap_service.delete_user_by_dn(
                        self.ldap_config_id, f.ad_dn) \
                        if hasattr(ldap_service, 'delete_user_by_dn') \
                        else self._delete_dn(f.ad_dn)
                elif f.kind == 'group':
                    res = ldap_service.delete_group(
                        self.ldap_config_id, f.ad_dn)
                else:
                    skip += 1
                    f.write({
                        'action_message': 'OUs worden niet verwijderd via deze flow.',
                    })
                    continue
                if res.get('success'):
                    f.write({
                        'state': 'done',
                        'status': 'delete_done',        # legacy mirror
                        'action_message': res.get('message', ''),
                        'last_action_at': fields.Datetime.now(),
                    })
                    ok += 1
                else:
                    f.write({'action_message': res.get('message', 'Unknown error')})
                    err += 1
            except Exception as e:
                _logger.exception(
                    '[AD-TAKEOVER] delete failed for %s', f.ad_dn)
                f.write({'action_message': str(e)})
                err += 1
        return self._notify(_('Cleanup uitgevoerd'),
                            f'OK: {ok}, Fouten: {err}, overgeslagen: {skip}',
                            kind='success' if err == 0 else 'warning')

    def _delete_dn(self, dn):
        """Generic LDAP delete fallback for a DN. Used for users since the
        existing ldap_service.delete_user requires a person record."""
        ldap_service = self.env['myschool.ldap.service']
        try:
            with ldap_service._get_connection(self.ldap_config_id) as conn:
                ok = conn.delete(dn)
                if ok:
                    return {'success': True, 'message': f'Deleted {dn}'}
                return {'success': False,
                        'message': f'Delete failed: {conn.result}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    # ------------------------------------------------------------------
    # Promote test → prod
    # ------------------------------------------------------------------

    def action_promote_to_prod(self):
        """Clone this verified test-session into a fresh prod-session
        with all proposals copied over.

        Strategy (chosen for reproducibility, see design doc):
          1. Find the active prod LDAP-config.
          2. Create a new session pointing at it, run a fresh scan.
          3. For each test-finding with a proposal, rewrite its DN
             from the test base_dn to the prod base_dn and match to
             a prod-finding. Copy proposal_kind + payload + risk.
          4. Prod-findings without a test-counterpart stay on
             ``state=discovered`` with a "drift" note — admin can
             still act on them, but they didn't go through test.
          5. The new session ALWAYS lands on ``proposed`` per row, not
             ``approved`` — admin re-confirms in prod even when test
             was unambiguous.
        """
        self.ensure_one()
        if self.environment != 'test':
            raise UserError(_(
                'Alleen test-sessies kunnen worden gepromoot. Deze '
                'sessie staat al op "%s".') % self.environment)
        if self.current_phase != 'done':
            raise UserError(_(
                'Promote vereist dat de test-sessie op fase '
                '"voltooid" staat. Huidige fase: %s.') % self.current_phase)

        LdapCfg = self.env['myschool.ldap.server.config']
        prod_cfg = LdapCfg.search([
            ('environment', '=', 'prod'),
            ('active', '=', True),
        ], limit=1)
        if not prod_cfg:
            raise UserError(_(
                'Geen actieve LDAP-config met environment=prod gevonden. '
                'Markeer eerst een prod-config als actief.'))

        prod_session = self.copy({
            'name': f'{self.name} — prod-promote '
                    f'({fields.Date.today().isoformat()})',
            'environment': 'prod',
            'ldap_config_id': prod_cfg.id,
            'current_phase': 'preflight',
            'state': 'draft',
            'last_scan_at': False,
            'scan_summary': False,
            'preflight_report_html': False,
            'preflight_report_at': False,
        })
        # ``copy`` triggered by Odoo also copies finding_ids by default
        # because of the One2many; wipe them so the prod-scan creates
        # them fresh against the prod LDAP.
        prod_session.finding_ids.unlink()

        prod_session.action_scan()

        # Copy proposals from test → prod with DN rewriting.
        test_base = (self.base_dn or '').strip()
        prod_base = (prod_session.base_dn or '').strip()
        if not test_base or not prod_base:
            return self._open_session(prod_session)

        matched = drift_test = 0
        prod_by_dn = {
            self._norm_dn(f.ad_dn): f for f in prod_session.finding_ids
        }
        for tf in self.finding_ids:
            if tf.source != 'ad' or not tf.proposal_kind:
                continue
            test_dn = tf.ad_dn or ''
            if not test_dn.lower().endswith(test_base.lower()):
                continue
            # rewrite suffix: cut off test_base, append prod_base
            prod_dn = test_dn[: -len(test_base)] + prod_base
            pf = prod_by_dn.get(self._norm_dn(prod_dn))
            if not pf:
                drift_test += 1
                continue
            pf.write({
                'proposal_kind': tf.proposal_kind,
                'proposal_payload_json': tf.proposal_payload_json,
                'risk_level': tf.risk_level,
                # State always proposed — admin re-approves in prod.
                'state': 'proposed',
                'status': 'investigate',         # legacy mirror
                'notes': (
                    f'Voorstel gekopieerd uit test-sessie "{self.name}". '
                    f'Origineel DN: {test_dn}.'),
            })
            matched += 1

        # Findings on prod that have NO test counterpart: drift.
        drift_prod = len(prod_session.finding_ids) - matched
        prod_session.scan_summary = (
            (prod_session.scan_summary or '')
            + f'\n\nPromote-overzicht:\n'
              f'  • {matched} voorstel(len) gekopieerd uit test\n'
              f'  • {drift_test} test-voorstel(len) zonder prod-match '
              f'(prod-data is gewijzigd?)\n'
              f'  • {drift_prod} prod-rij(en) zonder test-tegenhanger '
              f'(nieuw of niet getest)\n'
        )
        return self._open_session(prod_session)

    def _open_session(self, session):
        return {
            'type': 'ir.actions.act_window',
            'name': _('AD-takeover sessie'),
            'res_model': 'myschool.ad.takeover.session',
            'res_id': session.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Pre-flight rapport
    # ------------------------------------------------------------------

    def action_preflight_report(self):
        """Build a read-only pre-flight report for the current scope.

        Does NOT mutate findings. Pure analysis — surfaces classes of
        identity-drift that an admin should fix before running the
        actual takeover. Output lands in ``preflight_report_html`` for
        the form view to render.
        """
        self.ensure_one()
        if not self.scope_org_id:
            raise UserError(_('Scope-org ontbreekt — kan geen rapport opbouwen.'))

        data = self._build_preflight_data()
        html = self._render_preflight_html(data)
        self.write({
            'preflight_report_html': html,
            'preflight_report_at': fields.Datetime.now(),
        })
        total_blockers = sum(len(rows) for rows in data['critical'].values())
        return self._notify(
            _('Pre-flight rapport klaar'),
            (f'{total_blockers} kritieke item(s) gevonden — '
             f'zie het rapport in de vorm.'),
            kind='warning' if total_blockers else 'success')

    def _build_preflight_data(self):
        """Verzamel de zeven analyse-categorieën zonder schrijfacties.

        Categorieën zijn opgesplitst in 'critical' (blokkeren echt) en
        'warning' (mag, maar duidt op drift). Resultaten zijn lijsten
        van dicts klaar voor templating.
        """
        self.ensure_one()
        scope = self.scope_org_id
        Person = self.env['myschool.person'].with_context(active_test=False)

        only_employees = self.role_filter_preflight == 'employees_only'

        # All persons whose primary school is (or sits under) this
        # session's scope-org. current_school_id is computed-not-stored
        # so we can't search on it; resolve via the underlying
        # PERSON-TREE proprelation instead, scoped by the org's
        # name_tree prefix.
        Org = self.env['myschool.org'].with_context(active_test=False)
        scope_prefix = (scope.name_tree or '').strip()
        if scope_prefix:
            in_scope_orgs = Org.search([
                '|', ('name_tree', '=', scope_prefix),
                     ('name_tree', '=ilike', f'{scope_prefix}.%'),
            ])
        else:
            in_scope_orgs = scope
        ProprelationType = self.env['myschool.proprelation.type']
        pt_type = ProprelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        if pt_type and in_scope_orgs:
            person_tree_rels = self.env['myschool.proprelation'].search([
                ('proprelation_type_id', '=', pt_type.id),
                ('id_org', 'in', in_scope_orgs.ids),
                ('is_active', '=', True),
            ])
            persons_in_scope = person_tree_rels.mapped('id_person')
        else:
            persons_in_scope = Person.browse()
        if only_employees and persons_in_scope:
            EMPLOYEE = self.env['myschool.person.type'].search(
                [('name', '=', 'EMPLOYEE')], limit=1)
            if EMPLOYEE:
                persons_in_scope = persons_in_scope.filtered(
                    lambda p: p.person_type_id.id == EMPLOYEE.id)

        # Cat 1 — persons missing sap_ref entirely (cannot STAMP_ID).
        cat_missing_sap = persons_in_scope.filtered(lambda p: not p.sap_ref)

        # Cat 2 — persons with sap_ref but no person_fqdn_internal in scope
        # (DB thinks they have no AD presence — rescan can reveal one).
        cat_no_fqdn = persons_in_scope.filtered(
            lambda p: p.sap_ref and not p.person_fqdn_internal)

        # Cat 3 — duplicate sap_ref across persons (data corruption).
        # The unique constraint on sap_ref normally blocks this, but
        # legacy imports may have NULL-bypassed it. Defensive check.
        seen_sap = {}
        cat_dup_sap = []
        for p in persons_in_scope:
            if not p.sap_ref:
                continue
            other = seen_sap.get(p.sap_ref)
            if other:
                cat_dup_sap.append({'a': other, 'b': p, 'sap_ref': p.sap_ref})
            else:
                seen_sap[p.sap_ref] = p

        # Cat 4 — findings already classified by the linker as
        # identity_conflict. These MUST be resolved before bulk apply.
        cat_conflicts = self.finding_ids.filtered(
            lambda f: f.state == 'identity_conflict')

        # Cat 5 — pending STAMP_ID voorstellen. Blokkeren pre-flight.
        cat_stamp_pending = self.finding_ids.filtered(
            lambda f: f.proposal_kind == 'stamp_id'
                      and f.state in ('discovered', 'proposed', 'approved'))

        # Cat 6 — orphan AD-users (linker found no match) — informational.
        cat_orphans = self.finding_ids.filtered(
            lambda f: f.kind == 'user' and f.proposal_kind == 'link_only'
                      and f.state in ('proposed', 'discovered'))

        # Cat 7 — sAMAccountName ≠ res.users.login while sap_ref matches.
        # Surfaces via the existing linker notes — counted separately.
        cat_sam_mismatch = self.finding_ids.filtered(
            lambda f: f.kind == 'user' and f.matched_person_id
                      and f.matched_person_id.odoo_user_id
                      and f.ad_sam
                      and f.matched_person_id.odoo_user_id.login
                      and (f.ad_sam or '').lower() !=
                           (f.matched_person_id.odoo_user_id.login or '').lower())

        # Orphan AD-users that carry an employeeID can in principle be
        # auto-imported as a fresh DB-person with sap_ref=employeeID.
        # Surfacing this count separately makes the blanco-DB takeover
        # path explicit: it tells the admin "you'll get N new persons".
        cat_orphans_with_emp = cat_orphans.filtered(lambda f: f.sap_ref)

        return {
            'scope_name': scope.name_tree or scope.name,
            'only_employees': only_employees,
            'persons_in_scope_count': len(persons_in_scope),
            'orphans_with_employee_id': cat_orphans_with_emp,
            'critical': {
                'identity_conflicts': cat_conflicts,
                'stamp_id_pending':   cat_stamp_pending,
                'duplicate_sap_ref':  cat_dup_sap,
            },
            'warning': {
                'persons_missing_sap_ref':     cat_missing_sap,
                'persons_with_sap_no_fqdn':    cat_no_fqdn,
                'orphan_ad_users':             cat_orphans,
                'sam_login_mismatch':          cat_sam_mismatch,
            },
        }

    def _render_preflight_html(self, data):
        """Minimal, deterministic HTML — no template-file dependency.

        The form-view embeds this as a sanitized HTML field; commit 4
        replaces this with a proper QWeb template + per-row drill-down.
        """
        def _section(title, rows, kind, render_row):
            badge = 'bg-danger' if kind == 'critical' else 'bg-warning'
            count = len(rows)
            chips = (f'<span class="badge {badge}">{count}</span>'
                     if count else
                     '<span class="badge bg-success">0</span>')
            body = ''
            if count:
                body = '<ul>' + ''.join(render_row(r) for r in rows) + '</ul>'
            return (f'<h4 class="mt-3">{title} {chips}</h4>{body}')

        def _p_link(p):
            return (f'<a href="#" data-oe-model="myschool.person" '
                    f'data-oe-id="{p.id}">{p.display_name}</a> '
                    f'(sap_ref={p.sap_ref or "—"})')

        def _f_link(f):
            return (f'<code>{f.ad_dn or ""}</code> — {f.ad_cn or ""}')

        rows = []
        rows.append(
            f'<p class="text-muted">Scope: <strong>{data["scope_name"]}</strong>'
            f' · filter: <strong>{"alleen werknemers" if data["only_employees"] else "iedereen"}</strong>'
            f' · DB-personen in scope: <strong>{data["persons_in_scope_count"]}</strong>'
            f'</p>')

        # Blanco-DB advisory: 0 personen in scope én één of meer AD-users
        # met employeeID gevonden → de admin staat voor een eerste
        # import. STAMP_ID kan dan niet werken (geen DB-target), maar
        # LINK_ONLY-takeover creëert nieuwe persons met sap_ref
        # rechtstreeks uit het AD employeeID.
        if data['persons_in_scope_count'] == 0 and data['orphans_with_employee_id']:
            n = len(data['orphans_with_employee_id'])
            rows.append(
                f'<div class="alert alert-info" role="alert">'
                f'<strong>Blanco-DB takeover</strong> — geen personen in scope, '
                f'{n} AD-user(s) met employeeID gevonden. De takeover maakt '
                f'voor elk een nieuwe DB-persoon aan met '
                f'<code>sap_ref=employeeID</code>; Informat-sync kan ze '
                f'daarna verder verrijken (naam, geboortedatum, klas). '
                f'Volgorde tijdens "Pas voorstellen toe": OUs → groups → '
                f'users (automatisch).'
                f'</div>')
        elif data['persons_in_scope_count'] == 0:
            rows.append(
                f'<div class="alert alert-warning" role="alert">'
                f'<strong>Geen personen in scope</strong> — controleer of '
                f'PERSON-TREE proprelations correct gezet zijn, of dat de '
                f'scope-org juist gekozen is. Een echte blanco-DB heeft '
                f'normaal AD-users met employeeID; als die hier ook 0 zijn '
                f'is je AD waarschijnlijk pre-Informat (oude accounts).'
                f'</div>')

        # Critical first
        c = data['critical']
        rows.append(_section(
            'Identity-conflicts — moet handmatig opgelost',
            c['identity_conflicts'], 'critical',
            lambda f: f'<li>{_f_link(f)} · <em>{f.conflict_reason or ""}</em></li>'))
        rows.append(_section(
            'STAMP_ID openstaand — eerst goedkeuren en uitvoeren',
            c['stamp_id_pending'], 'critical',
            lambda f: f'<li>{_f_link(f)}'
                      f' → schrijft <code>employeeID={getattr(f.matched_person_id, "sap_ref", "?")}</code></li>'))
        rows.append(_section(
            'Duplicate sap_ref in DB — datacorruptie',
            c['duplicate_sap_ref'], 'critical',
            lambda r: f'<li>sap_ref <code>{r["sap_ref"]}</code> op '
                      f'<strong>{r["a"].display_name}</strong> én '
                      f'<strong>{r["b"].display_name}</strong></li>'))

        # Warnings
        w = data['warning']
        rows.append(_section(
            'Personen zonder sap_ref — kunnen niet via STAMP_ID worden gefixt',
            w['persons_missing_sap_ref'], 'warning',
            lambda p: f'<li>{_p_link(p)}</li>'))
        rows.append(_section(
            'Personen met sap_ref maar geen person_fqdn_internal',
            w['persons_with_sap_no_fqdn'], 'warning',
            lambda p: f'<li>{_p_link(p)}</li>'))
        rows.append(_section(
            'Orphan AD-users — geen DB-match, admin beslist',
            w['orphan_ad_users'], 'warning',
            lambda f: f'<li>{_f_link(f)}</li>'))
        rows.append(_section(
            'sAMAccountName ≠ res.users.login — login-drift',
            w['sam_login_mismatch'], 'warning',
            lambda f: f'<li>{_f_link(f)}'
                      f' · AD={f.ad_sam}'
                      f' · DB={f.matched_person_id.odoo_user_id.login}</li>'))

        return f'<div class="o_ad_takeover_preflight">{"".join(rows)}</div>'

    # ------------------------------------------------------------------
    # Phase gating
    # ------------------------------------------------------------------

    PHASE_ORDER = ('preflight', 'link', 'normalise', 'cleanup', 'done')

    def _get_phase_blockers(self, phase=None):
        """Return blocker counts for the given phase. Used by both the
        UI to grey out the advance button, and by ``action_advance_phase``
        to refuse the advance on test sessions.
        """
        self.ensure_one()
        phase = phase or self.current_phase
        f = self.finding_ids

        def in_progress(states=('proposed', 'approved', 'discovered'),
                        proposal=None, extra_state=None):
            res = f.filtered(lambda x: x.state in states)
            if proposal is not None:
                res = res.filtered(lambda x: x.proposal_kind == proposal)
            if extra_state is not None:
                res = res | f.filtered(lambda x: x.state == extra_state)
            return res

        if phase == 'preflight':
            return {
                'stamp_id_pending': in_progress(proposal='stamp_id'),
                'identity_conflicts': f.filtered(
                    lambda x: x.state == 'identity_conflict'),
            }
        if phase == 'link':
            return {
                'link_only_pending': in_progress(proposal='link_only'),
            }
        if phase == 'normalise':
            return {
                'rename_pending':         in_progress(proposal='rename'),
                'move_pending':           in_progress(proposal='move'),
                'membership_add_pending': in_progress(proposal='membership_add'),
            }
        if phase == 'cleanup':
            return {
                'delete_after_pending': in_progress(proposal='delete_after'),
            }
        return {}

    def action_advance_phase(self):
        """Move ``current_phase`` to the next stage.

        * Test sessions: hard block. Any blocker → UserError.
        * Prod sessions: soft warning via the action_message; advance
          succeeds anyway. Reasoning: prod admins occasionally need to
          skip a finding for legitimate reasons; test should mirror the
          full intended path.
        """
        self.ensure_one()
        if self.current_phase == 'done':
            raise UserError(_('Sessie staat al op fase "voltooid".'))

        blockers = self._get_phase_blockers()
        blocker_total = sum(len(rs) for rs in blockers.values())

        if blocker_total and self.environment == 'test':
            details = '\n'.join(
                f'  - {k}: {len(rs)}' for k, rs in blockers.items() if rs)
            raise UserError(_(
                'Kan niet vooruit van fase "%(phase)s" — er staan nog '
                '%(n)d blocker(s) open op deze test-sessie:\n%(d)s\n\n'
                'Behandel ze eerst af, of zet ze expliciet op "negeer".'
            ) % {
                'phase': self.current_phase,
                'n': blocker_total,
                'd': details,
            })

        try:
            idx = self.PHASE_ORDER.index(self.current_phase)
        except ValueError:
            raise UserError(_(
                'Onbekende huidige fase: %s') % self.current_phase)
        new_phase = self.PHASE_ORDER[idx + 1]
        self.current_phase = new_phase

        msg = _('Fase verplaatst naar: %s') % new_phase
        if blocker_total:
            msg += _(' (met %d openstaande blocker(s) — prod-sessie, '
                     'soft override)') % blocker_total
        return self._notify(_('Fase gewijzigd'), msg,
                            kind='success' if not blocker_total else 'warning')

    # ------------------------------------------------------------------
    # DB index for matching
    # ------------------------------------------------------------------

    def _build_db_index(self):
        """Build the lookup maps the linker uses.

        Fase A adds three deterministic identity-keys on top of the
        original fuzzy/DN maps:
          - sap_ref_to_person  — primary key for users in all sources
          - email_cloud_to_person — secondary, used for STAMP_ID
          - login_to_person    — secondary, used for STAMP_ID

        ``person_id`` is stored in every map; the linker resolves it to
        a Person record when needed.
        """
        Org = self.env['myschool.org'].with_context(active_test=False)
        Person = self.env['myschool.person'].with_context(active_test=False)

        ou_dn_to_org = {}
        group_dn_to_org = {}
        cloud_path_to_org = {}
        cloud_group_email_to_org = {}

        gsvc = (self.env['myschool.google.directory.service']
                if self.google_workspace_config_id else None)
        gcfg = self.google_workspace_config_id

        for org in Org.search([]):
            if org.ou_fqdn_internal:
                ou_dn_to_org[self._norm_dn(org.ou_fqdn_internal)] = org.id
            for f in ('com_group_fqdn_internal', 'sec_group_fqdn_internal'):
                v = self._norm_dn(getattr(org, f, '') or '')
                if v:
                    group_dn_to_org[v] = org.id
            if gsvc and gcfg:
                path = gsvc.org_to_google_path(org, gcfg)
                if path and path != '/':
                    cloud_path_to_org[path.lower()] = org.id
            cge = getattr(org, 'com_group_email', '') or ''
            if cge:
                cloud_group_email_to_org[cge.strip().lower()] = org.id

        user_dn_to_person   = {}
        user_mail_to_person = {}
        sap_ref_to_person   = {}
        login_to_person     = {}

        for p in Person.search([]):
            if p.person_fqdn_internal:
                user_dn_to_person[self._norm_dn(p.person_fqdn_internal)] = p.id
            if p.email_cloud:
                user_mail_to_person[p.email_cloud.strip().lower()] = p.id
            if p.sap_ref:
                # Person.sap_ref carries a UNIQUE constraint, so the
                # map is 1-to-1 by construction.
                sap_ref_to_person[str(p.sap_ref).strip()] = p.id
            if p.odoo_user_id and p.odoo_user_id.login:
                login_to_person[p.odoo_user_id.login.strip().lower()] = p.id

        # Kept for compatibility with the legacy fuzzy-notes block in
        # action_scan (unused once the linker fully replaces it in
        # commit 4 — left in for now so existing rescans don't lose
        # the "matches res.users.login" hint).
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        user_sam_to_login = {}
        for u in Users.search([]):
            if u.login:
                user_sam_to_login[u.login.strip().lower()] = u.id

        return {
            'ou_dn_to_org':              ou_dn_to_org,
            'group_dn_to_org':           group_dn_to_org,
            'user_dn_to_person':         user_dn_to_person,
            'user_mail_to_person':       user_mail_to_person,
            'user_sam_to_login':         user_sam_to_login,
            'sap_ref_to_person':         sap_ref_to_person,
            'login_to_person':           login_to_person,
            # Cloud-side keys (Fase B). Empty when no google config set.
            'cloud_path_to_org':         cloud_path_to_org,
            'cloud_group_email_to_org':  cloud_group_email_to_org,
        }

    # ------------------------------------------------------------------
    # Type / role / parent guessing
    # ------------------------------------------------------------------

    def _guess_ou_takeover(self, dn):
        """Best-effort: parent OU + org_type for a takeover-target OU.

        Heuristics:
          - parent RDN contains 'klas' / 'class' → CLASSGROUP
          - parent RDN contains 'groep' / 'group' / 'cgroup' → DEPARTMENT
          - else → DEPARTMENT
        Parent-org guessed by stripping the first OU-component and
        looking up the resulting DN in the existing OU index.
        """
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        parent_dn = self._strip_first_rdn(dn)
        parent_org = Org.search(
            [('ou_fqdn_internal', '=ilike', parent_dn)], limit=1) \
            if parent_dn else Org

        rdn_chain = [p.lower() for p in dn.split(',')
                     if p.lower().startswith('ou=')]
        type_name = 'DEPARTMENT'
        if len(rdn_chain) >= 2:
            parent_rdn = rdn_chain[1]
            if any(t in parent_rdn for t in ('klas', 'class')):
                type_name = 'CLASSGROUP'
            elif any(t in parent_rdn for t in ('groep', 'group', 'cgroup', 'sgroup')):
                type_name = 'DEPARTMENT'
        type_rec = OrgType.search([('name', '=', type_name)], limit=1)
        return {
            'parent_id': parent_org.id if parent_org else False,
            'type_id': type_rec.id if type_rec else False,
        }

    def _guess_group_parent(self, dn):
        """Find an existing org under whose ou_fqdn_internal this group
        lives. Walk parent DNs upward until a match (or no more)."""
        Org = self.env['myschool.org']
        parent_dn = self._strip_first_rdn(dn)
        while parent_dn:
            org = Org.search(
                [('ou_fqdn_internal', '=ilike', parent_dn)], limit=1)
            if org:
                return org
            parent_dn = self._strip_first_rdn(parent_dn)
        return Org

    def _guess_user_parent(self, dn):
        return self._guess_group_parent(dn)

    def _guess_role(self, parent_org):
        if not parent_org or not parent_org.org_type_id:
            return None
        Role = self.env['myschool.role']
        type_name = (parent_org.org_type_id.name or '').upper()
        if type_name == 'CLASSGROUP':
            return Role.search([('name', '=', 'STUDENT')], limit=1)
        short = (parent_org.name_short or '').lower()
        if any(t in short for t in ('leer', 'teach', 'lk')):
            return Role.search([('name', '=', 'TEACHER')], limit=1)
        return Role.search([('name', '=', 'EMPLOYEE')], limit=1)

    @staticmethod
    def _strip_first_rdn(dn):
        if not dn or ',' not in dn:
            return None
        return dn.split(',', 1)[1].strip()

    @staticmethod
    def _norm_dn(dn):
        """Canonicalize a DN for comparison.

        Lowercases and strips leading/trailing whitespace from each RDN
        value, including RFC 4514 ``\\<space>`` escapes. AD silently
        introduces those when an OU is created with a stray trailing
        space (the AD UI hides it but the LDAP wire surfaces it as
        e.g. ``OU=l5a\\ ,...``). Without this, such entries never match
        their clean DB counterpart.

        Note: does not handle escaped commas inside RDN values
        (``\\,``); those are virtually never used in OU/group/user
        names in this codebase.
        """
        if not dn:
            return ''
        parts = []
        for rdn in dn.split(','):
            if '=' in rdn:
                attr, _, val = rdn.partition('=')
                val = val.replace('\\ ', ' ').strip()
                parts.append(f'{attr.strip()}={val}')
            else:
                parts.append(rdn.strip())
        return ','.join(parts).lower()

    # ------------------------------------------------------------------
    # LDAP entry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_str(entry, attr):
        """ldap3 entry attribute → string ('' if missing)."""
        try:
            v = entry[attr].value if attr in entry else None
        except Exception:
            return ''
        if v is None:
            return ''
        if isinstance(v, list):
            return v[0] if v else ''
        return str(v)

    @staticmethod
    def _entry_to_json(entry):
        try:
            d = {}
            for attr_name in entry.entry_attributes:
                try:
                    d[attr_name] = str(entry[attr_name].value)
                except Exception:
                    continue
            return json.dumps(d, default=str)[:8000]
        except Exception:
            return '{}'

    def _notify(self, title, message, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title, 'message': message, 'type': kind, 'sticky': True,
            },
        }


class AdTakeoverFinding(models.Model):
    _name = 'myschool.ad.takeover.finding'
    _description = 'AD Takeover Finding'
    _order = 'kind, ad_dn'
    _rec_name = 'ad_dn'

    session_id = fields.Many2one(
        'myschool.ad.takeover.session', required=True, ondelete='cascade')
    kind = fields.Selection(KIND_SELECTION, required=True)
    ad_dn = fields.Char(required=True, string='DN')
    ad_cn = fields.Char(string='CN')
    ad_sam = fields.Char(string='sAMAccountName')
    ad_mail = fields.Char(string='Mail')
    ad_givenname = fields.Char(string='Voornaam')
    ad_sn = fields.Char(string='Achternaam')
    ad_attributes_json = fields.Text(string='Raw AD attributes')

    match_kind = fields.Selection(
        MATCH_SELECTION, default='unmatched', required=True)
    status = fields.Selection(
        STATUS_SELECTION, default='investigate', required=True, index=True)
    notes = fields.Text(string='Notities')

    proposed_parent_org_id = fields.Many2one(
        'myschool.org', string='Voorgestelde parent-org')
    proposed_org_type_id = fields.Many2one(
        'myschool.org.type', string='Voorgesteld org-type')
    proposed_person_role_id = fields.Many2one(
        'myschool.role', string='Voorgestelde rol (user)')

    last_action_at = fields.Datetime(readonly=True)
    action_message = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    # Phase A: source-agnostic / state-machine fields
    # ------------------------------------------------------------------
    # These coexist with the legacy ``status`` / ``match_kind`` columns
    # until phase B switches the scan/apply logic over. The post-init
    # migration backfills these from existing rows so the old fields
    # and new fields stay consistent on upgrade.

    source = fields.Selection(
        SOURCE_SELECTION,
        required=True,
        default='ad',
        index=True,
        string='Bron',
        help='Externe systeem waar dit object vandaan komt. In Fase A '
             'altijd "ad"; cloud/smartschool-scanners volgen in Fase B.'
    )
    external_id = fields.Char(
        index=True,
        string='Bron-ID',
        help='Natural key in de bron. AD: distinguishedName. '
             'Cloud: orgUnitId/groupId/userId. SS: internnumber/groupId.'
    )
    sap_ref = fields.Char(
        index=True,
        string='SAP-ref',
        help='Cross-source identity-key. AD employeeID, Cloud externalIds, '
             'SS internnumber — moet matchen met myschool.person.sap_ref.'
    )

    # Cross-source counterparts. Leeg in Fase A; populeert vanaf Fase B
    # wanneer Cloud- en SS-scanners actief worden.
    sibling_ids = fields.Many2many(
        'myschool.ad.takeover.finding',
        'myschool_ad_takeover_finding_sibling_rel',
        'finding_id', 'sibling_finding_id',
        string='Tegenhangers in andere bronnen')

    matched_person_id = fields.Many2one(
        'myschool.person', ondelete='set null', index=True,
        string='Gematcht persoon')
    matched_org_id = fields.Many2one(
        'myschool.org', ondelete='set null', index=True,
        string='Gematchte organisatie')

    proposal_kind = fields.Selection(
        PROPOSAL_KIND_SELECTION,
        index=True,
        string='Voorstel-type',
        help='Welk soort actie de takeover voor dit object voorstelt.')
    proposal_payload_json = fields.Text(
        string='Voorstel-payload (JSON)',
        help='Per-voorstel parameters. Schema verschilt per proposal_kind.')

    state = fields.Selection(
        STATE_SELECTION,
        default='discovered',
        required=True,
        index=True,
        string='Staat',
        help='Nieuwe state-machine (Fase A). Vervangt het legacy '
             '"status"-veld; tijdens de overgang houdt de migratie '
             'beide synchroon.')

    rollback_snapshot_json = fields.Text(
        readonly=True,
        string='Rollback-snapshot (JSON)',
        help='Volledige attribuut-set vóór de pilot-actie. Gebruikt om '
             'één pilot terug te draaien. Wordt geschreven door Fase C.')
    rollback_snapshot_at = fields.Datetime(readonly=True)

    conflict_partner_id = fields.Many2one(
        'myschool.ad.takeover.finding',
        ondelete='set null',
        string='Conflicteert met',
        help='Als state=identity_conflict: de andere finding (in deze of '
             'een andere bron) die dezelfde sap_ref claimt.')
    conflict_reason = fields.Text(readonly=True, string='Conflict-reden')

    risk_level = fields.Selection(
        RISK_SELECTION,
        default='low',
        index=True,
        string='Risico',
        help='Heuristische inschatting; gebruikt voor UI-sortering en '
             'als guard tegen onbedoelde bulk-acties op high-risk items.')

    _sql_constraints = [
        ('uniq_dn_per_session',
         'UNIQUE(session_id, ad_dn)',
         'Eén entry per DN per sessie.'),
        # New uniqueness key — works alongside the legacy one. AD-only
        # rows have external_id=ad_dn (set by the migration), so this
        # adds no new rejections for existing data. Cloud/SS rows in
        # Fase B will use this constraint instead of the DN-based one.
        ('uniq_source_extid_per_session',
         'UNIQUE(session_id, source, external_id, kind)',
         'Eén entry per (bron, bron-ID, kind) per sessie.'),
    ]

    # ------------------------------------------------------------------
    # Quick-mark actions
    # ------------------------------------------------------------------

    def action_mark_investigate(self):
        self.write({
            'status': 'investigate',
            'state': 'discovered',
            'last_action_at': fields.Datetime.now(),
        })
        return True

    def action_mark_delete_after(self):
        for rec in self:
            if rec.kind == 'ou':
                raise UserError(_(
                    'OU "%s" — OUs mogen niet als "verwijder na migratie" '
                    'worden gemarkeerd. Gebruik "Onderzoek" of "Takeover".'
                ) % rec.ad_dn)
        self.write({
            'status': 'delete_after_migration',
            'state': 'proposed',
            'proposal_kind': 'delete_after',
            'risk_level': 'high',
            'last_action_at': fields.Datetime.now(),
        })
        return True

    def action_mark_takeover_pending(self):
        """Legacy: 'mark for bulk takeover'. Maps to approved+link_only/stamp_id
        in the new state machine — same end result, distinct name kept
        because the existing XML buttons still bind to this."""
        for rec in self:
            rec.write({
                'status': 'takeover_pending',
                'state': 'approved',
                # If the linker already picked a proposal_kind (stamp_id,
                # delete_after, ...), keep it. Otherwise default to
                # link_only — the historical implicit meaning.
                'proposal_kind': rec.proposal_kind or 'link_only',
                'last_action_at': fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        """Explicit approve step on an existing proposal. Distinct from
        action_mark_takeover_pending only in stricter preconditions:
        requires a non-empty proposal_kind and a state that can be
        approved from."""
        for rec in self:
            if not rec.proposal_kind:
                raise UserError(_(
                    'Geen voorstel om goed te keuren op "%s".') % rec.ad_dn)
            if rec.state not in ('proposed', 'rolled_back', 'discovered'):
                raise UserError(_(
                    'Goedkeuren kan vanaf state "proposed"/"rolled_back"/'
                    '"discovered" — huidige state: %s.') % rec.state)
            rec.write({
                'state': 'approved',
                'status': ('takeover_pending'
                           if rec.proposal_kind in ('link_only', 'stamp_id')
                           else rec.status),
                'last_action_at': fields.Datetime.now(),
            })
        return True

    def action_mark_ignore(self):
        self.write({
            'status': 'ignored',
            'state': 'ignored',
            'proposal_kind': 'ignore',
            'last_action_at': fields.Datetime.now(),
        })
        return True

    def action_open_diff_wizard(self):
        """Open the slide-over diff wizard for this finding. The wizard
        shows BRON/DB/ACTIE in 3 columns plus a footer with the same
        approve/pilot/verify/rollback/ignore actions as the row-level
        buttons — useful when the row-buttons are cramped on mobile.
        """
        self.ensure_one()
        wiz = self.env['myschool.ad.takeover.diff.wizard'].create({
            'finding_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.ad.takeover.diff.wizard',
            'view_mode': 'form',
            'res_id': wiz.id,
            'target': 'new',
        }

    def action_resolve_conflict(self):
        """Acknowledge an identity_conflict — admin elects to ignore it
        for the rest of the session. Genuine resolution still requires
        fixing the DB record (e.g. person.person_fqdn_internal) by hand
        and rescanning."""
        for rec in self:
            if rec.state != 'identity_conflict':
                raise UserError(_(
                    'Geen conflict op "%s" (state=%s).'
                ) % (rec.ad_dn, rec.state))
        self.write({
            'state': 'ignored',
            'status': 'ignored',
            'proposal_kind': 'ignore',
            'action_message': _(
                'Identity-conflict expliciet genegeerd. Fix de DB-data '
                'handmatig als dit een echt issue is en hertik scan.'),
            'last_action_at': fields.Datetime.now(),
        })
        return True

    # ------------------------------------------------------------------
    # Per-row takeover
    # ------------------------------------------------------------------

    def action_takeover(self):
        """Execute the row's proposal.

        Dispatch order:
          1. If proposal_kind is set → route to the matching handler.
          2. Else (legacy rows pre-dating the linker) → use the kind-based
             takeover path (creates a DB record, the original behaviour).
        """
        live = self.exists()
        if len(live) != len(self):
            raise UserError(_(
                'Eén of meer rijen bestaan niet meer in de DB '
                '(waarschijnlijk verwijderd door een nieuwe scan). '
                'Vernieuw het scherm en probeer opnieuw.'))
        for rec in live:
            if rec.state == 'done' or rec.status in ('takeover_done',
                                                     'delete_done',
                                                     'matched'):
                raise UserError(_(
                    '"%s" is al voltooid — geen actie nodig.') % rec.ad_dn)
            if rec.state == 'identity_conflict':
                raise UserError(_(
                    'Identity-conflict op "%s" — los het conflict eerst '
                    'op via DB-data en hertik scan, of klik '
                    '"Conflict negeren".') % rec.ad_dn)
            if rec.match_kind == 'matched_in_db' and not rec.proposal_kind:
                # Pure legacy state: a matched row without a proposal can
                # only be ignored — nothing to take over.
                raise UserError(_('"%s" zit al in de DB.') % rec.ad_dn)
            try:
                pk = rec.proposal_kind
                if not pk or pk == 'link_only':
                    if rec.kind == 'ou':
                        rec._takeover_ou()
                    elif rec.kind == 'group':
                        rec._takeover_group()
                    elif rec.kind == 'user':
                        rec._takeover_user()
                elif pk == 'stamp_id':
                    rec._apply_stamp_id()
                elif pk == 'rename':
                    rec._apply_rename()
                elif pk == 'move':
                    rec._apply_move()
                elif pk == 'membership_add':
                    rec._apply_membership_add()
                elif pk == 'delete_after':
                    rec._apply_delete_after()
                elif pk == 'ignore':
                    raise UserError(_(
                        'Voorstel-type "negeer" — niets te doen op "%s".'
                    ) % rec.ad_dn)
                else:
                    raise UserError(_(
                        'Onbekend voorstel-type: %s') % pk)
            except UserError:
                raise
            except Exception as e:
                _logger.exception(
                    '[AD-TAKEOVER] takeover failed for finding %s (%s, dn=%s)',
                    rec.id, rec.kind, rec.ad_dn)
                if not rec.exists():
                    raise UserError(_(
                        'Takeover voor "%s" is mislukt en de finding-rij is '
                        'tijdens de operatie verdwenen. Onderliggende fout: %s'
                    ) % (rec.ad_dn, e))
                raise UserError(_(
                    'Takeover voor "%s" mislukt: %s'
                ) % (rec.ad_dn, e))
        return True

    def _takeover_ou(self):
        self.ensure_one()
        if not self.proposed_parent_org_id:
            raise UserError(_('Kies een parent-org voor de takeover.'))
        if not self.proposed_org_type_id:
            raise UserError(_('Kies een org-type voor de takeover.'))
        parent = self.proposed_parent_org_id
        cn = self.ad_cn or self._first_rdn_value(self.ad_dn) or 'unknown'

        domain_internal = parent.domain_internal
        domain_external = parent.domain_external

        # External OU FQDN: replace internal-DC suffix with external one
        ou_external = ''
        if domain_internal and domain_external:
            int_dc = ',' + ','.join(f'dc={p}' for p in domain_internal.split('.'))
            ext_dc = ',' + ','.join(f'dc={p}' for p in domain_external.split('.'))
            if self.ad_dn.lower().endswith(int_dc.lower()):
                ou_external = self.ad_dn[: -len(int_dc)] + ext_dc

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'ADD', {
            'name': cn,
            'name_short': cn.lower(),
            'inst_nr': parent.inst_nr,
            'org_type_id': self.proposed_org_type_id.id,
            'has_ou': True,
            'ou_fqdn_internal': self.ad_dn,
            'ou_fqdn_external': ou_external,
            'domain_internal': domain_internal,
            'domain_external': domain_external,
            'parent_org_id': parent.id,
        })
        self._mark_done()

    def _takeover_group(self):
        self.ensure_one()
        if not self.proposed_parent_org_id:
            raise UserError(_('Kies een parent-org voor de takeover.'))
        OrgType = self.env['myschool.org.type']
        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        if not pg_type:
            raise UserError(_('PERSONGROUP-type ontbreekt in DB.'))
        parent = self.proposed_parent_org_id

        # Detect com vs sec by parent OU naming hints in the DN
        is_sec = any(t in self.ad_dn.lower() for t in (',ou=sgroup,', ',ou=secgroup,'))
        cn = self.ad_cn or self._first_rdn_value(self.ad_dn) or 'unknown'
        vals = {
            'name': cn,
            'name_short': cn,  # PERSONGROUP-invariant: name == name_short
            'inst_nr': parent.inst_nr,
            'org_type_id': pg_type.id,
            'has_comgroup': not is_sec,
            'has_secgroup': is_sec,
            'parent_org_id': parent.id,
        }
        if is_sec:
            vals['sec_group_fqdn_internal'] = self.ad_dn
            vals['sec_group_name'] = cn
        else:
            vals['com_group_fqdn_internal'] = self.ad_dn
            vals['com_group_name'] = cn
            if self.ad_mail:
                vals['com_group_email'] = self.ad_mail
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'ADD', vals)
        self._mark_done()

    def _takeover_user(self):
        self.ensure_one()
        if not self.proposed_parent_org_id:
            raise UserError(_(
                'Kies de parent-org waaronder de user komt te hangen.'))
        parent = self.proposed_parent_org_id

        first = self.ad_givenname or ''
        last = self.ad_sn or self.ad_cn or 'unknown'
        person_vals = {
            'name': last,
            'first_name': first,
            'email_cloud': self.ad_mail or False,
            'person_fqdn_internal': self.ad_dn,
            # Carry employeeID → sap_ref so the new DB-person is
            # identifiable by all downstream syncs (Informat / Cloud / SS).
            # Without this, Informat would create a duplicate person on
            # the next sync because the sap_ref-match fails.
            'sap_ref': self.sap_ref or False,
            # automatic_sync=True so Informat takes over as the
            # authoritative source for personal data (name, birthdate,
            # registration) once it runs. AD-takeover only filled a
            # skeleton from LDAP attributes; Informat refines it. AD-
            # binding (person_fqdn_internal) is owned by this tool and
            # not touched by Informat.
            'automatic_sync': True,
            'is_active': True,
        }
        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('PERSON', 'ADD', person_vals)

        # Optional PPSBR if a role is suggested
        if self.proposed_person_role_id:
            # The PERSON/ADD handler returns the created person's id in the
            # task-changes; for simplicity we look up by DN here.
            Person = self.env['myschool.person']
            p = Person.search(
                [('person_fqdn_internal', '=', self.ad_dn)], limit=1)
            if p:
                service.create_manual_task('PROPRELATION', 'ADD', {
                    'type': 'PPSBR',
                    'person_id': p.id,
                    'org_id': parent.id,
                    'role_id': self.proposed_person_role_id.id,
                })
        self._mark_done()

    # ==================================================================
    # Pilot / verify / rollback — Fase C1
    # ==================================================================

    MUTATING_PROPOSALS = ('stamp_id', 'rename', 'move', 'membership_add')

    def action_pilot(self):
        """Capture a rollback snapshot, then perform the bron-mutation.
        Result: state=applied_pilot. Admin then clicks Verifieer (→ done)
        or Rollback (→ approved, snapshot replayed).

        Only available for muterende voorstellen — LINK_ONLY and
        DELETE_AFTER use action_takeover directly.
        """
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_(
                'Pilot vereist state=approved (huidige state: %s).'
            ) % self.state)
        if self.proposal_kind not in self.MUTATING_PROPOSALS:
            raise UserError(_(
                'Pilot is alleen zinvol voor muterende voorstellen. '
                'LINK_ONLY/DELETE_AFTER gaan direct via "Voer voorstel uit".'))

        try:
            snapshot = self._capture_snapshot()
        except Exception as e:
            _logger.exception(
                '[AD-TAKEOVER] snapshot capture failed for %s', self.ad_dn)
            raise UserError(_(
                'Snapshot maken mislukt — pilot afgebroken: %s') % e)

        self.write({
            'rollback_snapshot_json': json.dumps(snapshot, default=str),
            'rollback_snapshot_at': fields.Datetime.now(),
        })

        try:
            self._apply_mutation()
        except Exception as e:
            # Mutation failed — wipe the snapshot so a retry generates
            # a fresh one against the unchanged bron-state.
            self.write({
                'rollback_snapshot_json': False,
                'rollback_snapshot_at': False,
            })
            _logger.exception(
                '[AD-TAKEOVER] pilot mutation failed for %s', self.ad_dn)
            raise UserError(_('Pilot mislukt: %s') % e)

        self.write({
            'state': 'applied_pilot',
            'last_action_at': fields.Datetime.now(),
            'action_message': _(
                'Pilot uitgevoerd. Controleer in %(source)s; klik daarna '
                '"Verifieer" of "Rollback".'
            ) % {'source': self.source.upper()},
        })
        return True

    def action_verify(self):
        """Accept the pilot result and promote state → done."""
        self.ensure_one()
        if self.state != 'applied_pilot':
            raise UserError(_(
                'Verifieer vereist state=applied_pilot (huidige state: %s).'
            ) % self.state)
        self.write({
            'state': 'done',
            'status': 'takeover_done',
            'last_action_at': fields.Datetime.now(),
            'action_message': _('Pilot geverifieerd en geaccepteerd.'),
        })
        return True

    def action_rollback(self):
        """Reverse the piloted mutation using the snapshot. State
        returns to ``approved`` so admin can retry, skip, or rework."""
        self.ensure_one()
        if self.state != 'applied_pilot':
            raise UserError(_(
                'Rollback vereist state=applied_pilot (huidige state: %s).'
            ) % self.state)
        if not self.rollback_snapshot_json:
            raise UserError(_(
                'Geen snapshot beschikbaar — handmatige restore vereist.'))
        try:
            snapshot = json.loads(self.rollback_snapshot_json)
        except (ValueError, TypeError):
            raise UserError(_('Snapshot is corrupt — handmatige restore.'))

        try:
            self._restore_snapshot(snapshot)
        except Exception as e:
            _logger.exception(
                '[AD-TAKEOVER] rollback failed for %s', self.ad_dn)
            raise UserError(_('Rollback mislukt: %s') % e)

        self.write({
            'state': 'approved',
            'rollback_snapshot_json': False,
            'rollback_snapshot_at': False,
            'last_action_at': fields.Datetime.now(),
            'action_message': _(
                'Rollback uitgevoerd. Bron-staat hersteld; voorstel staat '
                'opnieuw op "goedgekeurd".'),
        })
        return True

    # ------------------------------------------------------------------
    # Snapshot / mutate / restore — dispatchers
    # ------------------------------------------------------------------

    def _capture_snapshot(self):
        """Read current bron-state into a dict. Per proposal_kind."""
        self.ensure_one()
        if self.proposal_kind == 'stamp_id':
            return self._snapshot_stamp_id()
        if self.proposal_kind == 'rename':
            return self._snapshot_rename()
        if self.proposal_kind == 'move':
            return self._snapshot_move()
        if self.proposal_kind == 'membership_add':
            return self._snapshot_membership_add()
        raise UserError(_(
            'Snapshot voor proposal_kind=%s nog niet geïmplementeerd.'
        ) % self.proposal_kind)

    def _restore_snapshot(self, snapshot):
        """Invert the bron-mutation using the snapshot."""
        self.ensure_one()
        if self.proposal_kind == 'stamp_id':
            return self._restore_stamp_id(snapshot)
        if self.proposal_kind == 'rename':
            return self._restore_rename(snapshot)
        if self.proposal_kind == 'move':
            return self._restore_move(snapshot)
        if self.proposal_kind == 'membership_add':
            return self._restore_membership_add(snapshot)
        raise UserError(_(
            'Rollback voor proposal_kind=%s nog niet geïmplementeerd.'
        ) % self.proposal_kind)

    def _apply_mutation(self):
        """Pure bron-write — no state-change, no DB-cascade. Used by
        action_pilot. For direct-apply (no pilot), see the _apply_*
        wrappers which call _mutate_* and then _mark_done."""
        self.ensure_one()
        if self.proposal_kind == 'stamp_id':
            return self._mutate_stamp_id()
        if self.proposal_kind == 'rename':
            return self._mutate_rename()
        if self.proposal_kind == 'move':
            return self._mutate_move()
        if self.proposal_kind == 'membership_add':
            return self._mutate_membership_add()
        raise UserError(_(
            'Mutatie voor proposal_kind=%s nog niet geïmplementeerd.'
        ) % self.proposal_kind)

    # ------------------------------------------------------------------
    # STAMP_ID — snapshot / mutate / restore (AD + Cloud)
    # ------------------------------------------------------------------

    def _snapshot_stamp_id(self):
        """Read the bron's current identity attribute so rollback can
        restore it. AD → employeeID; Cloud → externalIds list."""
        self.ensure_one()
        if self.source == 'ad':
            ldap = self.env['myschool.ldap.service']
            config = self.session_id.ldap_config_id
            old_value = ''
            with ldap._get_connection(config) as conn:
                conn.search(self.ad_dn, '(objectClass=*)',
                            search_scope='BASE',
                            attributes=['employeeID'])
                entries = list(conn.entries)
                if entries:
                    try:
                        old_value = str(entries[0]['employeeID'].value or '')
                    except Exception:
                        pass
            return {
                'source': 'ad',
                'attribute': 'employeeID',
                'old_value': old_value,
            }
        if self.source == 'cloud':
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            user = api.users().get(userKey=self.external_id).execute()
            return {
                'source': 'cloud',
                'attribute': 'externalIds',
                'old_value': user.get('externalIds') or [],
            }
        raise UserError(_(
            'STAMP_ID snapshot: source=%s wordt niet ondersteund.') % self.source)

    def _mutate_stamp_id(self):
        """Apply the STAMP_ID change. Pure bron-write."""
        self.ensure_one()
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        value = payload.get('value')
        if not value:
            raise UserError(_('Ongeldige STAMP_ID-payload.'))
        if self.source == 'ad':
            self._mutate_ad_employee_id(value)
        elif self.source == 'cloud':
            self._mutate_cloud_external_ids(value)
        else:
            raise UserError(_(
                'STAMP_ID mutatie: source=%s wordt niet ondersteund.'
            ) % self.source)

    def _restore_stamp_id(self, snapshot):
        """Write the snapshotted value back. Empty old_value on AD
        removes the attribute entirely; Cloud restore overwrites the
        whole externalIds list."""
        self.ensure_one()
        old = snapshot.get('old_value', '' if self.source == 'ad' else [])
        if self.source == 'ad':
            self._mutate_ad_employee_id(old)
        elif self.source == 'cloud':
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            api.users().patch(
                userKey=self.external_id,
                body={'externalIds': old}).execute()
        else:
            raise UserError(_(
                'STAMP_ID restore: source=%s niet ondersteund.') % self.source)

    def _mutate_ad_employee_id(self, value):
        """LDAP MODIFY employeeID. Empty value removes the attribute."""
        from ldap3 import MODIFY_REPLACE, MODIFY_DELETE
        ldap = self.env['myschool.ldap.service']
        config = self.session_id.ldap_config_id
        with ldap._get_connection(config) as conn:
            if value:
                conn.modify(self.ad_dn,
                            {'employeeID': [(MODIFY_REPLACE, [str(value)])]})
            else:
                conn.modify(self.ad_dn,
                            {'employeeID': [(MODIFY_DELETE, [])]})
            result = conn.result or {}
            # result=0 success; result=16 "no such attribute" on DELETE
            # is acceptable (already empty).
            if result.get('result') not in (0, 16):
                raise UserError(_(
                    'LDAP MODIFY mislukt voor %(dn)s: %(err)s'
                ) % {'dn': self.ad_dn,
                     'err': result.get('description') or result})

    def _mutate_cloud_external_ids(self, value):
        """Patch Cloud user.externalIds. Preserves non-'organization'
        entries (custom IDs the school may use for other systems)."""
        gsvc = self.env['myschool.google.directory.service']
        config = self.session_id.google_workspace_config_id
        api = gsvc._get_directory_service(config)
        user = api.users().get(userKey=self.external_id).execute()
        ext_ids = [e for e in (user.get('externalIds') or [])
                   if e.get('type') != 'organization']
        if value:
            ext_ids.append({'type': 'organization', 'value': str(value)})
        api.users().patch(
            userKey=self.external_id,
            body={'externalIds': ext_ids}).execute()

    # ------------------------------------------------------------------
    # RENAME — snapshot / mutate / restore (Fase C2)
    # ------------------------------------------------------------------
    #
    # Payload schema:
    #   {"new_name": "<new RDN value or display name>"}
    #
    # AD: LDAP MODIFY DN preserves objectSID, objectGUID, group
    # memberships, GPO links — exactly the guarantee we need for safe
    # renames. The new RDN replaces the leaf CN/OU value; the parent
    # DN stays put (move is a separate proposal kind).
    #
    # Cloud groups: PATCH name (email = identity, never touched).
    # Cloud OUs:    update_orgunit name (parent path preserved).
    # Cloud users:  REJECTED — primaryEmail is identity, renaming
    #               implies a primaryEmail change which we never do.

    def _snapshot_rename(self):
        """Snapshot of the bron-object's current name. Reads from the
        live bron rather than trusting our finding-cache so we restore
        to the actual state, not the cached one."""
        self.ensure_one()
        if self.source == 'ad':
            return {
                'source': 'ad',
                'kind': self.kind,
                'old_dn': self.ad_dn,
            }
        if self.source == 'cloud':
            if self.kind == 'user':
                raise UserError(_(
                    'Cloud-users hernoemen wordt niet ondersteund — '
                    'primaryEmail is de identity-sleutel.'))
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            if self.kind == 'group':
                grp = api.groups().get(groupKey=self.external_id).execute()
                return {
                    'source': 'cloud',
                    'kind': 'group',
                    'group_email': grp.get('email'),
                    'old_name': grp.get('name', ''),
                }
            if self.kind == 'ou':
                ou = api.orgunits().get(
                    customerId=config.customer_id or 'my_customer',
                    orgUnitPath=self.ad_dn  # we store cloud-path here
                ).execute()
                return {
                    'source': 'cloud',
                    'kind': 'ou',
                    'org_unit_path': ou.get('orgUnitPath'),
                    'old_name': ou.get('name', ''),
                }
        raise UserError(_(
            'RENAME snapshot: source=%s, kind=%s niet ondersteund.'
        ) % (self.source, self.kind))

    def _mutate_rename(self):
        """Rename the bron-object. Pure write — no state-change."""
        self.ensure_one()
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        new_name = (payload.get('new_name') or '').strip()
        if not new_name:
            raise UserError(_('RENAME-payload mist new_name.'))

        if self.source == 'ad':
            self._mutate_ad_rename(new_name)
            return
        if self.source == 'cloud':
            self._mutate_cloud_rename(new_name)
            return
        raise UserError(_(
            'RENAME mutatie: source=%s niet ondersteund.') % self.source)

    def _mutate_ad_rename(self, new_name):
        """LDAP MODIFY DN. Preserves SID, GUID, group memberships.
        Updates self.ad_dn after success so the finding reflects the
        post-rename state."""
        ldap = self.env['myschool.ldap.service']
        config = self.session_id.ldap_config_id
        # New RDN: use CN= for users/groups, OU= for OUs (matches AD
        # convention; the existing leaf prefix determines which).
        if self.kind == 'ou':
            new_rdn = f'OU={new_name}'
        else:
            new_rdn = f'CN={new_name}'
        with ldap._get_connection(config) as conn:
            ok = conn.modify_dn(self.ad_dn, new_rdn)
            result = conn.result or {}
            if not ok or result.get('result') != 0:
                raise UserError(_(
                    'LDAP MODIFY DN mislukt voor %(dn)s: %(err)s'
                ) % {'dn': self.ad_dn,
                     'err': result.get('description') or result})
        # Reconstruct the new full DN: replace the leftmost RDN.
        parent_dn = self.ad_dn.split(',', 1)[1] if ',' in self.ad_dn else ''
        new_dn = f'{new_rdn},{parent_dn}' if parent_dn else new_rdn
        self.write({
            'ad_dn': new_dn,
            'ad_cn': new_name,
            'external_id': new_dn,
        })

    def _mutate_cloud_rename(self, new_name):
        gsvc = self.env['myschool.google.directory.service']
        config = self.session_id.google_workspace_config_id
        api = gsvc._get_directory_service(config)
        if self.kind == 'group':
            api.groups().patch(
                groupKey=self.external_id,
                body={'name': new_name}).execute()
            self.write({'ad_cn': new_name})
        elif self.kind == 'ou':
            customer = config.customer_id or 'my_customer'
            api.orgunits().patch(
                customerId=customer,
                orgUnitPath=self.ad_dn,
                body={'name': new_name}).execute()
            self.write({'ad_cn': new_name})
        else:
            raise UserError(_(
                'Cloud-RENAME niet ondersteund voor kind=%s') % self.kind)

    def _restore_rename(self, snapshot):
        """Undo a rename using the snapshotted old name/DN."""
        self.ensure_one()
        if snapshot.get('source') == 'ad':
            old_dn = snapshot.get('old_dn')
            if not old_dn:
                raise UserError(_('Snapshot mist old_dn.'))
            ldap = self.env['myschool.ldap.service']
            config = self.session_id.ldap_config_id
            old_rdn = old_dn.split(',', 1)[0]
            with ldap._get_connection(config) as conn:
                ok = conn.modify_dn(self.ad_dn, old_rdn)
                result = conn.result or {}
                if not ok or result.get('result') != 0:
                    raise UserError(_(
                        'LDAP MODIFY DN rollback mislukt: %s'
                    ) % (result.get('description') or result))
            self.write({
                'ad_dn': old_dn,
                'ad_cn': old_rdn.split('=', 1)[1] if '=' in old_rdn else '',
                'external_id': old_dn,
            })
            return
        if snapshot.get('source') == 'cloud':
            old_name = snapshot.get('old_name') or ''
            if not old_name:
                raise UserError(_('Snapshot mist old_name.'))
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            if snapshot.get('kind') == 'group':
                api.groups().patch(
                    groupKey=self.external_id,
                    body={'name': old_name}).execute()
            elif snapshot.get('kind') == 'ou':
                customer = config.customer_id or 'my_customer'
                api.orgunits().patch(
                    customerId=customer,
                    orgUnitPath=self.ad_dn,
                    body={'name': old_name}).execute()
            self.write({'ad_cn': old_name})
            return
        raise UserError(_(
            'RENAME restore: source=%s niet ondersteund.'
        ) % snapshot.get('source'))

    def _apply_rename(self):
        """Direct-apply path. Snapshot + mutate + mark_done. Snapshot
        is preserved as audit-log even after done so a manual restore
        is still possible later."""
        self.ensure_one()
        snapshot = self._capture_snapshot()
        self.write({
            'rollback_snapshot_json': json.dumps(snapshot, default=str),
            'rollback_snapshot_at': fields.Datetime.now(),
        })
        self._mutate_rename()
        self._mark_done(action_message=_('Hernoemd in %s.') % self.source)

    # ------------------------------------------------------------------
    # MOVE — snapshot / mutate / restore (Fase C3)
    # ------------------------------------------------------------------
    #
    # Payload schema:
    #   AD:    {"new_parent": "OU=foo,OU=bar,DC=..."}
    #   Cloud: {"new_parent": "/path/to/new/parent"}  (orgUnitPath)
    #
    # AD: MODIFY DN with new_superior=parent moves the object beneath
    #     a different parent. RDN stays put (rename is separate).
    #     Memberships, SID, GUID all preserved.
    # Cloud user: patch orgUnitPath
    # Cloud OU:   patch parentOrgUnitPath
    # Cloud group: N/A — groups are tenant-flat, no OU concept.

    def _snapshot_move(self):
        self.ensure_one()
        if self.source == 'ad':
            parent_dn = (self.ad_dn.split(',', 1)[1]
                         if ',' in self.ad_dn else '')
            return {
                'source': 'ad',
                'kind': self.kind,
                'old_dn': self.ad_dn,
                'old_parent': parent_dn,
            }
        if self.source == 'cloud':
            if self.kind == 'group':
                raise UserError(_(
                    'Cloud-groups hebben geen OU — MOVE is N/A.'))
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            if self.kind == 'user':
                user = api.users().get(userKey=self.external_id).execute()
                return {
                    'source': 'cloud',
                    'kind': 'user',
                    'old_org_unit_path': user.get('orgUnitPath', '/'),
                }
            if self.kind == 'ou':
                customer = config.customer_id or 'my_customer'
                ou = api.orgunits().get(
                    customerId=customer,
                    orgUnitPath=self.ad_dn).execute()
                return {
                    'source': 'cloud',
                    'kind': 'ou',
                    'old_parent_path': ou.get('parentOrgUnitPath', '/'),
                    'old_path': ou.get('orgUnitPath'),
                }
        raise UserError(_(
            'MOVE snapshot: source=%s, kind=%s niet ondersteund.'
        ) % (self.source, self.kind))

    def _mutate_move(self):
        self.ensure_one()
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        new_parent = (payload.get('new_parent') or '').strip()
        if not new_parent:
            raise UserError(_('MOVE-payload mist new_parent.'))

        if self.source == 'ad':
            self._mutate_ad_move(new_parent)
            return
        if self.source == 'cloud':
            self._mutate_cloud_move(new_parent)
            return
        raise UserError(_('MOVE mutatie: source=%s niet ondersteund.')
                        % self.source)

    def _mutate_ad_move(self, new_parent_dn):
        """MODIFY DN with new_superior. Keeps RDN unchanged."""
        ldap = self.env['myschool.ldap.service']
        config = self.session_id.ldap_config_id
        old_rdn = self.ad_dn.split(',', 1)[0]
        with ldap._get_connection(config) as conn:
            ok = conn.modify_dn(self.ad_dn, old_rdn,
                                new_superior=new_parent_dn)
            result = conn.result or {}
            if not ok or result.get('result') != 0:
                raise UserError(_(
                    'LDAP MOVE mislukt voor %(dn)s → %(parent)s: %(err)s'
                ) % {'dn': self.ad_dn,
                     'parent': new_parent_dn,
                     'err': result.get('description') or result})
        new_dn = f'{old_rdn},{new_parent_dn}'
        self.write({
            'ad_dn': new_dn,
            'external_id': new_dn,
        })

    def _mutate_cloud_move(self, new_parent_path):
        gsvc = self.env['myschool.google.directory.service']
        config = self.session_id.google_workspace_config_id
        api = gsvc._get_directory_service(config)
        if self.kind == 'user':
            api.users().patch(
                userKey=self.external_id,
                body={'orgUnitPath': new_parent_path}).execute()
        elif self.kind == 'ou':
            customer = config.customer_id or 'my_customer'
            api.orgunits().patch(
                customerId=customer,
                orgUnitPath=self.ad_dn,
                body={'parentOrgUnitPath': new_parent_path}).execute()
            # New full path = parent + '/' + own_name
            own_name = self.ad_cn or self.ad_dn.rsplit('/', 1)[-1]
            new_path = (f'{new_parent_path.rstrip("/")}/{own_name}'
                        if new_parent_path != '/' else f'/{own_name}')
            self.write({'ad_dn': new_path, 'external_id': new_path})
        else:
            raise UserError(_(
                'Cloud-MOVE niet ondersteund voor kind=%s') % self.kind)

    def _restore_move(self, snapshot):
        self.ensure_one()
        if snapshot.get('source') == 'ad':
            old_parent = snapshot.get('old_parent')
            old_dn = snapshot.get('old_dn')
            if not old_parent or not old_dn:
                raise UserError(_('MOVE-snapshot incompleet.'))
            ldap = self.env['myschool.ldap.service']
            config = self.session_id.ldap_config_id
            current_rdn = self.ad_dn.split(',', 1)[0]
            with ldap._get_connection(config) as conn:
                ok = conn.modify_dn(self.ad_dn, current_rdn,
                                    new_superior=old_parent)
                result = conn.result or {}
                if not ok or result.get('result') != 0:
                    raise UserError(_(
                        'LDAP MOVE rollback mislukt: %s'
                    ) % (result.get('description') or result))
            self.write({'ad_dn': old_dn, 'external_id': old_dn})
            return
        if snapshot.get('source') == 'cloud':
            gsvc = self.env['myschool.google.directory.service']
            config = self.session_id.google_workspace_config_id
            api = gsvc._get_directory_service(config)
            if snapshot.get('kind') == 'user':
                api.users().patch(
                    userKey=self.external_id,
                    body={'orgUnitPath': snapshot.get('old_org_unit_path')}
                ).execute()
            elif snapshot.get('kind') == 'ou':
                customer = config.customer_id or 'my_customer'
                api.orgunits().patch(
                    customerId=customer,
                    orgUnitPath=self.ad_dn,
                    body={'parentOrgUnitPath': snapshot.get('old_parent_path')}
                ).execute()
                if snapshot.get('old_path'):
                    self.write({
                        'ad_dn': snapshot['old_path'],
                        'external_id': snapshot['old_path'],
                    })
            return
        raise UserError(_(
            'MOVE restore: source=%s niet ondersteund.'
        ) % snapshot.get('source'))

    def _apply_move(self):
        """Direct-apply: snapshot + mutate + mark_done."""
        self.ensure_one()
        snapshot = self._capture_snapshot()
        self.write({
            'rollback_snapshot_json': json.dumps(snapshot, default=str),
            'rollback_snapshot_at': fields.Datetime.now(),
        })
        self._mutate_move()
        self._mark_done(action_message=_('Verplaatst in %s.') % self.source)

    # ------------------------------------------------------------------
    # MEMBERSHIP_ADD — snapshot / mutate / restore (Fase C4)
    # ------------------------------------------------------------------
    #
    # Payload schema:
    #   AD:    {"target_group_dn": "...", "member_dn": "..."}
    #   Cloud: {"target_group_email": "...", "member_email": "..."}
    #
    # The finding represents the USER being added; the group is the
    # target. Snapshot is trivial: we know the membership did NOT
    # exist before (otherwise the proposal would not have been made),
    # so rollback simply removes it.

    def _snapshot_membership_add(self):
        self.ensure_one()
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        return {
            'source': self.source,
            'payload_at_pilot': payload,
        }

    def _mutate_membership_add(self):
        self.ensure_one()
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        if self.source == 'ad':
            group_dn = (payload.get('target_group_dn') or '').strip()
            member_dn = (payload.get('member_dn') or self.ad_dn or '').strip()
            if not group_dn or not member_dn:
                raise UserError(_(
                    'MEMBERSHIP_ADD-payload mist target_group_dn of member_dn.'))
            ldap = self.env['myschool.ldap.service']
            res = ldap.add_group_member(
                self.session_id.ldap_config_id, group_dn, member_dn)
            if not res.get('success'):
                raise UserError(_(
                    'LDAP add_group_member mislukt: %s'
                ) % res.get('message', 'onbekend'))
            return
        if self.source == 'cloud':
            group_email = (payload.get('target_group_email') or '').strip()
            member_email = (payload.get('member_email')
                            or self.ad_mail or '').strip()
            if not group_email or not member_email:
                raise UserError(_(
                    'MEMBERSHIP_ADD-payload mist target_group_email of '
                    'member_email.'))
            gsvc = self.env['myschool.google.directory.service']
            res = gsvc.add_group_member(
                self.session_id.google_workspace_config_id,
                group_email, member_email)
            if not res.get('success'):
                raise UserError(_(
                    'Cloud add_group_member mislukt: %s'
                ) % res.get('message', 'onbekend'))
            return
        raise UserError(_(
            'MEMBERSHIP_ADD mutatie: source=%s niet ondersteund.'
        ) % self.source)

    def _restore_membership_add(self, snapshot):
        self.ensure_one()
        payload = snapshot.get('payload_at_pilot') or {}
        if snapshot.get('source') == 'ad':
            group_dn = (payload.get('target_group_dn') or '').strip()
            member_dn = (payload.get('member_dn') or self.ad_dn or '').strip()
            if not group_dn or not member_dn:
                raise UserError(_(
                    'MEMBERSHIP_ADD-rollback mist DN-velden in snapshot.'))
            ldap = self.env['myschool.ldap.service']
            res = ldap.remove_group_member(
                self.session_id.ldap_config_id, group_dn, member_dn)
            if not res.get('success'):
                raise UserError(_(
                    'LDAP remove_group_member rollback mislukt: %s'
                ) % res.get('message', 'onbekend'))
            return
        if snapshot.get('source') == 'cloud':
            group_email = (payload.get('target_group_email') or '').strip()
            member_email = (payload.get('member_email')
                            or self.ad_mail or '').strip()
            gsvc = self.env['myschool.google.directory.service']
            res = gsvc.remove_group_member(
                self.session_id.google_workspace_config_id,
                group_email, member_email)
            if not res.get('success'):
                raise UserError(_(
                    'Cloud remove_group_member rollback mislukt: %s'
                ) % res.get('message', 'onbekend'))
            return
        raise UserError(_(
            'MEMBERSHIP_ADD restore: source=%s niet ondersteund.'
        ) % snapshot.get('source'))

    def _apply_membership_add(self):
        """Direct-apply: snapshot + mutate + mark_done."""
        self.ensure_one()
        snapshot = self._capture_snapshot()
        self.write({
            'rollback_snapshot_json': json.dumps(snapshot, default=str),
            'rollback_snapshot_at': fields.Datetime.now(),
        })
        self._mutate_membership_add()
        self._mark_done(action_message=_(
            'Toegevoegd aan groep in %s.') % self.source)

    def _apply_stamp_id(self):
        """Direct-apply path (no pilot): mutate + mark_done.

        Used by action_takeover when the admin chooses to skip the
        pilot step. For pilot/rollback path, see ``action_pilot`` which
        captures a snapshot before calling ``_mutate_stamp_id``.

        Works on AD (employeeID) and Cloud (externalIds.organization).
        """
        self.ensure_one()
        if self.kind != 'user':
            raise UserError(_(
                'STAMP_ID werkt alleen op user-findings (kind=%s).'
            ) % self.kind)
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        value = payload.get('value')
        if not value:
            raise UserError(_(
                'Ongeldige STAMP_ID-payload op "%s".') % self.ad_dn)

        # The pure bron-mutation.
        self._mutate_stamp_id()

        # DB-cascade (AD only): link person.person_fqdn_internal when
        # empty so the next rescan matches on the strongest key.
        person = self.matched_person_id
        if self.source == 'ad' and person and not person.person_fqdn_internal:
            service = self.env['myschool.manual.task.service']
            service.create_manual_task('PERSON', 'UPD', {
                'person_id': person.id,
                'vals': {'person_fqdn_internal': self.ad_dn},
            })

        attr = 'employeeID' if self.source == 'ad' else 'externalIds'
        self._mark_done(action_message=_(
            '%(attr)s=%(value)s naar bron geschreven (geen andere wijzigingen).'
        ) % {'attr': attr, 'value': value})

    def _apply_delete_after(self):
        """Cleanup-phase LDAP delete for a single finding. Mirrors the
        session-level apply_pending_deletes row-loop so the unified
        action_takeover dispatcher can drive it too."""
        self.ensure_one()
        if self.kind == 'ou':
            raise UserError(_(
                'OUs worden niet verwijderd via deze flow.'))
        if self.source != 'ad':
            raise UserError(_(
                'DELETE_AFTER is in Fase A alleen geïmplementeerd voor AD.'))
        ldap = self.env['myschool.ldap.service']
        config = self.session_id.ldap_config_id
        if self.kind == 'user':
            res = (ldap.delete_user_by_dn(config, self.ad_dn)
                   if hasattr(ldap, 'delete_user_by_dn')
                   else self.session_id._delete_dn(self.ad_dn))
        else:  # group
            res = ldap.delete_group(config, self.ad_dn)
        if not res.get('success'):
            raise UserError(_('LDAP delete mislukt: %s') % res.get(
                'message', 'onbekende fout'))
        self.write({
            'state': 'done',
            'status': 'delete_done',          # legacy mirror
            'action_message': res.get('message', ''),
            'last_action_at': fields.Datetime.now(),
        })

    def _mark_done(self, action_message=None):
        self.write({
            'state': 'done',
            'status': 'takeover_done',        # legacy mirror
            'last_action_at': fields.Datetime.now(),
            'action_message': action_message or _('Takeover voltooid.'),
        })

    @staticmethod
    def _first_rdn_value(dn):
        if not dn or '=' not in dn:
            return None
        rdn = dn.split(',', 1)[0]
        return rdn.split('=', 1)[1].strip() if '=' in rdn else None
