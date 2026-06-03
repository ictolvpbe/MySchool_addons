# Improvement Prompts for MySchool & Process Mapper Addons

Use these prompts with Claude Code to implement improvements one at a time.
Organized by module and priority (critical > high > medium > nice-to-have).

---

## 1. CROSS-MODULE: Testing

### 1.1 Add unit tests for myschool_core (Critical)
```
Create a tests/ directory in myschool_core with proper __init__.py. Write Odoo test classes
(TransactionCase) covering:
- Person model: creation, deactivation cascade (should deactivate linked Odoo user, HR employee,
  and proprelations), reactivation, audit trail task creation
- Organization model: name_tree computation from ou_fqdn_internal, audit trail
- Role model: find_by_shortname, find_roles_by_person, Odoo group sync
- PropRelation model: creation of PERSON-TREE, PPSBR, SRBR, BRSO types
- ConfigItem model: get/set values by scope, find_by_name
- CiRelation model: register_or_update, find_by_org
- BeTask model: status transitions (new -> processing -> completed_ok/error)
- BeTaskType model: auto-generated name from target+object+action, processor_method generation
Add the tests to __manifest__.py. Follow Odoo 19 test patterns with tagged('post_install', '-at_install').
```

### 1.2 Add unit tests for myschool_admin (Critical)
```
Create a tests/ directory in myschool_admin with Odoo test classes covering:
- Wizard tests: CreatePersonWizard (create person in org), AddChildOrgWizard (both new and
  existing org modes), AssignRoleWizard, PasswordWizard
- Model extension tests: org name_tree computation, proprelation standardized name computation,
  recalculate_all_org_trees
- Object browser tests: get_tree_data returns correct hierarchy, role list filtering
Keep tests focused on business logic, not UI rendering.
```

### 1.3 Add unit tests for process_mapper (High)
```
Create a tests/ directory in process_mapper. Write test classes covering:
- Process map CRUD and state transitions (draft -> review -> approved)
- save_diagram_data creates version snapshots
- restore_version reverts correctly
- get_diagram_data returns proper JSON structure with lanes, steps, connections
- Connection constraint: no_self_connection SQL constraint works
- action_generate_prompt produces valid output with workflow states and data models
- search_models returns ir.model results
- get_model_fields maps field types correctly
```

### 1.4 Add tests for remaining modules (Medium)
```
Create tests/ directories with basic test classes for:
- myschool_asset: asset lifecycle (draft->deployed->retired), depreciation calculation
  (straight_line and declining_balance), license seat tracking, checkout workflow
- myschool_itsm: ticket creation and state flow, SLA deadline calculation, priority auto-calc
  from impact/urgency matrix, problem-ticket linking, change management workflow,
  email-to-ticket creation via message_new
- knowledge_builder: knowledge object workflow, version snapshot/restore, share token generation
  and public access
- nascholing_workflow: request submit/approve/reject flow, notification sending
```

---

## 2. MYSCHOOL_CORE

### 2.1 Fix nascholing_workflow create() bug (Critical)
```
In nascholing_workflow/models/nascholing_aanvraag.py, the create() method has a bug at line 34:
`vals[0]['name'] = sequence` should be `vals['name'] = sequence` because vals is a dict, not a
list. Fix this so record creation works. Also verify the @api.model_create_multi decorator usage
is correct - if using model_create_multi, vals IS a list and the loop should iterate; if using
plain @api.model, vals is a single dict. Check the actual decorator and fix accordingly.
```

### 2.2 Split betask_processor.py into focused modules (High)
```
The file myschool_core/models/betask_processor.py is 4093 lines. Split it into logical sub-modules:
- betask_processor.py: Keep as base abstract model with shared helpers (_parse_date_safe,
  _get_field_changes, build_proprelation_name)
- betask_processor_person.py: Person-related processing (employee/student import, field mapping,
  deactivation)
- betask_processor_org.py: Organization processing (org import, ORG-TREE management)
- betask_processor_proprelation.py: PropRelation processing (PPSBR, SRBR, BRSO creation/update)
- betask_processor_ldap.py: LDAP/AD related task processing
Each sub-module should inherit from the base and add its specific processor methods.
Update models/__init__.py to import all sub-modules.
```

### 2.3 Implement TODO items in betask_processor (High)
```
In myschool_core/models/betask_processor.py there are incomplete TODOs:
- Line 2455: "TODO: Implement based on relation storage strategy"
- Line 2463: "TODO: Implement relation update logic"
Read the surrounding context to understand what relation storage strategy is being used
(proprelation model), then implement the missing logic for updating existing proprelation
records when data changes arrive from SAP/Informat sync.
```

### 2.4 Make SAP providers database-driven (Medium)
```
In myschool_core/models/org.py, SAP_PROVIDER_SELECTION is hardcoded as a list of tuples
(line ~18, TODO comment says "get providers from database instead of selection"). Create a new
model myschool.sap.provider with fields: name (Char, required), code (Char, required, unique),
description (Text), is_active (Boolean). Change the sap_provider field on myschool.org from
Selection to Many2one pointing to myschool.sap.provider. Create initial data records matching
the current selection values. Add security rules for the new model. Update views to use the
Many2one widget.
```

### 2.5 Clean up informat_service.py TODOs (Medium)
```
In myschool_core/models/informat_service.py there are stale TODOs:
- Line 1479: "Find the SAP Role TODO: REQUIRED?????" - Investigate whether this SAP role
  lookup is actually required for the sync flow. If yes, implement it properly. If no, remove
  the TODO and add a comment explaining why it's optional.
- Line 2012: "15.01.26: TODO: remove code after testing" - This TODO is over a year old.
  Review the code block it references. If the surrounding code works correctly in production,
  remove the dead code. If it's still needed, remove just the TODO comment.
```

### 2.6 Add missing data files to manifest (Medium)
```
In myschool_core/__manifest__.py, several data files exist but are not loaded:
- data/demo_data.xml
- data/betask_data.xml
- data/betask_type_2.xml
- data/ldap_task_types.xml (commented out)
Review each file's contents. If they contain valid seed data needed for the module to function,
add them to the 'data' or 'demo' keys in the manifest. If they are obsolete, delete them.
For ldap_task_types.xml, determine if LDAP task types are required when LDAP integration is
configured and add conditionally or document why it's excluded.
```

---

## 3. MYSCHOOL_ADMIN

### 3.1 Split wizards.py into focused files (High)
```
The file myschool_admin/models/wizards.py is 3479 lines with 21 wizard classes. Split into:
- wizards/__init__.py (import all sub-modules)
- wizards/helpers.py: build_proprelation_name(), compute_name_tree() utility functions
- wizards/person_wizards.py: CreatePersonWizard, MovePersonWizard, PasswordWizard,
  ManagePersonRolesWizard
- wizards/org_wizards.py: AddChildOrgWizard, MoveOrgWizard, ManageOrgRolesWizard
- wizards/role_wizards.py: AssignRoleWizard, BulkAssignRoleWizard, RoleRelationsManager,
  AddSRBRWizard, AddBRSOWizard, LinkRoleToOrgWizard, AddBRSORoleWizard
- wizards/ci_wizards.py: ManageCiRelationsWizard, AddCiRelationWizard, EditCiRelationWizard,
  RemoveCiRelationWizard
- wizards/maintenance_wizards.py: BulkMoveWizard, BackendTaskRollbackWizard
Update models/__init__.py to import from the new wizards package.
Move the import in proprelation_extension.py to reference the new location.
```

### 3.2 Re-enable or remove log viewer (Medium)
```
The log viewer feature in myschool_admin is half-disabled: the OWL component assets are
commented out in __manifest__.py but the model (log_viewer.py), views (log_viewer_views.xml),
and controller endpoints still exist. Either:
Option A: Re-enable it by uncommenting the assets in __manifest__.py and verify the OWL
component still works with current Odoo 19.
Option B: Remove it entirely - delete log_viewer.py, log_viewer.js, log_viewer.xml, the
views file, controller routes, and security records. Remove menu items referencing it.
Choose based on whether real-time log viewing in the browser is useful for this admin module.
```

### 3.3 Add loading states and error handling to Object Browser (Medium)
```
In myschool_admin/static/src/object_browser.js, improve the error handling:
- Wrap all orm.call() invocations in try/catch blocks
- Show user-friendly notification.add() messages on failure instead of silent failures
- Add a retry mechanism for transient network errors
- Show a proper empty state when the tree has no data
- Add a loading skeleton/shimmer effect while tree data loads instead of blank space
- Handle the case where the backend returns malformed data gracefully
```

### 3.4 Add keyboard navigation to Object Browser (Nice-to-have)
```
In myschool_admin/static/src/object_browser.js, add keyboard navigation support:
- Arrow Up/Down: Navigate between tree nodes
- Arrow Right: Expand node
- Arrow Left: Collapse node
- Enter: Select/activate node (show details)
- Space: Toggle checkbox in selection mode
- Home/End: Jump to first/last visible node
- Type-ahead search: Typing characters focuses matching node
Track the focused node separately from the selected node. Add visual focus indicator (outline).
Follow WAI-ARIA TreeView pattern for accessibility.
```

---

## 4. PROCESS MAPPER

### 4.1 Add touch/mobile support to canvas (High)
```
In process_mapper/static/src/process_mapper_canvas.js, all interactions are mouse-only.
Add touch event handlers:
- Single touch drag: Pan canvas (equivalent to mouse drag on background)
- Touch on shape: Select and drag step (equivalent to mousedown on step)
- Pinch zoom: Two-finger pinch to zoom in/out (replace scroll wheel)
- Long press on shape: Open context menu / show properties
- Double tap on shape: Start inline editing
Map touch events to the existing mouse handler logic where possible. Use pointer events
(pointerdown/pointermove/pointerup) instead of separate mouse/touch handlers for unified input.
Add touch-action: none CSS to the SVG to prevent browser scroll interference.
```

### 4.2 Add BPMN timer and message events (High)
```
In process_mapper, extend the step_type selection and canvas rendering to support additional
BPMN event types:
- timer_event: Circle with clock icon inside (used for scheduled triggers/delays)
- message_event: Circle with envelope icon (used for message-based triggers)
- signal_event: Circle with triangle icon (broadcast signals)
- error_event: Circle with lightning bolt icon (error handling)
Update:
1. process_map_step.py: Add new types to step_type selection
2. process_mapper_canvas.js: Add rendering functions for each new shape (circles with inner
   icons, similar to start/end but with distinct visual indicators)
3. process_mapper_canvas.js: Add default sizes (50x50 like start/end)
4. Toolbar template: Add palette buttons for the new types
5. Properties panel: Show relevant fields when these types are selected
6. Prompt generation: Include event semantics in generated prompts
```

### 4.3 Add snap-to-grid for step placement (Medium)
```
In process_mapper/static/src/process_mapper_canvas.js, steps can be placed at any pixel
position. Add optional snap-to-grid:
- When grid is enabled (gridEnabled state), snap step positions to 20px grid on drop and
  drag end
- Snap formula: Math.round(position / gridSize) * gridSize
- Apply to both x and y coordinates
- Apply during drag (onMoveStep/onMoveSteps) for visual snapping while dragging
- Apply on canvas drop (onCanvasDrop) for new shapes from palette
- Do NOT snap during active drag movement (feels janky), only on release
- Show visual snap indicators (subtle highlight on grid lines near snap point)
```

### 4.4 Add connection labels with positioning (Medium)
```
In the process_mapper canvas, connection labels currently render at a fixed midpoint position.
Improve label handling:
- Allow label repositioning by dragging the label text along the connection path
- Store label_offset (0.0 to 1.0, percentage along path) in the connection model
- Add label_offset field to process.map.connection model (Float, default 0.5)
- Render labels at the computed offset position on the orthogonal path
- Support label background with slight padding (white rect behind text for readability)
- In the frontend: track label drag and update offset
- Save offset via save_diagram_data
```

### 4.5 Add diagram validation (Medium)
```
Add a validation system to process_mapper that checks BPMN correctness:
Create a validate_diagram() method on process.map that checks:
- Every diagram has exactly one start event
- Every diagram has at least one end event
- All steps are reachable from the start (no orphan nodes)
- No dead-end steps (every non-end step has at least one outgoing connection)
- Exclusive gateways have 2+ outgoing connections with labels
- Parallel gateways have matching split/join pairs
Return a list of {level: 'error'|'warning', step_id, message} objects.
Display validation results in the frontend with clickable entries that select the
problematic step. Add a "Validate" button to the toolbar.
```

### 4.6 Add collaborative indicators (Nice-to-have)
```
Add basic multi-user awareness to process_mapper (not real-time collaboration, just conflict
prevention):
- When a user opens a diagram for editing, write a lock record with user_id and timestamp
- Show a banner "User X is currently editing this diagram (since HH:MM)" if another user
  has the lock
- Auto-release lock after 30 minutes of inactivity or on browser close (beforeunload)
- Add a force-unlock button for managers
- Store in a new model process.map.lock with fields: map_id, user_id, lock_time
- Check lock on loadDiagram() and show warning notification
```

### 4.7 Add PDF export with page layout options (Nice-to-have)
```
Add PDF export to process_mapper alongside existing PNG/SVG:
- Add "Export PDF" button to toolbar
- Use the SVG export as base, then convert to PDF client-side
- Add a layout dialog before export with options:
  - Page size: A4, A3, Letter
  - Orientation: Portrait, Landscape
  - Fit to page: Auto-scale to fit
  - Include title and metadata header
  - Include legend (shape type descriptions)
- Generate using jspdf library or server-side with reportlab
- Add the title, version, state, org name as header
- Add page numbers if multi-page
```

### 4.8 Improve auto-layout algorithm (Nice-to-have)
```
The current auto-layout in process_mapper uses basic BFS with fixed spacing. Improve it:
- Use the Sugiyama algorithm for layered graph drawing:
  1. Assign layers (longest path from start)
  2. Minimize crossings (barycenter method)
  3. Assign coordinates within layers (median positioning)
- Respect lane assignments: keep steps within their assigned lanes
- Handle parallel gateways: align split and join at same depth
- Handle conditions: place "Yes" path straight, "No" path branching
- Add animation: smoothly transition steps from old to new positions (CSS transition)
- Preserve manual adjustments: only auto-layout steps that haven't been manually positioned
  (add a manually_positioned boolean flag to steps)
```

---

## 5. KNOWLEDGE BUILDER

### 5.1 Add search and filtering to knowledge list (Medium)
```
In knowledge_builder, enhance the list view and editor with search capabilities:
- Add a search view with filters: by knowledge_type (procedure/qa/solution/information),
  by state (draft/review/published), by tag, by author (create_uid), by date range
- Add group-by options: knowledge_type, state, create_uid
- Add full-text search across name, details, and step text content
- In the OWL editor component, add a search bar that filters steps within the current
  knowledge object (highlight matching text in steps)
```

### 5.2 Add step reordering via drag-and-drop in editor (Medium)
```
In knowledge_builder/static/src/knowledge_builder_editor.js, steps are ordered by sequence
field. Add drag-and-drop reordering:
- Add drag handle (grip icon) to each step card
- On drag start: show drop zones between steps
- On drop: reorder sequence values and save
- Use HTML5 drag-and-drop API or pointer events
- Animate the reorder transition
- Update the sequence field values on the backend via save_editor_data
```

### 5.3 Add knowledge object duplication (Nice-to-have)
```
Add a "Duplicate" button to knowledge_builder that creates a copy of a knowledge object
including all its steps (with images). The duplicate should:
- Set state to 'draft'
- Prepend "Copy of " to the name
- Copy all steps with their content and images
- Clear the share_token (generate new one only if shared)
- Reset version history (start fresh)
- Open the new record in form view after creation
Add as a button in the form view header and as a server action.
```

---

## 6. MYSCHOOL_ASSET

### 6.1 Add asset import from CSV/Excel (High)
```
Create a wizard in myschool_asset for bulk importing assets from CSV or Excel files:
- Upload file field (Binary with filename)
- Preview first 10 rows in a list
- Column mapping: auto-detect columns by header name, allow manual override
- Required fields: name, category (by name lookup), asset_type
- Optional fields: serial_number, purchase_date, purchase_cost, location, organization
- Validation: check for duplicate asset_tags, validate category exists
- Import with progress indicator
- Summary report: X imported, Y skipped (with reasons)
Add the wizard as a menu item under Assets and as a button on the asset list view.
```

### 6.2 Add QR code/barcode label generation (Medium)
```
Add barcode/QR code label printing to myschool_asset:
- Generate QR codes containing the asset_tag value
- Create a report (ir.actions.report) for asset labels
- Label layout: QR code + asset_tag text + asset name + category
- Support printing multiple labels at once (from list view multi-select)
- Use Odoo's built-in barcode generation or qrcode Python library
- Add a "Print Label" button to the asset form view and list view
```

### 6.3 Add asset dashboard with statistics (Nice-to-have)
```
Create a dashboard view for myschool_asset showing:
- Total assets by state (pie chart)
- Assets by category (bar chart)
- Total asset value and depreciated value
- Assets with expiring warranties (next 30 days)
- Overdue checkouts count
- Recently added assets (last 7 days)
- License utilization (used vs available seats)
Implement as an OWL2 component registered as an action, similar to the Object Browser pattern
in myschool_admin. Use Odoo's chart.js integration or simple HTML/CSS stat cards.
```

---

## 7. MYSCHOOL_ITSM

### 7.1 Add ticket dashboard with KPIs (High)
```
Create a dashboard for myschool_itsm showing key ITSM metrics:
- Open tickets by priority (P1-P4 counts with color coding)
- Average response time vs SLA target
- Average resolution time vs SLA target
- SLA compliance percentage (met vs breached)
- Tickets by state (funnel visualization)
- Top 5 ticket categories
- Unassigned tickets count (needs attention)
- Problems with open root cause investigations
- Pending changes awaiting approval
Implement as an OWL2 component with stat cards and simple charts.
Add as the default landing page for the ITSM menu.
```

### 7.2 Add ticket templates for common requests (Medium)
```
Create a ticket template system in myschool_itsm:
- New model: itsm.ticket.template with fields: name, ticket_type, category, default_priority,
  description_template (with placeholders), default_assigned_to
- "Create from Template" button on ticket list view
- Template selection wizard showing available templates
- Auto-fills ticket fields from template on creation
- Allow managers to create/edit templates
- Include common school IT templates: "Password Reset", "New Account Request",
  "Software Installation", "Hardware Issue", "Network Problem"
Create initial template data in a data XML file.
```

### 7.3 Add self-service portal for end users (Nice-to-have)
```
Create a simple self-service portal for myschool_itsm accessible to non-admin users:
- Route: /itsm/portal (auth='user')
- "Submit a Ticket" form with: subject, description, category dropdown, priority
- "My Tickets" list showing the user's submitted tickets with status
- Ticket detail view showing status, comments, and resolution
- "Add Comment" form on ticket detail
- Use Odoo website/portal patterns (portal.mixin on itsm.ticket)
- Add portal access rules: users can only see their own tickets
- Responsive design for mobile access
```

---

## 8. CROSS-MODULE: Architecture & Quality

### 8.1 Add i18n/translation support (Medium)
```
None of the modules currently have translations. Add Dutch (nl_BE) translations since this is
a Belgian school management system:
- Create i18n/ directories in each module
- Generate .pot files using Odoo's export translation feature
- Create nl_BE.po files with Dutch translations for:
  - All field labels and help text
  - Menu items
  - Button labels
  - Wizard titles and descriptions
  - Status bar states
  - Error messages
Focus on myschool_admin and myschool_itsm first as they have the most user-facing text.
```

### 8.2 Add module documentation pages (Nice-to-have)
```
Create a docs/ section accessible from each module's settings or help menu:
- For myschool_core: Document the data model relationships (Person-Org-Role-Period via
  PropRelation), the BeTask processing pipeline, and the ConfigItem system
- For myschool_admin: Document the Object Browser usage, wizard workflows, and maintenance
  actions (recalculate trees, update names)
- For process_mapper: Document BPMN shape types, keyboard shortcuts, the prompt generation
  feature, and the Field Builder notation format
- For myschool_itsm: Document the ticket lifecycle, SLA enforcement, and CMDB relationships
Use static HTML pages or knowledge_builder objects for documentation.
```

### 8.3 Add system health monitoring (Nice-to-have)
```
Create a system health check mechanism in myschool_core:
- New model or wizard: myschool.health.check
- Checks to implement:
  1. LDAP connectivity: test connection to all configured LDAP servers
  2. Pending BeTask count: warn if > 100 pending tasks
  3. Error BeTask count: alert if any error tasks exist
  4. System event errors: count recent ERROR-BLOCKING events
  5. Orphan persons: persons without any active proprelation
  6. Orphan orgs: orgs not in any ORG-TREE
  7. Data integrity: persons with odoo_user_id pointing to deleted users
- Display as a dashboard with green/yellow/red indicators
- Add a cron job to run daily and log results as system events
- Send email alert to admins when critical issues are found
```
