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
        """Return ``{org_id: count}`` for active CI relations on each org
        in scope. One search_read replaces N search_counts."""
        if not all_org_ids or 'myschool.ci.relation' not in self.env:
            return {}
        CiRelation = self.env['myschool.ci.relation']
        domain = [('id_org', 'in', list(all_org_ids))]
        if 'isactive' in CiRelation._fields:
            domain.append(('isactive', '=', True))
        rows = CiRelation.search_read(domain, ['id_org'])
        counts = {}
        for r in rows:
            org_field = r.get('id_org')
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
        """Get all active CI relations for an organization."""
        if 'myschool.ci.relation' not in self.env:
            return []
        
        CiRelation = self.env['myschool.ci.relation']
        
        relations = CiRelation.search([
            ('id_org', '=', org_id),
            ('isactive', '=', True)
        ])
        
        result = []
        for rel in relations:
            ci = rel.id_ci
            if ci:
                # Determine value type and get value
                value = ''
                value_type = 'string'
                if ci.string_value:
                    value = ci.string_value
                    value_type = 'string'
                elif ci.integer_value:
                    value = str(ci.integer_value)
                    value_type = 'integer'
                elif ci.boolean_value is not None:
                    value = 'Yes' if ci.boolean_value else 'No'
                    value_type = 'boolean'
                
                result.append({
                    'id': rel.id,
                    'ci_id': ci.id,
                    'name': ci.name,
                    'scope': ci.scope or 'global',
                    'type': ci.type or 'config',
                    'value': value,
                    'value_type': value_type,
                    'description': ci.description or '',
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
