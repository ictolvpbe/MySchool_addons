# -*- coding: utf-8 -*-
"""
Object Browser Wizards
======================
Wizards for add, move, and bulk operations.
"""

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
    
    org = Org.browse(org_id)
    if not org.exists():
        return
    
    # Update this org's name_tree
    new_name_tree = compute_name_tree(env, org)
    if new_name_tree and org.name_tree != new_name_tree:
        org.write({'name_tree': new_name_tree})
        _logger.info(f"Updated name_tree for org {org.name_short}: {new_name_tree}")
    
    # Find and update all child orgs recursively
    child_rels = PropRelation.search([
        ('id_org_parent', '=', org_id),
        ('id_org', '!=', False),
        ('is_active', '=', True),
    ])
    
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
        """Get parent org via proprelation."""
        if debug_lines is None:
            debug_lines = []
            
        if not org:
            debug_lines.append("_get_parent_org: org is None")
            return None
        
        debug_lines.append(f"_get_parent_org: Looking for parent of org.id={org.id}, org.name={org.name}")
        
        try:
            PropRelation = self.env['myschool.proprelation']
            # id_org = current org (child), id_org_parent = parent org
            parent_rel = PropRelation.search([
                ('id_org', '=', org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel:
                debug_lines.append(f"_get_parent_org: Found relation id={parent_rel.id}")
                if parent_rel.id_org_parent:
                    debug_lines.append(f"_get_parent_org: Parent is {parent_rel.id_org_parent.name} (id={parent_rel.id_org_parent.id})")
                    return parent_rel.id_org_parent
                else:
                    debug_lines.append("_get_parent_org: id_org_parent is empty")
            else:
                debug_lines.append("_get_parent_org: No proprelation found with id_org_parent")
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
        """Get or create a proprelation type by name."""
        try:
            PropRelationType = self.env['myschool.proprelation.type']
            rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
            if not rel_type:
                rel_type = PropRelationType.create({'name': type_name, 'is_active': True})
            return rel_type
        except KeyError:
            return None

    def _get_parent_orgs(self, org):
        """Get all parent organizations in the tree (including the org itself)."""
        orgs = [org]
        PropRelation = self.env['myschool.proprelation']
        
        current_org = org
        max_depth = 20  # Prevent infinite loops
        depth = 0
        visited_ids = {org.id}  # Track visited orgs to prevent cycles
        
        _logger.info(f"Starting parent org search for: {org.name} (id={org.id})")
        
        while current_org and depth < max_depth:
            parent_org = None
            
            # Pattern 1: id_org (child) + id_org_parent (parent) - primary pattern
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            _logger.info(f"Depth {depth}: Looking for parent of {current_org.name} (id={current_org.id})")
            _logger.info(f"  Pattern 1 search result: {parent_rel.id if parent_rel else 'None'}")
            
            if parent_rel and parent_rel.id_org_parent:
                parent_org = parent_rel.id_org_parent
                _logger.info(f"  Found parent via Pattern 1: {parent_org.name} (id={parent_org.id})")
            
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
        OrgType = self.env['myschool.org.type']
        
        # Get SCHOOL org type
        school_type = OrgType.search([('name', '=', 'SCHOOL')], limit=1)
        if not school_type:
            _logger.warning("SCHOOL org type not found")
            return None
        
        # Check if start_org itself is a non-administrative school
        if (start_org.org_type_id and 
            start_org.org_type_id.id == school_type.id and 
            not start_org.is_administrative):
            return start_org
        
        # Walk up the tree to find a school
        current_org = start_org
        visited_ids = {current_org.id}
        max_depth = 20
        
        for _ in range(max_depth):
            # Find parent via ORG-TREE relation
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
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
                # Create with standardized name (include school if found)
                rel_name = build_proprelation_name(
                    'PPSBR',
                    id_role=role,
                    id_org_parent=school_org,
                    id_person=person
                )
                
                proprel_vals = {
                    'name': rel_name,
                    'proprelation_type_id': ppsbr_type.id,
                    'id_person': person.id,
                    'id_role': role.id,
                    'is_active': True,
                }
                
                # Add school org as id_org_parent if found
                if school_org:
                    proprel_vals['id_org_parent'] = school_org.id
                
                PropRelation.create(proprel_vals)
                _logger.info(f"Created PPSBR relation: {role.name} -> {person_name} (school: {school_org.name if school_org else 'None'})")

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

    def action_create(self):
        """Create the person and optionally link/create Odoo user."""
        self.ensure_one()
        
        Person = self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        
        # Prepare person values
        person_vals = {
            'first_name': self.first_name,
            'name': self.last_name,
            'is_active': True,
        }
        
        # Get external_domain (can't rely on readonly field being sent back)
        external_domain = self._get_domain_external_static(self.org_id, [])
        _logger.info(f"external_domain for email generation: {external_domain}")
        
        # Generate email based on person type
        email_cloud = None
        if self.person_type in ('employee', 'student_so'):
            # Standard email: firstname.lastname@domain
            if self.first_name and self.last_name and external_domain:
                clean_first = self._remove_diacritics(self.first_name).replace(' ', '').lower()
                clean_last = self._remove_diacritics(self.last_name).replace(' ', '').lower()
                email_cloud = f"{clean_first}.{clean_last}@{external_domain}"
        elif self.person_type == 'student_basis':
            # Student basis email: b+sap_ref+1631@domain
            if self.sap_ref and external_domain:
                clean_sap_ref = self.sap_ref.replace(' ', '')
                email_cloud = f"b{clean_sap_ref}1631@{external_domain}"
        
        if email_cloud:
            person_vals['email_cloud'] = email_cloud
            _logger.info(f"Generated email_cloud: {email_cloud}")
        else:
            _logger.warning(f"Could not generate email: person_type={self.person_type}, first_name={self.first_name}, last_name={self.last_name}, sap_ref={self.sap_ref}, external_domain={external_domain}")
        
        # Store email_private if provided
        if self.email_private:
            person_vals['email_private'] = self.email_private
            _logger.info(f"Storing email_private: {self.email_private}")
        
        # Store sap_ref directly
        if self.sap_ref:
            person_vals['sap_ref'] = self.sap_ref
            _logger.info(f"Storing sap_ref: {self.sap_ref}")
        
        # Set person_type_id based on wizard selection
        person_type_name = None
        if self.person_type == 'employee':
            person_type_name = 'EMPLOYEE'
        elif self.person_type in ('student_so', 'student_basis'):
            person_type_name = 'STUDENT'
        
        if person_type_name:
            try:
                PersonType = self.env['myschool.person.type']
                # Log all available person types for debugging
                all_types = PersonType.search([])
                _logger.info(f"Available person types: {[(t.id, t.name) for t in all_types]}")
                
                # Search case-insensitive
                pt = PersonType.search([('name', '=ilike', person_type_name)], limit=1)
                if pt:
                    person_vals['person_type_id'] = pt.id
                    _logger.info(f"Found person type: {pt.name} (id={pt.id})")
                else:
                    _logger.warning(f"Person type '{person_type_name}' not found in database")
            except Exception as e:
                _logger.warning(f"Error looking up person type: {str(e)}")
        
        # Store employee-specific fields
        if self.person_type == 'employee':
            if self.abbreviation:
                person_vals['abbreviation'] = self.abbreviation
        
        _logger.info(f"Final person_vals before create: {person_vals}")
        
        # Handle Odoo user linking/creation
        user = None
        hr_employee = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            # Create new Odoo user
            login = self.odoo_user_login or self.email_cloud
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            # Check if login already exists
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email_cloud or login,
            })
            
            # Create HR employee for employees
            if self.person_type == 'employee' and 'hr.employee' in self.env:
                hr_employee = self.env['hr.employee'].create({
                    'name': f"{self.first_name} {self.last_name}",
                    'user_id': user.id,
                    'work_email': self.email_cloud or login,
                })
                _logger.info(f"Created HR employee {hr_employee.name} with id={hr_employee.id}")
        
        # Link user if available
        if user and 'user_id' in Person._fields:
            person_vals['user_id'] = user.id
        
        # Create person
        _logger.info(f"Creating person with vals: {person_vals}")
        person = Person.create(person_vals)
        _logger.info(f"Created person id={person.id}, email_cloud={person.email_cloud}, person_type_id={person.person_type_id.id if person.person_type_id else None}")
        
        # Determine role based on selection
        role = None
        if self.person_type == 'employee':
            role = self._get_role_by_name('EMPLOYEE')
        elif self.person_type == 'student_so':
            role = self._get_role_by_name('STUDENT_SO')
        elif self.person_type == 'student_basis':
            role = self._get_role_by_name('STUDENT_BASIS')
        
        # Get or create PERSON-TREE relation type
        relation_type = self._get_or_create_proprelation_type('PERSON-TREE')
        
        # Build proprelation name using standardized format (PERSON-TREE only uses person and org)
        proprel_name = build_proprelation_name(
            'PERSON-TREE',
            id_person=person,
            id_org=self.org_id
        )
        
        # Create proprelation to org (PERSON-TREE only links person to org, no role)
        proprel_vals = {
            'name': proprel_name,
            'id_person': person.id,
            'id_org': self.org_id.id,
            'is_active': True,
        }
        if relation_type:
            proprel_vals['proprelation_type_id'] = relation_type.id
        
        PropRelation.create(proprel_vals)
        
        # Assign roles from parent org tree to person (creates separate PPSBR relations)
        self._assign_roles_to_person(person)
        
        _logger.info(f"Created person {person.name} in org {self.org_id.name}")
        
        # Open the person form for editing in a new dialog
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.person',
            'res_id': person.id,
            'views': [[False, 'form']],
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_create_and_close(self):
        """Create person and return to browser."""
        self.ensure_one()
        
        Person = self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        
        # Prepare person values
        person_vals = {
            'first_name': self.first_name,
            'name': self.last_name,
            'is_active': True,
        }
        
        # Get external_domain (can't rely on readonly field being sent back)
        external_domain = self._get_domain_external_static(self.org_id, [])
        
        # Generate email based on person type
        email_cloud = None
        if self.person_type in ('employee', 'student_so'):
            # Standard email: firstname.lastname@domain
            if self.first_name and self.last_name and external_domain:
                clean_first = self._remove_diacritics(self.first_name).replace(' ', '').lower()
                clean_last = self._remove_diacritics(self.last_name).replace(' ', '').lower()
                email_cloud = f"{clean_first}.{clean_last}@{external_domain}"
        elif self.person_type == 'student_basis':
            # Student basis email: b+sap_ref+1631@domain
            if self.sap_ref and external_domain:
                clean_sap_ref = self.sap_ref.replace(' ', '')
                email_cloud = f"b{clean_sap_ref}1631@{external_domain}"
        
        if email_cloud:
            person_vals['email_cloud'] = email_cloud
        
        # Store email_private if provided
        if self.email_private:
            person_vals['email_private'] = self.email_private
        
        # Store sap_ref directly
        if self.sap_ref:
            person_vals['sap_ref'] = self.sap_ref
        
        # Set person_type_id based on wizard selection
        person_type_name = None
        if self.person_type == 'employee':
            person_type_name = 'EMPLOYEE'
        elif self.person_type in ('student_so', 'student_basis'):
            person_type_name = 'STUDENT'
        
        if person_type_name:
            try:
                PersonType = self.env['myschool.person.type']
                # Search case-insensitive
                pt = PersonType.search([('name', '=ilike', person_type_name)], limit=1)
                if pt:
                    person_vals['person_type_id'] = pt.id
            except Exception:
                pass
        
        # Store employee-specific fields
        if self.person_type == 'employee':
            if self.abbreviation:
                person_vals['abbreviation'] = self.abbreviation
        
        # Handle Odoo user
        user = None
        hr_employee = None
        if self.link_existing_user and self.existing_user_id:
            user = self.existing_user_id
        elif self.create_odoo_user:
            login = self.odoo_user_login or self.email_cloud
            if not login:
                raise UserError("Login or email is required to create Odoo user")
            
            existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
            if existing_user:
                raise UserError(f"A user with login '{login}' already exists")
            
            user = self.env['res.users'].create({
                'name': f"{self.first_name} {self.last_name}",
                'login': login,
                'email': self.email_cloud or login,
            })
            
            # Create HR employee for employees
            if self.person_type == 'employee' and 'hr.employee' in self.env:
                hr_employee = self.env['hr.employee'].create({
                    'name': f"{self.first_name} {self.last_name}",
                    'user_id': user.id,
                    'work_email': self.email_cloud or login,
                })
                _logger.info(f"Created HR employee {hr_employee.name} with id={hr_employee.id}")
        
        if user and 'user_id' in Person._fields:
            person_vals['user_id'] = user.id
        
        person = Person.create(person_vals)
        
        # Determine role based on selection
        role = None
        if self.person_type == 'employee':
            role = self._get_role_by_name('EMPLOYEE')
        elif self.person_type == 'student_so':
            role = self._get_role_by_name('STUDENT_SO')
        elif self.person_type == 'student_basis':
            role = self._get_role_by_name('STUDENT_BASIS')
        
        # Get or create PERSON-TREE relation type
        relation_type = self._get_or_create_proprelation_type('PERSON-TREE')
        
        # Build proprelation name using standardized format (PERSON-TREE only uses person and org)
        proprel_name = build_proprelation_name(
            'PERSON-TREE',
            id_person=person,
            id_org=self.org_id
        )
        
        # Create proprelation to org (PERSON-TREE only links person to org, no role)
        proprel_vals = {
            'name': proprel_name,
            'id_person': person.id,
            'id_org': self.org_id.id,
            'is_active': True,
        }
        if relation_type:
            proprel_vals['proprelation_type_id'] = relation_type.id
        
        PropRelation.create(proprel_vals)
        
        # Assign roles from parent org tree to person (creates separate PPSBR relations)
        self._assign_roles_to_person(person)
        
        return {'type': 'ir.actions.act_window_close'}


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
    
    # Security group name - populated by onchange when has_secgroup is True
    new_org_sec_group_name = fields.Char(string='Security Group Name',
        help='Auto-generated from organization hierarchy (bgrp-parent1-parent2-...)')
    new_org_sec_group_fqdn_internal = fields.Char(string='Sec Group FQDN Internal',
        help='CN=sec_group_name,ou_fqdn_internal')
    new_org_sec_group_fqdn_external = fields.Char(string='Sec Group FQDN External',
        help='CN=sec_group_name,ou_fqdn_external')
    
    # Boolean flags
    new_org_has_ou = fields.Boolean(string='Heeft OU', default=False)
    new_org_has_role = fields.Boolean(string='Heeft Role', default=False)
    new_org_has_comgroup = fields.Boolean(string='Heeft Communicatiegroep', default=False)
    new_org_has_secgroup = fields.Boolean(string='Heeft Securitygroep', default=False)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values including parent_org_name and OU FQDN fields."""
        res = super().default_get(fields_list)
        if 'parent_org_id' in res and res['parent_org_id']:
            parent = self.env['myschool.org'].browse(res['parent_org_id'])
            if parent.exists():
                res['parent_org_name'] = parent.name_tree or parent.name
                
                # Initialize OU FQDN fields with placeholder (lowercase)
                ou_prefix = "ou=new,"
                
                if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                    res['new_org_ou_fqdn_intern'] = ou_prefix + parent.ou_fqdn_internal.lower()
                else:
                    res['new_org_ou_fqdn_intern'] = ou_prefix
                
                if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                    res['new_org_ou_fqdn_extern'] = ou_prefix + parent.ou_fqdn_external.lower()
                else:
                    res['new_org_ou_fqdn_extern'] = ou_prefix
        return res
    
    # Optional fields
    new_org_type_id = fields.Many2one('myschool.org.type', string='Organization Type')
    new_org_description = fields.Text(string='Description')

    @api.depends('parent_org_id')
    def _compute_inherited_fields(self):
        """Auto-inherit fields from parent organization."""
        for wizard in self:
            if wizard.parent_org_id:
                parent = wizard.parent_org_id
                
                # Set parent name for display (use name_tree)
                wizard.parent_org_name = parent.name_tree or parent.name
                
                # Inherit inst_nr
                if hasattr(parent, 'inst_nr') and parent.inst_nr:
                    wizard.new_org_inst_nr = parent.inst_nr
                else:
                    wizard.new_org_inst_nr = False
            else:
                wizard.parent_org_name = False
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
        
        # Walk up the parent chain
        PropRelation = self.env['myschool.proprelation']
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
            
            # Find parent via proprelation
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                current_org = parent_rel.id_org_parent
            else:
                break
        
        if parts:
            return prefix + '-'.join(parts)
        return False

    @api.onchange('new_org_name_short')
    def _onchange_name_short_update_fqdn(self):
        """Update OU FQDN and group names when short name changes."""
        if self.parent_org_id and self.new_org_name_short:
            parent = self.parent_org_id
            # Make OU prefix lowercase
            ou_prefix = f"ou={self.new_org_name_short.lower()},"
            
            # Always update OU FQDN fields (regardless of has_ou flag)
            # OU FQDN Internal - all lowercase
            if hasattr(parent, 'ou_fqdn_internal') and parent.ou_fqdn_internal:
                self.new_org_ou_fqdn_intern = ou_prefix + parent.ou_fqdn_internal.lower()
            else:
                self.new_org_ou_fqdn_intern = ou_prefix
            
            # OU FQDN External - all lowercase
            if hasattr(parent, 'ou_fqdn_external') and parent.ou_fqdn_external:
                self.new_org_ou_fqdn_extern = ou_prefix + parent.ou_fqdn_external.lower()
            else:
                self.new_org_ou_fqdn_extern = ou_prefix
            
            # Update com_group_name and FQDNs only if has_comgroup is True
            if self.new_org_has_comgroup:
                self.new_org_com_group_name = self._build_group_name('grp-')
                self._update_com_group_fqdns()
            
            # Update sec_group_name and FQDNs only if has_secgroup is True
            if self.new_org_has_secgroup:
                self.new_org_sec_group_name = self._build_group_name('bgrp-')
                self._update_sec_group_fqdns()
    
    @api.onchange('new_org_has_ou')
    def _onchange_has_ou(self):
        """Recalculate group FQDNs when has_ou checkbox changes."""
        # OU FQDN fields are always calculated, but group FQDNs depend on them
        if self.new_org_has_ou:
            # Recalculate group FQDNs if groups are enabled
            if self.new_org_has_comgroup:
                self._update_com_group_fqdns()
            if self.new_org_has_secgroup:
                self._update_sec_group_fqdns()
    
    @api.onchange('new_org_has_comgroup')
    def _onchange_has_comgroup(self):
        """Update com_group_name and FQDNs when has_comgroup checkbox changes."""
        if self.new_org_has_comgroup and self.parent_org_id:
            # First calculate the group name
            self.new_org_com_group_name = self._build_group_name('grp-')
            # Then calculate FQDNs based on group name and OU paths
            self._update_com_group_fqdns()
        else:
            self.new_org_com_group_name = False
            self.new_org_com_group_fqdn_internal = False
            self.new_org_com_group_fqdn_external = False
    
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
            
            # Walk up the org hierarchy to find the CI
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
                
                # Move to parent org
                try:
                    PropRelation = self.env['myschool.proprelation']
                    parent_rel = PropRelation.search([
                        ('id_org', '=', current_org.id),
                        ('id_org_parent', '!=', False),
                        ('is_active', '=', True),
                    ], limit=1)
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
    
    @api.onchange('new_org_has_secgroup')
    def _onchange_has_secgroup(self):
        """Update sec_group_name and FQDNs when has_secgroup checkbox changes."""
        if self.new_org_has_secgroup and self.parent_org_id:
            # First calculate the group name
            self.new_org_sec_group_name = self._build_group_name('bgrp-')
            # Then calculate FQDNs based on group name and OU paths
            self._update_sec_group_fqdns()
        else:
            self.new_org_sec_group_name = False
            self.new_org_sec_group_fqdn_internal = False
            self.new_org_sec_group_fqdn_external = False
    
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
        """Suggest name_short from name."""
        if self.new_org_name and not self.new_org_name_short:
            # Create abbreviation from first letters of words
            words = self.new_org_name.split()
            if len(words) > 1:
                self.new_org_name_short = ''.join(w[0].upper() for w in words if w)
            else:
                self.new_org_name_short = self.new_org_name[:10].upper()

    def action_add(self):
        """Add the child organization and open it for editing."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        Org = self.env['myschool.org']
        
        if self.use_existing:
            if not self.existing_org_id:
                raise UserError("Please select an existing organization")
            child_org = self.existing_org_id
        else:
            if not self.new_org_name:
                raise UserError("Please enter a name for the new organization")
            if not self.new_org_name_short:
                raise UserError("Please enter a short name for the organization")
            if not self.new_org_inst_nr:
                raise UserError("Please enter an institution number")
            
            # Create new org with required fields
            org_vals = {
                'name': self.new_org_name,
                'name_short': self.new_org_name_short,
                'inst_nr': self.new_org_inst_nr,
                'is_active': True,
            }
            
            # Add OU FQDN fields if present
            if self.new_org_ou_fqdn_intern:
                org_vals['ou_fqdn_internal'] = self.new_org_ou_fqdn_intern
            if self.new_org_ou_fqdn_extern:
                org_vals['ou_fqdn_external'] = self.new_org_ou_fqdn_extern
            
            # Add com_group fields if present
            if self.new_org_com_group_name:
                org_vals['com_group_name'] = self.new_org_com_group_name
            if self.new_org_com_group_fqdn_internal:
                org_vals['com_group_fqdn_internal'] = self.new_org_com_group_fqdn_internal
            if self.new_org_com_group_fqdn_external:
                org_vals['com_group_fqdn_external'] = self.new_org_com_group_fqdn_external
            
            # Add sec_group fields if present
            if self.new_org_sec_group_name:
                org_vals['sec_group_name'] = self.new_org_sec_group_name
            if self.new_org_sec_group_fqdn_internal:
                org_vals['sec_group_fqdn_internal'] = self.new_org_sec_group_fqdn_internal
            if self.new_org_sec_group_fqdn_external:
                org_vals['sec_group_fqdn_external'] = self.new_org_sec_group_fqdn_external
            
            # Add boolean flags
            org_vals['has_ou'] = self.new_org_has_ou
            org_vals['has_role'] = self.new_org_has_role
            org_vals['has_comgroup'] = self.new_org_has_comgroup
            org_vals['has_secgroup'] = self.new_org_has_secgroup
            
            # Compute and set name_tree from ou_fqdn_internal
            if self.new_org_ou_fqdn_intern:
                name_tree = compute_name_tree(self.env, {'name_short': self.new_org_name_short, 'ou_fqdn_internal': self.new_org_ou_fqdn_intern}, None)
                if name_tree:
                    org_vals['name_tree'] = name_tree
            
            if self.new_org_type_id:
                org_vals['org_type_id'] = self.new_org_type_id.id
            if self.new_org_description and 'description' in Org._fields:
                org_vals['description'] = self.new_org_description
            
            child_org = Org.create(org_vals)
        
        # Check for circular reference
        if child_org.id == self.parent_org_id.id:
            raise UserError("An organization cannot be its own parent")
        
        # Check if already a child
        existing = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '=', self.parent_org_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"{child_org.name} is already a child of {self.parent_org_id.name}")
        
        # Deactivate any existing parent relation
        old_parent = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ])
        if old_parent:
            old_parent.write({'is_active': False})
        
        # Get or create ORG-TREE proprelation type
        PropRelationType = self.env['myschool.proprelation.type']
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
            id_org=child_org,
            id_org_parent=self.parent_org_id
        )
        
        # Create new parent relation
        PropRelation.create({
            'name': relation_name,
            'proprelation_type_id': org_tree_type.id,
            'id_org': child_org.id,
            'id_org_parent': self.parent_org_id.id,
            'is_active': True,
        })
        
        _logger.info(f"Added org {child_org.name} under {self.parent_org_id.name}")
        
        # Open the org form for further editing in a new dialog
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.org',
            'res_id': child_org.id,
            'views': [[False, 'form']],
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_add_and_close(self):
        """Add org and return to browser without opening form."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        Org = self.env['myschool.org']
        
        if self.use_existing:
            if not self.existing_org_id:
                raise UserError("Please select an existing organization")
            child_org = self.existing_org_id
        else:
            if not self.new_org_name:
                raise UserError("Please enter a name for the new organization")
            if not self.new_org_name_short:
                raise UserError("Please enter a short name for the organization")
            if not self.new_org_inst_nr:
                raise UserError("Please enter an institution number")
            
            org_vals = {
                'name': self.new_org_name,
                'name_short': self.new_org_name_short,
                'inst_nr': self.new_org_inst_nr,
                'is_active': True,
            }
            
            # Add OU FQDN fields if present
            if self.new_org_ou_fqdn_intern:
                org_vals['ou_fqdn_internal'] = self.new_org_ou_fqdn_intern
            if self.new_org_ou_fqdn_extern:
                org_vals['ou_fqdn_external'] = self.new_org_ou_fqdn_extern
            
            # Add com_group fields if present
            if self.new_org_com_group_name:
                org_vals['com_group_name'] = self.new_org_com_group_name
            if self.new_org_com_group_fqdn_internal:
                org_vals['com_group_fqdn_internal'] = self.new_org_com_group_fqdn_internal
            if self.new_org_com_group_fqdn_external:
                org_vals['com_group_fqdn_external'] = self.new_org_com_group_fqdn_external
            
            # Add sec_group fields if present
            if self.new_org_sec_group_name:
                org_vals['sec_group_name'] = self.new_org_sec_group_name
            if self.new_org_sec_group_fqdn_internal:
                org_vals['sec_group_fqdn_internal'] = self.new_org_sec_group_fqdn_internal
            if self.new_org_sec_group_fqdn_external:
                org_vals['sec_group_fqdn_external'] = self.new_org_sec_group_fqdn_external
            
            # Add boolean flags
            org_vals['has_ou'] = self.new_org_has_ou
            org_vals['has_role'] = self.new_org_has_role
            org_vals['has_comgroup'] = self.new_org_has_comgroup
            org_vals['has_secgroup'] = self.new_org_has_secgroup
            
            # Compute and set name_tree from ou_fqdn_internal
            if self.new_org_ou_fqdn_intern:
                name_tree = compute_name_tree(self.env, {'name_short': self.new_org_name_short, 'ou_fqdn_internal': self.new_org_ou_fqdn_intern}, None)
                if name_tree:
                    org_vals['name_tree'] = name_tree
            
            if self.new_org_type_id:
                org_vals['org_type_id'] = self.new_org_type_id.id
            if self.new_org_description and 'description' in Org._fields:
                org_vals['description'] = self.new_org_description
            
            child_org = Org.create(org_vals)
        
        if child_org.id == self.parent_org_id.id:
            raise UserError("An organization cannot be its own parent")
        
        existing = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '=', self.parent_org_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"{child_org.name} is already a child of {self.parent_org_id.name}")
        
        old_parent = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True),
        ])
        if old_parent:
            old_parent.write({'is_active': False})
        
        # Get or create ORG-TREE proprelation type
        PropRelationType = self.env['myschool.proprelation.type']
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
            id_org=child_org,
            id_org_parent=self.parent_org_id
        )
        
        PropRelation.create({
            'name': relation_name,
            'proprelation_type_id': org_tree_type.id,
            'id_org': child_org.id,
            'id_org_parent': self.parent_org_id.id,
            'is_active': True,
        })
        
        return {'type': 'ir.actions.act_window_close'}


class MoveOrgWizard(models.TransientModel):
    """Wizard to move an organization to a new parent."""
    _name = 'myschool.move.org.wizard'
    _description = 'Move Organization'

    org_id = fields.Many2one('myschool.org', string='Organization', required=True)
    org_name = fields.Char(string='Organization Name', readonly=True)
    new_parent_id = fields.Many2one('myschool.org', string='New Parent Organization')
    move_to_root = fields.Boolean(string='Move to Root (no parent)')

    def action_move(self):
        """Move the organization."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        if self.move_to_root:
            # Remove parent relation
            existing = PropRelation.search([
                ('id_org', '=', self.org_id.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ])
            if existing:
                existing.write({'is_active': False})
        else:
            if not self.new_parent_id:
                raise UserError("Please select a new parent organization or check 'Move to Root'")
            
            # Use the object browser method for validation
            self.env['myschool.object.browser'].move_org(self.org_id.id, self.new_parent_id.id)
        
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
        """Move the person."""
        self.ensure_one()
        
        self.env['myschool.object.browser'].move_person_to_org(
            self.person_id.id, 
            self.new_org_id.id
        )
        
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

    def action_assign(self):
        """Assign the role."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Check if already exists
        domain = [
            ('id_person', '=', self.person_id.id),
            ('id_role', '=', self.role_id.id),
            ('is_active', '=', True),
        ]
        if self.org_id:
            domain.append(('id_org', '=', self.org_id.id))
        
        existing = PropRelation.search(domain, limit=1)
        
        if existing:
            raise UserError(f"{self.person_id.name} already has role {self.role_id.name}")
        
        vals = {
            'id_person': self.person_id.id,
            'id_role': self.role_id.id,
            'is_active': True,
        }
        if self.org_id:
            vals['id_org'] = self.org_id.id
        
        PropRelation.create(vals)
        
        return {'type': 'ir.actions.act_window_close'}


class BulkAssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to multiple persons."""
    _name = 'myschool.bulk.assign.role.wizard'
    _description = 'Bulk Assign Role'

    person_ids = fields.Many2many('myschool.person', string='Persons')
    person_count = fields.Integer(string='Number of Persons', readonly=True)
    role_id = fields.Many2one('myschool.role', string='Role', required=True)
    org_id = fields.Many2one('myschool.org', string='Organization (optional)')

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
        """Create the SRBR relation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create SRBR type
        rel_type = self._get_or_create_relation_type(
            'SRBR', 
            'SAP-Role to Backend-Role mapping'
        )
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.sap_role_id.id),
            ('id_role_parent', '=', self.backend_role_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name using standardized format
        rel_name = build_proprelation_name(
            'SRBR',
            id_role=self.sap_role_id,
            id_role_parent=self.backend_role_id
        )
        
        # Create the relation
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.sap_role_id.id,
            'id_role_parent': self.backend_role_id.id,
            'is_active': True,
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
        """Create the BRSO relation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create BRSO type
        rel_type = self._get_or_create_relation_type(
            'BRSO', 
            'Backend-Role to School/Department mapping for person creation'
        )
        
        # Check if relation already exists
        # id_org = department, id_org_parent = school
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.backend_role_id.id),
            ('id_org', '=', self.department_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name using standardized format
        rel_name = build_proprelation_name(
            'BRSO',
            id_role=self.backend_role_id,
            id_org_parent=self.school_id,
            id_org=self.department_id
        )
        
        # Create the relation
        # id_org = department (where person created), id_org_parent = school (higher level)
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.backend_role_id.id,
            'id_org': self.department_id.id,
            'id_org_parent': self.school_id.id,
            'is_active': True,
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
        """Find the school in the organization hierarchy."""
        try:
            PropRelation = self.env['myschool.proprelation']
        except KeyError:
            return None
        
        # Check if current org is a school
        if org.org_type_id and org.org_type_id.name == 'SCHOOL':
            return org
        
        # Walk up the hierarchy to find a school
        current_org = org
        visited = set()
        
        while current_org and current_org.id not in visited:
            visited.add(current_org.id)
            
            # Check if this org is a school
            if current_org.org_type_id and current_org.org_type_id.name == 'SCHOOL':
                return current_org
            
            # Find parent
            parent_rel = PropRelation.search([
                ('id_org', '=', current_org.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
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
        """Create the BRSO relation."""
        self.ensure_one()
        
        if not self.school_id:
            raise UserError('Please select a school.')
        
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create BRSO type
        rel_type = self._get_or_create_relation_type(
            'BRSO', 
            'Backend-Role to School/Department mapping for person creation'
        )
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', rel_type.id),
            ('id_role', '=', self.backend_role_id.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError('This relation already exists.')
        
        # Build relation name using standardized format
        rel_name = build_proprelation_name(
            'BRSO',
            id_role=self.backend_role_id,
            id_org_parent=self.school_id,
            id_org=self.org_id
        )
        
        # Create the relation
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': rel_type.id,
            'id_role': self.backend_role_id.id,
            'id_org': self.org_id.id,
            'id_org_parent': self.school_id.id,
            'is_active': True,
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
        """Set default school from org's parent."""
        res = super().default_get(fields_list)
        
        if 'org_id' in res and res['org_id']:
            # Try to find parent org
            PropRelation = self.env['myschool.proprelation']
            parent_rel = PropRelation.search([
                ('id_org', '=', res['org_id']),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                res['school_id'] = parent_rel.id_org_parent.id
        
        return res

    def action_add_role(self):
        """Create the BRSO proprelation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Get or create BRSO proprelation type
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            brso_type = PropRelationType.create({
                'name': 'BRSO',
                'usage': 'Backend Role - Organization relation',
                'is_active': True,
            })
        
        # Check if relation already exists (active)
        existing = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('id_role', '=', self.role_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"Role '{self.role_id.name}' is already linked to this organization.")
        
        # Check for inactive relation and reactivate
        inactive = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('id_role', '=', self.role_id.id),
            ('is_active', '=', False),
        ], limit=1)
        
        if inactive:
            inactive.write({'is_active': True})
            _logger.info(f"Reactivated BRSO relation: role {self.role_id.name} to org {self.org_id.name}")
        else:
            # Create the relation with standardized name
            rel_name = build_proprelation_name(
                'BRSO',
                id_role=self.role_id,
                id_org_parent=self.school_id,
                id_org=self.org_id
            )
            PropRelation.create({
                'name': rel_name,
                'proprelation_type_id': brso_type.id,
                'id_org': self.org_id.id,
                'id_org_parent': self.school_id.id,
                'id_role': self.role_id.id,
                'is_active': True,
            })
            _logger.info(f"Created BRSO relation: role {self.role_id.name} to org {self.org_id.name} (school: {self.school_id.name})")
        
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
        required=True,
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

    @api.model
    def default_get(self, fields_list):
        """Load existing BRSO relations as lines and set default school."""
        res = super().default_get(fields_list)
        
        if 'org_id' in res and res['org_id']:
            org_id = res['org_id']
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            
            # Try to find parent org (school)
            parent_rel = PropRelation.search([
                ('id_org', '=', org_id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            
            if parent_rel and parent_rel.id_org_parent:
                res['school_id'] = parent_rel.id_org_parent.id
            
            brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
            if brso_type:
                relations = PropRelation.search([
                    ('proprelation_type_id', '=', brso_type.id),
                    ('id_org', '=', org_id),
                    ('id_role', '!=', False),
                    ('is_active', '=', True),
                ])
                
                lines = []
                for rel in relations:
                    lines.append((0, 0, {
                        'proprelation_id': rel.id,
                        'role_name': rel.id_role.name if rel.id_role else '',
                        'is_active': rel.is_active,
                    }))
                res['line_ids'] = lines
        
        return res

    def action_add_role(self):
        """Add the selected role to the organization."""
        self.ensure_one()
        
        if not self.new_role_id:
            raise UserError("Please select a role to add.")
        
        if not self.school_id:
            raise UserError("Please select a school organization.")
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Get or create BRSO proprelation type
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            brso_type = PropRelationType.create({
                'name': 'BRSO',
                'usage': 'Backend Role - Organization relation',
                'is_active': True,
            })
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('id_role', '=', self.new_role_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"Role '{self.new_role_id.name}' is already linked to this organization.")
        
        # Check for inactive and reactivate
        inactive = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '=', self.school_id.id),
            ('id_role', '=', self.new_role_id.id),
            ('is_active', '=', False),
        ], limit=1)
        
        if inactive:
            inactive.write({'is_active': True})
        else:
            # Create with standardized name
            rel_name = build_proprelation_name(
                'BRSO',
                id_role=self.new_role_id,
                id_org_parent=self.school_id,
                id_org=self.org_id
            )
            PropRelation.create({
                'name': rel_name,
                'proprelation_type_id': brso_type.id,
                'id_org': self.org_id.id,
                'id_org_parent': self.school_id.id,
                'id_role': self.new_role_id.id,
                'is_active': True,
            })
        
        # Reopen wizard to show updated list
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.manage.org.roles.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_org_id': self.org_id.id,
                'default_org_name': self.org_name,
                'default_school_id': self.school_id.id,
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
    def default_get(self, fields_list):
        """Load existing PPSBR relations as lines."""
        res = super().default_get(fields_list)
        
        if 'person_id' in res and res['person_id']:
            person_id = res['person_id']
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            
            ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
            if ppsbr_type:
                relations = PropRelation.search([
                    ('proprelation_type_id', '=', ppsbr_type.id),
                    ('id_person', '=', person_id),
                    ('id_role', '!=', False),
                    ('is_active', '=', True),
                ])
                
                lines = []
                for rel in relations:
                    lines.append((0, 0, {
                        'proprelation_id': rel.id,
                        'role_name': rel.id_role.name if rel.id_role else '',
                        'is_active': rel.is_active,
                    }))
                res['line_ids'] = lines
        
        return res

    def action_add_role(self):
        """Add the selected role to the person."""
        self.ensure_one()
        
        if not self.new_role_id:
            raise UserError("Please select a role to add.")
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Get or create PPSBR proprelation type
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not ppsbr_type:
            ppsbr_type = PropRelationType.create({
                'name': 'PPSBR',
                'usage': 'Person - Role relation',
                'is_active': True,
            })
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', self.person_id.id),
            ('id_role', '=', self.new_role_id.id),
            ('is_active', '=', True),
        ], limit=1)
        
        if existing:
            raise UserError(f"Role '{self.new_role_id.name}' is already linked to this person.")
        
        # Check for inactive and reactivate
        inactive = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', self.person_id.id),
            ('id_role', '=', self.new_role_id.id),
            ('is_active', '=', False),
        ], limit=1)
        
        if inactive:
            inactive.write({'is_active': True})
        else:
            # Create with standardized name
            rel_name = build_proprelation_name(
                'PPSBR',
                id_role=self.new_role_id,
                id_person=self.person_id
            )
            PropRelation.create({
                'name': rel_name,
                'proprelation_type_id': ppsbr_type.id,
                'id_person': self.person_id.id,
                'id_role': self.new_role_id.id,
                'is_active': True,
            })
        
        # Reopen wizard to show updated list
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'myschool.manage.person.roles.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_person_id': self.person_id.id,
                'default_person_name': self.person_name,
            },
        }

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}


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
        
        # Save password to person record
        self.person_id.write({'password': self.new_password})
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_clear_password(self):
        """Clear the password."""
        self.ensure_one()

        self.person_id.write({'password': False})

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
