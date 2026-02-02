# Quality Control Checklist - MySchool Modules

## MYSCHOOL_CORE MODULE

### 1. Models (Database Entities)

| Model | Key Fields | Audit Trail | SQL Constraints |
|-------|-----------|-------------|-----------------|
| `myschool.org` | name, name_tree, inst_nr, is_active, domain_internal/external | ✅ Yes | - |
| `myschool.org.type` | name, description, is_active | ❌ No | - |
| `myschool.person` | name, first_name, sap_ref, person_type_id, odoo_user_id, odoo_employee_id | ✅ Yes | unique(sap_ref), unique(sap_person_uuid) |
| `myschool.person.type` | name, description, is_active | ❌ No | - |
| `myschool.person.details` | person_id, full_json_string, hoofd_ambt | ❌ No | - |
| `myschool.role` | name, shortname, role_type_id, has_odoo_group, odoo_group_id | ❌ No | unique(shortname) |
| `myschool.role.type` | name, description, is_active | ❌ No | - |
| `myschool.period` | name, start_date, end_date, period_type_id | ❌ No | - |
| `myschool.period.type` | name, description, is_active | ❌ No | - |
| `myschool.proprelation` | id_person, id_role, id_org, id_period, is_active | ❌ No | - |
| `myschool.proprelation.type` | name, description, is_active | ❌ No | - |
| `myschool.betask` | name, betasktype_id, status, data, changes | ❌ No | - |
| `myschool.betask.type` | target, object, action, auto_process, priority | ❌ No | unique(name), unique(target,object,action) |
| `myschool.sys.event` | syseventtype_id, source, status, data | ❌ No | - |
| `myschool.sys.event.type` | name, is_error_type, is_blocking | ❌ No | - |
| `myschool.config.item` | key, value, data_type, is_system | ❌ No | - |
| `myschool.ci.relation` | ci_parent, ci_child, relation_type | ❌ No | - |
| `myschool.ldap.server.config` | server_url, domain, username, use_tls | ❌ No | - |
| `myschool.informat.service.config` | api_client_id, storage_path, last_sync_date | ❌ No | - |

---

### 2. Person Model Actions

| Action Method | Purpose | Test Steps |
|--------------|---------|------------|
| `action_create_odoo_user()` | Create Odoo user account | Create person → Click "Create Odoo User" → Verify task created |
| `action_view_odoo_user()` | Navigate to linked Odoo user | Link user → Click stat button → Verify redirect |
| `action_view_odoo_employee()` | Navigate to linked HR employee | Link employee → Click stat button → Verify redirect |
| `action_sync_group_memberships()` | Sync Odoo groups from roles | Assign roles → Click sync → Verify group memberships |
| `action_deactivate_employee()` | Cascade deactivation | Active person → Click "Deactivate" → Verify user/employee/relations deactivated |
| `action_reactivate_employee()` | Reactivate person | Inactive person → Click "Reactivate" → Verify is_active=True |

---

### 3. Role Model Actions

| Action Method | Purpose | Test Steps |
|--------------|---------|------------|
| `action_sync_group_members()` | Sync PPSBR persons to Odoo group | Configure odoo_group_id → Click sync → Verify group members |
| `action_view_group_members()` | View users in Odoo group | Click "View Members" → Verify user list |
| `action_remove_all_group_members()` | Bulk remove from group | Click "Remove All" → Confirm → Verify group empty |

---

### 4. Backend Task System

#### Task Types (Target × Object × Action)

| Target | Objects | Actions |
|--------|---------|---------|
| DB | ORG, PERSON, STUDENT, EMPLOYEE, ROLE, PROPRELATION | ADD, UPD, DEL, DEACT |
| LDAP | USER, GROUP, GROUPMEMBER | ADD, UPD, DEL, DEACT, REMOVE |
| MANUAL | ORG, PERSON | ADD, UPD, DEL, DEACT |
| ODOO | PERSON, USER, GROUP | ADD, UPD, DEL |

#### Task Actions

| Action | Purpose | Test Steps |
|--------|---------|------------|
| `action_set_processing()` | Set status to PROCESSING | New task → Click action → Verify status |
| `action_set_completed()` | Mark as completed | Processing task → Complete → Verify status + changes |
| `action_set_error()` | Mark as error | Processing task → Fail → Verify error_description |
| `action_reset_to_new()` | Retry task | Error task → Reset → Verify status=new |
| `action_force_reset()` | Full reset with retry counter | Error task → Force reset → Verify retry_count=0 |
| `action_process_single()` | Process immediately | Pending task → Click "Process Now" → Verify completion |

#### Processor Methods

| Method | Task Type | Test Steps |
|--------|-----------|------------|
| `process_db_employee_add` | DB_EMPLOYEE_ADD | Create task with person data → Process → Verify person created |
| `process_db_employee_upd` | DB_EMPLOYEE_UPD | Create update task → Process → Verify changes |
| `process_db_employee_deact` | DB_EMPLOYEE_DEACT | Create deact task → Process → Verify is_active=False |
| `process_db_student_add` | DB_STUDENT_ADD | Create student task → Process → Verify student created |
| `process_db_org_add` | DB_ORG_ADD | Create org task → Process → Verify org created |
| `process_ldap_user_add` | LDAP_USER_ADD | Configure LDAP → Create task → Process → Verify AD account |
| `process_ldap_user_upd` | LDAP_USER_UPD | Create update task → Process → Verify AD changes |
| `process_ldap_user_deact` | LDAP_USER_DEACT | Create deact task → Process → Verify AD account disabled |
| `process_ldap_group_add` | LDAP_GROUP_ADD | Create group task → Process → Verify AD group |
| `process_ldap_groupmember_add` | LDAP_GROUPMEMBER_ADD | Create member task → Process → Verify membership |

---

### 5. System Events

| Action | Purpose | Test Steps |
|--------|---------|------------|
| `action_set_processing()` | Set to PROCESS | New event → Click action → Verify status |
| `action_set_error()` | Set to PRO_ERROR | Processing event → Fail → Verify status |
| `action_set_closed()` | Close event | Event → Close → Verify eventclosed timestamp |
| `action_reopen()` | Reopen closed event | Closed event → Reopen → Verify status=NEW |

---

### 6. LDAP Service

| Method | Purpose | Test Steps |
|--------|---------|------------|
| `_check_ldap3_available()` | Verify ldap3 library | Call method → Verify True/False |
| `_create_tls_config()` | Build TLS configuration | Configure certs → Build config → Verify TLS object |
| `connect()` | Establish LDAP connection | Configure server → Connect → Verify connection |
| `create_user()` | Create AD user account | Call with person data → Verify DN created |
| `update_user()` | Update AD user attributes | Call with changes → Verify attributes updated |
| `disable_user()` | Disable AD account | Call with DN → Verify userAccountControl flag |
| `create_group()` | Create AD security group | Call with group data → Verify group created |
| `add_group_member()` | Add user to group | Call with user/group DN → Verify membership |
| `remove_group_member()` | Remove user from group | Call with user/group DN → Verify removal |

---

### 7. Informat Service

| Method | Purpose | Test Steps |
|--------|---------|------------|
| `get_access_token()` | OAuth2 token retrieval | Configure credentials → Call → Verify token |
| `sync_employees()` | Sync employee data | Call sync → Verify JSON file + BeTasks created |
| `sync_students()` | Sync student data | Call sync → Verify JSON file + BeTasks created |
| `compare_with_database()` | Delta detection | Import data → Compare → Verify changes detected |

---

### 8. Audit Trail

#### Person Model Audit

| Event | Task Type Created | Data Captured |
|-------|------------------|---------------|
| Create | MANUAL_PERSON_ADD | new_values (all audit fields) |
| Update | MANUAL_PERSON_UPD | old_values, new_values, changes list |
| Deactivate | MANUAL_PERSON_DEACT | old_values, new_values, cascade info |
| Delete | MANUAL_PERSON_DEL | old_values |

#### Organization Model Audit

| Event | Task Type Created | Data Captured |
|-------|------------------|---------------|
| Create | MANUAL_ORG_ADD | new_values (all audit fields) |
| Update | MANUAL_ORG_UPD | old_values, new_values, changes list |
| Deactivate | MANUAL_ORG_DEACT | old_values, new_values |
| Delete | MANUAL_ORG_DEL | old_values |

---

## MYSCHOOL_ADMIN MODULE

### 9. Wizards

| Wizard | Actions | Test Steps |
|--------|---------|------------|
| `myschool.create.person.wizard` | action_create, action_create_and_close | Open wizard → Fill form → Create → Verify person |
| `myschool.add.child.org.wizard` | action_add, action_add_and_close | Select parent → Create child → Verify hierarchy |
| `myschool.move.org.wizard` | action_move | Select org → New parent → Move → Verify name_tree |
| `myschool.move.person.wizard` | action_move | Select person → New org → Move → Verify relations |
| `myschool.assign.role.wizard` | action_assign | Select person/role → Assign → Verify PPSBR |
| `myschool.bulk.assign.role.wizard` | action_assign | Select multiple persons → Assign role → Verify all |
| `myschool.bulk.move.wizard` | action_move | Select persons → Target org → Move → Verify all |
| `myschool.betask.rollback.wizard` | action_rollback | Select audit task → Rollback → Verify restoration |

---

### 10. Object Browser

| Method | Purpose | Test Steps |
|--------|---------|------------|
| `get_tree_data()` | Return org tree as JSON | Load browser → Verify tree structure |
| `_get_org_tree()` | Build org hierarchy | Call method → Verify parent-child links |
| `_get_role_list()` | Get available roles | Call method → Verify role list |

---

### 11. Maintenance Actions

| Action | Purpose | Test Steps |
|--------|---------|------------|
| `action_update_name_tree()` | Update single org name_tree | Select org → Run action → Verify name_tree |
| `action_update_all_name_trees()` | Bulk update all name_trees | Run from menu → Verify all orgs updated |
| `action_update_all_proprelation_names()` | Update relation names | Run from menu → Verify all names regenerated |

---

### 12. Menu Structure Verification

| Menu Path | Action | Verify |
|-----------|--------|--------|
| MySchool Admin → Master Data → Organizations | action_myschool_org | List/form views work |
| MySchool Admin → Master Data → Persons | action_myschool_person | List/form with buttons |
| MySchool Admin → Master Data → Roles | action_myschool_role | Odoo group sync buttons |
| MySchool Admin → Master Data → Periods | action_myschool_period | List/form views work |
| MySchool Admin → Relations → All Relations | action_myschool_proprelation | Relation list |
| MySchool Admin → Backend Tasks → All Tasks | action_betask_all | All tasks view |
| MySchool Admin → Backend Tasks → Pending Tasks | action_betask_pending | Filtered to pending |
| MySchool Admin → Backend Tasks → Error Tasks | action_betask_errors | Filtered to errors |
| MySchool Admin → Backend Tasks → Task Rollback | action_betask_rollback_wizard | Rollback wizard |
| MySchool Admin → System Events → All Events | action_sys_event_all | Event log |
| MySchool Admin → Integrations → LDAP Servers | action_ldap_server_config | LDAP configuration |
| MySchool Admin → Integrations → Informat Sync | action_informat_service_config | Informat configuration |
| MySchool Admin → Configuration → [All Types] | Various | Type management views |

---

### 13. Security Groups

| Group | Permissions | Test Steps |
|-------|-------------|------------|
| `group_myschool_core_user` | Read-only (1,0,0,0) | Login as user → Verify read-only |
| `group_myschool_core_admin` | Full CRUD (1,1,1,1) | Login as admin → Verify full access |

---

### 14. Scheduled Tasks (Cron)

| Cron Job | Schedule | Test Steps |
|----------|----------|------------|
| Process Pending Tasks | Every 15 min | Create pending task → Wait → Verify processed |
| Cleanup Old Tasks | Daily | Create old tasks → Wait → Verify archived |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Core Models | 19 |
| Action Methods | 27+ |
| Backend Task Processors | 15+ |
| Wizards | 8 |
| Security Groups | 2 |
| Scheduled Crons | 2 |
| Menu Items | 25+ |
| Models with Audit Trail | 2 (Person, Org) |

---

## QC Sign-off

| Section | Tested By | Date | Status |
|---------|-----------|------|--------|
| Models & Fields | | | ☐ |
| Person Actions | | | ☐ |
| Role Actions | | | ☐ |
| Backend Tasks | | | ☐ |
| System Events | | | ☐ |
| LDAP Service | | | ☐ |
| Informat Service | | | ☐ |
| Audit Trail | | | ☐ |
| Wizards | | | ☐ |
| Object Browser | | | ☐ |
| Maintenance Actions | | | ☐ |
| Menu Structure | | | ☐ |
| Security Groups | | | ☐ |
| Scheduled Tasks | | | ☐ |

---

*Generated: 2026-02-02*
