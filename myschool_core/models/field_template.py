# -*- coding: utf-8 -*-
"""
Field Template
==============

Configurable templates for computed person-fields (`cn`, `email_cloud`, …).

A FieldTemplate ties a small expression language to a concrete person-field
and a scope (one or more schools, optionally narrowed to one or more
person types). When the system needs the value of a templatable field
for a given person+org pair, it asks `find_for(field, person, org)` to
return the highest-priority active template that matches and evaluates
its expression.

Expression language
-------------------

Tokens separated by ``&`` (concatenation):

- ``'literal'``                — literal text (single-quoted)
- ``<field>``                  — value of ``person.<field>``
- ``<org.field>``              — value of ``org.<field>`` (the leaf org)
- ``<school.field>``           — value of the parent school's ``<field>``
- ``<field>+N`` / ``<field>-N``— integer arithmetic on the field value
- ``<field>:<filter>``         — string filter, applied left-to-right
                                 chainable: ``<first_name>:slug:trunc(20)``

Available filters:
- ``lower``       — lowercase
- ``upper``       — uppercase
- ``slug``        — strip diacritics, lowercase, drop spaces
- ``nodiacritics``— strip diacritics only
- ``trunc(N)``    — first N characters
- ``last(C)``     — last segment after splitting on ``C`` (default ``.``)

Examples
--------
- ``'t'&<sap_ref>+1631``                       → ``t1700`` (sap_ref=69)
- ``<first_name>:slug&'.'&<name>:slug``        → ``mark.demeyer``
- ``<first_name>:slug&'.'&<name>:slug&'@'&<school.domain_external>``
                                              → ``mark.demeyer@olvp.be``
"""

import logging
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FieldTemplate(models.Model):
    _name = 'myschool.field.template'
    _description = 'Field Template'
    _order = 'field_name, priority, id'

    name = fields.Char(string='Name', required=True,
                       help='Free description (e.g. "CN basisschool studenten")')

    # Currently supported templatable fields. Extend the selection (and
    # the corresponding caller in ldap_service / betask_processor) when
    # adding more.
    field_name = fields.Selection([
        ('cn', 'cn (account name)'),
        ('email_cloud', 'email_cloud'),
        ('last_name', 'last_name'),
        ('com_group_email', 'com_group_email'),
    ], string='Field', required=True)

    template = fields.Char(string='Template', required=True,
                           help='Expression — see model docstring for syntax')

    org_ids = fields.Many2many(
        'myschool.org', 'field_template_org_rel', 'template_id', 'org_id',
        string='Schools',
        help='Schools this template applies to. Empty = applies to all schools.')

    person_type_ids = fields.Many2many(
        'myschool.person.type', 'field_template_person_type_rel',
        'template_id', 'person_type_id',
        string='Person types',
        help='Restrict to these person types. Empty = all types.')

    priority = fields.Integer(string='Priority', default=10,
                              help='Lower number = higher priority. The first '
                                   'matching template wins.')

    active = fields.Boolean(default=True)

    note = fields.Text(string='Notes')

    # --- Preview ---
    preview_person_id = fields.Many2one(
        'myschool.person', string='Preview person',
        help='Pick a person to preview the template output.')
    preview_org_id = fields.Many2one(
        'myschool.org', string='Preview org',
        help='Pick the leaf-org used as <org.*> context for the preview.')
    preview_output = fields.Char(
        string='Preview result', compute='_compute_preview_output')

    available_fields_html = fields.Html(
        string='Available fields',
        compute='_compute_available_fields_html',
        sanitize=False)

    @api.depends('template', 'preview_person_id', 'preview_org_id', 'field_name')
    def _compute_preview_output(self):
        for rec in self:
            if not rec.template:
                rec.preview_output = ''
                continue
            # Person is optional for org-level fields (e.g. com_group_email).
            person = rec.preview_person_id or self.env['myschool.person']
            org = rec.preview_org_id or self.env['myschool.org']
            try:
                rec.preview_output = rec.evaluate(person or None, org or None)
            except Exception as e:
                rec.preview_output = f'<error: {e}>'

    # Field-types that are useless or unsafe to surface in the picker.
    _AVAILABLE_FIELDS_SKIP_TYPES = {'binary', 'json'}
    # Field-names common to every model that we never want to advertise.
    _AVAILABLE_FIELDS_SKIP_NAMES = {
        'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
        'display_name', '__last_update',
        'message_ids', 'message_follower_ids', 'message_partner_ids',
        'message_attachment_count', 'message_main_attachment_id',
        'message_has_error', 'message_has_error_counter',
        'message_needaction', 'message_needaction_counter',
        'message_has_sms_error', 'message_is_follower',
        'website_message_ids', 'has_message', 'rating_ids',
        'activity_ids', 'activity_state', 'activity_user_id',
        'activity_type_id', 'activity_type_icon', 'activity_date_deadline',
        'my_activity_date_deadline', 'activity_summary', 'activity_exception_decoration',
        'activity_exception_icon', 'activity_calendar_event_id',
    }

    def _compute_available_fields_html(self):
        """Render a 3-column table (person / org / school) listing the
        fields that can be referenced from a template."""
        person_rows = self._collect_field_rows('myschool.person')
        org_rows = self._collect_field_rows('myschool.org')
        # School = same model as Org (myschool.org), but referenced via
        # the <school.*> head — show the same list with a hint.
        school_rows = org_rows

        def render_section(title, prefix, rows):
            if not rows:
                return ''
            items = ''.join(
                f'<tr><td><code>&lt;{prefix}{name}&gt;</code></td>'
                f'<td>{label}</td><td><small class="text-muted">{ftype}</small></td></tr>'
                for name, label, ftype in rows)
            return (
                f'<div class="col-md-4">'
                f'<h6 class="mt-2">{title}</h6>'
                f'<table class="table table-sm table-borderless mb-0">'
                f'<tbody>{items}</tbody></table></div>')

        html = (
            '<div class="row">'
            + render_section('Person fields', '', person_rows)
            + render_section('Org fields (leaf)', 'org.', org_rows)
            + render_section('School fields (parent SCHOOL)', 'school.', school_rows)
            + '</div>'
            '<p class="text-muted mb-0 mt-2"><small>'
            'Bare names (e.g. <code>&lt;first_name&gt;</code>) read off the person. '
            'Use <code>&lt;org.*&gt;</code> for the leaf-org and '
            '<code>&lt;school.*&gt;</code> for the parent SCHOOL org. '
            'Append filters with <code>:</code> — e.g. '
            '<code>&lt;first_name&gt;:slug:trunc(20)</code>.'
            '</small></p>'
        )
        for rec in self:
            rec.available_fields_html = html

    def _collect_field_rows(self, model_name):
        """Return [(name, label, type)] for the user-relevant fields on
        `model_name`, sorted by name."""
        Model = self.env.get(model_name)
        if Model is None:
            return []
        rows = []
        for name, fld in Model._fields.items():
            if name.startswith('_'):
                continue
            if name in self._AVAILABLE_FIELDS_SKIP_NAMES:
                continue
            if fld.type in self._AVAILABLE_FIELDS_SKIP_TYPES:
                continue
            label = (fld.string or name).replace('<', '&lt;').replace('>', '&gt;')
            rows.append((name, label, fld.type))
        rows.sort(key=lambda r: r[0])
        return rows

    # =========================================================================
    # Public API
    # =========================================================================

    @api.model
    def find_for(self, field_name, person, org):
        """Return the highest-priority active template that matches the
        given (field, person, org). None if no template applies.

        Matching rules:
        - field_name must equal field
        - org_ids: either empty, OR contain the parent SCHOOL of `org`
        - person_type_ids: either empty, OR contain the person's type;
          person-less calls (``person=None``, e.g. for org-level fields
          like ``com_group_email``) skip this filter.

        Ranking — at equal ``priority`` the **more specific** template
        wins. Specificity = +2 when the template explicitly lists the
        resolved school in ``org_ids`` (vs. a catch-all empty list),
        +1 when it explicitly lists the person's type in
        ``person_type_ids``. So a school+type-specific template beats a
        catch-all even when both are saved at the default priority.
        Without this rank a generic ``firstname.lastname``-style
        template registered first would silently apply to schools that
        actually have their own (e.g. anonymised) naming convention.

        DEBUG logging: enable ``[FIELD-TEMPLATE]`` lines (logger
        ``odoo.addons.myschool_core.models.field_template``) at INFO
        level to trace each candidate's accept/reject reason. Useful
        when a template "should" match but doesn't.
        """
        if not field_name:
            return None
        school = self._resolve_school(org)
        raw_candidates = self.search([
            ('field_name', '=', field_name),
            ('active', '=', True),
        ])

        ptype = person.person_type_id if person else None

        def _specificity(tpl):
            s = 0
            if tpl.org_ids and school and school in tpl.org_ids:
                s += 2
            if tpl.person_type_ids and ptype and ptype in tpl.person_type_ids:
                s += 1
            return s

        # Stable-sort: priority asc → specificity desc → id asc. The
        # underlying search already ordered by (field_name, priority, id);
        # re-sort here so the within-priority order honours specificity.
        candidates = sorted(
            raw_candidates,
            key=lambda t: (t.priority, -_specificity(t), t.id))
        org_name = org.display_name if org else '(no org)'
        school_name = school.display_name if school else '(school not resolved)'
        ptype_name = (person.person_type_id.display_name
                      if person and person.person_type_id else '(no type)')
        _logger.info(
            '[FIELD-TEMPLATE] find_for(field=%s) — org=%s school=%s '
            'person=%s type=%s — %d candidate(s)',
            field_name, org_name, school_name,
            getattr(person, 'name', '(no person)'), ptype_name,
            len(candidates))
        for tpl in candidates:
            if tpl.org_ids:
                if not school:
                    _logger.info(
                        '[FIELD-TEMPLATE]  ✗ %s: school not resolved; '
                        'template restricted to %s',
                        tpl.name, [o.name_short or o.name for o in tpl.org_ids])
                    continue
                if school not in tpl.org_ids:
                    _logger.info(
                        '[FIELD-TEMPLATE]  ✗ %s: school %s not in template '
                        'scope %s',
                        tpl.name, school.name_short or school.name,
                        [o.name_short or o.name for o in tpl.org_ids])
                    continue
            if tpl.person_type_ids:
                if not person:
                    _logger.info(
                        '[FIELD-TEMPLATE]  ✗ %s: no person supplied, '
                        'template restricted to types %s',
                        tpl.name, [t.name for t in tpl.person_type_ids])
                    continue
                ptype = person.person_type_id
                if not ptype:
                    _logger.info(
                        '[FIELD-TEMPLATE]  ✗ %s: person has no '
                        'person_type_id; template restricted to %s',
                        tpl.name, [t.name for t in tpl.person_type_ids])
                    continue
                if ptype not in tpl.person_type_ids:
                    _logger.info(
                        '[FIELD-TEMPLATE]  ✗ %s: person_type %s not in '
                        'template scope %s',
                        tpl.name, ptype.name,
                        [t.name for t in tpl.person_type_ids])
                    continue
            _logger.info(
                '[FIELD-TEMPLATE]  ✓ %s matched (priority=%s, template=%r)',
                tpl.name, tpl.priority, tpl.template)
            return tpl
        _logger.info(
            '[FIELD-TEMPLATE] no match for field=%s — falling back '
            'to caller default', field_name)
        return None

    def action_apply_to_persons(self):
        """Re-run ``betask_processor._populate_person_account_fields``
        for every person whose PERSON-TREE org falls under this
        template's school scope and whose person_type matches.

        Writes the freshly-computed ``email_cloud``,
        ``person_fqdn_internal`` and ``person_fqdn_external`` to each
        person record. Idempotent: ``_populate_person_account_fields``
        only writes when the computed value differs from the stored
        one. Does NOT cascade to LDAP/Workspace — admin can run
        Operations → Backend Tasks afterwards if they want AD/Google
        to follow.

        Scope:
          - schools: ``org_ids`` (empty = every non-admin SCHOOL)
          - person types: ``person_type_ids`` (empty = every type)
        """
        self.ensure_one()
        Person = self.env['myschool.person']
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        processor = self.env['myschool.betask.processor']

        # 1. Resolve target schools.
        if self.org_ids:
            target_schools = self.org_ids
        else:
            target_schools = Org.search([
                ('org_type_id.name', '=', 'SCHOOL'),
                ('is_administrative', '=', False),
            ])
        if not target_schools:
            return self._notify(_('Geen scholen gevonden in de scope.'), 'warning')

        # 2. Collect every descendant org under those schools — that's
        #    where PERSON-TREE rows live (leaf orgs / classes etc.).
        all_org_ids = set()
        for school in target_schools:
            if hasattr(processor, '_collect_org_descendant_ids'):
                all_org_ids.update(
                    processor._collect_org_descendant_ids(school))
            else:
                all_org_ids.add(school.id)

        # 3. Find active PERSON-TREE rows in scope.
        pt_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return self._notify(_('PERSON-TREE type ontbreekt.'), 'warning')
        pt_rels = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_org', 'in', list(all_org_ids)),
            ('is_active', '=', True),
            ('id_person', '!=', False),
        ])

        # 4. Dedupe by person — keep the first (= active) PERSON-TREE org.
        person_to_org = {}
        for rel in pt_rels:
            if rel.id_person.id in person_to_org:
                continue
            if self.person_type_ids:
                if not rel.id_person.person_type_id \
                        or rel.id_person.person_type_id not in self.person_type_ids:
                    continue
            person_to_org[rel.id_person.id] = rel.id_org

        # 5. Run the populate helper for each, count outcomes.
        updated = 0
        unchanged = 0
        failed = 0
        for person_id, target_org in person_to_org.items():
            person = Person.browse(person_id).exists()
            if not person:
                continue
            before = (
                person.email_cloud or '',
                person.person_fqdn_internal or '',
                person.person_fqdn_external or '',
            )
            try:
                processor._populate_person_account_fields(person, target_org)
            except Exception as e:
                _logger.warning(
                    '[FIELD-TEMPLATE] apply failed for %s: %s',
                    person.name, e)
                failed += 1
                continue
            after = (
                person.email_cloud or '',
                person.person_fqdn_internal or '',
                person.person_fqdn_external or '',
            )
            if before == after:
                unchanged += 1
            else:
                updated += 1

        parts = [_('%(u)s gewijzigd') % {'u': updated}]
        if unchanged:
            parts.append(_('%(c)s onveranderd') % {'c': unchanged})
        if failed:
            parts.append(_('%(f)s fout(en)') % {'f': failed})
        msg = _('Persons in scope: %(t)s. %(d)s') % {
            't': len(person_to_org), 'd': ', '.join(parts)}
        return self._notify(msg, 'success' if not failed else 'warning')

    def _notify(self, message, msg_type):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Template %s') % self.name,
                'message': message,
                'type': msg_type,
                'sticky': True,
            },
        }

    def evaluate(self, person, org=None, _seen=None):
        """Evaluate this template against a person + (leaf) org. Returns
        the resulting string. Raises ValidationError on parse errors.

        Supports recursive references to other templatable fields: a
        bare ``<cn>`` inside an ``email_cloud`` template re-runs
        ``find_for('cn', …)``. ``_seen`` is the cycle-guard.
        """
        self.ensure_one()
        if not self.template:
            return ''
        seen = (_seen or frozenset()) | {self.field_name}
        return self._evaluate_expression(self.template, person, org, seen)

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains('template')
    def _check_template_parses(self):
        for rec in self:
            try:
                # Dry-run parse using a dummy person to detect glaring issues.
                rec._tokenize(rec.template)
            except Exception as e:
                raise ValidationError(
                    f'Template invalid: {e}\nValue: {rec.template!r}')

    # =========================================================================
    # Evaluation engine
    # =========================================================================

    @staticmethod
    def _resolve_school(org):
        """Walk up ORG-TREE from `org` to find the first non-admin SCHOOL."""
        if not org:
            return None
        # Re-use existing helper from betask_processor when present.
        env = org.env
        processor = env.get('myschool.betask.processor')
        if processor is not None and hasattr(processor, '_resolve_parent_school_from_org'):
            try:
                return processor._resolve_parent_school_from_org(org)
            except Exception:
                pass
        return None

    @classmethod
    def _tokenize(cls, template):
        """Split the template into segments separated by &, returning a
        list of (kind, payload) tuples. Used both at parse time (for the
        constraint) and at eval time."""
        tokens = []
        for raw in (template or '').split('&'):
            part = raw.strip()
            if not part:
                continue
            # Literal: 'xxx'
            m = re.match(r"^'([^']*)'$", part)
            if m:
                tokens.append(('literal', m.group(1)))
                continue
            # <field> [+/-N] [:filter[:filter…]]
            m = re.match(
                r'^<([\w.]+)>\s*'
                r'(?:([+-])\s*(\d+))?'
                r'((?::[\w]+(?:\(\w+\))?)*)\s*$',
                part)
            if m:
                field_path = m.group(1)
                op = m.group(2)
                num = int(m.group(3)) if m.group(3) else None
                filter_chain = m.group(4) or ''
                filters = [f for f in filter_chain.split(':') if f]
                tokens.append(('field', {
                    'path': field_path,
                    'op': op,
                    'num': num,
                    'filters': filters,
                }))
                continue
            raise ValueError(f'unrecognised segment: {part!r}')
        return tokens

    def _evaluate_expression(self, template, person, org, seen):
        out_parts = []
        for kind, payload in self._tokenize(template):
            if kind == 'literal':
                out_parts.append(payload)
            elif kind == 'field':
                value = self._resolve_field(payload['path'], person, org, seen)
                if payload['op'] and payload['num'] is not None:
                    try:
                        value = int(str(value).strip())
                        value = (value + payload['num']
                                 if payload['op'] == '+' else value - payload['num'])
                    except (ValueError, TypeError):
                        _logger.warning(
                            '[FIELD-TEMPLATE] %s is not numeric, skipping arithmetic',
                            payload['path'])
                value = '' if value is None else str(value)
                for f in payload['filters']:
                    value = self._apply_filter(value, f)
                out_parts.append(value)
        return ''.join(out_parts)

    def _resolve_field(self, path, person, org, seen):
        """Resolve <field>, <org.field>, <school.field> against the person
        and (leaf-)org context. Bare names that map to a templatable
        field_name (cn, email_cloud, …) recurse via ``find_for``."""
        if '.' in path:
            head, tail = path.split('.', 1)
            head = head.lower()
            if head == 'org':
                return getattr(org, tail, '') if org else ''
            if head == 'school':
                school = self._resolve_school(org)
                return getattr(school, tail, '') if school else ''
            if head == 'person':
                return getattr(person, tail, '') if person else ''
            return ''
        # Bare field — prefer a real attribute on the person; otherwise,
        # if the name matches a templatable field_name, evaluate that
        # template recursively (with cycle guard via `seen`).
        if person and path in person._fields:
            return getattr(person, path, '')
        templatable = {opt[0] for opt in self._fields['field_name'].selection}
        if path in templatable and path not in seen:
            tpl = self.env['myschool.field.template'].find_for(path, person, org)
            if tpl:
                return tpl.evaluate(person, org, _seen=seen)
        return getattr(person, path, '') if person else ''

    @staticmethod
    def _apply_filter(value, fname):
        """Apply a string filter to a value. Unknown filters are ignored."""
        s = '' if value is None else str(value)
        # Accept "trunc(5)" with embedded argument.
        m = re.match(r'^(\w+)(?:\((\w+)\))?$', fname)
        if not m:
            return s
        name = m.group(1).lower()
        arg = m.group(2)
        if name == 'lower':
            return s.lower()
        if name == 'upper':
            return s.upper()
        if name == 'nodiacritics':
            normalized = unicodedata.normalize('NFKD', s)
            return ''.join(c for c in normalized if not unicodedata.combining(c))
        if name == 'slug':
            normalized = unicodedata.normalize('NFKD', s)
            ascii_only = ''.join(c for c in normalized if not unicodedata.combining(c))
            return ascii_only.replace(' ', '').lower()
        if name == 'trunc':
            try:
                n = int(arg) if arg else 0
                return s[:n] if n > 0 else s
            except ValueError:
                return s
        if name == 'last':
            sep = arg if arg else '.'
            return s.rstrip(sep).split(sep)[-1]
        _logger.warning('[FIELD-TEMPLATE] unknown filter %r', fname)
        return s
