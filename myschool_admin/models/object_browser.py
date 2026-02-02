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
        tree = []
        for org in root_orgs:
            tree.append(self._build_org_node(org, org_dict, org_children, show_inactive, show_administrative, visited=set()))
        
        return tree

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

    def _build_org_node(self, org, org_dict, org_children, show_inactive=False, show_administrative=False, visited=None):
        """Build a single org node with children."""
        # Cycle detection
        if visited is None:
            visited = set()
        
        if org.id in visited:
            _logger.warning(f"Circular reference detected for org {org.id} ({org.name}), skipping")
            return None
        
        visited.add(org.id)
        
        child_ids = org_children.get(org.id, [])
        child_ids = [cid for cid in child_ids if cid in org_dict]
        
        # Get persons - only from PERSON-TREE proprelations
        person_count = 0
        persons = []
        if 'myschool.proprelation' in self.env and 'myschool.proprelation.type' in self.env:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            
            # Get PERSON-TREE type
            person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
            
            person_rel_domain = [
                ('id_org', '=', org.id),
                ('id_person', '!=', False),
            ]
            
            # Filter by PERSON-TREE type if it exists
            if person_tree_type:
                person_rel_domain.append(('proprelation_type_id', '=', person_tree_type.id))
            
            if not show_inactive:
                person_rel_domain.append(('is_active', '=', True))
            
            person_rels = PropRelation.search(person_rel_domain)
            
            person_dict = {}
            for rel in person_rels:
                person = rel.id_person
                
                if not show_administrative and hasattr(person, 'is_administrative') and person.is_administrative:
                    continue
                if not show_inactive and hasattr(person, 'is_active') and not person.is_active:
                    continue
                
                pid = person.id
                if pid not in person_dict:
                    name = person.name or 'Unknown'
                    if hasattr(person, 'first_name') and person.first_name:
                        name = f"{person.first_name} {person.name}"
                    person_dict[pid] = {
                        'id': pid,
                        'name': name,
                        'type': 'person',
                        'model': 'myschool.person',
                        'org_id': org.id,
                        'roles': [],
                        'is_administrative': person.is_administrative if hasattr(person, 'is_administrative') else False,
                    }
                if rel.id_role:
                    role = rel.id_role
                    role_name = role.shortname if hasattr(role, 'shortname') and role.shortname else role.name
                    if role_name not in person_dict[pid]['roles']:
                        person_dict[pid]['roles'].append(role_name)
            
            persons = list(person_dict.values())
            person_count = len(persons)
        
        # Get CI relations count
        ci_count = 0
        if 'myschool.ci.relation' in self.env:
            CiRelation = self.env['myschool.ci.relation']
            ci_count = CiRelation.search_count([
                ('id_org', '=', org.id),
                ('isactive', '=', True)
            ])
        
        is_administrative = org.is_administrative if hasattr(org, 'is_administrative') else False
        
        # Use short_name for display
        display_name = self._get_display_name(org)
        
        # Get name_tree for full tree path
        name_tree = org.name_tree if hasattr(org, 'name_tree') and org.name_tree else org.name
        
        node = {
            'id': org.id,
            'name': display_name,
            'full_name': org.name,  # Keep full name for tooltips/details
            'name_tree': name_tree,  # Full tree path for display in wizards
            'type': 'org',
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
                child_node = self._build_org_node(child_org, org_dict, org_children, show_inactive, show_administrative, visited.copy())
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
        """Move an organization under a new parent using proprelation."""
        if 'myschool.proprelation' not in self.env:
            raise UserError("PropRelation model not found")
        
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        org = Org.browse(org_id)
        new_parent = Org.browse(new_parent_id)
        
        if not org.exists():
            raise UserError("Organization not found")
        if not new_parent.exists():
            raise UserError("New parent organization not found")
        
        # Check for circular reference
        if self._would_create_cycle(org_id, new_parent_id):
            raise UserError("Cannot move: would create circular reference")
        
        # Get or create ORG-TREE proprelation type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'ORG-TREE',
                'usage': 'Organization hierarchy relationship',
                'is_active': True,
            })
        
        # Build the relation name using standardized format
        relation_name = build_proprelation_name(
            'ORG-TREE',
            id_org=org,
            id_org_parent=new_parent
        )
        
        # Find existing parent relation
        existing = PropRelation.search([
            ('id_org', '=', org_id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            # Update existing relation
            existing.write({
                'name': relation_name,
                'proprelation_type_id': org_tree_type.id,
                'id_org_parent': new_parent_id,
            })
        else:
            # Create new relation
            PropRelation.create({
                'name': relation_name,
                'proprelation_type_id': org_tree_type.id,
                'id_org': org_id,
                'id_org_parent': new_parent_id,
                'is_active': True,
            })
        
        # Update ou_fqdn fields based on new parent
        org_short = org.name_short if hasattr(org, 'name_short') and org.name_short else org.name
        if hasattr(new_parent, 'ou_fqdn_internal') and new_parent.ou_fqdn_internal:
            new_ou_internal = f"ou={org_short.lower()},{new_parent.ou_fqdn_internal.lower()}"
            org.write({'ou_fqdn_internal': new_ou_internal})
        
        if hasattr(new_parent, 'ou_fqdn_external') and new_parent.ou_fqdn_external:
            new_ou_external = f"ou={org_short.lower()},{new_parent.ou_fqdn_external.lower()}"
            org.write({'ou_fqdn_external': new_ou_external})
        
        # Update name_tree for this org and all descendants
        self._update_name_tree_recursive(org_id)
        
        # Update role names that reference this org
        self._update_roles_for_org(org)
        
        _logger.info(f"Moved org {org.name} under {new_parent.name}")
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
                    org.write({'name_tree': name_tree})
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
                
                if hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
                    new_child_ou_internal = f"ou={child_short.lower()},{org.ou_fqdn_internal.lower()}"
                    child.write({'ou_fqdn_internal': new_child_ou_internal})
                
                if hasattr(org, 'ou_fqdn_external') and org.ou_fqdn_external:
                    new_child_ou_external = f"ou={child_short.lower()},{org.ou_fqdn_external.lower()}"
                    child.write({'ou_fqdn_external': new_child_ou_external})
                
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
                        rel.write({'name': new_name})
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
        """Move a person to a different organization by updating PERSON-TREE relation."""
        if 'myschool.proprelation' not in self.env:
            raise UserError("PropRelation model not found")
        
        Person = self.env['myschool.person']
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        person = Person.browse(person_id)
        new_org = Org.browse(new_org_id)
        
        if not person.exists():
            raise UserError("Person not found")
        if not new_org.exists():
            raise UserError("Organization not found")
        
        # Get PERSON-TREE type
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        
        # Find existing PERSON-TREE relation for this person
        search_domain = [
            ('id_person', '=', person_id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
        ]
        if person_tree_type:
            search_domain.append(('proprelation_type_id', '=', person_tree_type.id))
        
        existing = PropRelation.search(search_domain)
        
        if existing:
            # Deactivate old PERSON-TREE relations
            existing.write({'is_active': False})
            _logger.info(f"Deactivated {len(existing)} old PERSON-TREE relations for person {person.name}")
        
        # Create new PERSON-TREE relation
        rel_name = f"PERSON-TREE:Pn={person.name},Or={new_org.name_tree or new_org.name}"
        
        proprel_vals = {
            'name': rel_name,
            'id_person': person_id,
            'id_org': new_org_id,
            'is_active': True,
        }
        if person_tree_type:
            proprel_vals['proprelation_type_id'] = person_tree_type.id
        
        PropRelation.create(proprel_vals)
        
        _logger.info(f"Moved person {person.name} to org {new_org.name}")
        return True

    @api.model
    def remove_person_from_org(self, person_id, org_id):
        """Remove a person from an organization (deactivate PERSON-TREE proprelation)."""
        if 'myschool.proprelation' not in self.env:
            raise UserError("PropRelation model not found")
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Get PERSON-TREE type
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        
        # Find and deactivate PERSON-TREE relations
        search_domain = [
            ('id_person', '=', person_id),
            ('id_org', '=', org_id),
            ('is_active', '=', True),
        ]
        if person_tree_type:
            search_domain.append(('proprelation_type_id', '=', person_tree_type.id))
        
        relations = PropRelation.search(search_domain)
        
        if relations:
            relations.write({'is_active': False})
            _logger.info(f"Removed person {person_id} from org {org_id} ({len(relations)} PERSON-TREE relations deactivated)")
        
        return True

    @api.model
    def deactivate_person(self, person_id):
        """Deactivate a person and all related proprelations."""
        if 'myschool.person' not in self.env:
            raise UserError("Person model not found")
        
        Person = self.env['myschool.person']
        person = Person.browse(person_id)
        
        if not person.exists():
            raise UserError("Person not found")
        
        # Get person name for logging
        person_name = person.name
        if hasattr(person, 'first_name') and person.first_name:
            person_name = f"{person.first_name} {person_name}"
        
        # Deactivate the person
        person.write({'is_active': False})
        _logger.info(f"Deactivated person: {person_name} (id={person_id})")
        
        # Deactivate all related proprelations
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            
            # Find all proprelations involving this person
            relations = PropRelation.search([
                '|', '|',
                ('id_person', '=', person_id),
                ('id_person_parent', '=', person_id),
                ('id_person_child', '=', person_id),
                ('is_active', '=', True),
            ])
            
            if relations:
                relations.write({'is_active': False})
                _logger.info(f"Deactivated {len(relations)} proprelations for person {person_id}")
        
        return True

    @api.model
    def delete_person(self, person_id):
        """Delete a person and all related proprelations."""
        if 'myschool.person' not in self.env:
            raise UserError("Person model not found")
        
        Person = self.env['myschool.person']
        person = Person.browse(person_id)
        
        if not person.exists():
            raise UserError("Person not found")
        
        # Get person name for logging/messages
        person_name = person.name
        if hasattr(person, 'first_name') and person.first_name:
            person_name = f"{person.first_name} {person_name}"
        
        # Delete all related proprelations first
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            
            # Find all proprelations involving this person
            relations = PropRelation.search([
                '|', '|',
                ('id_person', '=', person_id),
                ('id_person_parent', '=', person_id),
                ('id_person_child', '=', person_id),
            ])
            
            if relations:
                relation_count = len(relations)
                relations.unlink()
                _logger.info(f"Deleted {relation_count} proprelations for person {person_id}")
        
        # Delete the person
        person.unlink()
        _logger.info(f"Deleted person: {person_name} (id={person_id})")
        
        return True

    @api.model
    def delete_node(self, node_type, node_id):
        """Delete a node (org, person, or role)."""
        model_map = {
            'org': 'myschool.org',
            'person': 'myschool.person',
            'role': 'myschool.role',
        }
        
        model_name = model_map.get(node_type)
        if not model_name or model_name not in self.env:
            raise UserError(f"Unknown node type: {node_type}")
        
        record = self.env[model_name].browse(node_id)
        if not record.exists():
            raise UserError("Record not found")
        
        # Check for child objects before deleting an organization
        if node_type == 'org' and 'myschool.proprelation' in self.env:
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
        
        # Deactivate related proprelations
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            
            if node_type == 'org':
                # Deactivate all proprelations where this org is involved
                relations = PropRelation.search([
                    '|', '|',
                    ('id_org', '=', node_id),
                    ('id_org_parent', '=', node_id),
                    ('id_org_child', '=', node_id),
                    ('is_active', '=', True),
                ])
                if relations:
                    relations.write({'is_active': False})
                    _logger.info(f"Deactivated {len(relations)} proprelations for org {node_id}")
            
            elif node_type == 'person':
                # Deactivate all proprelations where this person is involved
                relations = PropRelation.search([
                    '|', '|',
                    ('id_person', '=', node_id),
                    ('id_person_parent', '=', node_id),
                    ('id_person_child', '=', node_id),
                    ('is_active', '=', True),
                ])
                if relations:
                    relations.write({'is_active': False})
                    _logger.info(f"Deactivated {len(relations)} proprelations for person {node_id}")
                
                # Remove linked Odoo user and HR employee
                if 'user_id' in record._fields and record.user_id:
                    user = record.user_id
                    _logger.info(f"Found linked Odoo user {user.login} (id={user.id}) for person {node_id}")
                    
                    # Remove HR employee linked to this user
                    if 'hr.employee' in self.env:
                        hr_employees = self.env['hr.employee'].search([('user_id', '=', user.id)])
                        if hr_employees:
                            _logger.info(f"Removing {len(hr_employees)} HR employee(s) linked to user {user.id}")
                            hr_employees.unlink()
                    
                    # Archive/deactivate the Odoo user
                    try:
                        user.write({'active': False})
                        _logger.info(f"Deactivated Odoo user {user.login} (id={user.id})")
                    except Exception as e:
                        _logger.warning(f"Could not deactivate user {user.id}: {e}")
            
            elif node_type == 'role':
                # Deactivate all proprelations where this role is involved
                relations = PropRelation.search([
                    '|', '|',
                    ('id_role', '=', node_id),
                    ('id_role_parent', '=', node_id),
                    ('id_role_child', '=', node_id),
                    ('is_active', '=', True),
                ])
                if relations:
                    relations.write({'is_active': False})
                    _logger.info(f"Deactivated {len(relations)} proprelations for role {node_id}")
        
        # Soft delete if is_active field exists, otherwise hard delete
        if 'is_active' in record._fields:
            record.write({'is_active': False})
            _logger.info(f"Deactivated {node_type} {node_id}")
        else:
            record.unlink()
            _logger.info(f"Deleted {node_type} {node_id}")
        
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
                vals = {
                    'id_person': person_id,
                    'id_role': role_id,
                    'is_active': True,
                }
                if org_id:
                    vals['id_org'] = org_id
                PropRelation.create(vals)
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
    def get_members_for_org(self, org_id):
        """
        Get all persons and persongroup orgs related to the selected org.
        Returns persons linked via PERSON-TREE proprelation and persongroups via ORG-TREE.
        """
        result = {
            'persons': [],
            'persongroups': [],
        }

        if not org_id:
            _logger.info("get_members_for_org called with no org_id")
            return result

        _logger.info(f"get_members_for_org called for org_id={org_id}")

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
                name = person.name or 'Unknown'
                if hasattr(person, 'first_name') and person.first_name:
                    name = f"{person.first_name} {person.name}"
                
                email = ''
                if hasattr(person, 'email_cloud') and person.email_cloud:
                    email = person.email_cloud
                elif hasattr(person, 'email') and person.email:
                    email = person.email
                
                person_dict[pid] = {
                    'id': pid,
                    'name': name,
                    'email': email,
                    'model': 'myschool.person',
                    'roles': [],
                }
            
            # Add role if present
            if rel.id_role:
                role = rel.id_role
                role_name = role.shortname if hasattr(role, 'shortname') and role.shortname else role.name
                if role_name and role_name not in person_dict[pid]['roles']:
                    person_dict[pid]['roles'].append(role_name)
        
        result['persons'] = list(person_dict.values())
        _logger.info(f"Returning {len(result['persons'])} persons")
        
        # Get persongroup orgs linked to this org
        # Persongroups are orgs with org_type.name = 'PERSONGROUP' that are children of this org
        if 'myschool.org.type' in self.env and 'myschool.org' in self.env:
            OrgType = self.env['myschool.org.type']
            Org = self.env['myschool.org']
            PropRelationType = self.env['myschool.proprelation.type']

            persongroup_type = OrgType.search([('name', '=ilike', 'PERSONGROUP')], limit=1)
            _logger.info(f"PERSONGROUP type found: {persongroup_type.id if persongroup_type else 'NOT FOUND'}")

            # Get ORG-TREE type for filtering
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            if persongroup_type:
                # Find orgs that are persongroups and are children of this org (via ORG-TREE only)
                # Pattern 1: id_org (child) + id_org_parent (parent) = org_id
                pg_search_domain = [
                    ('id_org_parent', '=', org_id),
                    ('id_org', '!=', False),
                    ('is_active', '=', True),
                ]
                if org_tree_type:
                    pg_search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

                pg_rels = PropRelation.search(pg_search_domain)

                _logger.info(f"Found {len(pg_rels)} potential persongroup relations (pattern 1)")

                persongroup_ids = set()
                for rel in pg_rels:
                    child_org = rel.id_org
                    if child_org and child_org.id != org_id:
                        # Check if this org is a persongroup
                        if hasattr(child_org, 'org_type_id') and child_org.org_type_id:
                            if child_org.org_type_id.id == persongroup_type.id:
                                persongroup_ids.add(child_org.id)
                                _logger.info(f"Found persongroup: {child_org.name} (id={child_org.id})")

                # Pattern 2: id_org_child + id_org_parent = org_id
                pg_search_domain2 = [
                    ('id_org_parent', '=', org_id),
                    ('id_org_child', '!=', False),
                    ('is_active', '=', True),
                ]
                if org_tree_type:
                    pg_search_domain2.append(('proprelation_type_id', '=', org_tree_type.id))

                pg_rels2 = PropRelation.search(pg_search_domain2)

                _logger.info(f"Found {len(pg_rels2)} potential persongroup relations (pattern 2)")

                for rel in pg_rels2:
                    if hasattr(rel, 'id_org_child') and rel.id_org_child:
                        child_org = rel.id_org_child
                        if child_org.id != org_id:
                            if hasattr(child_org, 'org_type_id') and child_org.org_type_id:
                                if child_org.org_type_id.id == persongroup_type.id:
                                    persongroup_ids.add(child_org.id)
                                    _logger.info(f"Found persongroup (pattern 2): {child_org.name} (id={child_org.id})")
                
                if persongroup_ids:
                    persongroups = Org.browse(list(persongroup_ids))
                    for pg in persongroups:
                        if hasattr(pg, 'is_active') and not pg.is_active:
                            continue
                        
                        display_name = pg.name
                        if hasattr(pg, 'name_short') and pg.name_short:
                            display_name = pg.name_short
                        
                        result['persongroups'].append({
                            'id': pg.id,
                            'name': display_name,
                            'full_name': pg.name,
                            'model': 'myschool.org',
                        })
        else:
            _logger.warning("myschool.org.type or myschool.org model not found")
        
        _logger.info(f"Returning {len(result['persongroups'])} persongroups")
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
                name = person.name or 'Unknown'
                if hasattr(person, 'first_name') and person.first_name:
                    name = f"{person.first_name} {person.name}"
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
