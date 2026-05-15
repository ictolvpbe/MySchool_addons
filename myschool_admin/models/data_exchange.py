# -*- coding: utf-8 -*-
import json
import base64
import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# PropRelation types to export (structural only, no person-related)
EXPORT_PR_TYPES = ('ORG-TREE', 'BRSO', 'SRBR')

# Org types to exclude from export (rebuilt per school year)
EXCLUDE_ORG_TYPES = ('CLASSGROUP', 'PERSONGROUP')


class DataExchange(models.TransientModel):
    _name = 'myschool.data.exchange'
    _description = 'MySchool Data Export/Import'

    mode = fields.Selection([
        ('export', 'Export'),
        ('import', 'Import'),
    ], string='Mode', default='export', required=True)

    import_file = fields.Binary(string='Import File')
    import_filename = fields.Char(string='Filename')

    result_summary = fields.Text(string='Result', readonly=True)

    # ---- Selective export/import options -----------------------------
    # When ``scope_org_id`` is set, only data tied to that org and its
    # ORG-TREE descendants is exported / imported. Leave empty = whole
    # database. Each ``include_*`` toggle gates one section so admins
    # can cherry-pick what to ship.

    scope_org_id = fields.Many2one(
        'myschool.org', string='Scope (school / koepel)',
        domain="[('org_type_id.name', 'in', ['SCHOOL', 'SCHOOLBOARD'])]",
        help='Beperk de export tot deze SCHOOL of SCHOOLBOARD en al haar '
             'ORG-TREE descendants. Laat leeg voor de hele database.')

    # Type-tables (foundational, small, recommended to always include).
    include_types = fields.Boolean(
        string='Include *_type tables', default=True,
        help='org_types, person_types, role_types, period_types, '
             'proprelation_types — kleine foundation-tabellen.')

    # Main models.
    include_orgs = fields.Boolean(
        string='Include orgs', default=True)
    include_persongroups = fields.Boolean(
        string='Include persongroups', default=False,
        help='PERSONGROUP-orgs zijn standaard uitgesloten omdat ze per '
             'schooljaar herbouwd worden. Aanvinken om ze toch te '
             'exporteren.')
    include_classgroups = fields.Boolean(
        string='Include classgroups', default=False,
        help='Idem voor CLASSGROUP-orgs (klassen) — standaard '
             'uitgesloten.')
    include_roles = fields.Boolean(
        string='Include roles', default=True)
    include_periods = fields.Boolean(
        string='Include periods', default=True)
    include_proprelations = fields.Boolean(
        string='Include proprelations (ORG-TREE, BRSO, SR-BR)',
        default=True)
    include_settings_items = fields.Boolean(
        string='Include Settings Items (catalogus)', default=True)
    include_settings_values = fields.Boolean(
        string='Include Settings Values (waarden)', default=True)
    include_betask_types = fields.Boolean(
        string='Include betask types', default=True)
    include_betasks = fields.Boolean(
        string='Include betasks', default=False,
        help='Betasks zijn typisch DB-specifiek en hoog-volume. '
             'Aanvinken alleen voor diagnostiek-/replay-scenarios.')
    include_persons = fields.Boolean(
        string='Include persons', default=False,
        help='Persoon-records zijn privacygevoelig en niet vereist voor '
             'structurele migratie. Aanvinken voor full-data copies. '
             'PERSON-TREE/PPSBR/PG-P proprelations worden NIET '
             'meegeëxporteerd — re-sync vanuit Informat na import.')

    # ------------------------------------------------------------------
    # Scope helpers
    # ------------------------------------------------------------------

    def _scope_org_ids(self):
        """Return the set of org-ids in scope, or ``None`` for "no
        filter / whole DB". BFS-walks ORG-TREE descendants from the
        ``scope_org_id`` root."""
        self.ensure_one()
        if not self.scope_org_id:
            return None
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        result = {self.scope_org_id.id}
        if not org_tree_type:
            return result
        frontier = {self.scope_org_id.id}
        while frontier:
            children = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', list(frontier)),
                ('is_active', '=', True),
            ])
            new_ids = set()
            for rel in children:
                if rel.id_org and rel.id_org.id not in result:
                    new_ids.add(rel.id_org.id)
                if rel.id_org_child and rel.id_org_child.id not in result:
                    new_ids.add(rel.id_org_child.id)
            new_ids -= result
            result.update(new_ids)
            frontier = new_ids
        return result

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------

    def action_export(self):
        self.ensure_one()
        # Use sudo to bypass sync record rules (e.g. automatic_sync read restriction).
        # Access is already guarded by the ACL on this model (admin group only).
        data = self.sudo()._build_export_data()
        json_bytes = json.dumps(data, indent=2, ensure_ascii=False, default=str).encode('utf-8')

        attachment = self.env['ir.attachment'].create({
            'name': f'myschool_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            'type': 'binary',
            'datas': base64.b64encode(json_bytes),
            'mimetype': 'application/json',
        })

        counts = data.get('metadata', {}).get('record_counts', {})
        summary_lines = [f"  {k}: {v}" for k, v in counts.items()]
        self.result_summary = "Export complete.\n" + "\n".join(summary_lines)

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def _build_export_data(self):
        scope_ids = self._scope_org_ids()
        out = {}
        if self.include_types:
            out['org_types'] = self._export_org_types()
            out['person_types'] = self._export_person_types()
            out['role_types'] = self._export_role_types()
            out['period_types'] = self._export_period_types()
            out['proprelation_types'] = self._export_proprelation_types()
        if self.include_orgs:
            out['orgs'] = self._export_orgs(scope_ids)
        if self.include_persongroups:
            out['persongroups'] = self._export_persongroups(scope_ids)
        if self.include_classgroups:
            out['classgroups'] = self._export_classgroups(scope_ids)
        if self.include_roles:
            out['roles'] = self._export_roles()
        if self.include_periods:
            out['periods'] = self._export_periods()
        if self.include_proprelations:
            out['proprelations'] = self._export_proprelations(scope_ids)
        if self.include_settings_items:
            out['settings_items'] = self._export_settings_items()
        if self.include_settings_values:
            out['settings_values'] = self._export_settings_values(scope_ids)
        if self.include_betask_types:
            out['betask_types'] = self._export_betask_types()
        if self.include_betasks:
            out['betasks'] = self._export_betasks()
        if self.include_persons:
            out['persons'] = self._export_persons(scope_ids)

        return {
            'metadata': {
                'version': '1.3',
                'export_date': datetime.now().isoformat(),
                'source_database': self.env.cr.dbname,
                'exported_by': self.env.user.name,
                'scope_org': (self.scope_org_id.name
                              if self.scope_org_id else '(whole database)'),
                'scope_org_count': len(scope_ids) if scope_ids else None,
                'record_counts': {k: len(v) for k, v in out.items()},
            },
            **out,
        }

    # --- type exports ---

    def _export_org_types(self):
        records = self.env['myschool.org.type'].search([])
        return [{'name': r.name, 'description': r.description or '', 'is_active': r.is_active} for r in records]

    def _export_person_types(self):
        records = self.env['myschool.person.type'].search([])
        return [{'name': r.name, 'is_active': r.is_active} for r in records]

    def _export_role_types(self):
        records = self.env['myschool.role.type'].search([])
        return [{
            'name': r.name, 'shortname': r.shortname or '',
            'is_active': r.is_active, 'description': r.description or '',
        } for r in records]

    def _export_period_types(self):
        records = self.env['myschool.period.type'].search([])
        return [{'name': r.name, 'is_active': r.is_active} for r in records]

    def _export_proprelation_types(self):
        records = self.env['myschool.proprelation.type'].search([])
        return [{'name': r.name, 'usage': r.usage or '', 'is_active': r.is_active} for r in records]

    # --- main model exports ---

    def _serialize_org(self, r):
        """One-record serializer used by every org-category export so
        the wire format stays identical regardless of which toggle
        produced the record."""
        return {
            'inst_nr': r.inst_nr,
            'name': r.name,
            'name_short': r.name_short,
            'name_tree': r.name_tree or '',
            'org_type': r.org_type_id.name if r.org_type_id else '',
            'is_active': r.is_active,
            'automatic_sync': r.automatic_sync,
            'is_administrative': r.is_administrative,
            'street': r.street or '',
            'street_nr': r.street_nr or '',
            'postal_code': r.postal_code or '',
            'community': r.community or '',
            'country': r.country or '',
            'sap_provider': r.sap_provider or '',
            'sap_login': r.sap_login or '',
            'domain_internal': r.domain_internal or '',
            'domain_external': r.domain_external or '',
            'has_ou': r.has_ou,
            'has_comgroup': r.has_comgroup,
            'has_secgroup': r.has_secgroup,
            'ou_fqdn_internal': r.ou_fqdn_internal or '',
            'ou_fqdn_external': r.ou_fqdn_external or '',
            'com_group_fqdn_internal': r.com_group_fqdn_internal or '',
            'com_group_fqdn_external': r.com_group_fqdn_external or '',
            'sec_group_fqdn_internal': r.sec_group_fqdn_internal or '',
            'sec_group_fqdn_external': r.sec_group_fqdn_external or '',
            'com_group_name': r.com_group_name or '',
            'com_group_email': r.com_group_email or '',
            'sec_group_name': r.sec_group_name or '',
        }

    def _export_orgs(self, scope_ids=None):
        """Export "regular" orgs — anything that's not a classgroup or
        persongroup. Classgroups + persongroups have their own toggles
        so admins can decide per category."""
        excluded_type_ids = self.env['myschool.org.type'].search(
            [('name', 'in', list(EXCLUDE_ORG_TYPES))]).ids
        domain = []
        if excluded_type_ids:
            domain = [('org_type_id', 'not in', excluded_type_ids)]
        if scope_ids is not None:
            domain.append(('id', 'in', list(scope_ids)))
        records = self.env['myschool.org'].search(domain)
        return [self._serialize_org(r) for r in records]

    def _export_persongroups(self, scope_ids=None):
        """Export PERSONGROUP-type orgs. Same wire format as ``orgs`` —
        kept in its own section so importers can decide whether to
        load them (typically rebuilt per school year, so usually
        skipped)."""
        domain = [('org_type_id.name', '=', 'PERSONGROUP')]
        if scope_ids is not None:
            domain.append(('id', 'in', list(scope_ids)))
        records = self.env['myschool.org'].search(domain)
        return [self._serialize_org(r) for r in records]

    def _export_classgroups(self, scope_ids=None):
        """Export CLASSGROUP-type orgs. Same caveats as persongroups."""
        domain = [('org_type_id.name', '=', 'CLASSGROUP')]
        if scope_ids is not None:
            domain.append(('id', 'in', list(scope_ids)))
        records = self.env['myschool.org'].search(domain)
        return [self._serialize_org(r) for r in records]

    def _export_persons(self, scope_ids=None):
        """Export myschool.person records.

        Privacy / data-protection: persons are not part of the default
        export. Opt-in via ``include_persons``.

        ``scope_ids`` filters to persons whose **active** PERSON-TREE
        org is within scope. Their proprelations (PERSON-TREE, PPSBR,
        PG-P) are intentionally not exported — re-sync from Informat
        after import to rebuild them.
        """
        Person = self.env['myschool.person']
        if scope_ids is not None:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            pt_type = PropRelationType.search(
                [('name', '=', 'PERSON-TREE')], limit=1)
            if not pt_type:
                return []
            rels = PropRelation.search([
                ('proprelation_type_id', '=', pt_type.id),
                ('id_org', 'in', list(scope_ids)),
                ('is_active', '=', True),
                ('id_person', '!=', False),
            ])
            person_ids = list({r.id_person.id for r in rels})
            records = Person.browse(person_ids)
        else:
            records = Person.search([])
        result = []
        for r in records:
            result.append({
                'sap_person_uuid': r.sap_person_uuid or '',
                'sap_ref': r.sap_ref or '',
                'first_name': r.first_name or '',
                'name': r.name or '',
                'last_name': r.last_name or '' if 'last_name' in r._fields else '',
                'abbreviation': r.abbreviation or '',
                'gender': r.gender or '' if 'gender' in r._fields else '',
                'email_cloud': r.email_cloud or '',
                'email_private': r.email_private or '',
                'person_type': r.person_type_id.name if r.person_type_id else '',
                'is_active': r.is_active,
                'automatic_sync': r.automatic_sync if 'automatic_sync' in r._fields else True,
                'person_fqdn_internal': r.person_fqdn_internal or ''
                    if 'person_fqdn_internal' in r._fields else '',
                'person_fqdn_external': r.person_fqdn_external or ''
                    if 'person_fqdn_external' in r._fields else '',
            })
        return result

    def _export_roles(self):
        records = self.env['myschool.role'].search([])
        result = []
        for r in records:
            result.append({
                'name': r.name,
                'label': r.label or '',
                'shortname': r.shortname if r.shortname and r.shortname != '0' else '',
                'role_type': r.role_type_id.name if r.role_type_id else '',
                'has_ui_access': r.has_ui_access,
                'priority': r.priority,
                'is_active': r.is_active,
                'automatic_sync': r.automatic_sync,
                'description': r.description or '',
            })
        return result

    def _export_periods(self):
        records = self.env['myschool.period'].search([])
        result = []
        for r in records:
            result.append({
                'name': r.name,
                'name_in_sap': r.name_in_sap,
                'period_type': r.period_type_id.name if r.period_type_id else '',
                'start_date': fields.Datetime.to_string(r.start_date) if r.start_date else '',
                'end_date': fields.Datetime.to_string(r.end_date) if r.end_date else '',
                'is_active': r.is_active,
            })
        return result

    def _export_proprelations(self, scope_ids=None):
        pr_type_ids = self.env['myschool.proprelation.type'].search(
            [('name', 'in', list(EXPORT_PR_TYPES))]).ids
        if not pr_type_ids:
            return []
        records = self.env['myschool.proprelation'].search(
            [('proprelation_type_id', 'in', pr_type_ids)])

        # Build set of exported org ids for filtering.
        excluded_type_ids = self.env['myschool.org.type'].search(
            [('name', 'in', list(EXCLUDE_ORG_TYPES))]).ids
        domain = []
        if excluded_type_ids:
            domain = [('org_type_id', 'not in', excluded_type_ids)]
        if scope_ids is not None:
            domain.append(('id', 'in', list(scope_ids)))
        exported_org_ids = set(self.env['myschool.org'].search(domain).ids)

        result = []
        for r in records:
            # Skip proprelations that reference orgs not in our export set
            org_ids_in_rec = [
                r.id_org.id if r.id_org else None,
                r.id_org_parent.id if r.id_org_parent else None,
                r.id_org_child.id if r.id_org_child else None,
            ]
            org_ids_in_rec = [oid for oid in org_ids_in_rec if oid is not None]
            if org_ids_in_rec and not all(oid in exported_org_ids for oid in org_ids_in_rec):
                continue

            entry = {
                'type': r.proprelation_type_id.name if r.proprelation_type_id else '',
                'is_active': r.is_active,
                'is_administrative': r.is_administrative,
                'is_organisational': r.is_organisational,
                'priority': r.priority,
                'automatic_sync': r.automatic_sync,
                'start_date': fields.Datetime.to_string(r.start_date) if r.start_date else '',
                'end_date': fields.Datetime.to_string(r.end_date) if r.end_date else '',
            }
            # Org references by inst_nr + name_short (inst_nr is NOT unique)
            if r.id_org:
                entry['org_inst_nr'] = r.id_org.inst_nr
                entry['org_name_short'] = r.id_org.name_short
            if r.id_org_parent:
                entry['org_parent_inst_nr'] = r.id_org_parent.inst_nr
                entry['org_parent_name_short'] = r.id_org_parent.name_short
            if r.id_org_child:
                entry['org_child_inst_nr'] = r.id_org_child.inst_nr
                entry['org_child_name_short'] = r.id_org_child.name_short
            # Role references by name
            if r.id_role:
                entry['role_name'] = r.id_role.name
            if r.id_role_parent:
                entry['role_parent_name'] = r.id_role_parent.name
            if r.id_role_child:
                entry['role_child_name'] = r.id_role_child.name
            # Period references by name
            if r.id_period:
                entry['period_name'] = r.id_period.name
            if r.id_period_parent:
                entry['period_parent_name'] = r.id_period_parent.name
            if r.id_period_child:
                entry['period_child_name'] = r.id_period_child.name

            result.append(entry)
        return result

    def _export_settings_items(self):
        """Catalog definities — geen waarden, geen scope-filter (definities
        zijn altijd globaal). Encrypted SI's worden wel meegenomen want
        defaults bevatten geen secrets."""
        records = self.env['myschool.settings.item'].search([])
        return [{
            'key': r.key,
            'label': r.label,
            'description': r.description or '',
            'category': r.category,
            'value_type': r.value_type,
            'scope_kind': r.scope_kind,
            'default_string': r.default_string or '',
            'default_integer': r.default_integer,
            'default_boolean': r.default_boolean,
            'is_encrypted': r.is_encrypted,
            'is_active': r.is_active,
        } for r in records]

    def _export_settings_values(self, scope_ids=None):
        """Waarden export. Skipt encrypted SI's (credentials) en
        per-person waarden (person-data is uitgesloten van export)."""
        domain = [
            ('person_id', '=', False),
            ('settings_item_id.is_encrypted', '=', False),
        ]
        # Scope filter: alleen waarden voor specifieke orgs (+ globale).
        if scope_ids is not None:
            domain.append('|')
            domain.append(('org_id', 'in', list(scope_ids)))
            domain.append(('org_id', '=', False))
        records = self.env['myschool.settings.value'].search(domain)
        result = []
        for r in records:
            entry = {
                'settings_key': r.settings_item_id.key if r.settings_item_id else '',
                'string_value': r.string_value or '',
                'integer_value': r.integer_value,
                'boolean_value': r.boolean_value,
                'inherit_to_children': r.inherit_to_children,
                'is_active': r.is_active,
            }
            # Use inst_nr + name_short for org references (inst_nr is NOT unique)
            if r.org_id:
                entry['org_inst_nr'] = r.org_id.inst_nr
                entry['org_name_short'] = r.org_id.name_short
            result.append(entry)
        return result

    def _export_betask_types(self):
        records = self.env['myschool.betask.type'].search([])
        return [{
            'name': r.name,
            'target': r.target,
            'object': r.object,
            'action': r.action,
            'description': r.description or '',
            'active': r.active,
            'processor_method': r.processor_method or '',
            'requires_confirmation': r.requires_confirmation,
            'auto_process': r.auto_process,
            'priority': r.priority,
        } for r in records]

    def _export_betasks(self):
        records = self.env['myschool.betask'].search([])
        return [{
            'name': r.name,
            'betask_type_name': r.betasktype_id.name if r.betasktype_id else '',
            'status': r.status,
            'automatic_sync': r.automatic_sync,
            'data': r.data or '',
            'data2': r.data2 or '',
            'changes': r.changes or '',
            'lastrun': fields.Datetime.to_string(r.lastrun) if r.lastrun else '',
            'error_description': r.error_description or '',
            'active': r.active,
            'retry_count': r.retry_count,
            'max_retries': r.max_retries,
        } for r in records]

    # ------------------------------------------------------------------
    # IMPORT
    # ------------------------------------------------------------------

    def action_import(self):
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("Please select a JSON file to import."))

        try:
            raw = base64.b64decode(self.import_file)
            data = json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise UserError(_("Invalid JSON file: %s") % str(e))

        if 'metadata' not in data:
            raise UserError(_("Invalid export file: missing metadata section."))

        stats = {}
        errors = []
        # Use sudo to bypass sync record rules during import.
        sudo_self = self.sudo()
        # Each section honours the same ``include_*`` toggles as the
        # export. An admin can import a full export but cherry-pick
        # which categories to materialise. Sections missing from the
        # JSON are skipped automatically.
        if self.include_types:
            if 'org_types' in data:
                stats['org_types'] = sudo_self._import_org_types(data['org_types'], errors)
            if 'person_types' in data:
                stats['person_types'] = sudo_self._import_person_types(data['person_types'], errors)
            if 'role_types' in data:
                stats['role_types'] = sudo_self._import_role_types(data['role_types'], errors)
            if 'period_types' in data:
                stats['period_types'] = sudo_self._import_period_types(data['period_types'], errors)
            if 'proprelation_types' in data:
                stats['proprelation_types'] = sudo_self._import_proprelation_types(data['proprelation_types'], errors)
        if self.include_settings_items and 'settings_items' in data:
            stats['settings_items'] = sudo_self._import_settings_items(data['settings_items'], errors)
        if self.include_orgs and 'orgs' in data:
            stats['orgs'] = sudo_self._import_orgs(data['orgs'], errors)
        if self.include_persongroups and 'persongroups' in data:
            stats['persongroups'] = sudo_self._import_orgs(data['persongroups'], errors)
        if self.include_classgroups and 'classgroups' in data:
            stats['classgroups'] = sudo_self._import_orgs(data['classgroups'], errors)
        if self.include_roles and 'roles' in data:
            stats['roles'] = sudo_self._import_roles(data['roles'], errors)
        if self.include_periods and 'periods' in data:
            stats['periods'] = sudo_self._import_periods(data['periods'], errors)
        if self.include_proprelations and 'proprelations' in data:
            stats['proprelations'] = sudo_self._import_proprelations(data['proprelations'], errors)
        if self.include_settings_values and 'settings_values' in data:
            stats['settings_values'] = sudo_self._import_settings_values(data['settings_values'], errors)
        if self.include_betask_types and 'betask_types' in data:
            stats['betask_types'] = sudo_self._import_betask_types(data['betask_types'], errors)
        if self.include_betasks and 'betasks' in data:
            stats['betasks'] = sudo_self._import_betasks(data['betasks'], errors)
        if self.include_persons and 'persons' in data:
            stats['persons'] = sudo_self._import_persons(data['persons'], errors)

        meta = data.get('metadata', {})
        lines = [
            f"Import complete from: {meta.get('source_database', '?')}",
            f"Exported on: {meta.get('export_date', '?')}",
            "",
        ]
        for key, (created, updated, skipped) in stats.items():
            lines.append(f"  {key}: {created} created, {updated} updated, {skipped} skipped")

        if errors:
            lines.append("")
            lines.append(f"Errors ({len(errors)}):")
            for err in errors[:50]:
                lines.append(f"  - {err}")
            if len(errors) > 50:
                lines.append(f"  ... and {len(errors) - 50} more")

        self.result_summary = "\n".join(lines)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # --- type imports (upsert on name) ---

    def _import_org_types(self, items, errors):
        Model = self.env['myschool.org.type']
        return self._upsert_by_name(Model, items, ['description', 'is_active'], errors)

    def _import_person_types(self, items, errors):
        Model = self.env['myschool.person.type']
        return self._upsert_by_name(Model, items, ['is_active'], errors)

    def _import_role_types(self, items, errors):
        Model = self.env['myschool.role.type']
        return self._upsert_by_name(Model, items, ['shortname', 'is_active', 'description'], errors)

    def _import_period_types(self, items, errors):
        Model = self.env['myschool.period.type']
        return self._upsert_by_name(Model, items, ['is_active'], errors)

    def _import_proprelation_types(self, items, errors):
        Model = self.env['myschool.proprelation.type']
        return self._upsert_by_name(Model, items, ['usage', 'is_active'], errors)

    def _import_settings_items(self, items, errors):
        """Import van SI-catalogus (definities). Idempotent — upsert op key."""
        Model = self.env['myschool.settings.item']
        created = updated = skipped = 0
        for item in items:
            key = item.get('key')
            if not key:
                skipped += 1
                continue
            try:
                existing = Model.search([('key', '=', key)], limit=1)
                vals = {
                    'key': key,
                    'label': item.get('label') or key,
                    'description': item.get('description') or False,
                    'category': item.get('category') or 'general',
                    'value_type': item.get('value_type') or 'string',
                    'scope_kind': item.get('scope_kind') or 'global',
                    'default_string': item.get('default_string') or False,
                    'default_integer': item.get('default_integer', 0),
                    'default_boolean': item.get('default_boolean', False),
                    'is_encrypted': item.get('is_encrypted', False),
                    'is_active': item.get('is_active', True),
                }
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Model.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"settings_item '{key}': {e}")
                skipped += 1
        return (created, updated, skipped)

    # --- main model imports ---

    def _import_orgs(self, items, errors):
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        created = updated = skipped = 0

        for item in items:
            inst_nr = item.get('inst_nr')
            name_short = item.get('name_short', '')
            if not inst_nr:
                skipped += 1
                continue

            try:
                org_type = OrgType.search([('name', '=', item.get('org_type', ''))], limit=1)
                vals = {
                    'inst_nr': inst_nr,
                    'name': item.get('name', ''),
                    'name_short': name_short,
                    'name_tree': item.get('name_tree') or False,
                    'org_type_id': org_type.id if org_type else False,
                    'is_active': item.get('is_active', True),
                    'automatic_sync': item.get('automatic_sync', True),
                    'is_administrative': item.get('is_administrative', False),
                    'street': item.get('street') or False,
                    'street_nr': item.get('street_nr') or False,
                    'postal_code': item.get('postal_code') or False,
                    'community': item.get('community') or False,
                    'country': item.get('country') or False,
                    'sap_provider': item.get('sap_provider') or False,
                    'sap_login': item.get('sap_login') or False,
                    'domain_internal': item.get('domain_internal') or False,
                    'domain_external': item.get('domain_external') or False,
                    'has_ou': item.get('has_ou', False),
                    'has_comgroup': item.get('has_comgroup', False),
                    'has_secgroup': item.get('has_secgroup', False),
                    'ou_fqdn_internal': item.get('ou_fqdn_internal') or False,
                    'ou_fqdn_external': item.get('ou_fqdn_external') or False,
                    'com_group_fqdn_internal': item.get('com_group_fqdn_internal') or False,
                    'com_group_fqdn_external': item.get('com_group_fqdn_external') or False,
                    'sec_group_fqdn_internal': item.get('sec_group_fqdn_internal') or False,
                    'sec_group_fqdn_external': item.get('sec_group_fqdn_external') or False,
                    'com_group_name': item.get('com_group_name') or False,
                    'com_group_email': item.get('com_group_email') or False,
                    'sec_group_name': item.get('sec_group_name') or False,
                }
                # Match by inst_nr + name_short (inst_nr is NOT unique across orgs)
                existing = Org.search([
                    ('inst_nr', '=', inst_nr),
                    ('name_short', '=', name_short),
                ], limit=1)
                if existing:
                    existing.with_context(skip_pg_flag_handling=True).write(vals)
                    updated += 1
                else:
                    Org.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"org '{inst_nr}/{name_short}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _import_roles(self, items, errors):
        Role = self.env['myschool.role']
        RoleType = self.env['myschool.role.type']
        created = updated = skipped = 0
        for item in items:
            name = item.get('name')
            if not name:
                skipped += 1
                continue
            try:
                shortname = item.get('shortname') or None
                if shortname == '0':
                    shortname = None
                role_type = RoleType.search([('name', '=', item.get('role_type', ''))], limit=1)
                vals = {
                    'name': name,
                    'label': item.get('label') or False,
                    'role_type_id': role_type.id if role_type else False,
                    'has_ui_access': item.get('has_ui_access', True),
                    'priority': item.get('priority', 0),
                    'is_active': item.get('is_active', True),
                    'automatic_sync': item.get('automatic_sync', True),
                    'description': item.get('description') or False,
                }
                # Only set shortname when non-empty to avoid UNIQUE constraint
                # violations from multiple roles with empty shortname
                if shortname:
                    vals['shortname'] = shortname
                # Match by name first, then by shortname
                existing = Role.search([('name', '=', name)], limit=1)
                if not existing and shortname:
                    existing = Role.search([('shortname', '=', shortname)], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Role.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"role '{name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _import_periods(self, items, errors):
        Period = self.env['myschool.period']
        PeriodType = self.env['myschool.period.type']
        created = updated = skipped = 0
        for item in items:
            name = item.get('name')
            name_in_sap = item.get('name_in_sap', '')
            if not name:
                skipped += 1
                continue
            try:
                period_type = PeriodType.search([('name', '=', item.get('period_type', ''))], limit=1)
                vals = {
                    'name': name,
                    'name_in_sap': name_in_sap or name,
                    'period_type_id': period_type.id if period_type else False,
                    'start_date': item.get('start_date') or False,
                    'end_date': item.get('end_date') or False,
                    'is_active': item.get('is_active', False),
                }
                existing = Period.search([('name', '=', name)], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Period.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"period '{name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _import_proprelations(self, items, errors):
        PR = self.env['myschool.proprelation']
        PRType = self.env['myschool.proprelation.type']
        created = updated = skipped = 0

        for item in items:
            type_name = item.get('type', '')
            try:
                pr_type = PRType.search([('name', '=', type_name)], limit=1)
                if not pr_type:
                    _logger.warning(f"[IMPORT] PropRelation type '{type_name}' not found, skipping")
                    skipped += 1
                    continue

                vals = {
                    'proprelation_type_id': pr_type.id,
                    'is_active': item.get('is_active', True),
                    'is_administrative': item.get('is_administrative', False),
                    'is_organisational': item.get('is_organisational', False),
                    'priority': item.get('priority', 0),
                    'automatic_sync': item.get('automatic_sync', True),
                    'start_date': item.get('start_date') or False,
                    'end_date': item.get('end_date') or False,
                }

                # Resolve FK references
                match_domain = [('proprelation_type_id', '=', pr_type.id)]

                # Orgs — use inst_nr + name_short composite key
                for inst_key, short_key, field_name in [
                    ('org_inst_nr', 'org_name_short', 'id_org'),
                    ('org_parent_inst_nr', 'org_parent_name_short', 'id_org_parent'),
                    ('org_child_inst_nr', 'org_child_name_short', 'id_org_child'),
                ]:
                    if inst_key in item:
                        org = self._resolve_org(item[inst_key], item.get(short_key))
                        if org:
                            vals[field_name] = org.id
                            match_domain.append((field_name, '=', org.id))
                        else:
                            _logger.warning(
                                f"[IMPORT] Org '{item[inst_key]}/{item.get(short_key, '?')}' not found")

                # Roles
                for json_key, field_name in [
                    ('role_name', 'id_role'),
                    ('role_parent_name', 'id_role_parent'),
                    ('role_child_name', 'id_role_child'),
                ]:
                    if json_key in item:
                        role = self._resolve_role(item[json_key])
                        if role:
                            vals[field_name] = role.id
                            match_domain.append((field_name, '=', role.id))
                        else:
                            _logger.warning(f"[IMPORT] Role '{item[json_key]}' not found")

                # Periods
                for json_key, field_name in [
                    ('period_name', 'id_period'),
                    ('period_parent_name', 'id_period_parent'),
                    ('period_child_name', 'id_period_child'),
                ]:
                    if json_key in item:
                        period = self._resolve_period(item[json_key])
                        if period:
                            vals[field_name] = period.id
                            match_domain.append((field_name, '=', period.id))
                        else:
                            _logger.warning(f"[IMPORT] Period '{item[json_key]}' not found")

                # Try to find existing by composite key
                existing = PR.search(match_domain, limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    PR.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"proprelation '{type_name}': {e}")
                skipped += 1

        return (created, updated, skipped)

    def _import_settings_values(self, items, errors):
        """Import van SI-waarden. Match op (settings_item, org). Person-
        scoped waarden zijn nooit geëxporteerd, dus die hoeven we hier
        niet te behandelen. Idempotent."""
        Value = self.env['myschool.settings.value']
        SI = self.env['myschool.settings.item']
        created = updated = skipped = 0

        for item in items:
            key = item.get('settings_key', '')
            if not key:
                skipped += 1
                continue

            try:
                si = SI.search([('key', '=', key)], limit=1)
                if not si:
                    _logger.warning(
                        "[IMPORT] Settings Item '%s' not found, "
                        "skipping value", key)
                    errors.append(f"settings_value: SI '{key}' not found")
                    skipped += 1
                    continue

                vals = {
                    'settings_item_id': si.id,
                    'is_active': item.get('is_active', True),
                    'inherit_to_children': item.get(
                        'inherit_to_children', True),
                }
                if si.value_type == 'string':
                    vals['string_value'] = item.get('string_value') or False
                elif si.value_type == 'integer':
                    vals['integer_value'] = item.get('integer_value', 0)
                elif si.value_type == 'boolean':
                    vals['boolean_value'] = item.get('boolean_value', False)

                match_domain = [
                    ('settings_item_id', '=', si.id),
                    ('person_id', '=', False),
                ]
                if 'org_inst_nr' in item:
                    org = self._resolve_org(
                        item['org_inst_nr'], item.get('org_name_short'))
                    if org:
                        vals['org_id'] = org.id
                        match_domain.append(('org_id', '=', org.id))
                    else:
                        # Org niet gevonden — skip; geen valse globale waarde
                        skipped += 1
                        continue
                else:
                    match_domain.append(('org_id', '=', False))

                existing = Value.search(match_domain, limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Value.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"settings_value '{key}': {e}")
                skipped += 1

        return (created, updated, skipped)

    def _import_betask_types(self, items, errors):
        Model = self.env['myschool.betask.type']
        created = updated = skipped = 0
        for item in items:
            name = item.get('name')
            if not name:
                skipped += 1
                continue
            try:
                vals = {
                    'name': name,
                    'target': item.get('target'),
                    'object': item.get('object'),
                    'action': item.get('action'),
                    'description': item.get('description') or False,
                    'active': item.get('active', True),
                    'processor_method': item.get('processor_method') or False,
                    'requires_confirmation': item.get('requires_confirmation', False),
                    'auto_process': item.get('auto_process', True),
                    'priority': item.get('priority', 10),
                }
                existing = Model.search([('name', '=', name)], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Model.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"betask_type '{name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _import_betasks(self, items, errors):
        Task = self.env['myschool.betask']
        TaskType = self.env['myschool.betask.type']
        created = updated = skipped = 0
        for item in items:
            name = item.get('name')
            type_name = item.get('betask_type_name', '')
            if not name:
                skipped += 1
                continue
            try:
                task_type = TaskType.search([('name', '=', type_name)], limit=1) if type_name else None
                if not task_type:
                    _logger.warning(f"[IMPORT] BeTask type '{type_name}' not found for task '{name}', skipping")
                    errors.append(f"betask '{name}': type '{type_name}' not found")
                    skipped += 1
                    continue

                vals = {
                    'name': name,
                    'betasktype_id': task_type.id,
                    'status': item.get('status', 'new'),
                    'automatic_sync': item.get('automatic_sync', True),
                    'data': item.get('data') or False,
                    'data2': item.get('data2') or False,
                    'changes': item.get('changes') or False,
                    'lastrun': item.get('lastrun') or False,
                    'error_description': item.get('error_description') or False,
                    'active': item.get('active', True),
                    'retry_count': item.get('retry_count', 0),
                    'max_retries': item.get('max_retries', 3),
                }
                existing = Task.search([('name', '=', name)], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Task.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"betask '{name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _import_persons(self, items, errors):
        """Import myschool.person records.

        Matched by ``sap_person_uuid`` when present (Informat-synced),
        otherwise by ``(first_name, name)``. Proprelations are NOT
        loaded — admins are expected to re-sync from Informat after
        import to rebuild PERSON-TREE / PPSBR / PG-P. Skip rows for
        which the linked ``person_type`` doesn't exist.
        """
        Person = self.env['myschool.person']
        PersonType = self.env['myschool.person.type']
        created = updated = skipped = 0
        for item in items:
            first_name = (item.get('first_name') or '').strip()
            name = (item.get('name') or '').strip()
            uuid = (item.get('sap_person_uuid') or '').strip()
            if not name and not first_name and not uuid:
                skipped += 1
                continue
            try:
                pt_name = (item.get('person_type') or '').strip()
                pt = PersonType.search([('name', '=', pt_name)], limit=1) \
                    if pt_name else None
                vals = {
                    'first_name': first_name or False,
                    'name': name or first_name,
                    'abbreviation': item.get('abbreviation') or False,
                    'email_cloud': item.get('email_cloud') or False,
                    'email_private': item.get('email_private') or False,
                    'sap_ref': item.get('sap_ref') or False,
                    'sap_person_uuid': uuid or False,
                    'is_active': item.get('is_active', True),
                }
                if pt:
                    vals['person_type_id'] = pt.id
                # Optional fields — only set when the column exists on
                # this DB's schema.
                for fname in ('last_name', 'gender', 'automatic_sync',
                              'person_fqdn_internal', 'person_fqdn_external'):
                    if fname in Person._fields and fname in item:
                        v = item.get(fname)
                        vals[fname] = v if v not in ('', None) else False

                # Match: prefer sap_person_uuid (stable Informat key),
                # fall back to first_name + name.
                existing = None
                if uuid:
                    existing = Person.search(
                        [('sap_person_uuid', '=', uuid)], limit=1)
                if not existing:
                    existing = Person.search([
                        ('first_name', '=', first_name or False),
                        ('name', '=', name or first_name),
                    ], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    Person.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(
                    f"person '{first_name} {name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _upsert_by_name(self, model, items, extra_fields, errors):
        created = updated = skipped = 0
        for item in items:
            name = item.get('name')
            if not name:
                skipped += 1
                continue
            try:
                vals = {'name': name}
                for f in extra_fields:
                    if f in item:
                        val = item[f]
                        # Skip empty strings for fields that may have UNIQUE
                        # constraints (e.g. shortname) to avoid violations
                        if val == '' and f == 'shortname':
                            continue
                        vals[f] = val if val != '' else False
                existing = model.search([('name', '=', name)], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    model.create(vals)
                    created += 1
            except Exception as e:
                self.env.cr.rollback()
                errors.append(f"{model._name} '{name}': {e}")
                skipped += 1
        return (created, updated, skipped)

    def _resolve_org(self, inst_nr, name_short=None):
        """Resolve an org by inst_nr + name_short composite key."""
        if not inst_nr:
            return None
        domain = [('inst_nr', '=', inst_nr)]
        if name_short:
            domain.append(('name_short', '=', name_short))
        return self.env['myschool.org'].search(domain, limit=1) or None

    def _resolve_role(self, name):
        if not name:
            return None
        return self.env['myschool.role'].search([('name', '=', name)], limit=1) or None

    def _resolve_period(self, name):
        if not name:
            return None
        return self.env['myschool.period'].search([('name', '=', name)], limit=1) or None
