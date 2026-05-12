# -*- coding: utf-8 -*-
"""Wizard to bulk-rename internal/external domains across a SCHOOL or
SCHOOLBOARD scope.

Two-step UX:
  1. Preview — collects the affected records (orgs, persons, com-groups,
     users) without writing.
  2. Commit — fires a single ``MANUAL/DOMAIN/RENAME`` betask whose
     handler does all DB writes + queues LDAP/USER/UPD and
     LDAP/GROUP/UPD per affected record.

Architectural note: per CLAUDE.md, all org/person mutations must go
through the betask pipeline. Because this rename touches many records
in one logical operation, we use **one** bulk MANUAL betask rather
than per-record MANUAL/ORG/UPD + MANUAL/PERSON/UPD tasks. The handler
itself respects the audit-trail bypass via ``skip_manual_audit``.
"""

import json
import re

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class DomainRenameWizard(models.TransientModel):
    _name = 'myschool.domain.rename.wizard'
    _description = 'Bulk rename internal/external domains'

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    scope_org_id = fields.Many2one(
        'myschool.org',
        string='Scope (SCHOOL of SCHOOLBOARD)',
        required=True,
        domain="[('org_type_id.name', 'in', ['SCHOOL', 'SCHOOLBOARD'])]",
        help='Wijziging wordt toegepast op deze org en al haar '
             'descendants via ORG-TREE. Kies een SCHOOLBOARD voor een '
             'koepelbrede rename, of een SCHOOL voor één enkele school.',
    )

    scope_kind = fields.Char(
        compute='_compute_scope_kind', readonly=True, string='Type')

    @api.depends('scope_org_id')
    def _compute_scope_kind(self):
        for rec in self:
            ot = rec.scope_org_id.org_type_id
            rec.scope_kind = (ot.name if ot else '') or ''

    # ------------------------------------------------------------------
    # Old/new domain values
    # ------------------------------------------------------------------

    old_domain_internal = fields.Char(
        compute='_compute_old_domains', readonly=True,
        string='Huidig intern domein')
    old_domain_external = fields.Char(
        compute='_compute_old_domains', readonly=True,
        string='Huidig extern domein')
    new_domain_internal = fields.Char(
        string='Nieuw intern domein',
        help='Laat leeg om het interne domein ongewijzigd te laten.')
    new_domain_external = fields.Char(
        string='Nieuw extern domein',
        help='Laat leeg om het externe domein ongewijzigd te laten.')

    @api.depends('scope_org_id')
    def _compute_old_domains(self):
        for rec in self:
            rec.old_domain_internal = rec.scope_org_id.domain_internal or ''
            rec.old_domain_external = rec.scope_org_id.domain_external or ''

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    state = fields.Selection(
        [('draft', 'Draft'), ('preview', 'Preview'), ('committed', 'Committed')],
        default='draft', required=True)

    preview_text = fields.Text(string='Preview', readonly=True)
    org_count = fields.Integer(string='Orgs in scope', readonly=True)
    person_count = fields.Integer(string='Personen', readonly=True)
    comgroup_count = fields.Integer(string='Com-groepen (mail)', readonly=True)
    secgroup_count = fields.Integer(string='Sec-groepen', readonly=True)
    odoo_user_count = fields.Integer(string='Odoo-users (login)', readonly=True)

    # ---- Post-rename patch: rewrite pending task payloads ----
    patch_old_email_domain = fields.Char(
        string='Patch — oud email-domein',
        help='Bv. "olvp.be" — wordt overal in pending task data '
             'vervangen door het nieuwe email-domein.')
    patch_new_email_domain = fields.Char(
        string='Patch — nieuw email-domein',
        help='Bv. "olvpedu.be"')

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @api.constrains('new_domain_internal', 'new_domain_external')
    def _check_at_least_one_change(self):
        for rec in self:
            if rec.state == 'draft':
                continue  # only enforce when committing/previewing
            if not rec.new_domain_internal and not rec.new_domain_external:
                raise ValidationError(_(
                    'Voer minstens één van "nieuw intern" of "nieuw extern" '
                    'domein in.'))

    @staticmethod
    def _normalize_domain(value):
        return (value or '').strip().lower().lstrip('.').rstrip('.')

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------

    def _resolve_scope_orgs(self):
        """Return a recordset with the scope_org and all its ORG-TREE
        descendants, regardless of org_type. Uses an iterative BFS to
        avoid recursion limits on deep trees."""
        self.ensure_one()
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)

        result_ids = {self.scope_org_id.id}
        if not org_tree_type:
            return Org.browse(list(result_ids))

        frontier = {self.scope_org_id.id}
        while frontier:
            children = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', list(frontier)),
                ('is_active', '=', True),
            ])
            child_ids = set()
            for rel in children:
                if rel.id_org and rel.id_org.id not in result_ids:
                    child_ids.add(rel.id_org.id)
                if rel.id_org_child and rel.id_org_child.id not in result_ids:
                    child_ids.add(rel.id_org_child.id)
            child_ids -= result_ids
            result_ids.update(child_ids)
            frontier = child_ids
        return Org.browse(list(result_ids))

    def _resolve_persons_in_scope(self, scope_orgs):
        """Persons reachable via active PERSON-TREE in any scope org."""
        self.ensure_one()
        if not scope_orgs:
            return self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pt_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return self.env['myschool.person']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_org', 'in', scope_orgs.ids),
            ('is_active', '=', True),
            ('id_person', '!=', False),
        ])
        return rels.mapped('id_person')

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        new_int = self._normalize_domain(self.new_domain_internal)
        new_ext = self._normalize_domain(self.new_domain_external)
        old_int = self._normalize_domain(self.old_domain_internal)
        old_ext = self._normalize_domain(self.old_domain_external)

        if not new_int and not new_ext:
            raise UserError(_(
                'Voer minstens één van "nieuw intern" of "nieuw extern" '
                'domein in.'))
        if new_int and new_int == old_int:
            new_int = ''  # no-op
        if new_ext and new_ext == old_ext:
            new_ext = ''
        if not new_int and not new_ext:
            raise UserError(_('De ingevoerde domeinen zijn gelijk aan de huidige.'))

        scope_orgs = self._resolve_scope_orgs()
        persons = self._resolve_persons_in_scope(scope_orgs)
        comgroups = scope_orgs.filtered(
            lambda o: o.has_comgroup and o.com_group_email)
        secgroups = scope_orgs.filtered(lambda o: o.has_secgroup)

        odoo_user_count = 0
        if new_ext and old_ext:
            odoo_user_count = self.env['res.users'].sudo().search_count(
                [('login', '=ilike', f'%@{old_ext}')])

        lines = [
            f'Scope: {self.scope_kind} "{self.scope_org_id.name}" '
            f'(id={self.scope_org_id.id})',
            f'Orgs in scope (incl. descendants): {len(scope_orgs)}',
            f'Personen via PERSON-TREE: {len(persons)}',
            f'Com-groepen (met e-mail): {len(comgroups)}',
            f'Sec-groepen: {len(secgroups)}',
            f'Odoo-users (login eindigt op @{old_ext}): {odoo_user_count}'
            if new_ext else 'Odoo-users: niet gewijzigd (geen nieuw extern domein)',
            '',
            f'Intern: {old_int or "-"} → {new_int or "(ongewijzigd)"}',
            f'Extern: {old_ext or "-"} → {new_ext or "(ongewijzigd)"}',
        ]

        self.write({
            'state': 'preview',
            'preview_text': '\n'.join(lines),
            'org_count': len(scope_orgs),
            'person_count': len(persons),
            'comgroup_count': len(comgroups),
            'secgroup_count': len(secgroups),
            'odoo_user_count': odoo_user_count,
        })
        return self._reopen()

    def action_commit(self):
        """Create a single MANUAL/DOMAIN/RENAME bulk betask. The handler
        in manual_task_processor does all writes + queues LDAP UPDs."""
        self.ensure_one()
        if self.state != 'preview':
            raise UserError(_('Voer eerst Preview uit voor commit.'))

        new_int = self._normalize_domain(self.new_domain_internal)
        new_ext = self._normalize_domain(self.new_domain_external)
        old_int = self._normalize_domain(self.old_domain_internal)
        old_ext = self._normalize_domain(self.old_domain_external)
        if new_int == old_int:
            new_int = ''
        if new_ext == old_ext:
            new_ext = ''

        data = {
            'scope_org_id': self.scope_org_id.id,
            'old_domain_internal': old_int,
            'new_domain_internal': new_int or None,
            'old_domain_external': old_ext,
            'new_domain_external': new_ext or None,
        }
        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('DOMAIN', 'RENAME', data)
        self.write({'state': 'committed'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Domeinrename uitgevoerd'),
                'message': _(
                    'Bulk-betask %(name)s — status %(status)s. Bekijk '
                    'Operations → Backend Tasks voor details en eventuele '
                    'LDAP UPD-cascades.'
                ) % {'name': task.name, 'status': task.status},
                'type': 'success' if task.status == 'completed_ok' else 'warning',
                'sticky': True,
            },
        }

    def action_reemit_cascade(self):
        """Re-queue the LDAP cascade (USER/UPD + GROUP/UPD) for the
        current scope **without** touching DB strings.

        Used when the DB rename succeeded but the cascade tasks errored
        out (e.g. a payload-format bug) — admin deletes the failed
        tasks and clicks this to regenerate them with the current
        (correct) field values.
        """
        self.ensure_one()
        if not self.scope_org_id:
            raise UserError(_('Kies eerst een scope.'))

        scope_orgs = self._resolve_scope_orgs()
        persons = self._resolve_persons_in_scope(scope_orgs)
        affected_comgroup_orgs = scope_orgs.filtered(
            lambda o: o.has_comgroup and o.com_group_email)

        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']
        user_upd = BeTaskType.search([
            ('target', '=', 'LDAP'), ('object', '=', 'USER'),
            ('action', '=', 'UPD')], limit=1)
        group_upd = BeTaskType.search([
            ('target', '=', 'LDAP'), ('object', '=', 'GROUP'),
            ('action', '=', 'UPD')], limit=1)
        if not user_upd or not group_upd:
            raise UserError(_(
                'LDAP/USER/UPD of LDAP/GROUP/UPD betask type ontbreekt.'))

        # person → first active PERSON-TREE org (mirrors the rename handler)
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pt_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        person_to_org = {}
        if pt_type:
            for rel in PropRelation.search([
                ('proprelation_type_id', '=', pt_type.id),
                ('id_org', 'in', scope_orgs.ids),
                ('is_active', '=', True),
                ('id_person', '!=', False),
            ]):
                if rel.id_person.id not in person_to_org:
                    person_to_org[rel.id_person.id] = rel.id_org

        user_count = 0
        for person in persons:
            target_org = person_to_org.get(person.id)
            BeTask.create({
                'name': f'LDAP/USER/UPD {person.name}',
                'betasktype_id': user_upd.id,
                'status': 'new',
                'data': json.dumps({
                    'person_id': person.id,
                    'org_id': target_org.id if target_org else None,
                }),
            })
            user_count += 1

        group_count = 0
        for org in affected_comgroup_orgs:
            group_dn = (org.com_group_fqdn_internal or '').strip()
            if not group_dn:
                continue
            BeTask.create({
                'name': f'LDAP/GROUP/UPD COM {org.name}',
                'betasktype_id': group_upd.id,
                'status': 'new',
                'data': json.dumps({
                    'org_id': org.id,
                    'group_dn': group_dn,
                    'changes': {'mail': org.com_group_email or ''},
                }),
            })
            group_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cascade heruitgestuurd'),
                'message': _(
                    'LDAP/USER/UPD: %(u)s — LDAP/GROUP/UPD (COM): %(g)s. '
                    'Run "Verwerk alle wachtende taken" om ze af te werken.'
                ) % {'u': user_count, 'g': group_count},
                'type': 'success', 'sticky': True,
            },
        }

    def action_patch_pending_task_emails(self):
        """Find every pending betask (status in ``new``/``error``) whose
        JSON ``data`` field contains ``@<old>`` and rewrite it to
        ``@<new>``. Resets ``error`` rows back to ``new`` so they're
        re-tried on the next ``process_all_pending`` run.

        Use this after a domain rename when pre-existing tasks have
        stale email values baked into their JSON (typically
        ``CLOUD/GROUP/ADD`` with ``group_email``, ``CLOUD/GROUPMEMBER/ADD``
        with ``group_email``/``member_email``).
        """
        self.ensure_one()
        old = self._normalize_domain(self.patch_old_email_domain)
        new = self._normalize_domain(self.patch_new_email_domain)
        if not old or not new:
            raise UserError(_(
                'Vul zowel het oude als nieuwe email-domein in.'))
        if old == new:
            raise UserError(_('Oud en nieuw zijn gelijk.'))

        suffix_old = f'@{old}'
        suffix_new = f'@{new}'

        BeTask = self.env['myschool.betask']
        tasks = BeTask.search([
            ('status', 'in', ('new', 'error')),
            ('data', 'ilike', suffix_old),
        ])
        patched = 0
        reset = 0
        for task in tasks:
            payload = task.data or ''
            if suffix_old.lower() not in payload.lower():
                continue
            # Case-insensitive replace of the @<old> suffix wherever
            # it appears. We deliberately don't try to parse the JSON
            # — surgical string replace is safe because @<domain> is
            # unlikely to appear as a non-email substring.
            import re as _re
            new_payload = _re.sub(
                _re.escape(suffix_old), suffix_new, payload,
                flags=_re.IGNORECASE)
            if new_payload == payload:
                continue
            vals = {'data': new_payload}
            if task.status == 'error':
                vals.update({
                    'status': 'new',
                    'processing_start': False,
                    'processing_end': False,
                    'error_description': False,
                    'retry_count': 0,
                })
                reset += 1
            task.write(vals)
            patched += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Task payloads gepatched'),
                'message': _(
                    '%(p)s task(s) gepatched, waarvan %(r)s gereset van '
                    'error → new. Run "Verwerk alle wachtende taken" om '
                    'ze af te werken.'
                ) % {'p': patched, 'r': reset},
                'type': 'success' if patched else 'info',
                'sticky': True,
            },
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
