# -*- coding: utf-8 -*-
"""
Object Browser - Hierarchical Tree View
========================================
Backend model that provides tree data as JSON and handles operations.
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
from .wizards import build_proprelation_name
import logging

_logger = logging.getLogger(__name__)


class ObjectBrowser(models.TransientModel):
    """
    Object Browser - provides tree data and operations for the OWL component.
    """
    _name = 'myschool.object.browser'
    _description = 'Object Browser'

    name = fields.Char(default='Object Browser')

    @staticmethod
    def _icon_url(model, rec_id, write_date):
        """Build a stable URL to a binary ``icon_image`` field. Includes a
        ``unique`` cache-buster bound to ``write_date`` so the browser
        fetches a fresh image after an admin upload."""
        unique = ''
        if write_date:
            unique = write_date.strftime('%Y%m%d%H%M%S')
        return f'/web/image/{model}/{rec_id}/icon_image?unique={unique}'

    # =========================================================================
    # DATA RETRIEVAL
    # =========================================================================

    @api.model
    def get_tree_data(self, search_text='', show_inactive=False, show_administrative=False):
        """Get tree data as JSON for the OWL component."""
        result = {
            'organizations': self._get_org_tree(search_text, show_inactive, show_administrative),
            'roles': self._get_role_list(show_inactive),
        }
        return result

    def _get_org_tree(self, search_text='', show_inactive=False, show_administrative=False):
        """Build organization tree using ORG-TREE proprelations only."""
        if 'myschool.org' not in self.env:
            return []

        Org = self.env['myschool.org']

        # Get all orgs with filters
        domain = []
        if not show_inactive:
            domain.append(('is_active', '=', True))
        if not show_administrative:
            if 'is_administrative' in Org._fields:
                domain.append(('is_administrative', '=', False))
        if search_text:
            domain.append('|')
            domain.append(('name', 'ilike', search_text))
            domain.append(('name_short', 'ilike', search_text))

        all_orgs = Org.search(domain, order='name')
        all_org_ids = set(all_orgs.ids)

        # Build parent-child map from proprelation
        org_children = {}
        org_parent = {}
        processed_relations = set()  # Track processed child-parent pairs to avoid duplicates

        if 'myschool.proprelation' in self.env and 'myschool.proprelation.type' in self.env:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']

            # Get ORG-TREE type - only use this type for building the org hierarchy
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            # Base domain for ORG-TREE relations
            base_domain = []
            if org_tree_type:
                base_domain.append(('proprelation_type_id', '=', org_tree_type.id))
            else:
                _logger.warning("ORG-TREE proprelation type not found, org tree may be incomplete")

            # Pattern 1: id_org (child) + id_org_parent (parent)
            pattern1_domain = base_domain + [
                ('id_org', '!=', False),
                ('id_org_parent', '!=', False),
            ]
            relations = PropRelation.search(pattern1_domain)

            for rel in relations:
                is_active = rel.is_active if hasattr(rel, 'is_active') else True
                if is_active or show_inactive:
                    child_id = rel.id_org.id
                    parent_id = rel.id_org_parent.id

                    # Skip self-references
                    if child_id == parent_id:
                        continue

                    # Skip if already processed this child-parent pair
                    pair_key = (child_id, parent_id)
                    if pair_key in processed_relations:
                        continue
                    processed_relations.add(pair_key)

                    if child_id in all_org_ids:
                        org_parent[child_id] = parent_id
                        if parent_id not in org_children:
                            org_children[parent_id] = []
                        if child_id not in org_children[parent_id]:
                            org_children[parent_id].append(child_id)

            # Pattern 2: id_org_child (child) + id_org_parent (parent)
            pattern2_domain = base_domain + [
                ('id_org_child', '!=', False),
                ('id_org_parent', '!=', False),
            ]
            relations2 = PropRelation.search(pattern2_domain)

            for rel in relations2:
                is_active = rel.is_active if hasattr(rel, 'is_active') else True
                if is_active or show_inactive:
                    child_id = rel.id_org_child.id
                    parent_id = rel.id_org_parent.id

                    # Skip self-references
                    if child_id == parent_id:
                        continue

                    # Skip if already processed this child-parent pair
                    pair_key = (child_id, parent_id)
                    if pair_key in processed_relations:
                        continue
                    processed_relations.add(pair_key)

                    if child_id in all_org_ids:
                        org_parent[child_id] = parent_id
                        if parent_id not in org_children:
                            org_children[parent_id] = []
                        if child_id not in org_children[parent_id]:
                            org_children[parent_id].append(child_id)
        
        # Find root orgs
        root_orgs = [org for org in all_orgs if org.id not in org_parent or org_parent[org.id] not in all_org_ids]

        # Build tree with cycle detection
        org_dict = {org.id: org for org in all_orgs}

        # ----- Bulk-prefetch (Phase A perf-fix) ----------------------------
        # Replace the per-node PERSON-TREE search + per-node CI search_count
        # in ``_build_org_node`` with two batched queries here. Org count
        # was ~ N round-trips before; now it is constant. The dicts are
        # passed through the recursion so each node reads from cache.
        person_tree_by_org = self._prefetch_person_tree_by_org(
            all_org_ids, show_inactive, show_administrative)
        ci_count_by_org = self._prefetch_ci_count_by_org(all_org_ids)
        # Warm Many2one caches the org-node renderer touches per org
        # (org_type_id.name, name_tree). One batched fetch each.
        all_orgs.mapped('org_type_id.name')
        all_orgs.mapped('name_tree')

        tree = []
        for org in root_orgs:
            tree.append(self._build_org_node(
                org, org_dict, org_children, show_inactive, show_administrative,
                visited=set(),
                person_tree_by_org=person_tree_by_org,
                ci_count_by_org=ci_count_by_org))

        return tree

    def _prefetch_person_tree_by_org(self, all_org_ids, show_inactive,
                                     show_administrative):
        """Return ``{org_id: [person-dict, ...]}`` for the orgs in scope.

        Single PropRelation.search + warm Person/Role caches via
        ``mapped()``. Replaces the per-node search in ``_build_org_node``.
        """
        if not all_org_ids:
            return {}
        if 'myschool.proprelation' not in self.env \
                or 'myschool.proprelation.type' not in self.env:
            return {}
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        person_tree_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        if not person_tree_type:
            return {}

        domain = [
            ('proprelation_type_id', '=', person_tree_type.id),
            ('id_org', 'in', list(all_org_ids)),
            ('id_person', '!=', False),
        ]
        if not show_inactive:
            domain.append(('is_active', '=', True))

        rels = PropRelation.search(domain)
        if not rels:
            return {}

        # One batched fetch per related model — beats per-record lazy load.
        # ``is_administrative`` lives on myschool.org only, so it is
        # not prefetched here on the person side.
        persons = rels.mapped('id_person')
        persons.mapped('name')
        persons.mapped('first_name')
        persons.mapped('is_active')
        if 'email_cloud' in persons._fields:
            persons.mapped('email_cloud')
        if 'sap_ref' in persons._fields:
            persons.mapped('sap_ref')
        # Person-type warm-up so icon resolution doesn't trigger N queries.
        if 'person_type_id' in persons._fields:
            persons.mapped('person_type_id.icon_fa_class')
            persons.mapped('person_type_id.icon_image')
            persons.mapped('person_type_id.write_date')
        roles = rels.mapped('id_role')
        roles.mapped('shortname')
        roles.mapped('name')

        by_org = {}
        # (org_id, person_id) -> aggregated dict so multiple PT-rows for
        # the same person under the same org collapse into one entry
        # with a merged role list (mirrors the original loop semantics).
        agg = {}
        for rel in rels:
            person = rel.id_person
            if not person:
                continue
            # ``is_administrative`` is an org-level concept only; the
            # filter is applied where it makes sense (org-tree domain
            # in ``_get_org_tree``). Persons inherit visibility purely
            # from their is_active flag here.
            if not show_inactive and not getattr(person, 'is_active', True):
                continue
            org_id = rel.id_org.id
            pid = person.id
            key = (org_id, pid)
            entry = agg.get(key)
            if entry is None:
                # Build display name from first_name + last_name. Avoid
                # ``person.name`` here — it stores "Achternaam, Voornaam"
                # and would duplicate the first name in the result.
                first = getattr(person, 'first_name', '') or ''
                lastname = getattr(person, 'last_name', '') or person.name or 'Unknown'
                if first and lastname and lastname != 'Unknown':
                    name = f"{first} {lastname}"
                elif first:
                    name = first
                else:
                    name = lastname
                # Per-type visual identity. Prefer uploaded icon, fall
                # back to FA-class, frontend falls further back to the
                # gekleurde initialen-avatar when both are empty.
                pt = getattr(person, 'person_type_id', None)
                p_type_name = (pt.name if pt else '') or ''
                p_icon_fa = (pt.icon_fa_class if pt else '') or ''
                p_color = (pt.icon_color if pt else '') or ''
                p_icon_url = ''
                if pt and getattr(pt, 'icon_image', False):
                    p_icon_url = self._icon_url(
                        'myschool.person.type', pt.id, pt.write_date)
                entry = {
                    'id': pid,
                    'name': name,
                    'lastname': lastname,
                    'type': 'person',
                    'model': 'myschool.person',
                    'org_id': org_id,
                    'person_type': p_type_name,
                    'person_type_icon_fa': p_icon_fa,
                    'person_type_icon_url': p_icon_url,
                    'person_type_color': p_color,
                    'email': getattr(person, 'email_cloud', '') or '',
                    'sap_ref': getattr(person, 'sap_ref', '') or '',
                    'is_active': bool(getattr(person, 'is_active', True)),
                    'roles': [],
                }
                agg[key] = entry
                by_org.setdefault(org_id, []).append(entry)
            if rel.id_role:
                role = rel.id_role
                role_name = role.shortname or role.name
                if role_name and role_name not in entry['roles']:
                    entry['roles'].append(role_name)
        for entries in by_org.values():
            entries.sort(key=lambda e: (e.get('lastname') or '').lower())
        return by_org

    def _prefetch_ci_count_by_org(self, all_org_ids):
        """Return ``{org_id: count}`` for actieve directe Settings Values
        per org. One search_read replaces N search_counts."""
        if not all_org_ids or 'myschool.settings.value' not in self.env:
            return {}
        Value = self.env['myschool.settings.value']
        domain = [
            ('org_id', 'in', list(all_org_ids)),
            ('is_active', '=', True),
        ]
        rows = Value.search_read(domain, ['org_id'])
        counts = {}
        for r in rows:
            org_field = r.get('org_id')
            if org_field:
                org_id = org_field[0] if isinstance(org_field, (list, tuple)) else org_field
                counts[org_id] = counts.get(org_id, 0) + 1
        return counts

    def _get_display_name(self, org):
        """Get display name for org - prefer name_short if available."""
        # Check possible field names for short name
        if hasattr(org, 'name_short') and org.name_short:
            return org.name_short
        if hasattr(org, 'short_name') and org.short_name:
            return org.short_name
        if hasattr(org, 'shortname') and org.shortname:
            return org.shortname
        return org.name

    def _build_org_node(self, org, org_dict, org_children, show_inactive=False,
                        show_administrative=False, visited=None,
                        person_tree_by_org=None, ci_count_by_org=None):
        """Build a single org node with children.

        Persons + CI-counts are read from prefetched dicts (built once
        in ``_get_org_tree``). Falls back to a per-node fetch if a caller
        invokes this without the dicts — preserves the original API for
        any external user.
        """
        # Cycle detection
        if visited is None:
            visited = set()

        if org.id in visited:
            _logger.warning(f"Circular reference detected for org {org.id} ({org.name}), skipping")
            return None

        visited.add(org.id)

        child_ids = org_children.get(org.id, [])
        child_ids = [cid for cid in child_ids if cid in org_dict]
        # Sort children alphabetically by their display name so the tree
        # is stable regardless of proprelation insertion order.
        child_ids.sort(key=lambda cid: (self._get_display_name(org_dict[cid]) or '').lower())

        # ----- persons -------------------------------------------------------
        if person_tree_by_org is None:
            # Backwards-compat path: caller did not prefetch.
            person_tree_by_org = self._prefetch_person_tree_by_org(
                {org.id}, show_inactive, show_administrative)
        persons = person_tree_by_org.get(org.id, [])
        person_count = len(persons)

        # ----- CI count ------------------------------------------------------
        if ci_count_by_org is None:
            ci_count_by_org = self._prefetch_ci_count_by_org({org.id})
        ci_count = ci_count_by_org.get(org.id, 0)

        is_administrative = org.is_administrative if hasattr(org, 'is_administrative') else False
        
        # Use short_name for display
        display_name = self._get_display_name(org)
        
        # Get name_tree for full tree path
        name_tree = org.name_tree if hasattr(org, 'name_tree') and org.name_tree else org.name
        
        # Get org type name for icon differentiation
        org_type_name = ''
        org_type_id = 0
        org_type_icon_fa = ''
        org_type_icon_url = ''
        org_type_color = ''
        if hasattr(org, 'org_type_id') and org.org_type_id:
            ot = org.org_type_id
            org_type_name = ot.name or ''
            org_type_id = ot.id
            org_type_icon_fa = getattr(ot, 'icon_fa_class', '') or ''
            org_type_color = getattr(ot, 'icon_color', '') or ''
            if getattr(ot, 'icon_image', False):
                # write_date is part of the URL so browsers re-fetch
                # when the admin uploads a new icon.
                org_type_icon_url = self._icon_url(
                    'myschool.org.type', ot.id, ot.write_date)

        node = {
            'id': org.id,
            'name': display_name,
            'full_name': org.name,  # Keep full name for tooltips/details
            'name_tree': name_tree,  # Full tree path for display in wizards
            'type': 'org',
            'org_type_id': org_type_id,
            'org_type_name': org_type_name,
            'org_type_icon_fa': org_type_icon_fa,
            'org_type_icon_url': org_type_icon_url,
            'org_type_color': org_type_color,
            'model': 'myschool.org',
            'child_count': len(child_ids),
            'person_count': person_count,
            'ci_count': ci_count,
            'children': [],
            'persons': persons,
            'is_administrative': is_administrative,
        }
        
        for child_id in child_ids:
            if child_id in org_dict and child_id not in visited:
                child_org = org_dict[child_id]
                child_node = self._build_org_node(
                    child_org, org_dict, org_children,
                    show_inactive, show_administrative,
                    visited=visited.copy(),
                    person_tree_by_org=person_tree_by_org,
                    ci_count_by_org=ci_count_by_org)
                if child_node:
                    node['children'].append(child_node)

        return node

    def _get_role_list(self, show_inactive=False):
        """Get flat list of roles."""
        if 'myschool.role' not in self.env:
            return []
        
        Role = self.env['myschool.role']
        domain = []
        if not show_inactive:
            if 'is_active' in Role._fields:
                domain.append(('is_active', '=', True))
        
        roles = Role.search(domain, order='name')
        
        return [{
            'id': role.id,
            'name': role.name,
            'shortname': role.shortname if hasattr(role, 'shortname') else '',
            'type': 'role',
            'model': 'myschool.role',
        } for role in roles]

    @api.model
    def search_persons(self, search_text, limit=50):
        """Search persons by name."""
        if 'myschool.person' not in self.env or not search_text:
            return []
        
        Person = self.env['myschool.person']
        domain = [
            '|',
            ('name', 'ilike', search_text),
            ('first_name', 'ilike', search_text),
        ]
        
        persons = Person.search(domain, limit=limit, order='name')
        
        return [{
            'id': p.id,
            'name': f"{p.first_name} {p.name}" if hasattr(p, 'first_name') and p.first_name else p.name,
            'type': 'person',
            'model': 'myschool.person',
        } for p in persons]

    # =========================================================================
    # OPERATIONS
    # =========================================================================

    @api.model
    def move_org(self, org_id, new_parent_id):
        """Move an organization under a new parent via betask."""
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'UPD', {
            'org_id': org_id,
            'new_parent_id': new_parent_id,
        })
        return True
    
    def _update_name_tree_recursive(self, org_id):
        """Update name_tree for an org and all its descendants."""
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        org = Org.browse(org_id)
        if not org.exists():
            return

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        # Compute new name_tree from ou_fqdn_internal
        if hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
            # Parse the FQDN: ou=pers,ou=bawa,dc=olvp,dc=int
            # Result should be: int.olvp.bawa.pers
            ou_fqdn = org.ou_fqdn_internal.lower()
            components = ou_fqdn.split(',')

            dc_parts = []
            ou_parts = []

            for comp in components:
                comp = comp.strip()
                if comp.startswith('dc='):
                    dc_parts.append(comp[3:])
                elif comp.startswith('ou='):
                    ou_parts.append(comp[3:])
                elif comp.startswith('cn='):
                    ou_parts.append(comp[3:])

            # Reverse DC parts and ou_parts
            dc_parts.reverse()
            ou_parts.reverse()

            # Build name_tree: dc parts first, then ou parts
            parts = dc_parts + ou_parts

            if parts:
                name_tree = '.'.join(parts)
                if org.name_tree != name_tree:
                    service = self.env['myschool.manual.task.service']
                    service.create_manual_task('ORG', 'UPD', {
                        'org_id': org.id,
                        'vals': {'name_tree': name_tree},
                    })
                    _logger.info(f"Updated name_tree for org {org.name_short}: {name_tree}")

        # Update all child orgs recursively (only via ORG-TREE relations)
        child_search_domain = [
            ('id_org_parent', '=', org_id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
        ]
        if org_tree_type:
            child_search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

        child_rels = PropRelation.search(child_search_domain)
        
        for rel in child_rels:
            if rel.id_org:
                # First update child's ou_fqdn based on this org's new ou_fqdn
                child = rel.id_org
                child_short = child.name_short if hasattr(child, 'name_short') and child.name_short else child.name
                
                service = self.env['myschool.manual.task.service']
                child_update = {}
                if hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
                    child_update['ou_fqdn_internal'] = f"ou={child_short.lower()},{org.ou_fqdn_internal.lower()}"
                if hasattr(org, 'ou_fqdn_external') and org.ou_fqdn_external:
                    child_update['ou_fqdn_external'] = f"ou={child_short.lower()},{org.ou_fqdn_external.lower()}"
                if child_update:
                    service.create_manual_task('ORG', 'UPD', {
                        'org_id': child.id,
                        'vals': child_update,
                    })
                
                # Then recursively update name_tree
                self._update_name_tree_recursive(child.id)
    
    def _update_roles_for_org(self, org):
        """Update role names that reference this org."""
        if 'myschool.role' not in self.env:
            return
        
        Role = self.env['myschool.role']
        org_short = org.name_short if hasattr(org, 'name_short') and org.name_short else org.name
        
        # Find roles linked to this org via proprelation
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            role_rels = PropRelation.search([
                ('id_org', '=', org.id),
                ('id_role', '!=', False),
                ('is_active', '=', True),
            ])
            
            for rel in role_rels:
                if rel.id_role:
                    role = rel.id_role
                    # Update proprelation name to reflect new org position
                    if rel.name and 'Or=' in rel.name:
                        new_name = f"Ro={role.shortname if hasattr(role, 'shortname') and role.shortname else role.name}.Or={org_short}"
                        service = self.env['myschool.manual.task.service']
                        service.create_manual_task('PROPRELATION', 'UPD', {
                            'proprelation_id': rel.id,
                            'vals': {'name': new_name},
                        })
                        _logger.info(f"Updated proprelation name for role {role.name}: {new_name}")

    def _would_create_cycle(self, org_id, new_parent_id):
        """Check if moving org under new_parent would create a cycle."""
        if org_id == new_parent_id:
            return True

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        # Walk up from new_parent to see if we reach org_id
        current_id = new_parent_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            if current_id == org_id:
                return True

            # Find parent of current (only via ORG-TREE relations)
            search_domain = [
                ('id_org', '=', current_id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            rel = PropRelation.search(search_domain, limit=1)

            if rel:
                current_id = rel.id_org_parent.id
            else:
                break

        return False

    @api.model
    def move_person_to_org(self, person_id, new_org_id):
        """Move a person to a different organization via betask."""
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'UPD', {
            'person_id': person_id,
            'new_org_id': new_org_id,
        })
        return True

    @api.model
    def remove_person_from_org(self, person_id, org_id):
        """Remove a person from an organization via betask."""
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'DEACT', {
            'person_id': person_id,
            'org_id': org_id,
        })
        return True

    @api.model
    def deactivate_person(self, person_id):
        """Deactivate a person and all related proprelations via betask."""
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'DEACT', {
            'person_id': person_id,
        })
        return True

    @api.model
    def delete_person(self, person_id):
        """Delete a person and all related proprelations via betask."""
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'DEL', {
            'person_id': person_id,
        })
        return True

    @api.model
    def delete_node(self, node_type, node_id):
        """Delete a node (org, persongroup, person, or role)."""
        # ``persongroup`` rows in the members panel are also
        # ``myschool.org`` records — both real PERSONGROUP-type orgs
        # and regular sub-orgs surface there. Route them through the
        # org delete path; the betask handler (and the persongroup
        # short-circuit below) figures out the rest.
        model_map = {
            'org': 'myschool.org',
            'persongroup': 'myschool.org',
            'person': 'myschool.person',
            'role': 'myschool.role',
        }

        model_name = model_map.get(node_type)
        if not model_name or model_name not in self.env:
            raise UserError(f"Unknown node type: {node_type}")

        # Treat persongroup like org for downstream routing.
        if node_type == 'persongroup':
            node_type = 'org'
        
        record = self.env[model_name].browse(node_id)
        if not record.exists():
            raise UserError("Record not found")
        
        # Check for child objects before deleting an organization
        # Skip pre-check for PERSONGROUP orgs — the ORG/DEL betask handles cleanup
        is_persongroup = (
            node_type == 'org'
            and hasattr(record, 'org_type_id')
            and record.org_type_id
            and record.org_type_id.name == 'PERSONGROUP'
        )
        if node_type == 'org' and not is_persongroup and 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']

            # Get ORG-TREE type for checking child orgs
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            # Check for child organizations (only via ORG-TREE relations)
            child_org_domain = [
                ('id_org_parent', '=', node_id),
                ('id_org', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                child_org_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            child_orgs = PropRelation.search(child_org_domain)

            # Check for persons in this org
            persons_in_org = PropRelation.search([
                ('id_org', '=', node_id),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])

            # Build error message if children exist
            errors = []
            if child_orgs:
                child_names = []
                for rel in child_orgs[:5]:  # Show max 5 names
                    if rel.id_org:
                        name = rel.id_org.name_short if hasattr(rel.id_org, 'name_short') and rel.id_org.name_short else rel.id_org.name
                        child_names.append(name)
                more = f" and {len(child_orgs) - 5} more" if len(child_orgs) > 5 else ""
                errors.append(f"{len(child_orgs)} sub-organization(s): {', '.join(child_names)}{more}")

            if persons_in_org:
                person_names = []
                for rel in persons_in_org[:5]:  # Show max 5 names
                    if rel.id_person:
                        name = rel.id_person.name
                        if hasattr(rel.id_person, 'first_name') and rel.id_person.first_name:
                            name = f"{rel.id_person.first_name} {name}"
                        person_names.append(name)
                more = f" and {len(persons_in_org) - 5} more" if len(persons_in_org) > 5 else ""
                errors.append(f"{len(persons_in_org)} person(s): {', '.join(person_names)}{more}")

            if errors:
                org_name = record.name_short if hasattr(record, 'name_short') and record.name_short else record.name
                raise UserError(
                    f"Cannot delete organization '{org_name}' because it contains:\n\n"
                    f"• {chr(10).join('• ' + e for e in errors)[2:]}\n\n"
                    f"Please move or delete these items first."
                )
        
        # Route deletion through betask pipeline
        service = self.env['myschool.manual.task.service']

        if node_type == 'org':
            service.create_manual_task('ORG', 'DEL', {
                'org_id': node_id,
                'org_name': record.name if hasattr(record, 'name') else str(node_id),
            })
            _logger.info(f"Created MANUAL/ORG/DEL betask for org {node_id}")

        elif node_type == 'person':
            # ``delete_node`` is the entry-point for both the tree-view
            # bulk-delete and the multi-select members-panel bulk-delete.
            # Both labels read "Verwijder N items" / "Delete" — so the
            # action must actually DELETE, not deactivate. (The context
            # menu has a separate "Deactivate" entry that routes through
            # ``deactivate_person`` for the soft-delete path.)
            service.create_manual_task('PERSON', 'DEL', {
                'person_id': node_id,
            })
            _logger.info(f"Created MANUAL/PERSON/DEL betask for person {node_id}")

        elif node_type == 'role':
            # Deactivate all proprelations for this role via betask
            if 'myschool.proprelation' in self.env:
                PropRelation = self.env['myschool.proprelation']
                relations = PropRelation.search([
                    '|', '|',
                    ('id_role', '=', node_id),
                    ('id_role_parent', '=', node_id),
                    ('id_role_child', '=', node_id),
                    ('is_active', '=', True),
                ])
                if relations:
                    service.create_manual_task('PROPRELATION', 'DEACT', {
                        'proprelation_ids': relations.ids,
                    })
            record.write({'is_active': False})
            _logger.info(f"Deactivated role {node_id}")
        
        return True

    @api.model
    def bulk_assign_role(self, person_ids, role_id, org_id=None):
        """Assign a role to multiple persons."""
        if 'myschool.proprelation' not in self.env:
            raise UserError("PropRelation model not found")
        
        PropRelation = self.env['myschool.proprelation']
        Role = self.env['myschool.role']
        
        role = Role.browse(role_id)
        if not role.exists():
            raise UserError("Role not found")
        
        count = 0
        for person_id in person_ids:
            # Check if relation already exists
            existing = PropRelation.search([
                ('id_person', '=', person_id),
                ('id_role', '=', role_id),
                ('is_active', '=', True),
            ], limit=1)
            
            if not existing:
                task_data = {
                    'type': 'PPSBR',
                    'person_id': person_id,
                    'role_id': role_id,
                }
                if org_id:
                    task_data['org_id'] = org_id
                service = self.env['myschool.manual.task.service']
                service.create_manual_task('PROPRELATION', 'ADD', task_data)
                count += 1
        
        _logger.info(f"Assigned role {role.name} to {count} persons")
        return count

    @api.model
    def bulk_move_to_org(self, person_ids, org_id):
        """Move multiple persons to an organization."""
        count = 0
        for person_id in person_ids:
            self.move_person_to_org(person_id, org_id)
            count += 1
        return count

    @api.model
    def get_proprelations_for_record(self, model, record_id):
        """Get all proprelations for a given record."""
        if 'myschool.proprelation' not in self.env:
            return []
        
        PropRelation = self.env['myschool.proprelation']
        
        domain = []
        if model == 'myschool.org':
            domain = ['|', '|',
                ('id_org', '=', record_id),
                ('id_org_parent', '=', record_id),
                ('id_org_child', '=', record_id),
            ]
        elif model == 'myschool.person':
            domain = [('id_person', '=', record_id)]
        elif model == 'myschool.role':
            domain = [('id_role', '=', record_id)]
        else:
            return []
        
        relations = PropRelation.search(domain)
        return relations.ids

    @api.model
    def get_ci_relations_for_org(self, org_id):
        """Get all active direct Settings Values for an organization.

        Returns dicts in the legacy shape (id/name/scope/value/value_type/
        description) zodat de bestaande OWL slide-over-template ongewijzigd
        blijft werken. Geërfde + globale waarden worden NIET getoond — die
        zijn via SettingsItem.get(key, org=...) te bevragen.
        """
        if 'myschool.settings.value' not in self.env:
            return []

        Value = self.env['myschool.settings.value']
        values = Value.search([
            ('org_id', '=', org_id),
            ('is_active', '=', True),
        ])

        result = []
        for v in values:
            si = v.settings_item_id
            if not si:
                continue
            # Encrypted values toon ik gemaskeerd zodat de slide-over
            # niet per ongeluk credentials lekt.
            if si.is_encrypted:
                value = '••••••••'
            elif si.value_type == 'string':
                value = v.string_value or ''
            elif si.value_type == 'integer':
                value = str(v.integer_value or 0)
            elif si.value_type == 'boolean':
                value = 'Yes' if v.boolean_value else 'No'
            else:
                value = ''

            result.append({
                'id': v.id,
                'ci_id': si.id,
                'name': si.key,
                'scope': si.scope_kind,
                'type': si.category,
                'value': value,
                'value_type': si.value_type,
                'description': si.description or '',
            })

        return result

    @api.model
    def get_members_for_org(self, org_id, show_inactive=False,
                            show_administrative=False):
        """
        Get all persons and persongroup orgs related to the selected org.
        Returns persons linked via PERSON-TREE proprelation and persongroups via ORG-TREE.

        ``show_administrative`` filters child orgs marked as administrative
        out of the ``persongroups`` list, matching the tree-side filter.
        ``show_inactive`` is currently informational (PERSON-TREE/PG-P
        queries always filter is_active=True; sub-org rows already skip
        inactive orgs).
        """
        result = {
            'persons': [],
            'persongroups': [],
        }

        if not org_id:
            _logger.info("get_members_for_org called with no org_id")
            return result

        _logger.info(f"get_members_for_org called for org_id={org_id} "
                     f"show_admin={show_administrative} show_inactive={show_inactive}")

        # Check if proprelation model exists
        if 'myschool.proprelation' not in self.env:
            _logger.warning("myschool.proprelation model not found in env")
            return result

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Get PERSON-TREE type for filtering persons
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)

        # Get persons linked to this org via PERSON-TREE proprelation only
        person_search_domain = [
            ('id_org', '=', org_id),
            ('id_person', '!=', False),
            ('is_active', '=', True),
        ]
        if person_tree_type:
            person_search_domain.append(('proprelation_type_id', '=', person_tree_type.id))

        person_rels = PropRelation.search(person_search_domain)

        _logger.info(f"Found {len(person_rels)} PERSON-TREE relations for org {org_id}")
        
        person_dict = {}
        for rel in person_rels:
            person = rel.id_person
            if not person:
                continue
            
            # Skip inactive persons
            if hasattr(person, 'is_active') and not person.is_active:
                continue
            
            pid = person.id
            if pid not in person_dict:
                first = getattr(person, 'first_name', '') or ''
                lastname = getattr(person, 'last_name', '') or person.name or 'Unknown'
                if first and lastname and lastname != 'Unknown':
                    name = f"{first} {lastname}"
                elif first:
                    name = first
                else:
                    name = lastname

                email = ''
                if hasattr(person, 'email_cloud') and person.email_cloud:
                    email = person.email_cloud
                elif hasattr(person, 'email') and person.email:
                    email = person.email

                person_type = ''
                p_icon_fa = ''
                p_icon_url = ''
                p_color = ''
                if hasattr(person, 'person_type_id') and person.person_type_id:
                    pt = person.person_type_id
                    person_type = pt.name or ''
                    p_icon_fa = getattr(pt, 'icon_fa_class', '') or ''
                    p_color = getattr(pt, 'icon_color', '') or ''
                    if getattr(pt, 'icon_image', False):
                        p_icon_url = self._icon_url(
                            'myschool.person.type', pt.id, pt.write_date)

                sap_ref = ''
                if hasattr(person, 'sap_ref') and person.sap_ref:
                    sap_ref = person.sap_ref

                person_dict[pid] = {
                    'id': pid,
                    'name': name,
                    'lastname': lastname,
                    'email': email,
                    'person_type': person_type,
                    'person_type_icon_fa': p_icon_fa,
                    'person_type_icon_url': p_icon_url,
                    'person_type_color': p_color,
                    'sap_ref': sap_ref,
                    'is_active': person.is_active if hasattr(person, 'is_active') else True,
                    'model': 'myschool.person',
                    'roles': [],
                }
            
            # Add role if present
            if rel.id_role:
                role = rel.id_role
                role_name = role.shortname if hasattr(role, 'shortname') and role.shortname else role.name
                if role_name and role_name not in person_dict[pid]['roles']:
                    person_dict[pid]['roles'].append(role_name)
        
        # Annotate each person with how many distinct **other** orgs
        # they're actively linked to (across PERSON-TREE, PPSBR, PG-P,
        # …). The UI uses this to suppress "Remove from this Org" when
        # the person has only this single org — for them "Delete" is
        # the only sensible action.
        if person_dict:
            other_org_rels = PropRelation.search([
                ('id_person', 'in', list(person_dict.keys())),
                ('id_org', '!=', False),
                ('id_org', '!=', org_id),
                ('is_active', '=', True),
            ])
            other_orgs_by_person = {}
            for rel in other_org_rels:
                pid = rel.id_person.id
                other_orgs_by_person.setdefault(pid, set()).add(rel.id_org.id)
            for pid, entry in person_dict.items():
                entry['other_active_org_count'] = len(
                    other_orgs_by_person.get(pid, ()))

        result['persons'] = sorted(
            person_dict.values(),
            key=lambda p: (p.get('lastname') or '').lower(),
        )
        _logger.info(f"Returning {len(result['persons'])} persons")

        # Get all child orgs linked to this org (via ORG-TREE).
        # Both PERSONGROUP-type and regular sub-orgs are surfaced in the
        # 'persongroups' list — the UI distinguishes them by org_type_name.
        if 'myschool.org' in self.env:
            Org = self.env['myschool.org']
            PropRelationType = self.env['myschool.proprelation.type']

            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            # Pattern 1: id_org (child) + id_org_parent (parent) = org_id
            pg_search_domain = [
                ('id_org_parent', '=', org_id),
                ('id_org', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                pg_search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            pg_rels = PropRelation.search(pg_search_domain)
            _logger.info(f"Found {len(pg_rels)} ORG-TREE child relations (pattern 1)")

            child_org_ids = set()
            for rel in pg_rels:
                child_org = rel.id_org
                if child_org and child_org.id != org_id:
                    child_org_ids.add(child_org.id)

            # Pattern 2: id_org_child + id_org_parent = org_id
            pg_search_domain2 = [
                ('id_org_parent', '=', org_id),
                ('id_org_child', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                pg_search_domain2.append(('proprelation_type_id', '=', org_tree_type.id))

            pg_rels2 = PropRelation.search(pg_search_domain2)
            _logger.info(f"Found {len(pg_rels2)} ORG-TREE child relations (pattern 2)")

            for rel in pg_rels2:
                if hasattr(rel, 'id_org_child') and rel.id_org_child:
                    child_org = rel.id_org_child
                    if child_org.id != org_id:
                        child_org_ids.add(child_org.id)

            if child_org_ids:
                child_orgs = Org.browse(list(child_org_ids)).sorted(
                    key=lambda o: (
                        (o.name_short if hasattr(o, 'name_short') and o.name_short else o.name) or ''
                    ).lower()
                )
                for sub in child_orgs:
                    if hasattr(sub, 'is_active') and not sub.is_active:
                        continue
                    # Honour the toolbar "Administrative" checkbox —
                    # without this, admin sub-orgs leak into the members
                    # pane even when the tree hides them.
                    if not show_administrative and getattr(sub, 'is_administrative', False):
                        continue

                    display_name = sub.name
                    if hasattr(sub, 'name_short') and sub.name_short:
                        display_name = sub.name_short

                    org_type_name = ''
                    org_type_icon_fa = ''
                    org_type_icon_url = ''
                    org_type_color = ''
                    if hasattr(sub, 'org_type_id') and sub.org_type_id:
                        ot = sub.org_type_id
                        org_type_name = ot.name or ''
                        org_type_icon_fa = getattr(ot, 'icon_fa_class', '') or ''
                        org_type_color = getattr(ot, 'icon_color', '') or ''
                        if getattr(ot, 'icon_image', False):
                            org_type_icon_url = self._icon_url(
                                'myschool.org.type', ot.id, ot.write_date)

                    result['persongroups'].append({
                        'id': sub.id,
                        'name': display_name,
                        'full_name': sub.name,
                        'model': 'myschool.org',
                        'org_type_name': org_type_name,
                        'org_type_icon_fa': org_type_icon_fa,
                        'org_type_icon_url': org_type_icon_url,
                        'org_type_color': org_type_color,
                        'is_persongroup': org_type_name == 'PERSONGROUP',
                    })
        else:
            _logger.warning("myschool.org model not found")

        _logger.info(f"Returning {len(result['persongroups'])} sub-orgs")

        # For PERSONGROUP orgs: also load PG-P members (persons linked via PG-P proprelation)
        if 'myschool.org' in self.env:
            Org = self.env['myschool.org']
            org = Org.browse(org_id)
            if org.exists() and org.org_type_id and org.org_type_id.name == 'PERSONGROUP':
                pgp_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
                if pgp_type:
                    pgp_rels = PropRelation.search([
                        ('id_org', '=', org_id),
                        ('proprelation_type_id', '=', pgp_type.id),
                        ('is_active', '=', True),
                        ('id_person', '!=', False),
                    ])
                    for rel in pgp_rels:
                        person = rel.id_person
                        if not person:
                            continue
                        pid = person.id
                        if pid not in person_dict:
                            first = getattr(person, 'first_name', '') or ''
                            lastname = getattr(person, 'last_name', '') or person.name or 'Unknown'
                            if first and lastname and lastname != 'Unknown':
                                name = f"{first} {lastname}"
                            elif first:
                                name = first
                            else:
                                name = lastname
                            email = ''
                            if hasattr(person, 'email_cloud') and person.email_cloud:
                                email = person.email_cloud
                            pt = person.person_type_id
                            p_icon_fa = (pt.icon_fa_class if pt else '') or ''
                            p_color = (pt.icon_color if pt else '') or ''
                            p_icon_url = ''
                            if pt and getattr(pt, 'icon_image', False):
                                p_icon_url = self._icon_url(
                                    'myschool.person.type', pt.id, pt.write_date)
                            person_dict[pid] = {
                                'id': pid,
                                'name': name,
                                'lastname': lastname,
                                'email': email,
                                'person_type': pt.name if pt else '',
                                'person_type_icon_fa': p_icon_fa,
                                'person_type_icon_url': p_icon_url,
                                'person_type_color': p_color,
                                'sap_ref': person.sap_ref or '',
                                'model': 'myschool.person',
                                'is_active': person.is_active,
                                'roles': [],
                            }
                    result['persons'] = sorted(
                        person_dict.values(),
                        key=lambda p: (p.get('lastname') or '').lower(),
                    )
                    _logger.info(f"Added {len(pgp_rels)} PG-P members for persongroup {org.name}")

        return result
    
    @api.model
    def global_search(self, query):
        """
        Search all object types (orgs, persons, roles) for the given query.
        Returns a list of matching results with type, id, name, and model.
        """
        results = []
        
        if not query or len(query) < 2:
            return results
        
        query_lower = query.lower()
        limit_per_type = 10
        
        # Search organizations
        if 'myschool.org' in self.env:
            Org = self.env['myschool.org']
            orgs = Org.search([
                '|', '|',
                ('name', 'ilike', query),
                ('name_short', 'ilike', query),
                ('inst_nr', 'ilike', query),
            ], limit=limit_per_type)
            
            for org in orgs:
                display_name = org.name_short if hasattr(org, 'name_short') and org.name_short else org.name
                results.append({
                    'id': org.id,
                    'name': display_name,
                    'full_name': org.name,
                    'type': 'org',
                    'model': 'myschool.org',
                })
        
        # Search persons
        if 'myschool.person' in self.env:
            Person = self.env['myschool.person']
            persons = Person.search([
                '|', '|', '|',
                ('name', 'ilike', query),
                ('first_name', 'ilike', query),
                ('email_cloud', 'ilike', query),
                ('sap_ref', 'ilike', query),
            ], limit=limit_per_type)
            
            for person in persons:
                first = getattr(person, 'first_name', '') or ''
                lastname = getattr(person, 'last_name', '') or person.name or 'Unknown'
                if first and lastname and lastname != 'Unknown':
                    name = f"{first} {lastname}"
                elif first:
                    name = first
                else:
                    name = lastname
                results.append({
                    'id': person.id,
                    'name': name,
                    'type': 'person',
                    'model': 'myschool.person',
                })
        
        # Search roles
        if 'myschool.role' in self.env:
            Role = self.env['myschool.role']
            roles = Role.search([
                '|',
                ('name', 'ilike', query),
                ('shortname', 'ilike', query),
            ], limit=limit_per_type)
            
            for role in roles:
                display_name = role.shortname if hasattr(role, 'shortname') and role.shortname else role.name
                results.append({
                    'id': role.id,
                    'name': display_name,
                    'full_name': role.name,
                    'type': 'role',
                    'model': 'myschool.role',
                })

        return results

    # =========================================================================
    # AD-BROWSER (Fase G) — read-only LDAP browse voor de Organisation
    # Manager. De OWL-component roept ``ad_get_ldap_configs`` aan om
    # de config-dropdown te vullen, en ``ad_browse_dn`` om children
    # lazy te laden bij het uitklappen van een tree-node.
    # =========================================================================

    @api.model
    def ad_get_ldap_configs(self):
        """Lijst van actieve LDAP-configs voor de tab-dropdown.

        Returns:
            list of dicts: ``{id, name, environment, base_dn, is_active_directory}``
        """
        configs = self.env['myschool.ldap.server.config'].search(
            [('active', '=', True)], order='sequence, name')
        return [{
            'id': c.id,
            'name': c.name,
            'environment': c.environment,
            'base_dn': c.base_dn,
            'is_active_directory': c.is_active_directory,
        } for c in configs]

    @api.model
    def ad_browse_dn(self, ldap_config_id, dn=None, include_attrs=True):
        """Browse één LDAP-node en return zijn directe children + attrs.

        Bedoeld voor lazy-load: de OWL-component vraagt root op
        (dn=None of dn=base_dn van de config), klikt op een OU-node om
        één extra niveau op te halen, enz.

        Args:
            ldap_config_id: id van myschool.ldap.server.config
            dn: DN om te browsen; None → base_dn van de config
            include_attrs: ook full attribuut-set van de node zelf
                ophalen voor het side-panel

        Returns:
            dict ``{node, children, error}``
                node     = dict {dn, kind, cn, attrs|None}
                children = lijst van dicts {dn, kind, cn, has_children}
                error    = str|None bij failure
        """
        LdapConfig = self.env['myschool.ldap.server.config']
        config = LdapConfig.browse(ldap_config_id).exists()
        if not config:
            return {'error': 'LDAP-config niet gevonden.',
                    'node': None, 'children': []}

        ldap_service = self.env['myschool.ldap.service']
        try:
            ldap_service._check_ldap3_available()
        except Exception as e:
            return {'error': str(e), 'node': None, 'children': []}

        target_dn = (dn or config.base_dn or '').strip()
        if not target_dn:
            return {'error': 'Geen DN opgegeven en config heeft geen base_dn.',
                    'node': None, 'children': []}

        # Attribuut-lijst die we per soort node willen tonen. We
        # vragen alle ad-takeover-relevante attrs op zodat het side-
        # panel meteen useful is.
        attr_list = [
            'distinguishedName', 'objectClass', 'cn', 'ou', 'name',
            'description', 'mail', 'sAMAccountName', 'employeeID',
            'givenName', 'sn', 'displayName', 'userAccountControl',
            'memberOf', 'member', 'groupType',
            'gPLink', 'gPOptions',
        ]

        try:
            with ldap_service._get_connection(config) as conn:
                # Eerst de node zelf (BASE-scope)
                conn.search(target_dn, '(objectClass=*)',
                            search_scope='BASE', attributes=attr_list)
                if not conn.entries:
                    return {'error': f'DN niet gevonden: {target_dn}',
                            'node': None, 'children': []}
                node_entry = conn.entries[0]
                node = self._ad_entry_to_dict(node_entry, include_attrs)

                # Children (ONE-LEVEL scope). Users worden bewust
                # weggelaten uit de tree — die zien we in de members-
                # pane wanneer een OU geselecteerd is. Alleen
                # OUs + groups dus.
                conn.search(target_dn,
                            '(|(objectClass=organizationalUnit)'
                            '(objectClass=group))',
                            search_scope='LEVEL', attributes=attr_list)
                children = []
                for entry in conn.entries:
                    child_dn = self._ad_entry_str(entry, 'distinguishedName')
                    if child_dn and child_dn.lower() == target_dn.lower():
                        continue  # skip de node zelf
                    child = self._ad_entry_to_dict(entry, include_attrs=False)
                    children.append(child)

                # Sort: OUs eerst, dan groups; alfabetisch op cn/ou.
                kind_order = {'ou': 0, 'group': 1, 'other': 9}
                children.sort(key=lambda c: (
                    kind_order.get(c['kind'], 9),
                    (c.get('cn') or '').lower()))

                # Voor elke child: heeft hij subnodes? Quick-check
                # via een aparte LEVEL-search alleen voor OUs.
                # Belangrijk:
                #  - LEVEL excludes de base entry zelf; ELK gereturnde
                #    entry IS een child. Dus check op > 0 (was foutief > 1).
                #  - Filter op (OU OR group) want users zijn niet
                #    zichtbaar in de tree en mogen geen has_children
                #    triggeren.
                for c in children:
                    if c['kind'] != 'ou':
                        c['has_children'] = False
                        continue
                    try:
                        conn.search(c['dn'],
                                    '(|(objectClass=organizationalUnit)'
                                    '(objectClass=group))',
                                    search_scope='LEVEL',
                                    attributes=['distinguishedName'],
                                    size_limit=1)
                        c['has_children'] = bool(conn.entries)
                    except Exception:
                        c['has_children'] = False

                # De node zelf krijgt ook ``has_children`` — handig wanneer
                # de OWL-frontend de node opnieuw fetcht (bv. na selectie)
                # en deze overschrijft in zijn cache; zonder dit veld zou
                # de caret verdwijnen.
                if node and node.get('kind') == 'ou':
                    try:
                        conn.search(target_dn,
                                    '(|(objectClass=organizationalUnit)'
                                    '(objectClass=group))',
                                    search_scope='LEVEL',
                                    attributes=['distinguishedName'],
                                    size_limit=1)
                        node['has_children'] = bool(conn.entries)
                    except Exception:
                        pass

                return {'error': None, 'node': node, 'children': children}
        except Exception as e:
            _logger.exception('[AD-BROWSE] failed for dn=%s', target_dn)
            return {'error': str(e), 'node': None, 'children': []}

    @api.model
    def ad_browse_members(self, ldap_config_id, dn):
        """Return de 'members' van een AD-node:
          * OU    → direct child users + groups (LEVEL-scope search)
          * group → members in het ``member``-attribuut, geresolveerd
                    naar dicts {dn, kind, cn}
          * user  → groepen via ``memberOf``, geresolveerd

        Returns: ``{members: [...], error: str|None}``
        """
        LdapConfig = self.env['myschool.ldap.server.config']
        config = LdapConfig.browse(ldap_config_id).exists()
        if not config:
            return {'error': 'LDAP-config niet gevonden.', 'members': []}
        ldap_service = self.env['myschool.ldap.service']
        try:
            ldap_service._check_ldap3_available()
        except Exception as e:
            return {'error': str(e), 'members': []}

        target_dn = (dn or '').strip()
        if not target_dn:
            return {'error': 'Geen DN opgegeven.', 'members': []}

        try:
            with ldap_service._get_connection(config) as conn:
                # Eerst het kind van de node achterhalen (BASE-search)
                conn.search(target_dn, '(objectClass=*)',
                            search_scope='BASE',
                            attributes=['objectClass', 'member',
                                        'memberOf'])
                if not conn.entries:
                    return {'error': f'DN niet gevonden: {target_dn}',
                            'members': []}
                entry = conn.entries[0]
                kind = self._ad_kind_of(entry)

                if kind == 'ou':
                    return self._ad_members_for_ou(conn, target_dn)
                if kind == 'group':
                    return self._ad_members_for_group(conn, entry)
                if kind == 'user':
                    return self._ad_groups_for_user(conn, entry)
                return {'error': None, 'members': []}
        except Exception as e:
            _logger.exception('[AD-BROWSE] members failed for dn=%s', target_dn)
            return {'error': str(e), 'members': []}

    def _ad_members_for_ou(self, conn, ou_dn):
        """LEVEL-search onder de OU; alleen users + groups."""
        conn.search(ou_dn,
                    '(|(objectClass=group)(&(objectClass=user)'
                    '(!(objectClass=computer))))',
                    search_scope='LEVEL',
                    attributes=['distinguishedName', 'objectClass',
                                'cn', 'mail', 'sAMAccountName'])
        members = []
        for e in conn.entries:
            child_dn = self._ad_entry_str(e, 'distinguishedName')
            if not child_dn or child_dn.lower() == ou_dn.lower():
                continue
            members.append({
                'dn': child_dn,
                'kind': self._ad_kind_of(e),
                'cn': (self._ad_entry_str(e, 'cn')
                       or child_dn.split(',', 1)[0]),
                'mail': self._ad_entry_str(e, 'mail'),
                'sam': self._ad_entry_str(e, 'sAMAccountName'),
            })
        members.sort(key=lambda m: (
            {'group': 0, 'user': 1}.get(m['kind'], 9),
            (m['cn'] or '').lower()))
        return {'error': None, 'members': members}

    def _ad_members_for_group(self, conn, group_entry):
        """Read group.member, resolve elk member-DN naar zijn kind+cn."""
        raw = group_entry['member'].value if 'member' in group_entry else None
        if raw is None:
            return {'error': None, 'members': []}
        dns = raw if isinstance(raw, (list, tuple)) else [raw]
        members = []
        for member_dn in dns:
            if not member_dn:
                continue
            try:
                conn.search(member_dn, '(objectClass=*)',
                            search_scope='BASE',
                            attributes=['objectClass', 'cn', 'mail',
                                        'sAMAccountName'])
                if not conn.entries:
                    continue
                e = conn.entries[0]
                members.append({
                    'dn': member_dn,
                    'kind': self._ad_kind_of(e),
                    'cn': (self._ad_entry_str(e, 'cn')
                           or member_dn.split(',', 1)[0]),
                    'mail': self._ad_entry_str(e, 'mail'),
                    'sam': self._ad_entry_str(e, 'sAMAccountName'),
                })
            except Exception:
                # Member-DN niet meer leesbaar (bv. cross-domain)
                members.append({
                    'dn': member_dn,
                    'kind': 'other',
                    'cn': member_dn.split(',', 1)[0],
                    'mail': '',
                    'sam': '',
                })
        members.sort(key=lambda m: (
            {'group': 0, 'user': 1}.get(m['kind'], 9),
            (m['cn'] or '').lower()))
        return {'error': None, 'members': members}

    def _ad_groups_for_user(self, conn, user_entry):
        """Read user.memberOf en resolve naar groep-info."""
        raw = (user_entry['memberOf'].value
               if 'memberOf' in user_entry else None)
        if raw is None:
            return {'error': None, 'members': []}
        dns = raw if isinstance(raw, (list, tuple)) else [raw]
        members = []
        for group_dn in dns:
            if not group_dn:
                continue
            try:
                conn.search(group_dn, '(objectClass=*)',
                            search_scope='BASE',
                            attributes=['objectClass', 'cn',
                                        'sAMAccountName', 'mail'])
                if not conn.entries:
                    continue
                e = conn.entries[0]
                members.append({
                    'dn': group_dn,
                    'kind': self._ad_kind_of(e),
                    'cn': (self._ad_entry_str(e, 'cn')
                           or group_dn.split(',', 1)[0]),
                    'mail': self._ad_entry_str(e, 'mail'),
                    'sam': self._ad_entry_str(e, 'sAMAccountName'),
                })
            except Exception:
                members.append({
                    'dn': group_dn, 'kind': 'group',
                    'cn': group_dn.split(',', 1)[0],
                    'mail': '', 'sam': '',
                })
        members.sort(key=lambda m: (m['cn'] or '').lower())
        return {'error': None, 'members': members}

    # =========================================================================
    # SS-BROWSER (Fase I6) — Smartschool is flat (geen hiërarchie van OUs).
    # Bestaat uit één lange user-lijst die client-side gefilterd wordt;
    # detail-fetch per username via getUserDetailsByUsername.
    # =========================================================================

    @api.model
    def ss_get_configs(self):
        """Actieve Smartschool-configs voor de SS-browser tenant-dropdown."""
        configs = self.env['myschool.smartschool.config'].search(
            [('active', '=', True)], order='sequence, name')
        return [{
            'id': c.id,
            'name': c.name,
            'platform_url': c.platform_url,
        } for c in configs]

    @api.model
    def ss_list_users(self, config_id):
        """Eén-shot dump van alle users in de SS-tenant via
        getAllAccountsExtended(code='', recursive='1'). Defensieve XML-
        parser (zelfde patroon als ad_takeover._ss_parse_users).
        """
        Config = self.env['myschool.smartschool.config']
        config = Config.browse(config_id).exists()
        if not config:
            return {'error': 'SS-config niet gevonden.', 'users': []}
        svc = self.env['myschool.smartschool.service']
        try:
            client = svc._get_client(config)
            raw = client.service.getAllAccountsExtended(
                accesscode=config.sudo().api_key,
                code='', recursive='1')
        except Exception as e:
            _logger.exception('[SS-BROWSE] list failed')
            return {'error': str(e), 'users': []}

        if isinstance(raw, (int, str)) and str(raw).strip().lstrip('-').isdigit():
            return {'error': f'Smartschool returncode {raw}', 'users': []}

        users = self._ss_parse_users_xml(str(raw))
        # Sort op naam (achternaam, voornaam, username)
        users.sort(key=lambda u: (
            (u.get('name') or u.get('surname') or '').lower(),
            (u.get('firstname') or '').lower(),
            (u.get('username') or '').lower()))
        # DB-match per user
        for u in users:
            match = self._ss_match_db_person(u)
            if match:
                u['matched_person'] = match
        return {'error': None, 'users': users, 'count': len(users)}

    @api.model
    def ss_browse_user(self, config_id, username):
        """Detail-fetch van één SS-user via getUserDetailsByUsername.
        Resultaat parseert dezelfde XML-vorm + DB-match."""
        Config = self.env['myschool.smartschool.config']
        config = Config.browse(config_id).exists()
        if not config:
            return {'error': 'SS-config niet gevonden.', 'user': None}
        svc = self.env['myschool.smartschool.service']
        try:
            client = svc._get_client(config)
            raw = client.service.getUserDetailsByUsername(
                accesscode=config.sudo().api_key, username=username)
        except Exception as e:
            return {'error': str(e), 'user': None}

        if isinstance(raw, (int, str)) and str(raw).strip().lstrip('-').isdigit():
            return {'error': f'Smartschool returncode {raw}', 'user': None}

        # Wrap as a list with single row + parse via shared helper
        parsed = self._ss_parse_users_xml(
            f'<root>{raw}</root>' if not str(raw).strip().startswith('<root')
            else str(raw))
        if not parsed:
            # Soms wordt de detail-XML niet in <row> verpakt; probeer
            # de hele tekst als één user-record te interpreteren.
            parsed = self._ss_parse_users_xml(
                f'<root><row>{raw}</row></root>')
        if not parsed:
            return {'error': 'Kon SS-detail niet parsen.',
                    'user': None, 'raw': str(raw)[:2000]}
        user = parsed[0]
        match = self._ss_match_db_person(user)
        if match:
            user['matched_person'] = match
        return {'error': None, 'user': user}

    @staticmethod
    def _ss_parse_users_xml(xml_text):
        """Identiek defensieve parser als in ad_takeover._ss_parse_users:
        zoekt elke node met <username> en/of <internnumber> als child."""
        if not xml_text or not xml_text.strip():
            return []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
        except Exception:
            return []
        users = []
        for node in root.iter():
            child_tags = {c.tag.lower() for c in node}
            if 'username' not in child_tags and 'internnumber' not in child_tags:
                continue
            user = {}
            for c in node:
                if list(c):
                    continue
                user[c.tag.lower()] = (c.text or '').strip()
            if user.get('username') or user.get('internnumber'):
                users.append(user)
        return users

    def _ss_match_db_person(self, ss_user):
        """SS-user → myschool.person via internnumber (= sap_ref)
        met fallback op email → email_cloud."""
        Person = self.env['myschool.person'].with_context(active_test=False)
        intern = (ss_user.get('internnumber') or '').strip()
        if intern:
            person = Person.search([('sap_ref', '=', intern)], limit=1)
            if person:
                return {
                    'id': person.id,
                    'display_name': person.display_name,
                    'sap_ref': person.sap_ref or '',
                    'email_cloud': person.email_cloud or '',
                    'matched_via': 'internnumber/sap_ref',
                }
        mail = (ss_user.get('email') or '').strip()
        if mail:
            person = Person.search(
                [('email_cloud', '=ilike', mail)], limit=1)
            if person:
                return {
                    'id': person.id,
                    'display_name': person.display_name,
                    'sap_ref': person.sap_ref or '',
                    'email_cloud': person.email_cloud or '',
                    'matched_via': 'email/email_cloud',
                }
        return None

    # =========================================================================
    # CLOUD-BROWSER (Fase I5) — leest Google Workspace via google_directory_
    # service. orgUnitPath is de "DN-equivalent"; groups zijn tenant-flat
    # (geen OU-hiërarchie); users hebben orgUnitPath. Slideover toont
    # full attribute dict; DB-koppeling via externalIds → person.sap_ref.
    # =========================================================================

    @api.model
    def cloud_get_workspace_configs(self):
        """Actieve Google-configs voor de Cloud-browser config-dropdown."""
        configs = self.env['myschool.google.workspace.config'].search(
            [('active', '=', True)], order='sequence, name')
        return [{
            'id': c.id,
            'name': c.name,
            'environment': c.environment,
            'domain': c.domain,
            'customer_id': c.customer_id,
        } for c in configs]

    @api.model
    def cloud_browse_path(self, config_id, org_unit_path=None):
        """Browse één Cloud-node: OU + direct child OUs + users direct
        in deze OU. Groups zijn tenant-flat dus die zitten niet in de
        tree — wel beschikbaar via cloud_browse_members op user/group.
        """
        Config = self.env['myschool.google.workspace.config']
        config = Config.browse(config_id).exists()
        if not config:
            return {'error': 'Google-config niet gevonden.',
                    'node': None, 'children': []}
        gsvc = self.env['myschool.google.directory.service']
        try:
            gsvc._check_google_available()
        except Exception as e:
            return {'error': str(e), 'node': None, 'children': []}

        target_path = (org_unit_path or '/').strip() or '/'
        customer = config.customer_id or 'my_customer'
        try:
            api = gsvc._get_directory_service(config)
            # Node zelf
            if target_path == '/':
                node = {
                    'path': '/',
                    'kind': 'ou',
                    'cn': '/ (root)',
                    'attrs': {'orgUnitPath': '/',
                              'description': 'Tenant root'},
                }
            else:
                # Google's orgunits.get() concatenates ``customer/{id}/orgunits``
                # with the orgUnitPath; een leading slash produceert dan
                # ``orgunits//baple`` → 404 "Org unit not found". List/insert
                # accepteren wel leading-slash, alleen get/patch niet.
                ou = api.orgunits().get(
                    customerId=customer,
                    orgUnitPath=target_path.lstrip('/')).execute()
                node = self._cloud_ou_to_dict(ou, include_attrs=True)
            # Direct child OUs onder dit pad. Users verschijnen NIET
            # in de tree (zelfde gedrag als AD-browser) — die zien we
            # in de members-pane wanneer een OU geselecteerd is.
            resp = api.orgunits().list(
                customerId=customer,
                orgUnitPath=target_path,
                type='children').execute()
            child_ous = resp.get('organizationUnits', []) or []
            children = [self._cloud_ou_to_dict(ou, include_attrs=False)
                        for ou in child_ous]
            children.sort(key=lambda c: (c.get('cn') or '').lower())
            # Altijd True voor OUs — een per-child orgunits.list-probe
            # zou een aparte API-call per child kosten. Bij expand
            # detecteren we 0 children client-side en tonen "no
            # children".
            for c in children:
                c['has_children'] = True
            # De node zelf krijgt ook has_children — defensief tegen
            # cache-overwrite na refetch (zelfde patroon als AD).
            if node and node.get('kind') == 'ou':
                node['has_children'] = bool(children)
            return {'error': None, 'node': node, 'children': children}
        except Exception as e:
            _logger.exception('[CLOUD-BROWSE] failed for path=%s', target_path)
            return {'error': str(e), 'node': None, 'children': []}

    @api.model
    def cloud_browse_members(self, config_id, identifier, kind):
        """Members per kind:
          * ou    → direct users in dit pad
          * group → leden via members.list (api group_email)
          * user  → groep-memberships via groups.list?userKey=
        """
        Config = self.env['myschool.google.workspace.config']
        config = Config.browse(config_id).exists()
        if not config:
            return {'error': 'Google-config niet gevonden.', 'members': []}
        gsvc = self.env['myschool.google.directory.service']
        try:
            gsvc._check_google_available()
        except Exception as e:
            return {'error': str(e), 'members': []}
        customer = config.customer_id or 'my_customer'
        try:
            api = gsvc._get_directory_service(config)
            if kind == 'ou':
                resp = api.users().list(
                    customer=customer,
                    query=f"orgUnitPath='{identifier}'",
                    maxResults=500).execute()
                users = resp.get('users', []) or []
                members = [self._cloud_user_to_dict(u, include_attrs=False)
                           for u in users]
                members.sort(key=lambda m: (m.get('cn') or '').lower())
                return {'error': None, 'members': members}
            if kind == 'group':
                resp = api.members().list(groupKey=identifier,
                                          maxResults=500).execute()
                members_raw = resp.get('members', []) or []
                members = []
                for m in members_raw:
                    members.append({
                        'path': m.get('email') or m.get('id') or '',
                        'kind': ('group' if m.get('type') == 'GROUP'
                                 else 'user'),
                        'cn': m.get('email') or m.get('id') or '',
                        'mail': m.get('email') or '',
                        'role': m.get('role', 'MEMBER'),
                    })
                return {'error': None, 'members': members}
            if kind == 'user':
                # Group-memberships van deze user
                resp = api.groups().list(userKey=identifier,
                                         maxResults=500).execute()
                groups = resp.get('groups', []) or []
                members = []
                for g in groups:
                    members.append({
                        'path': g.get('email') or g.get('id') or '',
                        'kind': 'group',
                        'cn': g.get('name') or g.get('email') or '',
                        'mail': g.get('email') or '',
                    })
                members.sort(key=lambda m: (m.get('cn') or '').lower())
                return {'error': None, 'members': members}
            return {'error': None, 'members': []}
        except Exception as e:
            _logger.exception('[CLOUD-BROWSE] members failed for %s/%s',
                              kind, identifier)
            return {'error': str(e), 'members': []}

    def _cloud_ou_to_dict(self, ou, include_attrs=True):
        result = {
            'path': ou.get('orgUnitPath', ''),
            'kind': 'ou',
            'cn': ou.get('name') or
                  (ou.get('orgUnitPath', '').rsplit('/', 1)[-1] or '/'),
        }
        if include_attrs:
            result['attrs'] = {
                k: str(v) for k, v in ou.items() if v not in (None, '')
            }
        return result

    def _cloud_user_to_dict(self, u, include_attrs=True):
        name = u.get('name') or {}
        cn = (name.get('fullName') if isinstance(name, dict) else '') \
             or u.get('primaryEmail') or u.get('id') or ''
        result = {
            'path': u.get('primaryEmail') or u.get('id') or '',
            'kind': 'user',
            'cn': cn,
            'mail': u.get('primaryEmail') or '',
            'suspended': bool(u.get('suspended')),
        }
        if include_attrs:
            # Flatten alle attrs naar string voor display
            flat = {}
            for k, v in u.items():
                if isinstance(v, (dict, list)):
                    import json as _json
                    try:
                        flat[k] = _json.dumps(v, ensure_ascii=False,
                                              default=str)
                    except Exception:
                        flat[k] = str(v)
                elif v in (None, ''):
                    continue
                else:
                    flat[k] = str(v)
            result['attrs'] = flat
            # DB-match (idem aan AD)
            match = self._cloud_match_db_person(u)
            if match:
                result['matched_person'] = match
        return result

    def _cloud_match_db_person(self, user_dict):
        """Cloud-user → myschool.person via externalIds (sap_ref) of
        primaryEmail."""
        Person = self.env['myschool.person'].with_context(active_test=False)
        # externalIds 'organization' = sap_ref
        sap = ''
        for eid in user_dict.get('externalIds') or []:
            if isinstance(eid, dict) and eid.get('type') == 'organization':
                sap = (eid.get('value') or '').strip()
                break
        if sap:
            person = Person.search([('sap_ref', '=', sap)], limit=1)
            if person:
                return {
                    'id': person.id,
                    'display_name': person.display_name,
                    'sap_ref': person.sap_ref or '',
                    'email_cloud': person.email_cloud or '',
                    'matched_via': 'externalIds/sap_ref',
                }
        mail = (user_dict.get('primaryEmail') or '').strip()
        if mail:
            person = Person.search(
                [('email_cloud', '=ilike', mail)], limit=1)
            if person:
                return {
                    'id': person.id,
                    'display_name': person.display_name,
                    'sap_ref': person.sap_ref or '',
                    'email_cloud': person.email_cloud or '',
                    'matched_via': 'primaryEmail/email_cloud',
                }
        return None

    # Whitelist van attrs die via de inline-edit in de AD-browser
    # gewijzigd mogen worden. Identity-attrs (sAMAccountName,
    # userPrincipalName, employeeID), passwords en account-state
    # (userAccountControl) staan EXPLICIET niet in de lijst —
    # die gaan via de takeover-flow met snapshot/rollback.
    _AD_INLINE_EDITABLE_ATTRS = frozenset({
        'description',
        'displayName',
        'mail',
        'telephoneNumber',
        'title',
        'department',
        'company',
        'physicalDeliveryOfficeName',
        'streetAddress',
        'l',           # city
        'st',          # state/region
        'postalCode',
        'co',          # country (display)
        'wWWHomePage',
    })

    @api.model
    def ad_inline_editable_attrs(self):
        """Whitelist exposeren naar de OWL frontend zodat de pencil-
        icoontjes alleen op de juiste rows verschijnen."""
        return sorted(self._AD_INLINE_EDITABLE_ATTRS)

    @api.model
    def ad_modify_attribute(self, ldap_config_id, dn, attribute, value):
        """LDAP MODIFY_REPLACE op één attribuut. Whitelist-only.

        Lege ``value`` ⇒ MODIFY_DELETE (verwijder het attribuut). Audit-
        entry naar ir.logging zodat er een trail blijft.
        """
        if attribute not in self._AD_INLINE_EDITABLE_ATTRS:
            return {'error': f'Attribuut "{attribute}" is niet inline-'
                             f'editable. Whitelist: '
                             f'{sorted(self._AD_INLINE_EDITABLE_ATTRS)}'}
        LdapConfig = self.env['myschool.ldap.server.config']
        config = LdapConfig.browse(ldap_config_id).exists()
        if not config:
            return {'error': 'LDAP-config niet gevonden.'}
        ldap_service = self.env['myschool.ldap.service']
        try:
            ldap_service._check_ldap3_available()
        except Exception as e:
            return {'error': str(e)}
        try:
            from ldap3 import MODIFY_REPLACE, MODIFY_DELETE
            with ldap_service._get_connection(config) as conn:
                if value is None or str(value).strip() == '':
                    conn.modify(dn, {attribute: [(MODIFY_DELETE, [])]})
                else:
                    conn.modify(dn, {attribute:
                                     [(MODIFY_REPLACE, [str(value)])]})
                result = conn.result or {}
                # result=16 op DELETE = "no such attribute" → niet kritisch
                if result.get('result') not in (0, 16):
                    return {'error': (result.get('description') or
                                      f'LDAP MODIFY mislukt: {result}')}
        except Exception as e:
            _logger.exception('[AD-EDIT] modify failed dn=%s attr=%s',
                              dn, attribute)
            return {'error': str(e)}

        # Audit-trail
        try:
            self.env['ir.logging'].sudo().create({
                'name': 'myschool_admin.ad_browser',
                'type': 'server',
                'level': 'INFO',
                'message': (
                    f'AD inline-edit by user_id={self.env.uid}: '
                    f'dn={dn} attr={attribute} value={value!r} '
                    f'(config={config.name}/{config.environment})'),
                'path': 'object_browser',
                'func': 'ad_modify_attribute',
                'line': '0',
            })
        except Exception:
            pass  # audit is best-effort

        return {'success': True, 'attribute': attribute, 'value': value}

    @api.model
    def ad_list_open_sessions(self, ldap_config_id):
        """Sessies waar de admin findings aan kan toevoegen vanuit de
        AD-browser. Filter: zelfde LDAP-config, niet state=completed.
        """
        Sessions = self.env['myschool.ad.takeover.session']
        sessions = Sessions.search([
            ('ldap_config_id', '=', ldap_config_id),
            ('state', '!=', 'completed'),
        ], order='create_date desc')
        return [{
            'id': s.id,
            'name': s.name,
            'environment': s.environment,
            'current_phase': s.current_phase,
            'finding_count': s.finding_count,
        } for s in sessions]

    @api.model
    def ad_create_finding_from_node(self, session_id, dn,
                                    proposal_kind, payload=None):
        """Maak een takeover-finding voor een AD-node, geïnitieerd
        vanuit de browser. Bedoeld voor quick-actions: DELETE_AFTER,
        RENAME, MOVE.

        Idempotent: als er al een finding bestaat voor (session, source,
        external_id, kind) wordt die UPDATED met het nieuwe voorstel
        ipv een tweede aan te maken (zou de UNIQUE-constraint breken).
        """
        Sessions = self.env['myschool.ad.takeover.session']
        session = Sessions.browse(session_id).exists()
        if not session:
            return {'error': 'Sessie niet gevonden.'}
        if not session.ldap_config_id:
            return {'error': 'Sessie heeft geen LDAP-config.'}

        allowed = ('delete_after', 'rename', 'move', 'membership_add')
        if proposal_kind not in allowed:
            return {'error': f'Voorstel-type "{proposal_kind}" niet toegestaan '
                             f'vanuit browser. Gebruik: {allowed}'}

        # Lees node-attrs voor cn + kind + ad_mail
        ldap_service = self.env['myschool.ldap.service']
        try:
            with ldap_service._get_connection(session.ldap_config_id) as conn:
                conn.search(dn, '(objectClass=*)', search_scope='BASE',
                            attributes=['distinguishedName', 'objectClass',
                                        'cn', 'mail', 'sAMAccountName',
                                        'employeeID'])
                if not conn.entries:
                    return {'error': f'DN niet gevonden: {dn}'}
                entry = conn.entries[0]
        except Exception as e:
            _logger.exception('[QUICK-ACTION] LDAP read failed')
            return {'error': f'LDAP read mislukt: {e}'}

        kind = self._ad_kind_of(entry)
        if kind == 'other':
            return {'error': 'Onbekend object-type — geen voorstel mogelijk.'}
        if proposal_kind == 'delete_after' and kind == 'ou':
            return {'error': 'OUs kunnen niet via DELETE_AFTER worden '
                             'verwijderd (architectural rule).'}

        cn = (self._ad_entry_str(entry, 'cn')
              or self._ad_entry_str(entry, 'sAMAccountName')
              or dn.split(',', 1)[0])
        mail = self._ad_entry_str(entry, 'mail')
        emp = self._ad_entry_str(entry, 'employeeID')

        import json
        Finding = self.env['myschool.ad.takeover.finding']
        existing = Finding.search([
            ('session_id', '=', session.id),
            ('source', '=', 'ad'),
            ('external_id', '=', dn),
            ('kind', '=', kind),
        ], limit=1)

        vals = {
            'proposal_kind': proposal_kind,
            'state': 'proposed',
            'status': ('delete_after_migration'
                       if proposal_kind == 'delete_after'
                       else 'investigate'),
            'risk_level': ('high' if proposal_kind in (
                'delete_after', 'rename', 'move') else 'medium'),
            'last_action_at': fields.Datetime.now(),
            'action_message': (
                f'Voorstel-type "{proposal_kind}" toegevoegd vanuit '
                f'AD-browser.'),
        }
        if payload:
            vals['proposal_payload_json'] = json.dumps(payload)
        vals['notes'] = (existing.notes if existing else '') or ''
        if existing.notes is None or proposal_kind not in (existing.notes or ''):
            vals['notes'] = (
                (vals['notes'] + '\n' if vals['notes'] else '')
                + f'Quick-action vanuit AD-browser: {proposal_kind}.'
            ).strip()

        if existing:
            existing.write(vals)
            finding = existing
        else:
            create_vals = dict(vals, **{
                'session_id': session.id,
                'source': 'ad',
                'external_id': dn,
                'ad_dn': dn,
                'kind': kind,
                'ad_cn': cn,
                'ad_mail': mail or False,
                'sap_ref': emp or False,
                'match_kind': 'unmatched',
            })
            finding = Finding.create(create_vals)
        return {
            'finding_id': finding.id,
            'session_id': session.id,
            'session_name': session.name,
            'state': finding.state,
            'updated': bool(existing),
        }

    @api.model
    def ad_search(self, ldap_config_id, query, limit=200):
        """Vrije substring-search over cn/sAMAccountName/mail/employeeID
        binnen de scope van een config (subtree onder base_dn).

        Returns: ``{matches: [{dn, kind, cn, mail, sam}], truncated: bool,
                    error: str|None}``
        """
        LdapConfig = self.env['myschool.ldap.server.config']
        config = LdapConfig.browse(ldap_config_id).exists()
        if not config:
            return {'error': 'LDAP-config niet gevonden.',
                    'matches': [], 'truncated': False}
        ldap_service = self.env['myschool.ldap.service']
        try:
            ldap_service._check_ldap3_available()
        except Exception as e:
            return {'error': str(e), 'matches': [], 'truncated': False}

        q = (query or '').strip()
        if len(q) < 2:
            return {'error': 'Zoekterm moet minstens 2 tekens lang zijn.',
                    'matches': [], 'truncated': False}
        # LDAP filter-escape: enkele '*' is wildcard, dus we beschermen
        # andere karakters.
        def _esc(s):
            return s.replace('\\', r'\5c').replace('*', r'\2a') \
                    .replace('(', r'\28').replace(')', r'\29') \
                    .replace('\x00', r'\00')
        qf = _esc(q)
        # Search: substring op cn/sAMAccountName/mail/employeeID;
        # filter alleen group/user (geen computers, geen kale OUs —
        # OUs zoek je niet typisch hierdoor).
        ldap_filter = (
            '(&'
            '(|'
            f'(cn=*{qf}*)'
            f'(sAMAccountName=*{qf}*)'
            f'(mail=*{qf}*)'
            f'(employeeID={qf})'
            f'(displayName=*{qf}*)'
            f'(sn=*{qf}*)'
            f'(givenName=*{qf}*)'
            ')'
            '(|(objectClass=group)(&(objectClass=user)(!(objectClass=computer))))'
            ')'
        )
        attr_list = ['distinguishedName', 'objectClass', 'cn',
                     'sAMAccountName', 'mail', 'employeeID']
        try:
            with ldap_service._get_connection(config) as conn:
                conn.search(config.base_dn, ldap_filter,
                            search_scope='SUBTREE',
                            attributes=attr_list,
                            size_limit=max(int(limit) + 1, 10))
                entries = list(conn.entries)
        except Exception as e:
            _logger.exception('[AD-SEARCH] failed: %s', q)
            return {'error': str(e), 'matches': [], 'truncated': False}

        truncated = len(entries) > limit
        if truncated:
            entries = entries[:limit]
        matches = []
        for e in entries:
            dn = self._ad_entry_str(e, 'distinguishedName')
            if not dn:
                continue
            matches.append({
                'dn': dn,
                'kind': self._ad_kind_of(e),
                'cn': self._ad_entry_str(e, 'cn') or dn.split(',', 1)[0],
                'mail': self._ad_entry_str(e, 'mail'),
                'sam': self._ad_entry_str(e, 'sAMAccountName'),
                'employeeID': self._ad_entry_str(e, 'employeeID'),
            })
        # Sorteer: users met sAMAccountName-match eerst (waarschijnlijk
        # exacter), dan alfabetisch op cn
        ql = q.lower()
        def _rank(m):
            if (m['sam'] or '').lower() == ql:
                return (0, '')
            if (m['employeeID'] or '') == q:
                return (1, '')
            if ql in (m['sam'] or '').lower():
                return (2, m['cn'])
            return (3, (m['cn'] or '').lower())
        matches.sort(key=_rank)
        return {'error': None, 'matches': matches, 'truncated': truncated}

    def _ad_kind_of(self, entry):
        try:
            raw = entry['objectClass'].value if 'objectClass' in entry else None
            if raw is None:
                classes = []
            elif isinstance(raw, (list, tuple)):
                classes = [str(c).lower() for c in raw]
            else:
                classes = [str(raw).lower()]
            if 'organizationalunit' in classes:
                return 'ou'
            if 'group' in classes:
                return 'group'
            if 'user' in classes and 'computer' not in classes:
                return 'user'
        except Exception:
            pass
        return 'other'

    @staticmethod
    def _ad_entry_str(entry, attr):
        try:
            v = entry[attr].value if attr in entry else None
        except Exception:
            return ''
        if v is None:
            return ''
        if isinstance(v, list):
            return v[0] if v else ''
        return str(v)

    def _ad_match_db_person(self, entry):
        """Vind de myschool.person die overeenkomt met deze AD-user-entry.

        Probeert in deze volgorde:
          1. employeeID → person.sap_ref (unique, deterministisch)
          2. mail → person.email_cloud
          3. sAMAccountName → res.users.login → person.odoo_user_id

        Returns: dict {id, display_name, sap_ref, email_cloud,
                       person_fqdn_internal, matched_via} of None.
        """
        emp = self._ad_entry_str(entry, 'employeeID')
        mail = self._ad_entry_str(entry, 'mail')
        sam = self._ad_entry_str(entry, 'sAMAccountName')
        Person = self.env['myschool.person'].with_context(active_test=False)
        person = None
        matched_via = None
        if emp:
            person = Person.search([('sap_ref', '=', emp)], limit=1)
            if person:
                matched_via = 'employeeID/sap_ref'
        if not person and mail:
            person = Person.search(
                [('email_cloud', '=ilike', mail)], limit=1)
            if person:
                matched_via = 'mail/email_cloud'
        if not person and sam:
            user = self.env['res.users'].sudo().with_context(
                active_test=False).search(
                [('login', '=ilike', sam)], limit=1)
            if user:
                person = Person.search(
                    [('odoo_user_id', '=', user.id)], limit=1)
                if person:
                    matched_via = 'sAMAccountName/odoo_user.login'
        if not person:
            return None
        return {
            'id': person.id,
            'display_name': person.display_name,
            'sap_ref': person.sap_ref or '',
            'email_cloud': person.email_cloud or '',
            'person_fqdn_internal': person.person_fqdn_internal or '',
            'matched_via': matched_via,
        }

    def _ad_entry_to_dict(self, entry, include_attrs=True):
        """Convert ldap3 entry → JSON-safe dict voor de OWL-frontend."""
        dn = self._ad_entry_str(entry, 'distinguishedName')
        kind = self._ad_kind_of(entry)
        cn = (self._ad_entry_str(entry, 'cn')
              or self._ad_entry_str(entry, 'ou')
              or self._ad_entry_str(entry, 'name')
              or dn.split(',', 1)[0])

        result = {'dn': dn, 'kind': kind, 'cn': cn}
        # DB-koppeling alleen bij volledige load (slideover/select-node)
        # en alleen voor users — OUs/groups hebben hier geen 1-op-1
        # equivalent.
        if include_attrs and kind == 'user':
            match = self._ad_match_db_person(entry)
            if match:
                result['matched_person'] = match
        if include_attrs:
            attrs = {}
            try:
                for name in entry.entry_attributes:
                    val = entry[name].value
                    if isinstance(val, (list, tuple)):
                        # Lijsten naar comma-string voor display; veel-
                        # waarde attrs zoals memberOf blijven leesbaar.
                        try:
                            attrs[name] = '\n'.join(str(v) for v in val)
                        except Exception:
                            attrs[name] = str(val)
                    elif val is None:
                        attrs[name] = ''
                    else:
                        attrs[name] = str(val)
            except Exception:
                pass
            result['attrs'] = attrs
        return result
