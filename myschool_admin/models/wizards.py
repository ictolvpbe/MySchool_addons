# -*- coding: utf-8 -*-
"""
Object Browser Wizards
======================
Wizards for add, move, and bulk operations.
"""

from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


def build_proprelation_name(proprelation_type_name, **kwargs):
    """
    Build a standardized proprelation name.
    
    Format: TYPE:Abbr1=value1,Abbr2=value2,...
    Example: BRSO:Ro=EMPLOYEE,OrP=int.olvp.bawa,Or=int.olvp.bawa.pers.lkr
    
    Field abbreviations:
        id_org -> Or (uses name_tree)
        id_org_parent -> OrP (uses name_tree)
        id_org_child -> OrC (uses name_tree)
        id_period -> Pd (uses name)
        id_period_parent -> PdP (uses name)
        id_period_child -> PdC (uses name)
        id_role -> Ro (uses name)
        id_role_parent -> RoP (uses name)
        id_role_child -> RoC (uses name)
        id_person -> Pn (uses name)
        id_person_parent -> PnP (uses name)
        id_person_child -> PnC (uses name)
    
    Args:
        proprelation_type_name: The type name (e.g., 'BRSO', 'ORG-TREE', 'PERSON-TREE')
        **kwargs: Field values, can be:
            - id_org, id_org_parent, id_org_child: Org records
            - id_role, id_role_parent, id_role_child: Role records
            - id_person, id_person_parent, id_person_child: Person records
            - id_period, id_period_parent, id_period_child: Period records
    
    Returns:
        String like 'BRSO:Ro=EMPLOYEE,OrP=int.olvp.bawa'
    """
    # Field mapping: field_name -> (abbreviation, value_field)
    field_map = {
        'id_org': ('Or', 'name_tree', 'name'),
        'id_org_parent': ('OrP', 'name_tree', 'name'),
        'id_org_child': ('OrC', 'name_tree', 'name'),
        'id_period': ('Pd', 'name', 'name'),
        'id_period_parent': ('PdP', 'name', 'name'),
        'id_period_child': ('PdC', 'name', 'name'),
        'id_role': ('Ro', 'name', 'name'),
        'id_role_parent': ('RoP', 'name', 'name'),
        'id_role_child': ('RoC', 'name', 'name'),
        'id_person': ('Pn', 'name', 'name'),
        'id_person_parent': ('PnP', 'name', 'name'),
        'id_person_child': ('PnC', 'name', 'name'),
    }
    
    # Order of fields in the name (for consistent output)
    field_order = [
        'id_role', 'id_role_parent', 'id_role_child',
        'id_org_parent', 'id_org', 'id_org_child',
        'id_person', 'id_person_parent', 'id_person_child',
        'id_period', 'id_period_parent', 'id_period_child',
    ]
    
    parts = []
    
    for field_name in field_order:
        if field_name in kwargs and kwargs[field_name]:
            record = kwargs[field_name]
            abbr, primary_field, fallback_field = field_map[field_name]
            
            # Get value from record
            value = None
            if hasattr(record, primary_field) and getattr(record, primary_field):
                value = getattr(record, primary_field)
            elif hasattr(record, fallback_field) and getattr(record, fallback_field):
                value = getattr(record, fallback_field)
            elif hasattr(record, 'name'):
                value = record.name
            
            if value:
                parts.append(f"{abbr}={value}")
    
    # Build the full name
    type_prefix = proprelation_type_name.upper() if proprelation_type_name else 'UNKNOWN'
    
    if parts:
        return f"{type_prefix}:{','.join(parts)}"
    return type_prefix


def compute_name_tree(env, org, parent_org=None):
    """
    Compute the name_tree field for an organization.
    
    Format: Start with internal domain and walk down the tree.
    Example: ou=pers,ou=bawa,dc=olvp,dc=int becomes int.olvp.bawa.pers
    
    Args:
        env: Odoo environment
        org: The organization record (or dict with name_short and ou_fqdn_internal)
        parent_org: Optional parent organization (if org not yet saved)
    
    Returns:
        String like 'int.olvp.bawa.pers' or None
    """
    # Helper to get value from org (could be record or dict)
    def get_val(obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None) if obj else None
    
    # If we have an ou_fqdn_internal, parse it
    ou_fqdn = get_val(org, 'ou_fqdn_internal')
    
    if not ou_fqdn and parent_org:
        # Build from parent's FQDN plus new org's name_short
        parent_fqdn = get_val(parent_org, 'ou_fqdn_internal')
        org_short = get_val(org, 'name_short')
        if org_short and parent_fqdn:
            ou_fqdn = f"ou={org_short},{parent_fqdn}"
    
    if not ou_fqdn:
        return None
    
    # Parse the FQDN: ou=pers,ou=bawa,dc=olvp,dc=int
    # Result should be: int.olvp.bawa.pers
    components = ou_fqdn.lower().split(',')
    
    # Extract values, reversing DC components to come first
    dc_parts = []
    ou_parts = []
    
    for comp in components:
        comp = comp.strip()
        if comp.startswith('dc='):
            dc_parts.append(comp[3:])  # Remove 'dc='
        elif comp.startswith('ou='):
            ou_parts.append(comp[3:])  # Remove 'ou='
        elif comp.startswith('cn='):
            ou_parts.append(comp[3:])  # Remove 'cn='
    
    # Reverse DC parts (they go from specific to general in LDAP, but we want domain first)
    dc_parts.reverse()
    
    # Build name_tree: dc parts first, then ou parts (already in correct order - leaf to root)
    # But we want root to leaf for tree display, so reverse ou_parts
    parts = dc_parts + list(reversed(ou_parts))
    
    if parts:
        return '.'.join(parts)
    return None


def update_name_tree_for_org_and_descendants(env, org_id):
    """
    Update name_tree for an organization and all its descendants.
    Also updates role names that reference this org.

    Args:
        env: Odoo environment
        org_id: The organization ID to start from
    """
    if 'myschool.org' not in env or 'myschool.proprelation' not in env:
        return

    Org = env['myschool.org']
    PropRelation = env['myschool.proprelation']
    PropRelationType = env['myschool.proprelation.type']

    org = Org.browse(org_id)
    if not org.exists():
        return

    # Get ORG-TREE type
    org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

    # Update this org's name_tree via betask
    new_name_tree = compute_name_tree(env, org)
    if new_name_tree and org.name_tree != new_name_tree:
        service = env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'UPD', {
            'org_id': org.id,
            'vals': {'name_tree': new_name_tree},
        })
        _logger.info(f"Updated name_tree for org {org.name_short}: {new_name_tree}")

    # Find and update all child orgs recursively (only via ORG-TREE relations)
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
            update_name_tree_for_org_and_descendants(env, rel.id_org.id)
    
    # Update role names that reference this org
    update_role_names_for_org(env, org)


def update_role_names_for_org(env, org):
    """
    Update role names that contain references to this org.
    
    Args:
        env: Odoo environment
        org: The organization record
    """
    if 'myschool.role' not in env:
        return
    
    Role = env['myschool.role']
    org_short = org.name_short if hasattr(org, 'name_short') and org.name_short else org.name
    
    # Find roles that might reference this org in their name
    roles = Role.search([
        '|',
        ('name', 'ilike', org_short),
        ('shortname', 'ilike', org_short),
    ])
    
    # Log found roles for debugging
    if roles:
        _logger.info(f"Found {len(roles)} roles potentially referencing org {org_short}")


class CreatePersonWizard(models.TransientModel):
    """Wizard to create a new person and add to an organization."""
    _name = 'myschool.create.person.wizard'
    _description = 'Create Person'

    # Context
    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    org_fqdn = fields.Char(string='Organization FQDN', readonly=True, 
        help='OU FQDN Internal of the parent organization')
    external_domain = fields.Char(string='External Domain', readonly=True,
        help='External domain for email generation')
    
    # Person fields
    first_name = fields.Char(string='First Name', required=True)
    last_name = fields.Char(string='Last Name', required=True)
    email_cloud = fields.Char(string='Email Cloud', 
        help='Auto-generated cloud email address')
    email_private = fields.Char(string='Email Private',
        help='Private email address')
    
    # Role selection (mutually exclusive)
    person_type = fields.Selection([
        ('employee', 'Employee'),
        ('student_so', 'Student SO'),
        ('student_basis', 'Student Basis'),
    ], string='Person Type', default=False)
    
    # Employee-specific fields
    abbreviation = fields.Char(string='Abbreviation', 
        help='Short abbreviation for the employee')
    sap_ref = fields.Char(string='SAP Ref',
        help='SAP reference number')
    
    # Odoo user linking
    create_odoo_user = fields.Boolean(string='Create Odoo User', default=False,
        help='Create a linked Odoo user account for this person')
    odoo_user_login = fields.Char(string='Login', 
        help='Leave empty to use email as login')
    link_existing_user = fields.Boolean(string='Link Existing User', default=False)
    existing_user_id = fields.Many2one('res.users', string='Existing Odoo User',
        help='Link to an existing Odoo user instead of creating new')
    
    # Debug field
    debug_info = fields.Text(string='Debug Info', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """Set defaults including FQDN from parent org."""
        res = super().default_get(fields_list)
        
        debug_lines = ["=== default_get START ==="]
        
        if 'org_id' in res and res['org_id']:
            org = self.env['myschool.org'].browse(res['org_id'])
            debug_lines.append(f"org_id: {res['org_id']}")
            debug_lines.append(f"org exists: {org.exists()}")
            
            if org.exists():
                res['org_name'] = org.name_tree or org.name
                debug_lines.append(f"org_name: {res['org_name']}")
                
                # Get ou_fqdn_internal from parent org
                parent_org = self._get_parent_org_static(org, debug_lines)
                debug_lines.append(f"parent_org: {parent_org.name if parent_org else 'None'}")
                
                if parent_org and hasattr(parent_org, 'ou_fqdn_internal') and parent_org.ou_fqdn_internal:
                    res['org_fqdn'] = parent_org.ou_fqdn_internal
                    debug_lines.append(f"org_fqdn (from parent): {parent_org.ou_fqdn_internal}")
                elif hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
                    res['org_fqdn'] = org.ou_fqdn_internal
                    debug_lines.append(f"org_fqdn (from org): {org.ou_fqdn_internal}")
                else:
                    debug_lines.append("org_fqdn: NOT FOUND")
                
                # Get domain_external for email generation
                domain_ext = self._get_domain_external_static(org, debug_lines)
                debug_lines.append(f"domain_external result: {domain_ext if domain_ext else 'NOT FOUND'}")
                if domain_ext:
                    res['external_domain'] = domain_ext
        else:
            debug_lines.append("org_id not in res or is empty")
        
        debug_lines.append("=== default_get END ===")
        res['debug_info'] = "\n".join(debug_lines)
        
        return res

    def _get_parent_org_static(self, org, debug_lines=None):
        """Get parent org via ORG-TREE proprelation."""
        if debug_lines is None:
            debug_lines = []

        if not org:
            debug_lines.append("_get_parent_org: org is None")
            return None

        debug_lines.append(f"_get_parent_org: Looking for parent of org.id={org.id}, org.name={org.name}")

        try:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']

            # Get ORG-TREE type
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            # id_org = current org (child), id_org_parent = parent org (only via ORG-TREE)
            search_domain = [
                ('id_org', '=', org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            if parent_rel:
                debug_lines.append(f"_get_parent_org: Found relation id={parent_rel.id}")
                if parent_rel.id_org_parent:
                    debug_lines.append(f"_get_parent_org: Parent is {parent_rel.id_org_parent.name} (id={parent_rel.id_org_parent.id})")
                    return parent_rel.id_org_parent
                else:
                    debug_lines.append("_get_parent_org: id_org_parent is empty")
            else:
                debug_lines.append("_get_parent_org: No ORG-TREE proprelation found with id_org_parent")
        except KeyError:
            debug_lines.append("_get_parent_org: PropRelation model not found")
        except Exception as e:
            debug_lines.append(f"_get_parent_org: Error - {str(e)}")

        return None

    def _get_domain_external_static(self, org, debug_lines=None):
        """Walk up the org hierarchy to find domain_external value."""
        if debug_lines is None:
            debug_lines = []
            
        if not org:
            return None
        
        visited = set()
        current_org = org
        
        while current_org and current_org.id not in visited:
            visited.add(current_org.id)
            
            debug_lines.append(f"_get_domain_external: Checking org.id={current_org.id}, org.name={current_org.name}")
            
            # Check if this org has domain_external
            if hasattr(current_org, 'domain_external') and current_org.domain_external:
                debug_lines.append(f"_get_domain_external: FOUND domain_external={current_org.domain_external}")
                return current_org.domain_external
            else:
                has_field = hasattr(current_org, 'domain_external')
                value = getattr(current_org, 'domain_external', 'N/A') if has_field else 'field not exists'
                debug_lines.append(f"_get_domain_external: domain_external not set (has_field={has_field}, value={value})")
            
            # Try to find parent org via proprelation
            current_org = self._get_parent_org_static(current_org, debug_lines)
            if not current_org:
                debug_lines.append("_get_domain_external: No more parents, stopping")
                break
        
        return None

    def _remove_diacritics(self, text):
        """Remove diacritic characters and replace with normal variants."""
        import unicodedata
        if not text:
            return ''
        # Normalize to decomposed form (NFD), then filter out combining characters
        normalized = unicodedata.normalize('NFD', text)
        # Remove combining diacritical marks
        result = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
        return result

    def _generate_email_standard(self):
        """Generate email address for Employee and Student SO: firstname.lastname@domain."""
        if not self.first_name or not self.last_name or not self.external_domain:
            return ''
        
        # Clean names: remove diacritics and spaces, lowercase
        clean_first = self._remove_diacritics(self.first_name).replace(' ', '').lower()
        clean_last = self._remove_diacritics(self.last_name).replace(' ', '').lower()
        
        return f"{clean_first}.{clean_last}@{self.external_domain}"

    def _generate_email_student_basis(self):
        """Generate email address for Student Basis: b+sap_ref+1631@domain."""
        if not self.sap_ref or not self.external_domain:
            return ''
        
        # Clean sap_ref: remove spaces
        clean_sap_ref = self.sap_ref.replace(' ', '')
        
        return f"b{clean_sap_ref}1631@{self.external_domain}"

    def _update_email(self):
        """Update email based on current role selection."""
        debug_lines = (self.debug_info or "").split("\n")
        debug_lines.append(f"--- _update_email called ---")
        debug_lines.append(f"person_type: {self.person_type}")
        debug_lines.append(f"first_name: {self.first_name}")
        debug_lines.append(f"last_name: {self.last_name}")
        debug_lines.append(f"sap_ref: {self.sap_ref}")
        debug_lines.append(f"external_domain: {self.external_domain}")
        
        if self.person_type in ('employee', 'student_so'):
            # Standard email: firstname.lastname@domain
            email = self._generate_email_standard()
            debug_lines.append(f"Generated standard email: {email}")
            self.email_cloud = email
        elif self.person_type == 'student_basis':
            # Student basis email: b+sap_ref+1631@domain
            email = self._generate_email_student_basis()
            debug_lines.append(f"Generated student_basis email: {email}")
            self.email_cloud = email
        else:
            debug_lines.append("No person_type selected, email cleared")
            self.email_cloud = ''
        
        self.debug_info = "\n".join(debug_lines)

    def _get_role_by_name(self, role_name):
        """Find role by name."""
        try:
            Role = self.env['myschool.role']
            role = Role.search(['|', ('name', '=ilike', role_name), ('shortname', '=ilike', role_name)], limit=1)
            return role
        except KeyError:
            return None

    def _get_or_create_proprelation_type(self, type_name):
        """Get a proprelation type by name (raises if not found)."""
        try:
            PropRelationType = self.env['myschool.proprelation.type']
            rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
            if not rel_type:
                raise UserError(f"PropRelation type '{type_name}' not found. Please create it first.")
            return rel_type
        except KeyError:
            return None

    def _get_parent_orgs(self, org):
        """Get all parent organizations in the tree (including the org itself) via ORG-TREE relations."""
        orgs = [org]
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        current_org = org
        max_depth = 20  # Prevent infinite loops
        depth = 0
        visited_ids = {org.id}  # Track visited orgs to prevent cycles

        _logger.info(f"Starting parent org search for: {org.name} (id={org.id})")

        while current_org and depth < max_depth:
            parent_org = None

            # Search for parent via ORG-TREE relation only
            search_domain = [
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            _logger.info(f"Depth {depth}: Looking for parent of {current_org.name} (id={current_org.id})")
            _logger.info(f"  ORG-TREE search result: {parent_rel.id if parent_rel else 'None'}")

            if parent_rel and parent_rel.id_org_parent:
                parent_org = parent_rel.id_org_parent
                _logger.info(f"  Found parent via ORG-TREE: {parent_org.name} (id={parent_org.id})")

            if parent_org:
                # Avoid cycles
                if parent_org.id in visited_ids:
                    _logger.info(f"  Cycle detected, stopping")
                    break

                visited_ids.add(parent_org.id)
                orgs.append(parent_org)
                _logger.info(f"  Added parent org: {parent_org.name} (id={parent_org.id})")
                current_org = parent_org
            else:
                _logger.info(f"  No more parents found, stopping")
                break
            depth += 1

        _logger.info(f"Final parent orgs list for {org.name}: {[o.name for o in orgs]}")
        return orgs

    def _get_brso_roles_for_orgs(self, orgs):
        """Get all BRSO roles (BACKEND type only) linked to the given organizations."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        RoleType = self.env['myschool.role.type']
        
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            return []
        
        # Get BACKEND role type
        backend_type = RoleType.search([('name', '=', 'BACKEND')], limit=1)
        
        org_ids = [org.id for org in orgs]
        
        # Find BRSO relations for these orgs
        brso_relations = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', 'in', org_ids),
            ('id_role', '!=', False),
            ('is_active', '=', True),
        ])
        
        # Return unique BACKEND roles only
        roles = {}
        for rel in brso_relations:
            if rel.id_role and rel.id_role.id not in roles:
                # Only include BACKEND roles
                if backend_type and rel.id_role.role_type_id and rel.id_role.role_type_id.id == backend_type.id:
                    roles[rel.id_role.id] = rel.id_role
                elif not backend_type:
                    # If no BACKEND type exists, include all roles (fallback)
                    roles[rel.id_role.id] = rel.id_role
        
        return list(roles.values())

    def _find_school_org(self, start_org):
        """
        Find the first parent org of type SCHOOL where is_administrative=False.

        Args:
            start_org: The organization to start searching from

        Returns:
            The school org record or None if not found
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']

        # Get SCHOOL org type
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)
        if not school_type:
            _logger.warning("SCHOOL org type not found")
            return None

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        # Check if start_org itself is a non-administrative school
        if (start_org.org_type_id and
            start_org.org_type_id.id == school_type.id and
            not start_org.is_administrative):
            return start_org

        # Walk up the tree to find a school (only via ORG-TREE relations)
        current_org = start_org
        visited_ids = {current_org.id}
        max_depth = 20

        for _ in range(max_depth):
            # Find parent via ORG-TREE relation only
            search_domain = [
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            if not parent_rel or not parent_rel.id_org_parent:
                break

            parent_org = parent_rel.id_org_parent

            # Avoid cycles
            if parent_org.id in visited_ids:
                break
            visited_ids.add(parent_org.id)

            # Check if this parent is a non-administrative school
            if (parent_org.org_type_id and
                parent_org.org_type_id.id == school_type.id and
                not parent_org.is_administrative):
                _logger.info(f"Found school org: {parent_org.name}")
                return parent_org

            current_org = parent_org

        _logger.warning(f"No school org found for {start_org.name}")
        return None

    def _assign_roles_to_person(self, person):
        """Assign BRSO roles from parent org tree to person via PPSBR relations."""
        PropRelation = self.env['myschool.proprelation']
        
        # Get all parent orgs including current org
        parent_orgs = self._get_parent_orgs(self.org_id)
        _logger.info(f"Parent orgs for {self.org_id.name}: {[o.name for o in parent_orgs]}")
        
        # Get all BRSO roles from these orgs
        roles = self._get_brso_roles_for_orgs(parent_orgs)
        _logger.info(f"BRSO roles to assign: {[r.name for r in roles]}")
        
        if not roles:
            return
        
        # Get or create PPSBR proprelation type
        ppsbr_type = self._get_or_create_proprelation_type('PPSBR')
        if not ppsbr_type:
            _logger.warning("Could not get/create PPSBR proprelation type")
            return
        
        # Find the school org (first parent of type SCHOOL where is_administrative=False)
        school_org = self._find_school_org(self.org_id)
        
        # Create PPSBR relations for each role
        person_name = person.name
        if hasattr(person, 'first_name') and person.first_name:
            person_name = f"{person.first_name} {person_name}"
        
        for role in roles:
            # Check if relation already exists
            existing = PropRelation.search([
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('id_person', '=', person.id),
                ('id_role', '=', role.id),
                ('is_active', '=', True),
            ], limit=1)
            
            if not existing:
                task_data = {
                    'type': 'PPSBR',
                    'person_id': person.id,
                    'role_id': role.id,
                }
                if school_org:
                    task_data['org_parent_id'] = school_org.id
                service = self.env['myschool.manual.task.service']
                service.create_manual_task('PROPRELATION', 'ADD', task_data)
                _logger.info(f"Created PPSBR betask: {role.name} -> {person_name} (school: {school_org.name if school_org else 'None'})")

    @api.onchange('person_type')
    def _onchange_person_type(self):
        """Handle person type selection."""
        debug_lines = (self.debug_info or "").split("\n")
        debug_lines.append(f"--- _onchange_person_type: {self.person_type} ---")
        
        if self.person_type == 'employee':
            self.create_odoo_user = True
            debug_lines.append("create_odoo_user set to True")
        else:
            self.create_odoo_user = False
            debug_lines.append("create_odoo_user set to False")
        
        self.debug_info = "\n".join(debug_lines)
        self._update_email()

    @api.onchange('first_name', 'last_name')
    def _onchange_names(self):
        """Generate email when names change (for employee or student SO)."""
        if self.person_type in ('employee', 'student_so'):
            self._update_email()

    @api.onchange('sap_ref')
    def _onchange_sap_ref(self):
        """Generate email when sap_ref changes (for student basis)."""
        if self.person_type == 'student_basis':
            self._update_email()

    @api.onchange('email_cloud')
    def _onchange_email_cloud(self):
        """Default login to email_cloud."""
        if self.email_cloud and not self.odoo_user_login:
            self.odoo_user_login = self.email_cloud

    @api.onchange('link_existing_user')
    def _onchange_link_existing_user(self):
        """Clear create_odoo_user if linking existing."""
        if self.link_existing_user:
            self.create_odoo_user = False

    @api.onchange('create_odoo_user')
    def _onchange_create_odoo_user(self):
        """Clear link_existing_user if creating new."""
        if self.create_odoo_user:
            self.link_existing_user = False

    def _build_person_task_data(self):
        """Build the data dict for a MANUAL/PERSON/ADD betask from wizard fields."""
        self.ensure_one()

        # Get external_domain (can't rely on readonly field being sent back)
        external_domain = self._get_domain_external_static(self.org_id, [])

        # Generate email based on person type
        email_cloud = None
        if self.person_type in ('employee', 'student_so'):
            if self.first_name and self.last_name and external_domain:
                clean_first = self._remove_diacritics(self.first_name).replace(' ', '').lower()
                clean_last = self._remove_diacritics(self.last_name).replace(' ', '').lower()
                email_cloud = f"{clean_first}.{clean_last}@{external_domain}"
        elif self.person_type == 'student_basis':
            if self.sap_ref and external_domain:
                clean_sap_ref = self.sap_ref.replace(' ', '')
                email_cloud = f"b{clean_sap_ref}1631@{external_domain}"

        # Determine person_type_name
        person_type_name = None
        if self.person_type == 'employee':
            person_type_name = 'EMPLOYEE'
        elif self.person_type in ('student_so', 'student_basis'):
            person_type_name = 'STUDENT'

        data = {
            'first_name': self.first_name,
            'name': self.last_name,
            'org_id': self.org_id.id,
        }
        if email_cloud:
            data['email_cloud'] = email_cloud
        if self.email_private:
            data['email_private'] = self.email_private
        if self.sap_ref:
            data['sap_ref'] = self.sap_ref
        if person_type_name:
            data['person_type_name'] = person_type_name
        if self.person_type == 'employee' and self.abbreviation:
            data['abbreviation'] = self.abbreviation

        # Odoo user linking/creation
        if self.link_existing_user and self.existing_user_id:
            data['link_user_id'] = self.existing_user_id.id
        elif self.create_odoo_user:
            login = self.odoo_user_login or email_cloud
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            data['create_user'] = True
            data['user_login'] = login
            if self.person_type == 'employee':
                data['create_employee'] = True

        return data

    def _assign_org_roles_to_person(self, person_id):
        """Auto-assign roles linked to the org (via BRSO) to the newly created person."""
        if not person_id or not self.org_id:
            return

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            return

        # Find all active BRSO relations for this org
        brso_rels = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', '=', self.org_id.id),
            ('id_role', '!=', False),
            ('is_active', '=', True),
        ])

        service = self.env['myschool.manual.task.service']
        for brso in brso_rels:
            service.create_manual_task('PROPRELATION', 'ADD', {
                'type': 'PPSBR',
                'person_id': person_id,
                'role_id': brso.id_role.id,
                'org_parent_id': brso.id_org_parent.id if brso.id_org_parent else False,
            })

    def action_create(self):
        """Create the person via betask and open the person form."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('PERSON', 'ADD', self._build_person_task_data())

        person_id = self._extract_person_id_from_task(task)
        if person_id:
            # Auto-assign roles from org's BRSO relations
            self._assign_org_roles_to_person(person_id)

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'myschool.person',
                'res_id': person_id,
                'views': [[False, 'form']],
                'target': 'new',
                'context': {'form_view_initial_mode': 'edit'},
            }

        return {'type': 'ir.actions.act_window_close'}

    def action_create_and_close(self):
        """Create person via betask and return to browser."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('PERSON', 'ADD', self._build_person_task_data())

        person_id = self._extract_person_id_from_task(task)
        if person_id:
            self._assign_org_roles_to_person(person_id)

        return {'type': 'ir.actions.act_window_close'}

    def _extract_person_id_from_task(self, task):
        """Try to extract the created person ID from the task's changes field."""
        import re
        if task.changes:
            match = re.search(r'Created person:.*\(ID:\s*(\d+)\)', task.changes)
            if match:
                return int(match.group(1))
        return None


class AddChildOrgWizard(models.TransientModel):
    """Wizard to add a child organization."""
    _name = 'myschool.add.child.org.wizard'
    _description = 'Add Child Organization'

    parent_org_id = fields.Many2one('myschool.org', string='Parent Organization', required=True)
    parent_org_name = fields.Char(string='Parent Organization Name', readonly=True)
    
    # Option 1: Select existing org
    use_existing = fields.Boolean(string='Use Existing Organization', default=False)
    existing_org_id = fields.Many2one('myschool.org', string='Existing Organization')
    
    # Option 2: Create new org (default)
    # Required fields
    new_org_name = fields.Char(string='Full Name', required=True)
    new_org_name_short = fields.Char(string='Short Name', required=True,
        help='Short code/abbreviation for the organization')
    new_org_inst_nr = fields.Char(string='Institution Number', required=True,
        help='Official institution number (inherited from parent by default)',
        compute='_compute_inherited_fields', store=True, readonly=False, precompute=True)
    
    # LDAP OU fields - populated by onchange when has_ou is True
    new_org_ou_fqdn_intern = fields.Char(string='OU FQDN Intern',
        help='Internal LDAP OU path (auto-generated from parent)')
    new_org_ou_fqdn_extern = fields.Char(string='OU FQDN Extern',
        help='External LDAP OU path (auto-generated from parent)')
    
    # Communication group name - populated by onchange when has_comgroup is True
    new_org_com_group_name = fields.Char(string='Communication Group Name',
        help='Auto-generated from organization hierarchy (grp-parent1-parent2-...)')
    new_org_com_group_fqdn_internal = fields.Char(string='Com Group FQDN Internal',
        help='CN=com_group_name,ou_fqdn_internal')
    new_org_com_group_fqdn_external = fields.Char(string='Com Group FQDN External',
        help='CN=com_group_name,ou_fqdn_external')
    
    # Security group name
    new_org_sec_group_name = fields.Char(string='Security Group Name',
        help='Auto-generated from organization hierarchy (bgrp-parent1-parent2-...)')
    new_org_sec_group_fqdn_internal = fields.Char(string='Sec Group FQDN Internal',
        help='CN=sec_group_name,ou_fqdn_internal')
    new_org_sec_group_fqdn_external = fields.Char(string='Sec Group FQDN External',
        help='CN=sec_group_name,ou_fqdn_external')

    # Communication group email
    new_org_com_group_email = fields.Char(string='Com Group Email',
        help='Auto-generated: com_group_name@external_domain')

    # Domain fields (inherited from school)
    new_org_domain_internal = fields.Char(string='Internal Domain')
    new_org_domain_external = fields.Char(string='External Domain')

    # Boolean flags
    new_org_has_ou = fields.Boolean(string='Heeft OU', default=False)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values including parent_org_name, OU FQDN, and domain fields."""
        res = super().default_get(fields_list)
        if 'parent_org_id' in res and res['parent_org_id']:
            parent = self.env['myschool.org'].browse(res['parent_org_id'])
            if parent.exists():
                res['parent_org_name'] = parent.name_tree or parent.name

                # Initialize OU FQDN fields with placeholder (lowercase)
                ou_prefix = "ou=new,"
                if parent.ou_fqdn_internal:
                    res['new_org_ou_fqdn_intern'] = ou_prefix + parent.ou_fqdn_internal.lower()
                else:
                    res['new_org_ou_fqdn_intern'] = ou_prefix
                if parent.ou_fqdn_external:
                    res['new_org_ou_fqdn_extern'] = ou_prefix + parent.ou_fqdn_external.lower()
                else:
                    res['new_org_ou_fqdn_extern'] = ou_prefix

                # Inherit domain from school org
                processor = self.env['myschool.betask.processor']
                school = processor._resolve_parent_school_from_org(parent)
                if school:
                    res['new_org_domain_internal'] = school.domain_internal or parent.domain_internal or ''
                    res['new_org_domain_external'] = school.domain_external or parent.domain_external or ''
                else:
                    res['new_org_domain_internal'] = parent.domain_internal or ''
                    res['new_org_domain_external'] = parent.domain_external or ''
        return res
    
    # Optional fields
    new_org_type_id = fields.Many2one('myschool.org.type', string='Organization Type')
    new_org_description = fields.Text(string='Description')

    def _find_school_org(self):
        """Walk up ORG-TREE from parent_org to find the school org."""
        processor = self.env['myschool.betask.processor']
        return processor._resolve_parent_school_from_org(self.parent_org_id) if self.parent_org_id else None

    @api.depends('parent_org_id')
    def _compute_inherited_fields(self):
        """Auto-inherit inst_nr from parent organization."""
        for wizard in self:
            if wizard.parent_org_id:
                wizard.new_org_inst_nr = wizard.parent_org_id.inst_nr or False
            else:
                wizard.new_org_inst_nr = False
    
    @api.onchange('parent_org_id')
    def _onchange_parent_org_id(self):
        """Initialize OU FQDN fields when parent is set."""
        if self.parent_org_id:
            parent = self.parent_org_id
            short_name = (self.new_org_name_short or 'new').lower()
            ou_prefix = f"ou={short_name},"
            
            # OU FQDN Internal (lowercase)
            if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal.lower()
            else:
                self.new_org_ou_fqdn_intern = ou_prefix
            
            # OU FQDN External (lowercase)
            if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external.lower()
            else:
                self.new_org_ou_fqdn_extern = ou_prefix
    
    def _build_group_name(self, prefix='grp-'):
        """Build group name from org hierarchy.

        Format: <prefix><name_short>-<parent_short>-<grandparent_short>-...
        Excludes: is_administrative=True orgs and orgs with type 'SCHOOLBOARD'

        Args:
            prefix: 'grp-' for communication group, 'bgrp-' for security group
        """
        self.ensure_one()

        parts = []

        # Add current org's name_short
        if self.new_org_name_short:
            parts.append(self.new_org_name_short.lower())

        # Walk up the parent chain (only via ORG-TREE relations)
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        current_org = self.parent_org_id
        visited = set()

        while current_org and current_org.id not in visited:
            visited.add(current_org.id)

            # Check if this org should be excluded
            should_exclude = False

            # Exclude if is_administrative is True
            if hasattr(current_org, 'is_administrative') and current_org.is_administrative:
                should_exclude = True

            # Exclude if org_type is SCHOOLBOARD
            if hasattr(current_org, 'org_type_id') and current_org.org_type_id:
                if current_org.org_type_id.name == 'SCHOOLBOARD':
                    should_exclude = True

            # Add to parts if not excluded
            if not should_exclude:
                short_name = current_org.name_short if hasattr(current_org, 'name_short') and current_org.name_short else current_org.name
                if short_name:
                    parts.append(short_name.lower())

            # Find parent via ORG-TREE proprelation only
            search_domain = [
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            if parent_rel and parent_rel.id_org_parent:
                current_org = parent_rel.id_org_parent
            else:
                break

        if parts:
            return prefix + '-'.join(parts)
        return False

    @api.onchange('new_org_name_short')
    def _onchange_name_short_update_fqdn(self):
        """Update all auto-generated fields when short name changes."""
        if self.parent_org_id and self.new_org_name_short:
            # Force lowercase
            self.new_org_name_short = self.new_org_name_short.lower()
            short_lower = self.new_org_name_short

            parent = self.parent_org_id
            ou_prefix = f"ou={short_lower},"

            # OU FQDN fields
            if parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal.lower()
            else:
                self.new_org_ou_fqdn_intern = ou_prefix
            if parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external.lower()
            else:
                self.new_org_ou_fqdn_extern = ou_prefix

            # Always auto-complete group names
            self.new_org_com_group_name = self._build_group_name('grp-')
            self.new_org_sec_group_name = self._build_group_name('bgrp-')
            self._update_com_group_fqdns()
            self._update_sec_group_fqdns()

            # Com group email
            domain_ext = self.new_org_domain_external or ''
            if self.new_org_com_group_name and domain_ext:
                self.new_org_com_group_email = f"{self.new_org_com_group_name}@{domain_ext}"
            else:
                self.new_org_com_group_email = False
    
    @api.onchange('new_org_has_ou')
    def _onchange_has_ou(self):
        """Recalculate group FQDNs when has_ou checkbox changes."""
        if self.new_org_has_ou:
            self._update_com_group_fqdns()
            self._update_sec_group_fqdns()
    
    def _get_ou_for_groups(self):
        """Get the OuForGroups CI value from the organization hierarchy.
        
        Searches for a CI named 'OuForGroups' linked to the parent org or its ancestors.
        Returns the string value (e.g., 'grp') or None if not found.
        """
        if not self.parent_org_id:
            return None
        
        # Check if CI models exist
        if 'myschool.config.item' not in self.env:
            return None
        
        ConfigItem = self.env['myschool.config.item']
        
        # Try to get via ConfigItem's method if available
        if hasattr(ConfigItem, 'get_ci_value_by_org_and_name'):
            parent_short = self.parent_org_id.name_short if hasattr(self.parent_org_id, 'name_short') else self.parent_org_id.name
            value = ConfigItem.get_ci_value_by_org_and_name(parent_short, 'OuForGroups')
            if value:
                return value
        
        # Fallback: search directly in CiRelation
        if 'myschool.ci.relation' in self.env:
            CiRelation = self.env['myschool.ci.relation']
            PropRelationType = self.env['myschool.proprelation.type']

            # Get ORG-TREE type
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            # Walk up the org hierarchy to find the CI (only via ORG-TREE relations)
            current_org = self.parent_org_id
            visited = set()

            while current_org and current_org.id not in visited:
                visited.add(current_org.id)

                # Search for OuForGroups CI linked to this org
                ci_relation = CiRelation.search([
                    ('id_org', '=', current_org.id),
                    ('id_ci.name', '=', 'OuForGroups'),
                    ('isactive', '=', True)
                ], limit=1)

                if ci_relation and ci_relation.id_ci and ci_relation.id_ci.string_value:
                    return ci_relation.id_ci.string_value

                # Move to parent org via ORG-TREE relation only
                try:
                    PropRelation = self.env['myschool.proprelation']
                    search_domain = [
                        ('id_org', '=', current_org.id),
                        ('id_org_parent', '!=', False),
                        ('is_active', '=', True),
                    ]
                    if org_tree_type:
                        search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

                    parent_rel = PropRelation.search(search_domain, limit=1)
                    current_org = parent_rel.id_org_parent if parent_rel else None
                except KeyError:
                    break

        return None
    
    def _update_com_group_fqdns(self):
        """Update communication group FQDNs based on group name and OU paths.
        
        Format: cn={group_name},ou={OuForGroups},{parent_ou_fqdn}
        Example: cn=grp-lkr-bawa,ou=grp,ou=bawa,dc=olvp,dc=test
        
        Note: Groups are placed under the PARENT org's OU, not the new org's OU.
        All values are lowercase.
        """
        if self.new_org_com_group_name and self.parent_org_id:
            group_name = self.new_org_com_group_name.lower()
            ou_for_groups = self._get_ou_for_groups()
            
            # Get parent's OU FQDN (not the new org's)
            parent_ou_internal = ''
            parent_ou_external = ''
            if hasattr(self.parent_org_id, 'ou_fqdn_internal') and self.parent_org_id.ou_fqdn_internal:
                parent_ou_internal = self.parent_org_id.ou_fqdn_internal.lower()
            if hasattr(self.parent_org_id, 'ou_fqdn_external') and self.parent_org_id.ou_fqdn_external:
                parent_ou_external = self.parent_org_id.ou_fqdn_external.lower()
            
            # Build internal FQDN
            if parent_ou_internal:
                if ou_for_groups:
                    self.new_org_com_group_fqdn_internal = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_internal}"
                else:
                    self.new_org_com_group_fqdn_internal = f"cn={group_name},{parent_ou_internal}"
            else:
                self.new_org_com_group_fqdn_internal = False
            
            # Build external FQDN
            if parent_ou_external:
                if ou_for_groups:
                    self.new_org_com_group_fqdn_external = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_external}"
                else:
                    self.new_org_com_group_fqdn_external = f"cn={group_name},{parent_ou_external}"
            else:
                self.new_org_com_group_fqdn_external = False
        else:
            self.new_org_com_group_fqdn_internal = False
            self.new_org_com_group_fqdn_external = False
    
    def _update_sec_group_fqdns(self):
        """Update security group FQDNs based on group name and OU paths.
        
        Format: cn={group_name},ou={OuForGroups},{parent_ou_fqdn}
        Example: cn=bgrp-lkr-bawa,ou=grp,ou=bawa,dc=olvp,dc=test
        
        Note: Groups are placed under the PARENT org's OU, not the new org's OU.
        All values are lowercase.
        """
        if self.new_org_sec_group_name and self.parent_org_id:
            group_name = self.new_org_sec_group_name.lower()
            ou_for_groups = self._get_ou_for_groups()
            
            # Get parent's OU FQDN (not the new org's)
            parent_ou_internal = ''
            parent_ou_external = ''
            if hasattr(self.parent_org_id, 'ou_fqdn_internal') and self.parent_org_id.ou_fqdn_internal:
                parent_ou_internal = self.parent_org_id.ou_fqdn_internal.lower()
            if hasattr(self.parent_org_id, 'ou_fqdn_external') and self.parent_org_id.ou_fqdn_external:
                parent_ou_external = self.parent_org_id.ou_fqdn_external.lower()
            
            # Build internal FQDN
            if parent_ou_internal:
                if ou_for_groups:
                    self.new_org_sec_group_fqdn_internal = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_internal}"
                else:
                    self.new_org_sec_group_fqdn_internal = f"cn={group_name},{parent_ou_internal}"
            else:
                self.new_org_sec_group_fqdn_internal = False
            
            # Build external FQDN
            if parent_ou_external:
                if ou_for_groups:
                    self.new_org_sec_group_fqdn_external = f"cn={group_name},ou={ou_for_groups.lower()},{parent_ou_external}"
                else:
                    self.new_org_sec_group_fqdn_external = f"cn={group_name},{parent_ou_external}"
            else:
                self.new_org_sec_group_fqdn_external = False
        else:
            self.new_org_sec_group_fqdn_internal = False
            self.new_org_sec_group_fqdn_external = False

    @api.onchange('new_org_name')
    def _onchange_new_org_name(self):
        """Suggest name_short from name (lowercase)."""
        if self.new_org_name and not self.new_org_name_short:
            words = self.new_org_name.split()
            if len(words) > 1:
                self.new_org_name_short = ''.join(w[0] for w in words if w).lower()
            else:
                self.new_org_name_short = self.new_org_name[:10].lower()

    def _build_org_task_data(self):
        """Build the data dict for a MANUAL/ORG/ADD betask from wizard fields."""
        self.ensure_one()

        Org = self.env['myschool.org']

        data = {'parent_org_id': self.parent_org_id.id}

        if self.use_existing:
            if not self.existing_org_id:
                raise UserError("Please select an existing organization")
            data['existing_org_id'] = self.existing_org_id.id
        else:
            if not self.new_org_name:
                raise UserError("Please enter a name for the new organization")
            if not self.new_org_name_short:
                raise UserError("Please enter a short name for the organization")
            if not self.new_org_inst_nr:
                raise UserError("Please enter an institution number")

            data['name'] = self.new_org_name
            data['name_short'] = self.new_org_name_short.lower()
            data['inst_nr'] = self.new_org_inst_nr

            # Domain fields (inherited from school)
            if self.new_org_domain_internal:
                data['domain_internal'] = self.new_org_domain_internal
            if self.new_org_domain_external:
                data['domain_external'] = self.new_org_domain_external

            # OU FQDN fields
            if self.new_org_ou_fqdn_intern:
                data['ou_fqdn_internal'] = self.new_org_ou_fqdn_intern
            if self.new_org_ou_fqdn_extern:
                data['ou_fqdn_external'] = self.new_org_ou_fqdn_extern

            # Com group fields (always set)
            if self.new_org_com_group_name:
                data['com_group_name'] = self.new_org_com_group_name
            if self.new_org_com_group_email:
                data['com_group_email'] = self.new_org_com_group_email
            if self.new_org_com_group_fqdn_internal:
                data['com_group_fqdn_internal'] = self.new_org_com_group_fqdn_internal
            if self.new_org_com_group_fqdn_external:
                data['com_group_fqdn_external'] = self.new_org_com_group_fqdn_external

            # Sec group fields (always set)
            if self.new_org_sec_group_name:
                data['sec_group_name'] = self.new_org_sec_group_name
            if self.new_org_sec_group_fqdn_internal:
                data['sec_group_fqdn_internal'] = self.new_org_sec_group_fqdn_internal
            if self.new_org_sec_group_fqdn_external:
                data['sec_group_fqdn_external'] = self.new_org_sec_group_fqdn_external

            # Boolean flags — always enable comgroup and secgroup
            data['has_ou'] = self.new_org_has_ou
            data['has_role'] = True
            data['has_comgroup'] = True
            data['has_secgroup'] = True

            # name_tree
            if self.new_org_ou_fqdn_intern:
                name_tree = compute_name_tree(
                    self.env,
                    {'name_short': self.new_org_name_short, 'ou_fqdn_internal': self.new_org_ou_fqdn_intern},
                    None,
                )
                if name_tree:
                    data['name_tree'] = name_tree

            if self.new_org_type_id:
                data['org_type_id'] = self.new_org_type_id.id

        return data

    def action_add(self):
        """Add the child organization via betask and open it for editing."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('ORG', 'ADD', self._build_org_task_data())

        # Try to extract the org ID from the task changes for immediate mode
        org_id = self._extract_org_id_from_task(task)
        if org_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'myschool.org',
                'res_id': org_id,
                'views': [[False, 'form']],
                'target': 'new',
                'context': {'form_view_initial_mode': 'edit'},
            }

        return {'type': 'ir.actions.act_window_close'}

    def action_add_and_close(self):
        """Add org via betask and return to browser."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'ADD', self._build_org_task_data())

        return {'type': 'ir.actions.act_window_close'}

    def _extract_org_id_from_task(self, task):
        """Try to extract the created org ID from the task's changes field."""
        import re
        if task.changes:
            match = re.search(r'Created org:.*\(ID:\s*(\d+)\)', task.changes)
            if match:
                return int(match.group(1))
        # For existing org attachment, try to get from data
        if task.data:
            try:
                import json
                data = json.loads(task.data)
                if data.get('existing_org_id'):
                    return data['existing_org_id']
            except (json.JSONDecodeError, TypeError):
                pass
        return None


class MoveOrgWizard(models.TransientModel):
    """Wizard to move an organization to a new parent."""
    _name = 'myschool.move.org.wizard'
    _description = 'Move Organization'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    new_parent_id = fields.Many2one('myschool.org', string='New Parent Organization')
    move_to_root = fields.Boolean(string='Move to Root (no parent)')

    def action_move(self):
        """Move the organization via betask."""
        self.ensure_one()

        if not self.move_to_root and not self.new_parent_id:
            raise UserError("Please select a new parent organization or check 'Move to Root'")

        data = {'org_id': self.org_id.id}
        if self.move_to_root:
            data['move_to_root'] = True
        else:
            data['new_parent_id'] = self.new_parent_id.id

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'UPD', data)

        return {'type': 'ir.actions.act_window_close'}


class MovePersonWizard(models.TransientModel):
    """Wizard to move a person to a different organization."""
    _name = 'myschool.move.person.wizard'
    _description = 'Move Person to Organization'

    person_id = fields.Many2one('myschool.person', string='Person', required=True)
    person_name = fields.Char(string='Person Name', readonly=True)
    new_org_id = fields.Many2one('myschool.org', string='New Organization', required=True)
    keep_roles = fields.Boolean(string='Keep Existing Roles', default=True)

    def action_move(self):
        """Move the person via betask."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'UPD', {
            'person_id': self.person_id.id,
            'new_org_id': self.new_org_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}


class AssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to a person."""
    _name = 'myschool.assign.role.wizard'
    _description = 'Assign Role to Person'

    person_id = fields.Many2one('myschool.person', string='Person', required=True)
    person_name = fields.Char(string='Person Name', readonly=True)
    role_id = fields.Many2one('myschool.role', string='Role', required=True)
    org_id = fields.Many2one('myschool.org', string='Organization (optional)',
                             help='Assign role in context of this organization')
    is_master = fields.Boolean(string='Is Master', default=False,
                               help='Master relation overrides priority for PERSON-TREE calculation')
    automatic_sync = fields.Boolean(string='Auto Sync', default=True,
                                     help='Allow automated sync to modify this relation')

    @api.onchange('is_master')
    def _onchange_is_master(self):
        if self.is_master:
            self.automatic_sync = False

    def action_assign(self):
        """Assign the role via betask."""
        self.ensure_one()

        data = {
            'type': 'PPSBR',
            'person_id': self.person_id.id,
            'role_id': self.role_id.id,
            'is_master': self.is_master,
            'automatic_sync': self.automatic_sync,
        }
        if self.org_id:
            data['org_id'] = self.org_id.id

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', data)

        return {'type': 'ir.actions.act_window_close'}


class BulkAssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to multiple persons."""
    _name = 'myschool.bulk.assign.role.wizard'
    _description = 'Bulk Assign Role'

    person_ids = fields.Many2many('myschool.person', string='Persons')
    person_count = fields.Integer(string='Number of Persons', readonly=True)
    role_id = fields.Many2one('myschool.role', string='Role', required=True)
    org_id = fields.Many2one('myschool.org', string='Organization (optional)')
    is_master = fields.Boolean(string='Is Master', default=False,
                               help='Master relation overrides priority for PERSON-TREE calculation')
    automatic_sync = fields.Boolean(string='Auto Sync', default=True,
                                     help='Allow automated sync to modify this relation')

    def action_assign(self):
        """Assign role to all selected persons."""
        self.ensure_one()
        
        person_ids = self.person_ids.ids
        if not person_ids:
            # Try to get from context
            person_ids = self.env.context.get('default_person_ids', [])
        
        if not person_ids:
            raise UserError("No persons selected")
        
        count = self.env['myschool.object.browser'].bulk_assign_role(
            person_ids,
            self.role_id.id,
            self.org_id.id if self.org_id else None
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Assigned role to {count} persons',
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class BulkMoveWizard(models.TransientModel):
    """Wizard to move multiple persons to an organization."""
    _name = 'myschool.bulk.move.wizard'
    _description = 'Bulk Move Persons'

    person_ids = fields.Many2many('myschool.person', string='Persons')
    person_count = fields.Integer(string='Number of Persons', readonly=True)
    org_id = fields.Many2one('myschool.org', string='Target Organization', required=True)

    def action_move(self):
        """Move all selected persons."""
        self.ensure_one()
        
        person_ids = self.person_ids.ids
        if not person_ids:
            person_ids = self.env.context.get('default_person_ids', [])
        
        if not person_ids:
            raise UserError("No persons selected")
        
        count = self.env['myschool.object.browser'].bulk_move_to_org(
            person_ids,
            self.org_id.id
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Moved {count} persons to {self.org_id.name}',
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


# =============================================================================
# Configuration Item Wizards
# =============================================================================

class ManageCiRelationsWizard(models.TransientModel):
    """Wizard to manage Configuration Item relations for an organization."""
    _name = 'myschool.manage.ci.relations.wizard'
    _description = 'Manage Configuration Items'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', compute='_compute_org_name')
    ci_relation_count = fields.Integer(compute='_compute_ci_relation_count')
    
    @api.depends('org_id')
    def _compute_org_name(self):
        for wizard in self:
            if wizard.org_id:
                wizard.org_name = wizard.org_id.name_tree or wizard.org_id.name
            else:
                wizard.org_name = ''
    
    @api.depends('org_id')
    def _compute_ci_relation_count(self):
        CiRelation = self.env['myschool.ci.relation']
        for wizard in self:
            if wizard.org_id:
                wizard.ci_relation_count = CiRelation.search_count([
                    ('id_org', '=', wizard.org_id.id),
                    ('isactive', '=', True)
                ])
            else:
                wizard.ci_relation_count = 0
    
    def action_add_ci(self):
        """Open wizard to add a new CI relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ci.relation.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }
    
    def action_view_all(self):
        """View all CI relations for this org in a list."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.ci.relation',
            'views': [[False, 'tree'], [False, 'form']],
            'target': 'current',
            'domain': [('id_org', '=', self.org_id.id)],
            'context': {
                'default_id_org': self.org_id.id,
            },
        }


class AddCiRelationWizard(models.TransientModel):
    """Wizard to add a Configuration Item relation to an organization."""
    _name = 'myschool.add.ci.relation.wizard'
    _description = 'Add Configuration Item'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization', compute='_compute_org_name')
    
    # Option 1: Select existing CI
    use_existing_ci = fields.Boolean(string='Use Existing Config Item', default=True)
    existing_ci_id = fields.Many2one('myschool.config.item', string='Config Item',
        domain=[('is_active', '=', True)])
    
    # Option 2: Create new CI
    new_ci_name = fields.Char(string='Name')
    new_ci_scope = fields.Selection([
        ('global', 'Global'),
        ('local', 'Local'),
        ('module', 'Module'),
        ('org', 'Organization'),
        ('user', 'User'),
    ], string="Scope", default='org')
    new_ci_type = fields.Selection([
        ('config', 'Configuration'),
        ('status', 'Status'),
        ('setting', 'Setting'),
        ('parameter', 'Parameter'),
        ('credential', 'Credential'),
        ('api', 'API Setting'),
    ], string="Type", default='config')
    
    # Value fields
    value_type = fields.Selection([
        ('string', 'Text'),
        ('integer', 'Number'),
        ('boolean', 'Yes/No'),
    ], string="Value Type", default='string')
    string_value = fields.Char(string='Text Value')
    integer_value = fields.Integer(string='Number Value')
    boolean_value = fields.Boolean(string='Yes/No Value')
    
    new_ci_description = fields.Text(string='Description')
    
    @api.depends('org_id')
    def _compute_org_name(self):
        for wizard in self:
            if wizard.org_id:
                wizard.org_name = wizard.org_id.name_tree or wizard.org_id.name
            else:
                wizard.org_name = ''
    
    def action_add(self):
        """Add the CI relation."""
        self.ensure_one()
        
        CiRelation = self.env['myschool.ci.relation']
        ConfigItem = self.env['myschool.config.item']
        
        if self.use_existing_ci:
            if not self.existing_ci_id:
                raise UserError("Please select a Configuration Item")
            config_item = self.existing_ci_id
        else:
            if not self.new_ci_name:
                raise UserError("Please enter a name for the Configuration Item")
            
            # Create new ConfigItem
            ci_vals = {
                'name': self.new_ci_name,
                'scope': self.new_ci_scope,
                'type': self.new_ci_type,
                'is_active': True,
            }
            
            # Set value based on type
            if self.value_type == 'string':
                ci_vals['string_value'] = self.string_value
            elif self.value_type == 'integer':
                ci_vals['integer_value'] = self.integer_value
            elif self.value_type == 'boolean':
                ci_vals['boolean_value'] = self.boolean_value
            
            if self.new_ci_description:
                ci_vals['description'] = self.new_ci_description
            
            config_item = ConfigItem.create(ci_vals)
        
        # Check if relation already exists
        existing = CiRelation.search([
            ('id_org', '=', self.org_id.id),
            ('id_ci', '=', config_item.id),
            ('isactive', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"Configuration Item '{config_item.name}' is already linked to this organization")
        
        # Create the relation
        CiRelation.create({
            'id_org': self.org_id.id,
            'id_ci': config_item.id,
            'isactive': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_add_and_new(self):
        """Add the CI relation and open wizard for another."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.ci.relation.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }


class EditCiRelationWizard(models.TransientModel):
    """Wizard to edit a Configuration Item relation value."""
    _name = 'myschool.edit.ci.relation.wizard'
    _description = 'Edit Configuration Item'

    ci_relation_id = fields.Many2one('myschool.ci.relation', string='Relation', required=True)
    ci_name = fields.Char(string='Config Item', readonly=True)
    org_name = fields.Char(string='Organization', readonly=True)
    
    # Value fields
    value_type = fields.Selection([
        ('string', 'Text'),
        ('integer', 'Number'),
        ('boolean', 'Yes/No'),
    ], string="Value Type", default='string')
    string_value = fields.Char(string='Text Value')
    integer_value = fields.Integer(string='Number Value')
    boolean_value = fields.Boolean(string='Yes/No Value')
    
    @api.model
    def default_get(self, fields_list):
        """Load current values from the CI relation."""
        res = super().default_get(fields_list)
        
        if 'ci_relation_id' in res and res['ci_relation_id']:
            relation = self.env['myschool.ci.relation'].browse(res['ci_relation_id'])
            if relation.exists() and relation.id_ci:
                ci = relation.id_ci
                res['ci_name'] = ci.name
                if relation.id_org:
                    res['org_name'] = relation.id_org.name_tree or relation.id_org.name
                else:
                    res['org_name'] = ''
                
                # Determine value type and load value
                if ci.string_value:
                    res['value_type'] = 'string'
                    res['string_value'] = ci.string_value
                elif ci.integer_value:
                    res['value_type'] = 'integer'
                    res['integer_value'] = ci.integer_value
                elif ci.boolean_value is not None:
                    res['value_type'] = 'boolean'
                    res['boolean_value'] = ci.boolean_value
        
        return res
    
    def action_save(self):
        """Save the updated value."""
        self.ensure_one()
        
        if not self.ci_relation_id or not self.ci_relation_id.id_ci:
            raise UserError("Invalid Configuration Item relation")
        
        ci = self.ci_relation_id.id_ci
        
        # Update value based on type
        vals = {
            'string_value': False,
            'integer_value': 0,
            'boolean_value': False,
        }
        
        if self.value_type == 'string':
            vals['string_value'] = self.string_value
        elif self.value_type == 'integer':
            vals['integer_value'] = self.integer_value
        elif self.value_type == 'boolean':
            vals['boolean_value'] = self.boolean_value
        
        ci.write(vals)
        
        return {'type': 'ir.actions.act_window_close'}


class RemoveCiRelationWizard(models.TransientModel):
    """Wizard to remove (deactivate) a Configuration Item relation."""
    _name = 'myschool.remove.ci.relation.wizard'
    _description = 'Remove Configuration Item'

    ci_relation_id = fields.Many2one('myschool.ci.relation', string='Relation', required=True)
    ci_name = fields.Char(string='Config Item', readonly=True)
    org_name = fields.Char(string='Organization', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Load info from the CI relation."""
        res = super().default_get(fields_list)
        
        if 'ci_relation_id' in res and res['ci_relation_id']:
            relation = self.env['myschool.ci.relation'].browse(res['ci_relation_id'])
            if relation.exists():
                res['ci_name'] = relation.id_ci.name if relation.id_ci else ''
                if relation.id_org:
                    res['org_name'] = relation.id_org.name_tree or relation.id_org.name
                else:
                    res['org_name'] = ''
        
        return res
    
    def action_remove(self):
        """Deactivate the CI relation."""
        self.ensure_one()
        
        if self.ci_relation_id:
            self.ci_relation_id.write({'isactive': False})
        
        return {'type': 'ir.actions.act_window_close'}


# =============================================================================
# Role Relations Manager
# =============================================================================

class RoleRelationsManager(models.TransientModel):
    """
    Manager for Role-based PropRelations.
    
    Manages two types of relations:
    1. SRBR: SAP-Role to Backend-Role mapping
    2. BRSO: Backend-Role to School+Department mapping (determines where persons are created)
    """
    _name = 'myschool.role.relations.manager'
    _description = 'Role Relations Manager'

    relation_type = fields.Selection([
        ('SRBR', 'SAP-Role to Backend-Role (SRBR)'),
        ('BRSO', 'Backend-Role to School/Department (BRSO)'),
    ], string='Relation Type', default='SRBR', required=True)
    
    # Computed counts
    srbr_count = fields.Integer(compute='_compute_counts', string='SRBR Relations')
    brso_count = fields.Integer(compute='_compute_counts', string='BRSO Relations')
    
    @api.depends('relation_type')
    def _compute_counts(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        for wizard in self:
            # Count SRBR relations
            srbr_type = PropRelationType.search([('name', '=', 'SRBR')], limit=1)
            wizard.srbr_count = PropRelation.search_count([
                ('proprelation_type_id', '=', srbr_type.id),
                ('is_active', '=', True)
            ]) if srbr_type else 0
            
            # Count BRSO relations
            brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
            wizard.brso_count = PropRelation.search_count([
                ('proprelation_type_id', '=', brso_type.id),
                ('is_active', '=', True)
            ]) if brso_type else 0
    
    def action_view_srbr(self):
        """View all SRBR relations."""
        return self._view_relations('SRBR')
    
    def action_view_brso(self):
        """View all BRSO relations."""
        return self._view_relations('BRSO')
    
    def _view_relations(self, type_name):
        """View relations of a specific type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        
        if not rel_type:
            raise UserError(f"Relation type '{type_name}' not found.")
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'{type_name} Relations',
            'res_model': 'myschool.proprelation',
            'view_mode': 'list,form',
            'domain': [
                ('proprelation_type_id', '=', rel_type.id),
                ('is_active', '=', True)
            ],
            'target': 'current',
        }
    
    def action_add_srbr(self):
        """Open wizard to add SRBR relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.srbr.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }
    
    def action_add_brso(self):
        """Open wizard to add BRSO relation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.brso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class AddSRBRWizard(models.TransientModel):
    """
    Wizard to create SRBR relation.
    Links a SAP-Role to a Backend-Role.
    Uses role_type_id to filter by role type (BACKEND, SAP).
    """
    _name = 'myschool.add.srbr.wizard'
    _description = 'Add SAP-Role to Backend-Role Relation'

    sap_role_id = fields.Many2one(
        'myschool.role', 
        string='SAP Role',
        required=True,
        domain="[('role_type_id.name', '=', 'SAP')]",
        help='Select the SAP role'
    )
    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role to link to'
    )
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_add(self):
        """Create the SRBR relation via betask."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'SRBR',
            'role_id': self.sap_role_id.id,
            'role_parent_id': self.backend_role_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}

    def action_add_and_new(self):
        """Create and open new wizard."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.srbr.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class AddBRSOWizard(models.TransientModel):
    """
    Wizard to create BRSO relation.
    Links a Backend-Role to a School and Department.
    Used to determine where persons with a certain role in a school will be created.
    
    Field mapping:
    - id_role = Backend Role
    - id_org = Department (where person will be created)
    - id_org_parent = School (higher level in tree)
    """
    _name = 'myschool.add.brso.wizard'
    _description = 'Add Backend-Role to School/Department Relation'

    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role'
    )
    school_id = fields.Many2one(
        'myschool.org', 
        string='School',
        required=True,
        domain="[('org_type_id.name', '=', 'SCHOOL')]",
        help='Select the school (org with type SCHOOL)'
    )
    department_id = fields.Many2one(
        'myschool.org', 
        string='Department',
        required=True,
        domain="[('org_type_id.name', '=', 'DEPARTMENT')]",
        help='Select the department where persons will be created'
    )
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_add(self):
        """Create the BRSO relation via betask."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'BRSO',
            'role_id': self.backend_role_id.id,
            'org_id': self.department_id.id,
            'org_parent_id': self.school_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}

    def action_add_and_new(self):
        """Create and open new wizard."""
        self.action_add()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.add.brso.wizard',
            'views': [[False, 'form']],
            'target': 'new',
        }


class LinkRoleToOrgWizard(models.TransientModel):
    """
    Wizard to link a Role to an Organization (BRSO relation).
    Opens from the Organization context menu.
    
    Creates a BRSO relation where:
    - id_org = the selected org (as department)
    - id_org_parent = the school (auto-detected from hierarchy)
    - id_role = selected backend role
    """
    _name = 'myschool.link.role.org.wizard'
    _description = 'Link Role to Organization'

    org_id = fields.Many2one(
        'myschool.org', 
        string='Organization',
        required=True,
        readonly=True,
        help='The organization to link the role to'
    )
    org_name = fields.Char(string='Organization', compute='_compute_org_info')
    org_type_name = fields.Char(string='Organization Type', compute='_compute_org_info')
    
    school_id = fields.Many2one(
        'myschool.org', 
        string='School',
        domain="[('org_type_id.name', '=', 'SCHOOL')]",
        help='Select the school (auto-detected if possible)'
    )
    
    backend_role_id = fields.Many2one(
        'myschool.role', 
        string='Backend Role',
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select the backend role to link'
    )
    
    @api.depends('org_id')
    def _compute_org_info(self):
        for wizard in self:
            if wizard.org_id:
                wizard.org_name = wizard.org_id.name_tree or wizard.org_id.name
                wizard.org_type_name = wizard.org_id.org_type_id.name if wizard.org_id.org_type_id else ''
            else:
                wizard.org_name = ''
                wizard.org_type_name = ''
    
    @api.model
    def default_get(self, fields_list):
        """Set defaults and auto-detect school from hierarchy."""
        res = super().default_get(fields_list)
        
        if 'org_id' in res and res['org_id']:
            org = self.env['myschool.org'].browse(res['org_id'])
            if org.exists():
                # Try to find the school in the hierarchy
                school = self._find_school_in_hierarchy(org)
                if school:
                    res['school_id'] = school.id
        
        return res
    
    def _find_school_in_hierarchy(self, org):
        """Find the school in the organization hierarchy (via ORG-TREE relations only)."""
        try:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
        except KeyError:
            return None

        # Get ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        # Check if current org is a school
        if org.org_type_id and org.org_type_id.name == 'SCHOOL':
            return org

        # Walk up the hierarchy to find a school (only via ORG-TREE relations)
        current_org = org
        visited = set()

        while current_org and current_org.id not in visited:
            visited.add(current_org.id)

            # Check if this org is a school
            if current_org.org_type_id and current_org.org_type_id.name == 'SCHOOL':
                return current_org

            # Find parent via ORG-TREE relation only
            search_domain = [
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            if parent_rel and parent_rel.id_org_parent:
                current_org = parent_rel.id_org_parent
            else:
                break

        return None
    
    def _get_or_create_relation_type(self, name, usage=''):
        """Get or create a proprelation type."""
        PropRelationType = self.env['myschool.proprelation.type']
        rel_type = PropRelationType.search([('name', '=', name)], limit=1)
        if not rel_type:
            rel_type = PropRelationType.create({
                'name': name,
                'usage': usage,
                'is_active': True,
            })
        return rel_type
    
    def action_link(self):
        """Create the BRSO relation via betask."""
        self.ensure_one()

        if not self.school_id:
            raise UserError('Please select a school.')

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'BRSO',
            'role_id': self.backend_role_id.id,
            'org_id': self.org_id.id,
            'org_parent_id': self.school_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}
    
    def action_link_and_new(self):
        """Create and open new wizard for same org."""
        self.action_link()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.link.role.org.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
            },
        }


class AddBRSORoleWizard(models.TransientModel):
    """Simple wizard to add a BRSO role to an organization."""
    _name = 'myschool.add.brso.role.wizard'
    _description = 'Add Backend Role to Organization'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True, readonly=True)
    school_id = fields.Many2one(
        'myschool.org', 
        string='School', 
        required=True,
        help='Select the school organization (parent)'
    )
    role_id = fields.Many2one(
        'myschool.role', 
        string='Role', 
        required=True,
        domain="[('role_type_id.name', '=', 'BACKEND')]",
        help='Select a Backend role to add'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default school from org's parent (via ORG-TREE relation only)."""
        res = super().default_get(fields_list)

        if 'org_id' in res and res['org_id']:
            # Try to find parent org via ORG-TREE relation
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']

            # Get ORG-TREE type
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

            search_domain = [
                ('id_org', '=', res['org_id']),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)

            if parent_rel and parent_rel.id_org_parent:
                res['school_id'] = parent_rel.id_org_parent.id

        return res

    def action_add_role(self):
        """Create the BRSO proprelation via betask."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'BRSO',
            'role_id': self.role_id.id,
            'org_id': self.org_id.id,
            'org_parent_id': self.school_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}


class ManageOrgRolesWizard(models.TransientModel):
    """Wizard to manage BRSO roles for an organization."""
    _name = 'myschool.manage.org.roles.wizard'
    _description = 'Manage Organization Roles'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True, readonly=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        help='Select the school organization (parent)'
    )

    line_ids = fields.One2many(
        'myschool.org.role.line',
        'wizard_id',
        string='Role Lines',
    )
    
    # For adding new role
    new_role_id = fields.Many2one(
        'myschool.role',
        string='Add Role',
        domain="[('role_type_id.name', '=', 'BACKEND')]",
    )
    new_has_accounts = fields.Boolean(string='Accounts', default=False)
    new_has_ldap_com_group = fields.Boolean(string='LDAP COM Group', default=False)
    new_has_ldap_sec_group = fields.Boolean(string='LDAP SEC Group', default=False)
    new_has_odoo_group = fields.Boolean(string='Odoo Group', default=False)

    @api.model
    def action_open(self, org_id, org_name):
        """Create the wizard with lines saved to DB and return the action to open it."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Find the school: check the org itself, then traverse ORG-TREE upward
        school_id = False
        first_parent_id = False
        Org = self.env['myschool.org']
        org = Org.browse(org_id)
        if org.org_type_id and org.org_type_id.name == 'SCHOOL':
            school_id = org.id
        else:
            org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
            if org_tree_type:
                current_org_id = org_id
                for _guard in range(10):  # prevent infinite loops
                    parent_rel = PropRelation.search([
                        ('id_org', '=', current_org_id),
                        ('id_org_parent', '!=', False),
                        ('proprelation_type_id', '=', org_tree_type.id),
                        ('is_active', '=', True),
                    ], limit=1)
                    if not parent_rel or not parent_rel.id_org_parent:
                        break
                    parent_org = parent_rel.id_org_parent
                    if not first_parent_id:
                        first_parent_id = parent_org.id
                    if parent_org.org_type_id and parent_org.org_type_id.name == 'SCHOOL':
                        school_id = parent_org.id
                        break
                    current_org_id = parent_org.id
            # Fallback: use nearest parent if no SCHOOL-type ancestor found
            if not school_id:
                school_id = first_parent_id

        # Build line vals from BRSO relations
        lines = []
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if brso_type:
            relations = PropRelation.search([
                ('proprelation_type_id', '=', brso_type.id),
                ('id_org', '=', org_id),
                ('id_role', '!=', False),
                ('is_active', '=', True),
            ])
            for rel in relations:
                role = rel.id_role
                lines.append((0, 0, {
                    'proprelation_id': rel.id,
                    'role_name': role.name if role else '',
                    'role_label': role.label or role.name if role else '',
                    'is_active': rel.is_active,
                    'is_master': rel.is_master,
                    'automatic_sync': rel.automatic_sync,
                    'has_accounts': rel.has_accounts,
                    'has_ldap_com_group': rel.has_ldap_com_group,
                    'has_ldap_sec_group': rel.has_ldap_sec_group,
                    'has_odoo_group': rel.has_odoo_group,
                }))

        wizard_vals = {
            'org_id': org_id,
            'org_name': org_name,
            'line_ids': lines,
        }
        if school_id:
            wizard_vals['school_id'] = school_id
        wizard = self.create(wizard_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': wizard.id,
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def action_add_role(self):
        """Add the selected role to the organization via betask."""
        self.ensure_one()

        if not self.new_role_id:
            raise UserError("Please select a role to add.")
        if not self.school_id:
            raise UserError("Please select a school organization.")

        # Check: has_accounts role may only be linked to one org per school
        if self.new_has_accounts:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            Org = self.env['myschool.org']
            brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
            if brso_type:
                # Match all school variants (admin + non-admin) by inst_nr
                school_org_ids = {self.school_id.id}
                if self.school_id.inst_nr:
                    same_inst = Org.search([
                        ('inst_nr', '=', self.school_id.inst_nr),
                        ('is_active', '=', True),
                    ])
                    school_org_ids.update(same_inst.ids)

                existing = PropRelation.search([
                    ('proprelation_type_id', '=', brso_type.id),
                    ('id_role', '=', self.new_role_id.id),
                    ('id_org_parent', 'in', list(school_org_ids)),
                    ('id_org', '!=', self.org_id.id),
                    ('has_accounts', '=', True),
                    ('is_active', '=', True),
                ], limit=1)
                if existing:
                    org_name = existing.id_org.name if existing.id_org else '?'
                    role_label = self.new_role_id.label or self.new_role_id.name
                    raise UserError(
                        f"Rol '{role_label}' is al gekoppeld aan '{org_name}' "
                        f"met Has Accounts binnen school '{self.school_id.name}'. "
                        f"Per school mag een rol met Has Accounts maar aan één organisatie gekoppeld zijn."
                    )

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'BRSO',
            'role_id': self.new_role_id.id,
            'org_id': self.org_id.id,
            'org_parent_id': self.school_id.id,
            'has_accounts': self.new_has_accounts,
            'has_ldap_com_group': self.new_has_ldap_com_group,
            'has_ldap_sec_group': self.new_has_ldap_sec_group,
            'has_odoo_group': self.new_has_odoo_group,
        })

        # Reopen wizard with saved records
        return self.action_open(self.org_id.id, self.org_name)

    def action_save(self):
        """Save changes and reopen the wizard."""
        self.ensure_one()
        return self.action_open(self.org_id.id, self.org_name)

    def action_update_all_groups(self):
        """Update groups for all attached roles based on their boolean flags."""
        self.ensure_one()
        processor = self.env['myschool.betask.processor']

        school_org = self.school_id
        if not school_org:
            raise UserError("Please select a school organization first.")

        count = 0
        for line in self.line_ids:
            rel = line.proprelation_id
            if not rel or not rel.id_role:
                continue
            data = {
                'has_ldap_com_group': rel.has_ldap_com_group,
                'has_ldap_sec_group': rel.has_ldap_sec_group,
                'has_odoo_group': rel.has_odoo_group,
            }
            if any(data.values()):
                processor._process_brso_groups(rel, data)
                count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Update All',
                'message': f'Updated groups for {count} role(s).',
                'type': 'success',
                'next': self.action_open(self.org_id.id, self.org_name),
            },
        }

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}


class ManagePersonRolesWizard(models.TransientModel):
    """Wizard to manage PPSBR roles for a person."""
    _name = 'myschool.manage.person.roles.wizard'
    _description = 'Manage Person Roles'

    person_id = fields.Many2one('myschool.person', string='Person', required=True, readonly=True)
    person_name = fields.Char(string='Person Name', readonly=True)
    
    line_ids = fields.One2many(
        'myschool.person.role.line',
        'wizard_id',
        string='Role Lines',
    )
    
    # For adding new role
    new_role_id = fields.Many2one(
        'myschool.role',
        string='Add Role',
    )

    @api.model
    def action_open(self, person_id, person_name):
        """Create the wizard with lines saved to DB and return the action to open it."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        lines = []
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if ppsbr_type:
            relations = PropRelation.search([
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('id_person', '=', person_id),
                ('id_role', '!=', False),
                ('is_active', '=', True),
            ])
            for rel in relations:
                lines.append((0, 0, {
                    'proprelation_id': rel.id,
                    'role_name': rel.id_role.name if rel.id_role else '',
                    'is_active': rel.is_active,
                    'is_master': rel.is_master,
                    'automatic_sync': rel.automatic_sync,
                }))

        wizard = self.create({
            'person_id': person_id,
            'person_name': person_name,
            'line_ids': lines,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': wizard.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_add_role(self):
        """Add the selected role to the person via betask."""
        self.ensure_one()

        if not self.new_role_id:
            raise UserError("Please select a role to add.")

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PROPRELATION', 'ADD', {
            'type': 'PPSBR',
            'person_id': self.person_id.id,
            'role_id': self.new_role_id.id,
        })

        # Reopen wizard with saved records
        return self.action_open(self.person_id.id, self.person_name)

    def action_recalc_roles(self):
        """Recalculate roles for this person based on their hoofd_ambt assignment."""
        self.ensure_one()
        person = self.person_id
        if not person:
            raise UserError("No person selected.")

        updated, msg = self._recalc_employee_roles_for_person(person)

        # Reopen wizard to show updated roles
        action = self.action_open(person.id, self.person_name)
        action['context'] = {
            **self.env.context,
            'show_notification': True,
            'notification_message': msg,
        }
        return action

    @api.model
    def _recalc_employee_roles_for_person(self, person):
        """Recalculate PPSBR roles for a person based on hoofd_ambt from PersonDetails.

        Looks up the hoofd_ambt code, finds the SAP role by shortname, resolves
        the backend role via SRBR, and ensures a PPSBR exists for that backend role.

        Returns:
            tuple: (bool updated, str message)
        """
        _logger.info(f'[RECALC-ROLES] === Processing {person.name} (ID: {person.id}) ===')

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Role = self.env['myschool.role']

        # Get the latest active person_details for hoofd_ambt
        details = self.env['myschool.person.details'].search([
            ('person_id', '=', person.id),
            ('is_active', '=', True),
        ], limit=1, order='create_date desc')

        _logger.info(f'[RECALC-ROLES] PersonDetails found: {bool(details)}, hoofd_ambt: {details.hoofd_ambt if details else "N/A"}')

        if not details or not details.hoofd_ambt:
            return False, f'{person.name}: no active assignment (hoofd_ambt) found.'

        ambt_code = details.hoofd_ambt

        # Find SAP role by shortname
        sap_role = Role.search([('shortname', '=', ambt_code)], limit=1)
        _logger.info(f'[RECALC-ROLES] SAP role lookup for shortname "{ambt_code}": {"found " + sap_role.name + " (ID: " + str(sap_role.id) + ")" if sap_role else "NOT FOUND"}')
        if not sap_role:
            return False, f'{person.name}: SAP role not found for code "{ambt_code}".'

        # Find backend role via SRBR
        srbr_type = PropRelationType.search([('name', '=', 'SRBR')], limit=1)
        if not srbr_type:
            _logger.warning(f'[RECALC-ROLES] SR-BR proprelation type not found!')
            return False, f'{person.name}: SR-BR proprelation type not found.'

        srbr_rel = PropRelation.search([
            ('proprelation_type_id', '=', srbr_type.id),
            ('is_active', '=', True),
            ('id_role_parent', '!=', False),
            '|',
            ('id_role', '=', sap_role.id),
            ('id_role_child', '=', sap_role.id),
        ], limit=1)

        _logger.info(f'[RECALC-ROLES] SRBR lookup: {"found -> backend role: " + srbr_rel.id_role_parent.name + " (ID: " + str(srbr_rel.id_role_parent.id) + ")" if srbr_rel and srbr_rel.id_role_parent else "NOT FOUND"}')

        if not srbr_rel or not srbr_rel.id_role_parent:
            return False, f'{person.name}: no SRBR mapping for SAP role "{sap_role.name}".'

        backend_role = srbr_rel.id_role_parent

        # Check if PPSBR already exists for this backend role
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not ppsbr_type:
            _logger.warning(f'[RECALC-ROLES] PPSBR proprelation type not found!')
            return False, f'{person.name}: PPSBR proprelation type not found.'

        existing_ppsbr = PropRelation.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_role', '=', backend_role.id),
            ('is_active', '=', True),
        ], limit=1)

        if existing_ppsbr:
            _logger.info(f'[RECALC-ROLES] PPSBR already exists: {existing_ppsbr.name} (ID: {existing_ppsbr.id})')
            return False, f'{person.name}: PPSBR already exists for role "{backend_role.name}".'

        # Find the person's school org from existing PPSBR
        any_ppsbr = PropRelation.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('is_active', '=', True),
            ('id_org', '!=', False),
        ], limit=1)

        org = any_ppsbr.id_org if any_ppsbr else False
        org_parent = any_ppsbr.id_org_parent if any_ppsbr else False
        _logger.info(f'[RECALC-ROLES] Existing PPSBR org context: org={org.name if org else "None"}, org_parent={org_parent.name if org_parent else "None"}')

        # Find active period
        Period = self.env['myschool.period']
        period = Period.search([('is_active', '=', True)], limit=1)
        _logger.info(f'[RECALC-ROLES] Active period: {period.name if period else "None"}')

        # Build name
        name_kwargs = {'id_person': person, 'id_role': backend_role}
        if org:
            name_kwargs['id_org'] = org
        if period:
            name_kwargs['id_period'] = period

        relation_name = build_proprelation_name('PPSBR', **name_kwargs)

        ppsbr_vals = {
            'name': relation_name,
            'proprelation_type_id': ppsbr_type.id,
            'id_person': person.id,
            'id_role': backend_role.id,
            'is_active': True,
            'is_organisational': True,
            'automatic_sync': True,
            'start_date': fields.Datetime.now(),
        }
        if org:
            ppsbr_vals['id_org'] = org.id
        if org_parent:
            ppsbr_vals['id_org_parent'] = org_parent.id
        if period:
            ppsbr_vals['id_period'] = period.id
        if backend_role.priority:
            ppsbr_vals['priority'] = backend_role.priority

        new_ppsbr = PropRelation.create(ppsbr_vals)
        _logger.info(f'[RECALC-ROLES] Created PPSBR: {relation_name} (ID: {new_ppsbr.id})')

        # Recalculate PERSON-TREE
        processor = self.env['myschool.betask.processor']
        processor._update_person_tree_position(person)
        _logger.info(f'[RECALC-ROLES] PERSON-TREE recalculated for {person.name}')

        return True, f'{person.name}: created PPSBR for role "{backend_role.name}" (from ambt "{ambt_code}").'

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}


class RecalcEmployeeRolesWizard(models.TransientModel):
    """Wizard to recalculate roles for all employees based on their hoofd_ambt."""
    _name = 'myschool.recalc.employee.roles.wizard'
    _description = 'Recalculate Employee Roles'

    result_text = fields.Text(string='Results', readonly=True)
    state = fields.Selection([
        ('confirm', 'Confirm'),
        ('done', 'Done'),
    ], default='confirm')

    def action_recalc(self):
        """Recalculate roles for all active employees."""
        self.ensure_one()

        Person = self.env['myschool.person']
        PersonType = self.env['myschool.person.type']

        employee_type = PersonType.search([('name', '=', 'EMPLOYEE')], limit=1)
        if not employee_type:
            raise UserError("EMPLOYEE person type not found.")

        employees = Person.search([
            ('is_active', '=', True),
            ('person_type_id', '=', employee_type.id),
        ])

        helper = self.env['myschool.manage.person.roles.wizard']
        created = 0
        skipped = 0
        errors = []

        for emp in employees:
            try:
                updated, msg = helper._recalc_employee_roles_for_person(emp)
                if updated:
                    created += 1
                else:
                    skipped += 1
                _logger.info(msg)
            except Exception as e:
                errors.append(f'{emp.name}: {str(e)}')
                _logger.error(f'Error recalculating roles for {emp.name}: {e}')

        result_lines = [
            f'Processed {len(employees)} employees.',
            f'Created: {created} new PPSBR relations.',
            f'Skipped: {skipped} (already correct or no assignment).',
        ]
        if errors:
            result_lines.append(f'Errors: {len(errors)}')
            result_lines.extend(errors[:20])  # show first 20 errors

        self.write({
            'result_text': '\n'.join(result_lines),
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
        }


class PasswordWizard(models.TransientModel):
    """Wizard to manage password for a person."""
    _name = 'myschool.password.wizard'
    _description = 'Manage Password'
    
    person_id = fields.Many2one('myschool.person', string='Person', required=True)
    person_name = fields.Char(string='Person Name', compute='_compute_person_name')
    current_password = fields.Char(string='Current Password', readonly=True)
    new_password = fields.Char(string='New Password')
    confirm_password = fields.Char(string='Confirm Password')
    generate_random = fields.Boolean(string='Generate Random Password', default=False)
    
    @api.depends('person_id')
    def _compute_person_name(self):
        for record in self:
            if record.person_id:
                name = record.person_id.name or ''
                if hasattr(record.person_id, 'first_name') and record.person_id.first_name:
                    name = f"{record.person_id.first_name} {name}"
                record.person_name = name
            else:
                record.person_name = ''
    
    @api.model
    def default_get(self, fields_list):
        """Load current password if available."""
        res = super().default_get(fields_list)
        
        if 'person_id' in res and res['person_id']:
            person = self.env['myschool.person'].browse(res['person_id'])
            if person.exists() and hasattr(person, 'password') and person.password:
                res['current_password'] = person.password
        
        return res
    
    @api.onchange('generate_random')
    def _onchange_generate_random(self):
        """Generate random password when checkbox is checked."""
        if self.generate_random:
            import random
            import string
            # Generate a random 8-character password
            chars = string.ascii_letters + string.digits
            self.new_password = ''.join(random.choice(chars) for _ in range(8))
            self.confirm_password = self.new_password
    
    def action_save_password(self):
        """Save the new password."""
        self.ensure_one()
        
        if not self.new_password:
            raise UserError("Please enter a new password or generate one.")
        
        if self.new_password != self.confirm_password:
            raise UserError("Passwords do not match.")
        
        if len(self.new_password) < 4:
            raise UserError("Password must be at least 4 characters long.")
        
        # Save password to person record via betask
        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'UPD', {
            'person_id': self.person_id.id,
            'vals': {'password': self.new_password},
        })

        return {'type': 'ir.actions.act_window_close'}

    def action_clear_password(self):
        """Clear the password."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('PERSON', 'UPD', {
            'person_id': self.person_id.id,
            'vals': {'password': False},
        })

        return {'type': 'ir.actions.act_window_close'}


# =============================================================================
# BACKEND TASK ROLLBACK WIZARD
# =============================================================================

class BackendTaskRollbackWizard(models.TransientModel):
    """
    Wizard to rollback backend task changes to a specific point in time.

    This wizard:
    1. Rolls back PersonDetails to their state at the rollback point
    2. Creates reversal tasks for external systems (LDAP/AD)
    3. Marks affected backend tasks as rolled back
    """
    _name = 'myschool.betask.rollback.wizard'
    _description = 'Backend Task Rollback Wizard'

    rollback_datetime = fields.Datetime(
        string='Rollback To',
        required=True,
        default=fields.Datetime.now,
        help='All changes made after this datetime will be rolled back'
    )

    include_person_details = fields.Boolean(
        string='Rollback PersonDetails',
        default=True,
        help='Rollback PersonDetails versions to their state at the rollback point'
    )

    include_external_systems = fields.Boolean(
        string='Create Reversal Tasks',
        default=True,
        help='Create reversal backend tasks for external systems (LDAP/AD)'
    )

    reset_tasks = fields.Boolean(
        string='Reset Backend Tasks',
        default=False,
        help='Reset affected backend tasks to "new" status for reprocessing'
    )

    # Preview fields
    preview_mode = fields.Boolean(
        string='Preview Mode',
        default=True
    )

    affected_tasks_count = fields.Integer(
        string='Affected Tasks',
        compute='_compute_preview',
        store=False
    )

    affected_person_details_count = fields.Integer(
        string='PersonDetails Versions to Rollback',
        compute='_compute_preview',
        store=False
    )

    affected_persons_count = fields.Integer(
        string='Affected Persons',
        compute='_compute_preview',
        store=False
    )

    preview_text = fields.Text(
        string='Preview',
        compute='_compute_preview',
        store=False
    )

    rollback_log = fields.Text(
        string='Rollback Log',
        readonly=True
    )

    @api.depends('rollback_datetime', 'include_person_details', 'include_external_systems')
    def _compute_preview(self):
        for wizard in self:
            if not wizard.rollback_datetime:
                wizard.affected_tasks_count = 0
                wizard.affected_person_details_count = 0
                wizard.affected_persons_count = 0
                wizard.preview_text = "Select a rollback datetime."
                continue

            # Find affected backend tasks
            BeTask = self.env['myschool.betask']
            affected_tasks = BeTask.search([
                ('status', '=', 'completed_ok'),
                ('processing_end', '>', wizard.rollback_datetime)
            ])
            wizard.affected_tasks_count = len(affected_tasks)

            # Find affected PersonDetails versions
            PersonDetails = self.env['myschool.person.details']
            affected_details = PersonDetails.search([
                ('create_date', '>', wizard.rollback_datetime),
                ('is_active', '=', True)
            ])
            wizard.affected_person_details_count = len(affected_details)

            # Count affected persons
            affected_person_ids = affected_details.mapped('person_id.id')
            wizard.affected_persons_count = len(set(affected_person_ids))

            # Build preview text
            preview_lines = [
                f"=== ROLLBACK PREVIEW ===",
                f"Rollback point: {wizard.rollback_datetime}",
                f"",
                f"Affected items:",
                f"  - Backend tasks completed after rollback point: {wizard.affected_tasks_count}",
                f"  - PersonDetails versions to deactivate: {wizard.affected_person_details_count}",
                f"  - Persons affected: {wizard.affected_persons_count}",
                f"",
            ]

            # Show task breakdown by type
            if affected_tasks:
                preview_lines.append("Tasks by type:")
                task_types = {}
                for task in affected_tasks:
                    type_name = task.betasktype_id.name if task.betasktype_id else 'Unknown'
                    task_types[type_name] = task_types.get(type_name, 0) + 1
                for type_name, count in sorted(task_types.items()):
                    preview_lines.append(f"  - {type_name}: {count}")
                preview_lines.append("")

            # Show what will happen
            preview_lines.append("Actions to be performed:")
            if wizard.include_person_details:
                preview_lines.append("  ✓ Deactivate PersonDetails created after rollback point")
                preview_lines.append("  ✓ Reactivate previous PersonDetails versions")
            if wizard.include_external_systems:
                preview_lines.append("  ✓ Create reversal tasks for LDAP/AD changes")
            if wizard.reset_tasks:
                preview_lines.append("  ✓ Reset backend tasks to 'new' status")

            wizard.preview_text = '\n'.join(preview_lines)

    def action_preview(self):
        """Refresh the preview."""
        self.ensure_one()
        self.preview_mode = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_execute_rollback(self):
        """Execute the rollback."""
        self.ensure_one()

        if not self.rollback_datetime:
            raise UserError("Please select a rollback datetime.")

        log_lines = [
            f"=== ROLLBACK EXECUTED ===",
            f"Rollback point: {self.rollback_datetime}",
            f"Executed by: {self.env.user.name}",
            f"Executed at: {fields.Datetime.now()}",
            f"",
        ]

        rollback_stats = {
            'person_details_deactivated': 0,
            'person_details_reactivated': 0,
            'reversal_tasks_created': 0,
            'tasks_reset': 0,
        }

        # 1. Rollback PersonDetails
        if self.include_person_details:
            stats = self._rollback_person_details()
            rollback_stats.update(stats)
            log_lines.append(f"PersonDetails rollback:")
            log_lines.append(f"  - Versions deactivated: {stats['person_details_deactivated']}")
            log_lines.append(f"  - Previous versions reactivated: {stats['person_details_reactivated']}")
            log_lines.append("")

        # 2. Create reversal tasks for external systems
        if self.include_external_systems:
            stats = self._create_reversal_tasks()
            rollback_stats['reversal_tasks_created'] = stats['reversal_tasks_created']
            log_lines.append(f"Reversal tasks created: {stats['reversal_tasks_created']}")
            log_lines.append("")

        # 3. Reset backend tasks
        if self.reset_tasks:
            stats = self._reset_backend_tasks()
            rollback_stats['tasks_reset'] = stats['tasks_reset']
            log_lines.append(f"Backend tasks reset to 'new': {stats['tasks_reset']}")
            log_lines.append("")

        log_lines.append("=== ROLLBACK COMPLETE ===")

        self.rollback_log = '\n'.join(log_lines)
        self.preview_mode = False

        # Create a system event for the rollback
        self._log_rollback_event(rollback_stats)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _rollback_person_details(self):
        """Rollback PersonDetails to their state at the rollback point."""
        PersonDetails = self.env['myschool.person.details']

        stats = {
            'person_details_deactivated': 0,
            'person_details_reactivated': 0,
        }

        # Find PersonDetails versions created after rollback point that are active
        new_versions = PersonDetails.search([
            ('create_date', '>', self.rollback_datetime),
            ('is_active', '=', True)
        ])

        # Group by person_id and extra_field_1 (instNr)
        person_inst_groups = {}
        for detail in new_versions:
            key = (detail.person_id.id, detail.extra_field_1 or '')
            if key not in person_inst_groups:
                person_inst_groups[key] = []
            person_inst_groups[key].append(detail)

        for (person_id, inst_nr), details_to_deactivate in person_inst_groups.items():
            # Deactivate the new versions
            for detail in details_to_deactivate:
                detail.write({'is_active': False})
                stats['person_details_deactivated'] += 1
                _logger.info(f"Rollback: Deactivated PersonDetails ID {detail.id}")

            # Find and reactivate the most recent version before the rollback point
            previous_version = PersonDetails.search([
                ('person_id', '=', person_id),
                ('extra_field_1', '=', inst_nr),
                ('create_date', '<=', self.rollback_datetime),
                ('is_active', '=', False)
            ], order='create_date desc', limit=1)

            if previous_version:
                previous_version.write({'is_active': True})
                stats['person_details_reactivated'] += 1
                _logger.info(f"Rollback: Reactivated PersonDetails ID {previous_version.id}")

        return stats

    def _create_reversal_tasks(self):
        """Create reversal backend tasks for external systems."""
        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']

        stats = {
            'reversal_tasks_created': 0,
        }

        # Find completed tasks after rollback point that affect external systems
        external_tasks = BeTask.search([
            ('status', '=', 'completed_ok'),
            ('processing_end', '>', self.rollback_datetime),
            ('target', 'in', ['LDAP', 'ALL'])
        ])

        # Map of actions to their reversal
        action_reversal_map = {
            'ADD': 'DEACT',
            'UPD': 'UPD',  # UPD reversal needs the old data
            'DEACT': 'ADD',  # Reactivate
        }

        for task in external_tasks:
            reversal_action = action_reversal_map.get(task.action)
            if not reversal_action:
                continue

            # Find or create the reversal task type
            reversal_type = BeTaskType.search([
                ('target', '=', task.target),
                ('object', '=', task.object_type),
                ('action', '=', reversal_action)
            ], limit=1)

            if not reversal_type:
                _logger.warning(f"Rollback: No reversal task type found for {task.target}-{task.object_type}-{reversal_action}")
                continue

            # Create reversal task with reference to original
            reversal_data = {
                'rollback_of_task': task.name,
                'original_data': task.data,
                'rollback_datetime': str(self.rollback_datetime),
            }

            BeTask.create({
                'betasktype_id': reversal_type.id,
                'data': str(reversal_data),
                'data2': task.data,  # Original data for reference
                'status': 'new',
                'automatic_sync': False,  # Manual review recommended
            })

            stats['reversal_tasks_created'] += 1
            _logger.info(f"Rollback: Created reversal task for {task.name}")

        return stats

    def _reset_backend_tasks(self):
        """Reset backend tasks completed after rollback point to 'new' status."""
        BeTask = self.env['myschool.betask']

        stats = {
            'tasks_reset': 0,
        }

        tasks_to_reset = BeTask.search([
            ('status', '=', 'completed_ok'),
            ('processing_end', '>', self.rollback_datetime)
        ])

        for task in tasks_to_reset:
            task.write({
                'status': 'new',
                'processing_start': False,
                'processing_end': False,
                'changes': f"[ROLLBACK] Reset by rollback to {self.rollback_datetime}\nOriginal changes:\n{task.changes or 'N/A'}",
            })
            stats['tasks_reset'] += 1
            _logger.info(f"Rollback: Reset task {task.name} to 'new'")

        return stats

    def _log_rollback_event(self, stats):
        """Log the rollback as a system event."""
        SysEvent = self.env.get('myschool.sys.event')
        if SysEvent:
            try:
                SysEvent.create({
                    'name': 'ROLLBACK',
                    'event_type': 'ROLLBACK',
                    'data': str({
                        'rollback_datetime': str(self.rollback_datetime),
                        'executed_by': self.env.user.name,
                        'stats': stats,
                    }),
                })
            except Exception as e:
                _logger.warning(f"Could not create rollback system event: {e}")


class InitSchoolyearWizard(models.TransientModel):
    _name = 'myschool.init.schoolyear.wizard'
    _description = 'Init Schooljaar Wizard'

    new_schoolyear_name = fields.Char(
        string='New Schoolyear',
        required=True,
        default=lambda self: self._default_new_schoolyear_name(),
    )

    def _default_new_schoolyear_name(self):
        """Suggest next schoolyear by parsing CurrentSchoolYear and incrementing."""
        ConfigItem = self.env['myschool.config.item']
        current = ConfigItem.get_ci_value_by_org_and_name('olvp', 'CurrentSchoolYear')
        if current and '-' in current:
            try:
                parts = current.split('-')
                return f"{int(parts[0]) + 1}-{int(parts[1]) + 1}"
            except (ValueError, IndexError):
                pass
        return ''

    def action_init(self):
        """Create PPSBR relations for all students in active classgroups for the new schoolyear."""
        self.ensure_one()

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        Role = self.env['myschool.role']
        Period = self.env['myschool.period']
        PeriodType = self.env['myschool.period.type']
        ConfigItem = self.env['myschool.config.item']
        CiRelation = self.env['myschool.ci.relation']

        # TODO: reactivate steps below when ready

        # # 1. Find Period with name = new_schoolyear_name and type SCHOOLJAAR
        # school_year_type = PeriodType.search([('name', '=', 'SCHOOLJAAR')], limit=1)
        # if not school_year_type:
        #     return self._notify('danger', 'PeriodType SCHOOLJAAR not found.')
        #
        # new_period = Period.search([
        #     ('name', '=', self.new_schoolyear_name),
        #     ('period_type_id', '=', school_year_type.id),
        # ], limit=1)
        # if not new_period:
        #     return self._notify('danger',
        #         f'Period "{self.new_schoolyear_name}" with type SCHOOLJAAR not found. '
        #         'Create it first via Master Data > Periods.')

        # # 2. Find STUDENT backend role
        # student_role = Role.search([('name', '=', 'STUDENT')], limit=1)
        # if not student_role:
        #     return self._notify('danger', 'Backend role STUDENT not found.')

        # # 3. Find PPSBR and PERSON-TREE proprelation types
        # ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        # person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        # if not ppsbr_type:
        #     return self._notify('danger', 'PropRelation type PPSBR not found.')

        # # 4. Find all active classgroup orgs
        # classgroup_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        # if not classgroup_type:
        #     return self._notify('danger', 'OrgType CLASSGROUP not found.')
        #
        # classgroups = Org.search([
        #     ('org_type_id', '=', classgroup_type.id),
        #     ('is_active', '=', True),
        # ])
        # if not classgroups:
        #     return self._notify('warning', 'No active classgroups found.')
        #
        # created = 0
        # skipped = 0
        # errors = 0
        #
        # for cg in classgroups:
        #     # Find school org by inst_nr (first active non-CLASSGROUP org with same inst_nr)
        #     school_org = Org.search([
        #         ('inst_nr', '=', cg.inst_nr),
        #         ('is_active', '=', True),
        #         ('org_type_id', '!=', classgroup_type.id),
        #     ], limit=1) if cg.inst_nr else None
        #
        #     if not school_org:
        #         _logger.warning(f'[INIT-SY] No school org found for classgroup {cg.name} (inst_nr={cg.inst_nr})')
        #         errors += 1
        #         continue
        #
        #     # Find all students via PERSON-TREE relations
        #     if not person_tree_type:
        #         continue
        #
        #     person_trees = PropRelation.search([
        #         ('proprelation_type_id', '=', person_tree_type.id),
        #         ('id_org', '=', cg.id),
        #         ('is_active', '=', True),
        #     ])
        #
        #     for pt in person_trees:
        #         person = pt.id_person
        #         if not person:
        #             continue
        #
        #         # Check if PPSBR already exists for this person + period + org + role
        #         existing = PropRelation.search([
        #             ('proprelation_type_id', '=', ppsbr_type.id),
        #             ('id_person', '=', person.id),
        #             ('id_period', '=', new_period.id),
        #             ('id_org', '=', school_org.id),
        #             ('id_role', '=', student_role.id),
        #         ], limit=1)
        #
        #         if existing:
        #             skipped += 1
        #             continue
        #
        #         try:
        #             ppsbr_name = build_proprelation_name(
        #                 'PPSBR',
        #                 id_person=person,
        #                 id_role=student_role,
        #                 id_org=school_org,
        #                 id_period=new_period,
        #             )
        #             PropRelation.create({
        #                 'name': ppsbr_name,
        #                 'proprelation_type_id': ppsbr_type.id,
        #                 'id_person': person.id,
        #                 'id_role': student_role.id,
        #                 'id_org': school_org.id,
        #                 'id_org_parent': school_org.id,
        #                 'id_period': new_period.id,
        #                 'is_active': True,
        #                 'is_organisational': True,
        #                 'automatic_sync': True,
        #                 'start_date': fields.Datetime.now(),
        #             })
        #             created += 1
        #         except Exception as e:
        #             _logger.error(f'[INIT-SY] Error creating PPSBR for {person.name}: {e}')
        #             errors += 1

        # # 5. Update CurrentSchoolYear config item
        # ci_relation = CiRelation.search([
        #     ('id_ci.name', '=', 'CurrentSchoolYear'),
        #     ('isactive', '=', True),
        # ], limit=1)
        # if ci_relation and ci_relation.id_ci:
        #     ci_relation.id_ci.set_value(self.new_schoolyear_name)
        #     _logger.info(f'[INIT-SY] Updated CurrentSchoolYear to {self.new_schoolyear_name}')

        # 6. Return placeholder notification
        return self._notify('info',
            f'Init Schooljaar wizard opened for "{self.new_schoolyear_name}". '
            'Processing steps are currently deactivated.')

    def _notify(self, ntype, message):
        """Return a notification action."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Init Schooljaar',
                'message': message,
                'type': ntype,
                'sticky': True,
            },
        }


class UpdateStudentRelationsWizard(models.TransientModel):
    _name = 'myschool.update.student.relations.wizard'
    _description = 'Fix Student PPSBRs (set id_org to classgroup)'

    def action_update(self):
        """Fix existing student PPSBRs: set id_org to classgroup org (from PERSON-TREE)."""
        self.ensure_one()

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        Role = self.env['myschool.role']
        Period = self.env['myschool.period']
        PeriodType = self.env['myschool.period.type']

        # 1. Get current schoolyear period
        school_year_type = PeriodType.search([('name', '=', 'SCHOOLJAAR')], limit=1)
        if not school_year_type:
            return self._notify('danger', 'PeriodType SCHOOLJAAR not found.')

        current_period = Period.search([
            ('is_active', '=', True),
            ('period_type_id', '=', school_year_type.id),
        ], limit=1)
        if not current_period:
            return self._notify('danger', 'No active SCHOOLJAAR period found.')

        # 2. Find STUDENT role and proprelation types
        student_role = Role.search([('name', '=', 'STUDENT')], limit=1)
        if not student_role:
            return self._notify('danger', 'Backend role STUDENT not found.')

        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not person_tree_type or not ppsbr_type:
            return self._notify('danger', 'PropRelation type PERSON-TREE or PPSBR not found.')

        # 3. Find all active classgroup orgs
        classgroup_type = OrgType.search([('name', '=', 'CLASSGROUP')], limit=1)
        if not classgroup_type:
            return self._notify('danger', 'OrgType CLASSGROUP not found.')

        classgroups = Org.search([
            ('org_type_id', '=', classgroup_type.id),
            ('is_active', '=', True),
        ])
        if not classgroups:
            return self._notify('warning', 'No active classgroups found.')

        # 4. Per classgroup: find students via PERSON-TREE, fix their PPSBR id_org
        updated_count = 0

        for cg in classgroups:
            person_trees = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', '=', cg.id),
                ('is_active', '=', True),
            ])

            for pt in person_trees:
                person = pt.id_person
                if not person:
                    continue

                # Find the student's PPSBR with STUDENT role
                ppsbr = PropRelation.search([
                    ('proprelation_type_id', '=', ppsbr_type.id),
                    ('id_person', '=', person.id),
                    ('id_role', '=', student_role.id),
                    ('is_active', '=', True),
                ], limit=1)

                if ppsbr and ppsbr.id_org.id != cg.id:
                    # PPSBR points to school instead of classgroup — fix it via betask
                    service = self.env['myschool.manual.task.service']
                    service.create_manual_task('PROPRELATION', 'UPD', {
                        'proprelation_id': ppsbr.id,
                        'vals': {
                            'id_org_parent': ppsbr.id_org.id,
                            'id_org': cg.id,
                        },
                    })
                    updated_count += 1

        return self._notify('success',
            f'Updated {updated_count} student PPSBRs across '
            f'{len(classgroups)} classgroups (period: {current_period.name}).')

    def _notify(self, ntype, message):
        """Return a notification action."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Update Student Relations',
                'message': message,
                'type': ntype,
                'sticky': True,
            },
        }


# ==========================================================================
# CREATE PERSONGROUP WIZARD
# ==========================================================================

class CreatePersongroupWizard(models.TransientModel):
    """Wizard to create a persongroup org under a school's OuForGroups org."""
    _name = 'myschool.create.persongroup.wizard'
    _description = 'Create Persongroup'

    parent_org_id = fields.Many2one('myschool.org', string='Parent Organization', required=True)
    parent_org_name = fields.Char(string='Parent Organization', readonly=True)
    group_name = fields.Char(string='Group Name', required=True,
        help='Human-readable name for the persongroup')
    group_name_short = fields.Char(string='Short Name (auto)', readonly=True,
        help='Lowercase, spaces replaced with hyphens')
    member_ids = fields.Many2many('myschool.person', string='Members',
        help='Select persons to add as members of this persongroup')

    # Preview fields (readonly, auto-computed)
    preview_com_group_name = fields.Char(string='Com Group Name', readonly=True)
    preview_com_group_email = fields.Char(string='Com Group Email', readonly=True)
    preview_ou_fqdn_internal = fields.Char(string='OU FQDN Internal', readonly=True)
    preview_ou_fqdn_external = fields.Char(string='OU FQDN External', readonly=True)
    preview_com_group_fqdn_internal = fields.Char(string='Com Group FQDN Internal', readonly=True)
    preview_com_group_fqdn_external = fields.Char(string='Com Group FQDN External', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'parent_org_id' in res and res['parent_org_id']:
            parent = self.env['myschool.org'].browse(res['parent_org_id'])
            if parent.exists():
                res['parent_org_name'] = parent.name_tree or parent.name
        return res

    def _resolve_parent_school(self):
        """Walk up ORG-TREE from parent_org_id to find the first non-admin SCHOOL org."""
        self.ensure_one()
        if not self.parent_org_id:
            return None

        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)

        current = self.parent_org_id
        visited = set()

        # Check if current org is already a non-admin SCHOOL
        if (school_type and current.org_type_id.id == school_type.id
                and not current.is_administrative):
            return current

        # Walk up the tree
        while current and current.id not in visited:
            visited.add(current.id)
            search_domain = [
                ('id_org', '=', current.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ]
            if org_tree_type:
                search_domain.append(('proprelation_type_id', '=', org_tree_type.id))

            parent_rel = PropRelation.search(search_domain, limit=1)
            if not parent_rel or not parent_rel.id_org_parent:
                break

            candidate = parent_rel.id_org_parent
            if (school_type and candidate.org_type_id.id == school_type.id
                    and not candidate.is_administrative):
                return candidate
            current = candidate

        return None

    def _resolve_ou_for_groups_org(self, school_org):
        """Find the OuForGroups CI value on the school, then locate the child org with that name_short."""
        if not school_org:
            return None, None

        ConfigItem = self.env['myschool.config.item']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']

        ou_value = ConfigItem.get_ci_value_by_org_and_name(school_org.name_short, 'OuForGroups')
        if not ou_value:
            return None, None

        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)

        # Find child of school with name_short == ou_value
        child_rels = PropRelation.search([
            ('proprelation_type_id', '=', org_tree_type.id),
            ('id_org_parent', '=', school_org.id),
            ('is_active', '=', True),
        ])
        child_org_ids = [r.id_org.id for r in child_rels if r.id_org]

        ou_org = None
        if child_org_ids:
            ou_org = Org.search([
                ('id', 'in', child_org_ids),
                ('name_short', '=', ou_value),
                ('is_active', '=', True),
            ], limit=1)

        return ou_value, ou_org

    def _build_persongroup_group_name(self, group_name_short, school_org):
        """Build com_group_name: grp-{group_name_short}-{school_short}."""
        if not group_name_short or not school_org:
            return False
        school_short = (school_org.name_short or school_org.name or '').lower()
        return f"grp-{group_name_short}-{school_short}"

    @api.onchange('group_name')
    def _onchange_group_name(self):
        """Compute all preview fields when group_name changes."""
        if not self.group_name or not self.parent_org_id:
            self.group_name_short = False
            self.preview_com_group_name = False
            self.preview_com_group_email = False
            self.preview_ou_fqdn_internal = False
            self.preview_ou_fqdn_external = False
            self.preview_com_group_fqdn_internal = False
            self.preview_com_group_fqdn_external = False
            return

        # Compute short name
        self.group_name_short = self.group_name.strip().lower().replace(' ', '-')

        # Resolve school and OuForGroups
        school_org = self._resolve_parent_school()
        if not school_org:
            return

        ou_value, ou_org = self._resolve_ou_for_groups_org(school_org)

        # Com group name
        self.preview_com_group_name = self._build_persongroup_group_name(
            self.group_name_short, school_org)

        # Com group email
        domain_ext = school_org.domain_external if school_org.domain_external else ''
        if self.preview_com_group_name and domain_ext:
            self.preview_com_group_email = f"{self.preview_com_group_name}@{domain_ext}"
        else:
            self.preview_com_group_email = False

        # OU FQDNs (persongroup placed under the OuForGroups org)
        if ou_org:
            if ou_org.ou_fqdn_internal:
                self.preview_ou_fqdn_internal = f"ou={self.group_name_short},{ou_org.ou_fqdn_internal.lower()}"
            else:
                self.preview_ou_fqdn_internal = False
            if ou_org.ou_fqdn_external:
                self.preview_ou_fqdn_external = f"ou={self.group_name_short},{ou_org.ou_fqdn_external.lower()}"
            else:
                self.preview_ou_fqdn_external = False
        else:
            self.preview_ou_fqdn_internal = False
            self.preview_ou_fqdn_external = False

        # Com group FQDNs: cn={com_group_name},ou={OuForGroups},{school_ou_fqdn}
        if self.preview_com_group_name:
            cn = self.preview_com_group_name.lower()
            if ou_value and school_org.ou_fqdn_internal:
                self.preview_com_group_fqdn_internal = f"cn={cn},ou={ou_value.lower()},{school_org.ou_fqdn_internal.lower()}"
            else:
                self.preview_com_group_fqdn_internal = False
            if ou_value and school_org.ou_fqdn_external:
                self.preview_com_group_fqdn_external = f"cn={cn},ou={ou_value.lower()},{school_org.ou_fqdn_external.lower()}"
            else:
                self.preview_com_group_fqdn_external = False
        else:
            self.preview_com_group_fqdn_internal = False
            self.preview_com_group_fqdn_external = False

    def _build_persongroup_task_data(self):
        """Build the data dict for a MANUAL/ORG/ADD betask for a persongroup."""
        self.ensure_one()

        if not self.group_name:
            raise UserError("Please enter a group name")

        school_org = self._resolve_parent_school()
        if not school_org:
            raise UserError("Could not resolve parent school organization")

        ou_value, ou_org = self._resolve_ou_for_groups_org(school_org)
        if not ou_org:
            raise UserError(
                f"Could not find OuForGroups org under school {school_org.name}. "
                f"Make sure the OuForGroups CI is configured.")

        # Get PERSONGROUP org type
        OrgType = self.env['myschool.org.type']
        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        if not pg_type:
            raise UserError("PERSONGROUP org type not found. Please create it first.")

        group_name_short = self.group_name.strip().lower().replace(' ', '-')
        com_group_name = self._build_persongroup_group_name(group_name_short, school_org)

        data = {
            'parent_org_id': ou_org.id,  # Place under OuForGroups org
            'org_type_name': 'PERSONGROUP',
            'org_type_id': pg_type.id,
            'name': self.group_name.strip(),
            'name_short': group_name_short,
            'inst_nr': school_org.inst_nr or '',
            'has_ou': True,
            'has_comgroup': True,
            'has_secgroup': False,
            'has_role': False,
            'com_group_name': com_group_name,
            'domain_internal': school_org.domain_internal or '',
            'domain_external': school_org.domain_external or '',
        }

        # Com group email
        if com_group_name and school_org.domain_external:
            data['com_group_email'] = f"{com_group_name}@{school_org.domain_external}"

        # OU FQDNs
        if ou_org.ou_fqdn_internal:
            data['ou_fqdn_internal'] = f"ou={group_name_short},{ou_org.ou_fqdn_internal.lower()}"
        if ou_org.ou_fqdn_external:
            data['ou_fqdn_external'] = f"ou={group_name_short},{ou_org.ou_fqdn_external.lower()}"

        # Com group FQDNs
        if com_group_name and ou_value:
            if school_org.ou_fqdn_internal:
                data['com_group_fqdn_internal'] = f"cn={com_group_name.lower()},ou={ou_value.lower()},{school_org.ou_fqdn_internal.lower()}"
            if school_org.ou_fqdn_external:
                data['com_group_fqdn_external'] = f"cn={com_group_name.lower()},ou={ou_value.lower()},{school_org.ou_fqdn_external.lower()}"

        # name_tree
        if data.get('ou_fqdn_internal'):
            name_tree = compute_name_tree(
                self.env,
                {'name_short': group_name_short, 'ou_fqdn_internal': data['ou_fqdn_internal']},
                None,
            )
            if name_tree:
                data['name_tree'] = name_tree

        # Member IDs
        if self.member_ids:
            data['member_ids'] = self.member_ids.ids

        return data

    def action_create(self):
        """Create persongroup via betask and open it for editing."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        task = service.create_manual_task('ORG', 'ADD', self._build_persongroup_task_data())

        # Try to open the created org
        org_id = self._extract_org_id_from_task(task)
        if org_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'myschool.org',
                'res_id': org_id,
                'views': [[False, 'form']],
                'target': 'new',
                'context': {'form_view_initial_mode': 'edit'},
            }
        return {'type': 'ir.actions.act_window_close'}

    def action_create_and_close(self):
        """Create persongroup via betask and return to browser."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        service.create_manual_task('ORG', 'ADD', self._build_persongroup_task_data())

        return {'type': 'ir.actions.act_window_close'}

    def _extract_org_id_from_task(self, task):
        """Try to extract the created org ID from the task's changes field."""
        import re
        if task.changes:
            match = re.search(r'Created org:.*\(ID:\s*(\d+)\)', task.changes)
            if match:
                return int(match.group(1))
        return None


# ==========================================================================
# MANAGE PERSONGROUP MEMBERS WIZARD
# ==========================================================================

class ManagePersongroupMembersWizard(models.TransientModel):
    """Wizard to manage members (persons) of a persongroup."""
    _name = 'myschool.manage.persongroup.members.wizard'
    _description = 'Manage Persongroup Members'

    persongroup_id = fields.Many2one('myschool.org', string='Persongroup', required=True)
    persongroup_name = fields.Char(string='Persongroup', readonly=True)
    current_member_ids = fields.Many2many(
        'myschool.person', 'persongroup_wizard_current_members_rel',
        string='Current Members', readonly=True)
    add_member_ids = fields.Many2many(
        'myschool.person', 'persongroup_wizard_add_members_rel',
        string='Add Members')
    remove_member_ids = fields.Many2many(
        'myschool.person', 'persongroup_wizard_remove_members_rel',
        string='Remove Members')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        pg_id = res.get('persongroup_id')
        if pg_id:
            pg = self.env['myschool.org'].browse(pg_id)
            if pg.exists():
                res['persongroup_name'] = pg.name_tree or pg.name

                # Load current members from active PG-P proprelations
                PropRelation = self.env['myschool.proprelation']
                PropRelationType = self.env['myschool.proprelation.type']
                pg_p_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
                if pg_p_type:
                    rels = PropRelation.search([
                        ('proprelation_type_id', '=', pg_p_type.id),
                        ('id_org', '=', pg_id),
                        ('is_active', '=', True),
                    ])
                    member_ids = [r.id_person.id for r in rels if r.id_person]
                    res['current_member_ids'] = [(6, 0, member_ids)]
        return res

    def action_apply(self):
        """Create betasks for adding/removing members."""
        self.ensure_one()

        service = self.env['myschool.manual.task.service']
        pg_id = self.persongroup_id.id
        changes = []

        # Add new members
        for person in self.add_member_ids:
            service.create_manual_task('PROPRELATION', 'ADD', {
                'type': 'PG-P',
                'org_id': pg_id,
                'person_id': person.id,
            })
            changes.append(f"Adding {person.name}")

        # Remove members
        for person in self.remove_member_ids:
            service.create_manual_task('PROPRELATION', 'DEACT', {
                'type': 'PG-P',
                'org_id': pg_id,
                'person_id': person.id,
            })
            changes.append(f"Removing {person.name}")

        return {'type': 'ir.actions.act_window_close'}

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}


class CleanupWizard(models.TransientModel):
    """
    Wizard to archive or permanently delete old backend tasks or system events.

    Opened from two menu items (Backend Tasks > Cleanup and System Events > Cleanup)
    with context setting the default cleanup_target. Retention days are stored as a
    CI on the schoolboard org and persist across uses.
    """
    _name = 'myschool.cleanup.wizard'
    _description = 'Cleanup Old Records'

    cleanup_target = fields.Selection(
        selection=[
            ('betasks', 'Backend Tasks'),
            ('events', 'System Events'),
        ],
        string='Cleanup Target',
        required=True,
        readonly=True,
    )

    cleanup_action = fields.Selection(
        selection=[
            ('archive', 'Archive'),
            ('delete', 'Permanently Delete'),
        ],
        string='Action',
        required=True,
        default='archive',
    )

    clean_all = fields.Boolean(
        string='Clean All',
        default=False,
        help='Ignore retention period and clean all matching records, including today.',
    )

    retention_days = fields.Integer(
        string='Retention Days',
        required=True,
        default=90,
        help='Records older than this many days will be cleaned up',
    )

    cutoff_date = fields.Date(
        string='Cutoff Date',
        compute='_compute_preview',
        store=False,
    )

    preview_count = fields.Integer(
        string='Matching Records',
        compute='_compute_preview',
        store=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ci = self._get_retention_ci()
        if ci and ci.integer_value:
            res['retention_days'] = ci.integer_value
        return res

    def _get_schoolboard_org(self):
        sb_type = self.env['myschool.org.type'].search([('name', '=', 'SCHOOLBOARD')], limit=1)
        if not sb_type:
            return self.env['myschool.org']
        return self.env['myschool.org'].search([('org_type_id', '=', sb_type.id), ('is_active', '=', True)], limit=1)

    def _get_retention_ci(self):
        return self.env['myschool.config.item'].search([('name', '=', 'CLEANUP_RETENTION_DAYS')], limit=1)

    def _get_status_domain(self):
        if self.cleanup_target == 'betasks':
            return [('status', 'in', ('completed_ok', 'error'))]
        elif self.cleanup_target == 'events':
            return [('status', 'in', ('CLOSED', 'PRO_ERROR'))]
        return []

    def _get_model(self):
        if self.cleanup_target == 'betasks':
            return self.env['myschool.betask'].with_context(active_test=False)
        elif self.cleanup_target == 'events':
            return self.env['myschool.sys.event'].with_context(active_test=False)
        return None

    def _get_search_domain(self):
        if self.clean_all:
            return []
        domain = self._get_status_domain()
        cutoff = fields.Datetime.now() - timedelta(days=self.retention_days)
        domain.append(('create_date', '<', cutoff))
        return domain

    @api.depends('retention_days', 'cleanup_target', 'clean_all')
    def _compute_preview(self):
        for wizard in self:
            if not wizard.clean_all and (not wizard.retention_days or wizard.retention_days < 1):
                wizard.cutoff_date = False
                wizard.preview_count = 0
                continue

            if wizard.clean_all:
                wizard.cutoff_date = False
            else:
                cutoff = fields.Datetime.now() - timedelta(days=wizard.retention_days)
                wizard.cutoff_date = cutoff.date()

            model = wizard._get_model()
            if model is not None:
                wizard.preview_count = model.search_count(wizard._get_search_domain())
            else:
                wizard.preview_count = 0

    def _save_retention_ci(self):
        ci = self._get_retention_ci()
        if not ci:
            ci = self.env['myschool.config.item'].create({
                'name': 'CLEANUP_RETENTION_DAYS',
                'scope': 'org',
                'type': 'setting',
                'integer_value': self.retention_days,
                'description': 'Number of days to retain completed/error backend tasks and closed/error system events before cleanup.',
            })
            sb_org = self._get_schoolboard_org()
            if sb_org:
                self.env['myschool.ci.relation'].create({
                    'id_ci': ci.id,
                    'id_org': sb_org.id,
                })
        else:
            ci.write({'integer_value': self.retention_days})

    def action_cleanup(self):
        self.ensure_one()
        if not self.clean_all and self.retention_days < 1:
            raise UserError("Retention days must be at least 1.")

        self._save_retention_ci()

        model = self._get_model()
        if model is None:
            raise UserError("Invalid cleanup target.")

        domain = self._get_search_domain()
        records = model.search(domain)
        count = len(records)
        label = 'backend tasks' if self.cleanup_target == 'betasks' else 'system events'

        _logger.info(
            "Cleanup wizard: target=%s, action=%s, clean_all=%s, domain=%s, found=%d records",
            self.cleanup_target, self.cleanup_action, self.clean_all, domain, count,
        )

        if self.cleanup_action == 'archive':
            records.write({'active': False})
            action_label = 'Archived'
        else:
            records.unlink()
            action_label = 'Permanently deleted'

        if self.clean_all:
            period = '(all matching records)'
        else:
            period = f'older than {self.retention_days} days'

        msg = f'{action_label} {count} {label} {period}.'
        _logger.info("Cleanup wizard result: %s", msg)

        # Reopen the matching list view so the user sees the updated data
        if self.cleanup_target == 'betasks':
            action = self.env['ir.actions.act_window']._for_xml_id('myschool_admin.action_betask_all')
        else:
            action = self.env['ir.actions.act_window']._for_xml_id('myschool_admin.action_sys_event_all')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cleanup Complete',
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': action,
            },
        }
