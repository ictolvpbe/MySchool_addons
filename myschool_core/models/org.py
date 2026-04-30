from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


# myschool.org (Org.java)
class Org(models.Model):
    _name = 'myschool.org'
    _description = 'Organisatie'
    # _inherit = 'mail.thread'

    #Tijdelijk
    OldId = fields.Char(string='OldId', required=False)

    # Aanname: SapProvider is een selection field. Vul de waarden aan indien nodig.
    SAP_PROVIDER_SELECTION = [('1', 'INFORMAT'), ('2', 'NONE')]  #TODO : get providers from database in stead of selection

    name = fields.Char(string='Naam', required=True)
    name_short = fields.Char(string='Korte Naam', required=True)
    name_tree = fields.Char(string='Full Tree name', required=False)

    @api.depends('name')
    def _compute_display_name(self):
        for record in self:
            name = record.name or ''
            if ',' in name:
                name = name.split(',', 1)[1].strip()
            record.display_name = name

    _rec_names_search = ['name']
    inst_nr = fields.Char(string='Instellingsnummer', required=True, size=10)
    is_active = fields.Boolean(string='Actief', default=True, required=True)
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)

    # Relatie
    org_type_id = fields.Many2one('myschool.org.type', string='Organisatie Type', ondelete='restrict')

    # Adres
    street = fields.Char(string='Straat', size=50)
    street_nr = fields.Char(string='Straatnummer', size=10)
    postal_code = fields.Char(string='Postcode', size=10)
    community = fields.Char(string='Gemeente', size=50)
    country = fields.Char(string='Land', size=30)

    # SAP & Accounts
    sap_provider = fields.Selection(SAP_PROVIDER_SELECTION, string='SAP Provider')
    sap_login = fields.Char(string='SAP Login', size=100)
    sap_password = fields.Char(string='SAP Wachtwoord', size=50, groups="base.group_system")
    is_administrative = fields.Boolean(string='Is Administratief', default=False)

    # AD/OU Velden
    domain_internal = fields.Char(string='Intern Domein')
    domain_external = fields.Char(string='Extern Domein')
    has_ou = fields.Boolean(string='Heeft OU', default=False)
    has_role = fields.Boolean(string='Heeft Role', default=False)
    has_comgroup = fields.Boolean(string='Heeft Communicatiegroep', default=False)
    has_secgroup = fields.Boolean(string='Heeft Securitygroep', default=False)
    has_accounts = fields.Boolean(string='Heeft Accounts', default=False)
    ou_fqdn_internal = fields.Char(string='OU FQDN Intern')
    ou_fqdn_external = fields.Char(string='OU FQDN Extern')
    com_group_fqdn_internal = fields.Char(string='Com Groep FQDN Intern')
    com_group_fqdn_external = fields.Char(string='Com Groep FQDN Extern')
    sec_group_fqdn_internal = fields.Char(string='Sec Groep FQDN Intern')
    sec_group_fqdn_external = fields.Char(string='Sec Groep FQDN Extern')
    com_group_name = fields.Char(string='Com Groep Naam')
    com_group_email = fields.Char(string='Com Groep Email', size=200)
    sec_group_name = fields.Char(string='Sec Groep Naam')

    # Redundant
    orggroup_working_period = fields.Char(string='Werktijd Periode', size=30)
    richting = fields.Char(string='Richting', size=30)

    def update_org_flags(self):
        """Recalculate has_role, has_accounts, has_comgroup, has_secgroup from BRSO state."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            return

        for org in self:
            brso_rels = PropRelation.search([
                ('proprelation_type_id', '=', brso_type.id),
                ('id_org', '=', org.id),
                ('is_active', '=', True),
            ])
            vals = {
                'has_role': bool(brso_rels),
                'has_accounts': any(r.has_accounts for r in brso_rels),
                'has_comgroup': any(r.has_ldap_com_group or r.has_odoo_group for r in brso_rels) or bool(org.com_group_name),
                'has_secgroup': any(r.has_ldap_sec_group for r in brso_rels) or bool(org.sec_group_name),
            }
            org.with_context(skip_pg_flag_handling=True).write(vals)

    # =========================================================================
    # Audit Trail - Create backend tasks for manual changes
    # =========================================================================

    # Fields to track for audit
    _AUDIT_FIELDS = [
        'name', 'name_short', 'name_tree', 'inst_nr', 'is_active',
        'org_type_id', 'street', 'street_nr', 'postal_code', 'community',
        'country', 'is_administrative', 'domain_internal', 'domain_external',
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to log audit trail."""
        records = super().create(vals_list)

        for record in records:
            record._create_audit_task('ADD', new_values=record._get_audit_values())

        return records

    def write(self, vals):
        """Override write to log audit trail and handle persongroup flags."""
        # Capture old values before write
        old_values_map = {}
        for record in self:
            old_values_map[record.id] = record._get_audit_values()

        # Capture old persongroup flags before write
        _PG_FLAG_FIELDS = ('has_comgroup', 'has_secgroup', 'has_accounts', 'has_role')
        old_pg_flags = {}
        if not self.env.context.get('skip_pg_flag_handling') and \
                any(f in vals for f in _PG_FLAG_FIELDS):
            for record in self:
                old_pg_flags[record.id] = {
                    'has_comgroup': record.has_comgroup,
                    'has_secgroup': record.has_secgroup,
                    'has_accounts': record.has_accounts,
                    'has_role': record.has_role,
                }

        # Check if this is a deactivation
        is_deactivation = 'is_active' in vals and vals['is_active'] is False

        result = super().write(vals)

        # Create audit tasks after write
        for record in self:
            old_values = old_values_map.get(record.id, {})
            new_values = record._get_audit_values()

            # Determine action type
            if is_deactivation and old_values.get('is_active') is True:
                action = 'DEACT'
            else:
                action = 'UPD'

            # Only log if there are actual changes
            changes = self._get_value_changes(old_values, new_values)
            if changes:
                record._create_audit_task(
                    action,
                    old_values=old_values,
                    new_values=new_values,
                    changes=changes
                )

        # Handle persongroup flag changes (create/deactivate persongroups)
        if old_pg_flags:
            for record in self:
                old_flags = old_pg_flags.get(record.id)
                if old_flags:
                    try:
                        record._handle_persongroup_flags(old_flags)
                    except Exception as e:
                        _logger.warning(
                            f'[PG-SYNC] Failed to handle persongroup flags for {record.name}: {e}')

        return result

    def unlink(self):
        """Override unlink to log audit trail before deletion."""
        # Capture values before deletion
        for record in self:
            record._create_audit_task('DEL', old_values=record._get_audit_values())

        return super().unlink()

    def _get_audit_values(self):
        """Get current field values for audit logging."""
        self.ensure_one()
        values = {'id': self.id}

        for field_name in self._AUDIT_FIELDS:
            value = getattr(self, field_name, None)
            # Handle Many2one fields
            if hasattr(value, 'id'):
                values[field_name] = value.id
                values[f'{field_name}_name'] = value.name if value else None
            else:
                values[field_name] = value

        return values

    def _get_value_changes(self, old_values, new_values):
        """Compare old and new values and return list of changes."""
        changes = []

        for field_name in self._AUDIT_FIELDS:
            old_val = old_values.get(field_name)
            new_val = new_values.get(field_name)

            # Normalize for comparison
            if old_val != new_val:
                old_display = str(old_val) if old_val is not None else '(empty)'
                new_display = str(new_val) if new_val is not None else '(empty)'
                changes.append(f"{field_name}: {old_display} → {new_display}")

        return changes

    def _create_audit_task(self, action, old_values=None, new_values=None, changes=None):
        """
        Create a completed backend task for audit/rollback purposes.

        Args:
            action: 'ADD', 'UPD', 'DEACT', or 'DEL'
            old_values: dict of values before the change
            new_values: dict of values after the change
            changes: list of change descriptions
        """
        self.ensure_one()

        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']

        # Find or create the task type
        task_type = BeTaskType.search([
            ('target', '=', 'MANUAL'),
            ('object', '=', 'ORG'),
            ('action', '=', action),
        ], limit=1)

        if not task_type:
            # Create the task type if it doesn't exist
            task_type = BeTaskType.create({
                'name': f'MANUAL_ORG_{action}',
                'target': 'MANUAL',
                'object': 'ORG',
                'action': action,
                'description': f'Manual organization {action.lower()} operation (audit trail)',
                'auto_process': False,
                'requires_confirmation': False,
            })

        # Prepare task data for potential rollback
        task_data = {
            'org_id': self.id,
            'org_name': self.name,
            'action': action,
            'timestamp': fields.Datetime.now().isoformat(),
            'user_id': self.env.user.id,
            'user_name': self.env.user.name,
        }

        if old_values:
            task_data['old_values'] = old_values
        if new_values:
            task_data['new_values'] = new_values

        # Build changes description
        changes_text = []
        if action == 'ADD':
            changes_text.append(f"Organization created: {self.name}")
            changes_text.append(f"Name tree: {self.name_tree or 'N/A'}")
            changes_text.append(f"Institution nr: {self.inst_nr}")
        elif action == 'DEL':
            changes_text.append(f"Organization deleted: {old_values.get('name', 'Unknown')}")
            changes_text.append(f"Name tree: {old_values.get('name_tree', 'N/A')}")
        elif action == 'DEACT':
            changes_text.append(f"Organization deactivated: {self.name}")
        elif action == 'UPD' and changes:
            changes_text.append(f"Organization updated: {self.name}")
            changes_text.extend(changes)

        # Create the task with completed status
        BeTask.create({
            'name': f'MANUAL_ORG_{action}_{self.name}_{fields.Datetime.now().strftime("%Y%m%d%H%M%S")}',
            'betasktype_id': task_type.id,
            'status': 'completed_ok',
            'data': json.dumps(task_data),
            'changes': '\n'.join(changes_text),
        })

        _logger.info(f'Audit task created: MANUAL_ORG_{action} for {self.name}')

    # =========================================================================
    # Persongroup flag handling (has_comgroup / has_secgroup toggles)
    # =========================================================================

    def _handle_persongroup_flags(self, old_flags):
        """Handle persongroup creation/deactivation when comgroup/secgroup flags change.

        When a flag turns ON:
          1. Compute and write group name / FQDN / email fields on this org
          2. Create the persongroup via betask
          3. Sync PG-P members
        When a flag turns OFF:
          Deactivate the persongroup and its PG-P / ORG-TREE relations.
        """
        self.ensure_one()
        processor = self.env['myschool.betask.processor']

        flag_pairs = [
            # (flag_field, name_field, fqdn_int_field, fqdn_ext_field, email_field, prefix)
            ('has_comgroup', 'com_group_name', 'com_group_fqdn_internal',
             'com_group_fqdn_external', 'com_group_email', 'grp-'),
            ('has_secgroup', 'sec_group_name', 'sec_group_fqdn_internal',
             'sec_group_fqdn_external', None, 'bgrp-'),
        ]

        for flag_field, name_field, fqdn_int_field, fqdn_ext_field, email_field, prefix in flag_pairs:
            old_val = old_flags.get(flag_field, False)
            new_val = getattr(self, flag_field, False)

            if not old_val and new_val:
                # ── Flag turned ON ──────────────────────────────────────
                if not self.has_accounts and not self.has_role:
                    msg = (f'{self.name}: {flag_field}=True but has_accounts=False '
                           f'and has_role=False — skipping persongroup creation')
                    _logger.warning(f'[PG-SYNC] {msg}')
                    try:
                        self.env['myschool.sys.event.service'].create_sys_error(
                            code='PG-SYNC-SKIP', data=msg,
                            error_type='ERROR-NONBLOCKING',
                            log_to_screen=True, source='BE')
                    except Exception:
                        pass
                    continue

                # Resolve school and OuForGroups
                school_org = processor._resolve_parent_school_from_org(self)
                if not school_org:
                    _logger.warning(
                        f'[PG-SYNC] {self.name}: cannot resolve parent school')
                    continue

                # Step 1 — compute group name, FQDNs, email and write to this org
                group_name = self._compute_and_write_group_fields(
                    school_org, processor, prefix,
                    name_field, fqdn_int_field, fqdn_ext_field, email_field)
                if not group_name:
                    continue

                # Step 2 — create persongroup via betask
                pg, _created = processor._find_or_create_persongroup(
                    group_name, group_name, school_org,
                    source_label=f'org:{self.name}:{flag_field}')
                if not pg:
                    continue

                # Step 3 — sync PG-P members
                self._sync_persongroup_members(pg, processor, flag_field)

            elif old_val and not new_val:
                # ── Flag turned OFF ─────────────────────────────────────
                group_name = getattr(self, name_field, None)
                if group_name:
                    self._deactivate_persongroup_by_name(group_name)
                # Clear related fields on this org
                clear_vals = {name_field: False, fqdn_int_field: False, fqdn_ext_field: False}
                if email_field:
                    clear_vals[email_field] = False
                self.with_context(skip_pg_flag_handling=True).write(clear_vals)

    # -----------------------------------------------------------------
    # Helpers for _handle_persongroup_flags
    # -----------------------------------------------------------------

    def _compute_and_write_group_fields(self, school_org, processor,
                                        prefix, name_field, fqdn_int_field,
                                        fqdn_ext_field, email_field):
        """Compute group name / FQDN / email from ORG-TREE and write to this org.

        Returns the computed group_name, or None on failure.
        """
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ConfigItem = self.env['myschool.config.item']

        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            return None

        org_short = (self.name_short or '').lower()
        if not org_short:
            _logger.warning(f'[PG-SYNC] {self.name}: name_short is empty, cannot compute group name')
            return None

        # Build group name by walking up the ORG-TREE
        # Format: {prefix}{org_short}-{parent1}-{parent2}-...
        # Excluding administrative orgs and SCHOOLBOARD type
        name_parts = [org_short]

        # Find immediate ORG-TREE parent to start the walk
        parent_rel = PropRelation.search([
            ('proprelation_type_id', '=', org_tree_type.id),
            ('id_org', '=', self.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ], limit=1)
        current = parent_rel.id_org_parent if parent_rel else None
        visited = set()

        while current and current.id not in visited:
            visited.add(current.id)
            skip = current.is_administrative
            if not skip and current.org_type_id and current.org_type_id.name == 'SCHOOLBOARD':
                skip = True
            if not skip:
                short = (current.name_short or current.name or '').lower()
                if short:
                    name_parts.append(short)
            parent_rel = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org', '=', current.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            current = parent_rel.id_org_parent if parent_rel else None

        group_name = prefix + '-'.join(name_parts)

        # Resolve OuForGroups for FQDN computation
        ou_for_groups = ConfigItem.get_ci_value_by_org_and_name(
            school_org.name_short, 'OuForGroups') if school_org else None
        ou_for_groups_lower = (ou_for_groups or '').lower()

        # Parent FQDNs (from the ORG-TREE parent, not this org)
        parent_fqdn_int = ''
        parent_fqdn_ext = ''
        parent_rel = PropRelation.search([
            ('proprelation_type_id', '=', org_tree_type.id),
            ('id_org', '=', self.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ], limit=1)
        if parent_rel and parent_rel.id_org_parent:
            parent_fqdn_int = (parent_rel.id_org_parent.ou_fqdn_internal or '').lower()
            parent_fqdn_ext = (parent_rel.id_org_parent.ou_fqdn_external or '').lower()

        # Build update dict
        org_update = {name_field: group_name}
        grp_lower = group_name.lower()

        for direction, parent_fqdn, fqdn_field in [
            ('internal', parent_fqdn_int, fqdn_int_field),
            ('external', parent_fqdn_ext, fqdn_ext_field),
        ]:
            if parent_fqdn:
                if ou_for_groups_lower:
                    org_update[fqdn_field] = f"cn={grp_lower},ou={ou_for_groups_lower},{parent_fqdn}"
                else:
                    org_update[fqdn_field] = f"cn={grp_lower},{parent_fqdn}"

        # Email (only for com_group)
        if email_field and group_name and school_org.domain_external:
            org_update[email_field] = f"{group_name}@{school_org.domain_external}"

        self.with_context(skip_pg_flag_handling=True).write(org_update)
        _logger.info(f'[PG-SYNC] Updated AD fields on {self.name}: {org_update}')
        return group_name

    def _sync_persongroup_members(self, pg, processor, flag_field):
        """Sync PG-P members after persongroup creation."""
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        source = f'org:{self.name}:{flag_field}'

        if self.has_accounts:
            # has_accounts=True: persons from PERSON-TREE on this org
            pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
            if pt_type:
                pt_rels = PropRelation.search([
                    ('proprelation_type_id', '=', pt_type.id),
                    ('id_org', '=', self.id),
                    ('is_active', '=', True),
                    ('id_person', '!=', False),
                ])
                processor._sync_pg_p_members(
                    pg, [r.id_person.id for r in pt_rels], source_label=source)
        else:
            # has_accounts=False, has_role=True: persons from BRSO roles
            brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
            ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
            if brso_type and ppsbr_type:
                brso_rels = PropRelation.search([
                    ('proprelation_type_id', '=', brso_type.id),
                    ('id_org_parent', '=', self.id),
                    ('is_active', '=', True),
                    ('id_role', '!=', False),
                ])
                if brso_rels:
                    org_ids = {self.id}
                    if self.inst_nr:
                        same_inst = self.env['myschool.org'].search([
                            ('inst_nr', '=', self.inst_nr),
                            ('is_active', '=', True),
                        ])
                        org_ids.update(same_inst.ids)
                    role_ids = list(set(r.id_role.id for r in brso_rels))
                    ppsbr_rels = PropRelation.search([
                        ('proprelation_type_id', '=', ppsbr_type.id),
                        ('id_role', 'in', role_ids),
                        ('id_org_parent', 'in', list(org_ids)),
                        ('is_active', '=', True),
                        ('id_person', '!=', False),
                    ])
                    person_ids = list(set(r.id_person.id for r in ppsbr_rels))
                    processor._sync_pg_p_members(pg, person_ids, source_label=source)

    def _deactivate_persongroup_by_name(self, group_name):
        """Find and delete a persongroup via MANUAL/ORG/DEL betask."""
        self.ensure_one()
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']

        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        if not pg_type:
            return

        # Search by com_group_name or sec_group_name
        pg = Org.search([
            ('org_type_id', '=', pg_type.id),
            '|',
            ('com_group_name', '=', group_name),
            ('sec_group_name', '=', group_name),
            ('is_active', '=', True),
        ], limit=1)

        if not pg:
            _logger.info(f'[PG-SYNC] Persongroup "{group_name}" not found for deletion')
            return

        # Delete via MANUAL/ORG/DEL betask
        service = self.env['myschool.manual.task.service']
        task_data = {
            'org_id': pg.id,
            'org_name': pg.name,
            'group_name': group_name,
            'source_org_id': self.id,
            'source_org_name': self.name,
        }
        service.create_manual_task('ORG', 'DEL', task_data)
        _logger.info(f'[PG-SYNC] Created MANUAL/ORG/DEL betask for persongroup: {pg.name} (ID: {pg.id})')

    # =========================================================================
    # Recalculate ORG-TREE for Classgroups
    # =========================================================================

    @api.model
    def recalculate_classgroup_org_trees(self):
        """Recalculate ORG-TREE relations and AD/OU properties for all active classgroups.

        For each classgroup:
        1. Resolve the parent org via the OuForClasses CI linked to the school org.
        2. Create ORG-TREE relation.
        3. Populate AD/OU fields (domains, FQDNs, group names, name_tree).
        """
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ConfigItem = self.env['myschool.config.item']

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            org_tree_type = PropRelationType.create({'name': 'ORG-TREE', 'is_active': True})

        # Get CLASSGROUP org type
        classgroup_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        if not classgroup_type:
            _logger.warning('[CG-UPDATE] CLASSGROUP org type NOT FOUND')
            return {'removed': 0, 'created': 0, 'skipped': 0, 'ad_updated': 0, 'errors': ['CLASSGROUP org type not found']}

        classgroups = Org.search([
            ('org_type_id', '=', classgroup_type.id),
            ('is_active', '=', True)
        ])
        _logger.info(f'[CG-UPDATE] Found {len(classgroups)} active classgroups')

        # Remove existing ORG-TREE relations for classgroups
        removed = 0
        if classgroups:
            old_rels = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org', 'in', classgroups.ids),
                ('id_org_parent', '!=', False),
            ])
            removed = len(old_rels)
            _logger.info(f'[CG-UPDATE] Removing {removed} old ORG-TREE relations')
            old_rels.unlink()

        # Cache: inst_nr -> (parent_org, ci_lookup_org) resolved via OuForClasses CI
        parent_cache = {}
        success = 0
        ad_updated = 0
        skipped = 0
        errors = []

        processor = self.env['myschool.betask.processor']

        for cg in classgroups:
            inst_nr = cg.inst_nr
            if inst_nr in parent_cache:
                parent_org, ci_lookup_org = parent_cache[inst_nr]
                _logger.info(f'[CG-UPDATE] Cache hit for inst_nr={inst_nr} -> parent={parent_org.name if parent_org else "None"}')
            else:
                parent_org = None
                ci_lookup_org = None
                # Step 1: Find school org for this inst_nr
                school_org = Org.search([
                    ('inst_nr', '=', inst_nr),
                    ('org_type_id', '!=', classgroup_type.id),
                    ('is_active', '=', True),
                ], limit=1)

                if not school_org:
                    _logger.warning(f'[CG-UPDATE] inst_nr={inst_nr}: NO school_org found')
                    parent_cache[inst_nr] = (None, None)
                    skipped += 1
                    errors.append(f"{cg.name}: no school_org for inst_nr {inst_nr}")
                    continue

                _logger.info(f'[CG-UPDATE] inst_nr={inst_nr}: school_org={school_org.name} '
                    f'(name_short={school_org.name_short}, is_administrative={school_org.is_administrative})')

                # Step 2: Find first non-administrative parent of type SCHOOL
                school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)
                ci_lookup_org = school_org
                if school_org.is_administrative:
                    # Traverse ORG-TREE upward to find first non-admin SCHOOL
                    current = school_org
                    found = False
                    for _depth in range(10):
                        parent_rel = PropRelation.search([
                            ('proprelation_type_id', '=', org_tree_type.id),
                            ('id_org', '=', current.id),
                            ('id_org_parent', '!=', False),
                            ('is_active', '=', True),
                        ], limit=1)
                        if not parent_rel or not parent_rel.id_org_parent:
                            break
                        candidate = parent_rel.id_org_parent
                        if not candidate.is_administrative and school_type and candidate.org_type_id.id == school_type.id:
                            ci_lookup_org = candidate
                            found = True
                            _logger.info(f'[CG-UPDATE]   administrative -> non-admin SCHOOL parent: {ci_lookup_org.name} '
                                f'(name_short={ci_lookup_org.name_short})')
                            break
                        current = candidate
                    if not found:
                        _logger.warning(f'[CG-UPDATE]   no non-admin SCHOOL parent found for {school_org.name_short}')
                elif school_type and school_org.org_type_id.id != school_type.id:
                    _logger.warning(f'[CG-UPDATE]   school_org {school_org.name_short} is not of type SCHOOL')

                # Step 3: Look up OuForClasses CI
                ou_value = ConfigItem.get_ci_value_by_org_and_name(ci_lookup_org.name_short, 'OuForClasses')
                _logger.info(f'[CG-UPDATE]   OuForClasses on {ci_lookup_org.name_short} -> {ou_value!r}')

                # Step 4: Find the org with that name_short as a direct child of ci_lookup_org
                if ou_value:
                    child_rels = PropRelation.search([
                        ('proprelation_type_id', '=', org_tree_type.id),
                        ('id_org_parent', '=', ci_lookup_org.id),
                        ('is_active', '=', True),
                    ])
                    child_org_ids = [r.id_org.id for r in child_rels if r.id_org]

                    if child_org_ids:
                        parent_org = Org.search([
                            ('id', 'in', child_org_ids),
                            ('name_short', '=', ou_value),
                            ('is_active', '=', True),
                        ], limit=1)

                    if parent_org:
                        _logger.info(f'[CG-UPDATE]   parent org -> {parent_org.name} '
                            f'(name_short={parent_org.name_short}, inst_nr={parent_org.inst_nr})')
                    else:
                        _logger.warning(f'[CG-UPDATE]   parent org NOT FOUND as child of {ci_lookup_org.name_short} with name_short={ou_value}')

                parent_cache[inst_nr] = (parent_org, ci_lookup_org)

            if not parent_org or parent_org.id == cg.id:
                skipped += 1
                errors.append(f"{cg.name}: no parent resolved for inst_nr {inst_nr}")
                _logger.warning(f'[CG-UPDATE] SKIPPED {cg.name}: no parent org resolved for inst_nr={inst_nr}')
                continue

            or_p = parent_org.name_tree or parent_org.name
            or_c = cg.name_tree or cg.name
            rel_name = f"ORG-TREE|OrP:{or_p}|Or:{or_c}"

            _logger.info(f'[CG-UPDATE] LINK {cg.name} (inst_nr={inst_nr}) -> {parent_org.name} (name_short={parent_org.name_short}, inst_nr={parent_org.inst_nr})')

            PropRelation.create({
                'name': rel_name,
                'proprelation_type_id': org_tree_type.id,
                'id_org': cg.id,
                'id_org_parent': parent_org.id,
                'is_active': True,
            })
            success += 1

            # Update AD/OU fields for this classgroup
            changes = []
            processor._populate_classgroup_ad_fields(
                cg, parent_org, ci_lookup_org,
                org_tree_type, ConfigItem, changes)
            ad_updated += 1

        _logger.info(f'[CG-UPDATE] DONE: removed={removed}, created={success}, ad_updated={ad_updated}, skipped={skipped}')
        return {'removed': removed, 'created': success, 'skipped': skipped,
                'ad_updated': ad_updated, 'total': len(classgroups), 'errors': errors}
