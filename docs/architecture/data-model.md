# Data-model

Kern-entiteiten van het MySchool-platform en hun relaties. Gebaseerd op `myschool_core/models/`. Andere modules (admin, activiteiten, appfoundry, ...) breiden uit op deze fundamenten.

⚠️ Niet exhaustief — focus op de structuur-bepalende entiteiten. Voor volledig veld-overzicht: zie de Python-models zelf in `myschool_core/models/`.

## Kern-entiteiten

### Organisatie-laag

```mermaid
erDiagram
    Org ||--o{ Org : "parent (tree)"
    Org }o--|| OrgType : "type"
    Org ||--o{ Period : "schooljaren"
    Period }o--|| PeriodType : "type"

    Org {
        char name "Naam"
        char name_short "Korte naam"
        char name_tree "Hiërarchische naam"
        char inst_nr "Instellingsnummer"
        m2o org_type_id
        char domain_internal "Intern AD-domein"
        char domain_external "Publiek domein"
        char ou_fqdn_internal "OU FQDN intern"
        selection sap_provider
        char sap_login
        char sap_password "groups=group_system"
    }

    OrgType {
        char name
    }

    Period {
        char name "Naam"
        char name_in_sap "Naam in SAP-systeem"
        m2o period_type_id
    }

    PeriodType {
        char name
    }
```

**`Org`** = school-organisatie. Kan in tree-structuur (parent_id) staan voor groepering van zelfde overkoepelende organisatie. Bevat AD/domein-config zodat user-sync per org weet welke OU te targeten.

**`Period`** = schooljaar of trimester. Wordt gekoppeld aan `proprelation` (wie heeft welke rol in welk schooljaar).

### Persoon + rol-laag

```mermaid
erDiagram
    Person }o--|| PersonType : "type"
    Person ||--o{ PersonDetails : "details"
    Person ||--o{ PropRelation : "verbindingen"

    Role }o--|| RoleType : "type"
    Role ||--o{ PropRelation : "instanties"

    Org ||--o{ PropRelation : "in welke org"
    Period ||--o{ PropRelation : "in welk schooljaar"

    Person {
        char first_name
        char short_name
        char name "computed"
        m2o person_type_id
    }

    PersonType {
        char name "Leerling/Leerkracht/Ouder/..."
    }

    Role {
        char name
        char role_type_name "computed"
        char odoo_group_name "Mapping naar Odoo-group"
    }

    RoleType {
        char name "Admin/Leerkracht/Stagiair/..."
    }

    PropRelation {
        m2o person_id
        m2o role_id
        m2o org_id
        m2o period_id
        date date_from
        date date_to
        bool active
    }
```

**Kernontwerp**: `PropRelation` is de centrale **4-weg-link** tussen Persoon × Rol × Organisatie × Periode. Eén persoon kan tegelijk leerkracht zijn in school A (periode 2025) én admin in school B (periode 2026). De `proprelation`-records modelleren dat zonder de Person-records te dupliceren.

Dit is een typische multi-tenant + multi-role-pattern voor onderwijs-organisaties.

### Service-laag (LDAP + sync + tasks)

```mermaid
erDiagram
    LdapServerConfig ||--|{ LdapService : "config gebruikt door"
    InformatServiceConfig ||--|{ InformatService : "config gebruikt door"
    InformatService ||--o{ InformatDto : "fetches"

    BeTask }o--|| BeTaskType : "type"
    BeTask }o--o{ BeTaskService : "verwerkt door"

    ManualTaskProcessor ||--o{ ManualTaskService : "verwerkt"

    LdapServerConfig {
        char ldap_host
        int ldap_port
        char bind_dn
        char bind_password "encrypted"
        char base_dn
        int sync_interval_min
    }

    LdapService {
        m2o ldap_config_id
        m2o org_id
        char ou_filter
        bool active
    }

    InformatServiceConfig {
        char api_url
        char api_key "encrypted"
        m2o org_id
    }

    BeTask {
        char name
        char target
        char object_type
        char action
        selection status "draft/running/success/error"
        text error_description
        m2o task_type_id
        m2o user_id
    }

    BeTaskType {
        char name
        char service_name
    }
```

**`LdapServerConfig` + `LdapService`**: per organisatie (school) kan een LDAP-bind naar AD-DC ingesteld worden. Sync trekt user-data + groepen.

**`InformatService`**: integratie met externe Informat school-administratie-systeem (Vlaams onderwijs). Periodieke sync via XML-API.

**`BeTask`**: background-task framework. Alle long-running operaties (rapporten, syncs, bulk-acties) lopen als BeTask records met status-tracking, retry-policy, audit-trail via `mail.thread`.

### CMDB-laag (config items)

```mermaid
erDiagram
    ConfigItem ||--o{ CIRelation : "source"
    ConfigItem ||--o{ CIRelation : "target"
    
    ConfigItem {
        char name
        char ci_type
        selection lifecycle "in-use/spare/retired"
        m2o owner_person_id
        m2o location_org_id
    }
    
    CIRelation {
        m2o source_ci_id
        m2o target_ci_id
        selection relation_type "depends_on/installed_on/..."
    }
```

**`ConfigItem`** + **`CIRelation`** vormen een lichte CMDB binnen `myschool_core`. `myschool_asset` biedt een rijkere asset-management-UI hier bovenop.

## Extension-laag (per module)

Modules bovenop `core` voegen hun eigen entiteiten toe:

| Module | Belangrijkste entiteiten |
|---|---|
| `myschool_admin` | Admin-views op core (geen eigen models, alleen UI + wizards) |
| `myschool_appfoundry` | `Project`, `Item` (story/bug/task/improvement), `Stage`, `Sprint`, `Release`, `Tag` |
| `myschool_devhub` | Vergelijkbaar met appfoundry + process-flow per project |
| `myschool_itsm` | `Ticket`/`Incident`, `Change`, `KnowledgeArticle`, gebruikt `myschool_asset.Asset` |
| `myschool_asset` | `Asset`, lifecycle-tracking |
| `activiteiten` | `Activiteit`, `KostenLine`, `BusAssignment`, `OrgStudents` (snapshot) |
| `planner` | `Planner`, `VervangingLine`, `Tijdslot` |
| `professionalisering` | `ProfessionaliseringsAanvraag`, budget-lines |
| `process_mapper` | Process-flows (BPMN-achtig), prompt-templates |
| `knowledge_builder` | KnowledgeObject + Step |

Voor full details per module: zie [`../modules/`](../modules/).

## Cross-cutting

### Multi-company (Odoo standaard)

Odoo's `res.company`-model wordt gebruikt voor multi-tenancy op infra-niveau. Per `Org` is er normaal één company (of meerdere companies per org bij grote koepels).

Records met `company_id` field zijn company-scoped (Odoo's record rules zorgen voor isolatie).

### Mail.thread (chatter)

Veel kernentiteiten erven van `mail.thread` zodat ze:
- Chatter-historie hebben (audit-trail)
- Followers + notificaties ondersteunen
- Wijzigingen worden gelogd

Bij MCP-toolcalls verschijnen acties als chatter-entries onder de echte user (zie [`mcp-architecture.md`](mcp-architecture.md)).

### Sys event (audit)

`sys.event` (uit een module die hier niet beschreven is, mogelijk in core) is de centrale audit-log:

- `MCP-CALL` voor MCP-tool-executions
- `MCP-ERROR` voor MCP-failures
- Andere `source`-prefixes voor andere subsystemen

UI: **Operations → Systeemevents → Alle events**.

## Migraties

Schema-evolutie via Odoo's `migrations/<version>/`-folders per module. Voorbeeld: `activiteiten/migrations/1.9/post-migrate.py` voor pre-1.9 → 1.9 data-transformatie.

Best-practice bij schema-wijziging:
1. Wijzig `__manifest__.py` `version`-bump
2. Schrijf `pre-migrate.py` (vóór schema-update) en/of `post-migrate.py` (na)
3. Test in lokale dev-DB met `odoo -u <module> -d <db>`
4. Promote via [`../operations/branch-promote.md`](../operations/branch-promote.md)

## Open punten

- **Data-dictionary** per module ontbreekt (alleen aggregaat-overzicht hier)
- **ER-diagram volledig** (alle modules) is veel werk — huidige Mermaid covert alleen core
- **`Person` ↔ `hr.employee` ↔ `res.users`** mapping is impliciet — heeft documentatie verdiend
- **`ConfigItem` vs `myschool_asset.Asset`** verhouding is dubbelzinnig — kandidaat voor refactor of duidelijker boundary
