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
    ldap_config_id = fields.Many2one(
        'myschool.ldap.server.config', required=True,
        string='LDAP-server',
        domain="[('active', '=', True)]")
    scope_org_id = fields.Many2one(
        'myschool.org', required=True, string='Scope (SCHOOL/SCHOOLBOARD)',
        domain="[('org_type_id.name', 'in', ['SCHOOL', 'SCHOOLBOARD'])]",
        help='Scan-scope is SUBTREE onder ou_fqdn_internal van deze org. '
             'Strikt — geen LDAP-zoekoperaties buiten deze tak.')
    base_dn = fields.Char(
        compute='_compute_base_dn', store=True, readonly=True)

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
        tracking=True,
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

    @api.constrains('ldap_config_id', 'environment')
    def _check_environment_consistency(self):
        for s in self:
            if not s.ldap_config_id:
                continue
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

    @api.depends('finding_ids', 'finding_ids.state', 'finding_ids.proposal_kind')
    def _compute_counts(self):
        for rec in self:
            f = rec.finding_ids
            rec.finding_count = len(f)

            # New state-based counters
            rec.discovered_count = len(f.filtered(lambda x: x.state == 'discovered'))
            rec.proposed_count   = len(f.filtered(lambda x: x.state == 'proposed'))
            rec.approved_count   = len(f.filtered(lambda x: x.state == 'approved'))
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
        self.ensure_one()
        if not self.base_dn:
            raise UserError(_(
                'Scope org "%s" heeft geen ou_fqdn_internal — kan geen '
                'base_dn afleiden.') % self.scope_org_id.name)

        ldap_service = self.env['myschool.ldap.service']
        ldap_service._check_ldap3_available()

        index = self._build_db_index()

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

        # On rescan: wipe ONLY rows the admin never touched. Anything past
        # `discovered` represents human decisions or in-flight work and
        # must survive the rescan.
        wipe_states = ('discovered',)
        self.finding_ids.filtered(
            lambda r: r.state in wipe_states).unlink()

        existing_by_extid = {
            (f.source, self._norm_dn(f.external_id or f.ad_dn)): f
            for f in self.finding_ids
        }

        Finding = self.env['myschool.ad.takeover.finding']
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

        if new_findings:
            Finding.create(new_findings)

        summary = (
            f'OUs: {ou_total} gevonden — {ou_match} al gelinkt, '
            f'{ou_total - ou_match} nieuw.\n'
            f'Groups: {gr_total} gevonden — {gr_match} al gelinkt, '
            f'{gr_total - gr_match} nieuw.\n'
            f'Users: {us_total} gevonden — {us_match} al gelinkt, '
            f'{us_stamp} STAMP_ID, {us_orphan} orphan, '
            f'{us_conflict} identity-conflict.'
        )
        self.write({
            'state': 'discovered' if self.state == 'draft' else 'in_progress',
            'last_scan_at': fields.Datetime.now(),
            'scan_summary': summary,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AD-scan voltooid'),
                'message': summary,
                'type': 'success',
                'sticky': True,
            },
        }

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
        # session's scope-org. SCHOOL scope: direct match on
        # current_school_id. SCHOOLBOARD scope: every SCHOOL whose
        # name_tree starts with the schoolboard's name_tree counts.
        scope_school_ids = [scope.id]
        if (scope.org_type_id and scope.org_type_id.name == 'SCHOOLBOARD'
                and scope.name_tree):
            children = self.env['myschool.org'].search([
                ('name_tree', '=ilike', f'{scope.name_tree}.%'),
                ('org_type_id.name', '=', 'SCHOOL'),
            ])
            scope_school_ids = children.ids or scope_school_ids
        persons_in_scope = Person.search([
            ('current_school_id', 'in', scope_school_ids),
        ])
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

        return {
            'scope_name': scope.name_tree or scope.name,
            'only_employees': only_employees,
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
            f'</p>')

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
        for org in Org.search([]):
            if org.ou_fqdn_internal:
                ou_dn_to_org[self._norm_dn(org.ou_fqdn_internal)] = org.id
            for f in ('com_group_fqdn_internal', 'sec_group_fqdn_internal'):
                v = self._norm_dn(getattr(org, f, '') or '')
                if v:
                    group_dn_to_org[v] = org.id

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
            'ou_dn_to_org':         ou_dn_to_org,
            'group_dn_to_org':      group_dn_to_org,
            'user_dn_to_person':    user_dn_to_person,
            'user_mail_to_person':  user_mail_to_person,
            'user_sam_to_login':    user_sam_to_login,
            'sap_ref_to_person':    sap_ref_to_person,
            'login_to_person':      login_to_person,
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
        tracking=True,
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
                elif pk == 'delete_after':
                    rec._apply_delete_after()
                elif pk == 'ignore':
                    raise UserError(_(
                        'Voorstel-type "negeer" — niets te doen op "%s".'
                    ) % rec.ad_dn)
                elif pk in ('rename', 'move', 'membership_add'):
                    raise UserError(_(
                        'Voorstel-type "%s" is gepland voor Fase C en nog '
                        'niet uitvoerbaar.') % pk)
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
            'automatic_sync': False,  # manueel beheerd, geen Informat-overrules
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

    def _apply_stamp_id(self):
        """Write the matched person's sap_ref into the AD user's
        ``employeeID`` attribute.

        Pure attribute write — no DN change, no group-membership
        change, no password touch. The safest mutation in the system:
        AD-users that miss employeeID get their identity-key filled in
        so subsequent scans match them deterministically.
        """
        self.ensure_one()
        if self.source != 'ad':
            raise UserError(_(
                'STAMP_ID is in Fase A alleen geïmplementeerd voor AD.'))
        if self.kind != 'user':
            raise UserError(_(
                'STAMP_ID werkt alleen op user-findings (kind=%s).'
            ) % self.kind)
        try:
            payload = json.loads(self.proposal_payload_json or '{}')
        except (ValueError, TypeError):
            payload = {}
        attr  = payload.get('target_attribute', 'employeeID')
        value = payload.get('value')
        if attr != 'employeeID' or not value:
            raise UserError(_(
                'Ongeldige STAMP_ID-payload op "%s".') % self.ad_dn)

        # Import lazily so the module loads even when ldap3 is missing
        # (the scan itself would have already failed earlier).
        from ldap3 import MODIFY_REPLACE
        ldap = self.env['myschool.ldap.service']
        config = self.session_id.ldap_config_id
        with ldap._get_connection(config) as conn:
            conn.modify(self.ad_dn,
                        {'employeeID': [(MODIFY_REPLACE, [str(value)])]})
            result = conn.result or {}
            if result.get('result') != 0:
                raise UserError(_(
                    'LDAP MODIFY mislukt voor %(dn)s: %(err)s') % {
                        'dn': self.ad_dn,
                        'err': result.get('description') or result,
                    })

        # Mirror into DB: link person.person_fqdn_internal when empty, so
        # the next rescan matches on the strongest key.
        person = self.matched_person_id
        if person and not person.person_fqdn_internal:
            service = self.env['myschool.manual.task.service']
            service.create_manual_task('PERSON', 'UPD', {
                'person_id': person.id,
                'vals': {'person_fqdn_internal': self.ad_dn},
            })

        self._mark_done(action_message=_(
            'employeeID=%s naar AD geschreven (geen andere wijzigingen).'
        ) % value)

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
