# Employee Deactivation Process Flowchart

```mermaid
flowchart TD
    subgraph PHASE1["Phase 1: _sync_employee_persons"]
        A[Start: Process imported employee JSON] --> B{Parse employee data}
        B --> C[Get pension_date, isActive, isOverleden]
        C --> D{Person exists in DB?}

        D -->|No| E{pension_ok AND isActive AND NOT isOverleden?}
        E -->|Yes| F[Create DB-EMPLOYEE-ADD task]
        E -->|No| G[Skip - don't create person]

        D -->|Yes| H{Should deactivate for instNr?}

        H -->|Check conditions| I["Conditions:<br/>- isActive = false OR<br/>- isOverleden = true OR<br/>- pension_date < 1 month ago"]

        I -->|Any condition TRUE| J[Call _deactivate_employee_for_instnr]
        I -->|All conditions FALSE| K{Should reactivate?}

        K -->|Yes| L[Create DB-EMPLOYEE-UPD REACTIVATE task]
        K -->|No| M{PersonDetails exists for instNr?}

        M -->|No| N[Create DB-EMPLOYEE-UPD ADD-DETAILS task]
        M -->|Yes| O{Data changed?}

        O -->|Yes| P[Create DB-EMPLOYEE-UPD UPDATE task]
        O -->|No| Q[No action needed]
    end

    subgraph PHASE2["_deactivate_employee_for_instnr"]
        J --> R{Find Org for instNr}
        R -->|Not found| S[Log event and return]
        R -->|Found| T{Find active PropRelations<br/>for person at org}

        T -->|None found| U{Any active PropRelations<br/>for person anywhere?}
        U -->|Yes| V[Return - person still has other proprels]
        U -->|No| W{Person is_active?}
        W -->|Yes| X[Create DB-EMPLOYEE-DEACT task]
        W -->|No| Y[Return - already inactive]

        T -->|PropRelations found| Z[For each PropRelation]
        Z --> AA[Create DB-PROPRELATION-DEACT task]
        AA --> AB{More PropRelations?}
        AB -->|Yes| Z
        AB -->|No| AC[End Phase 2]
    end

    subgraph PHASE3["process_db_proprelation_deact"]
        AC --> AD[Process PROPRELATION-DEACT task]
        AD --> AE{PropRelation exists?}
        AE -->|No| AF[Log warning - may be already deactivated]
        AE -->|Yes| AG{PropRelation is_active?}

        AG -->|No| AH[Already inactive - skip]
        AG -->|Yes| AI[Set PropRelation is_active = False]

        AI --> AJ{Is PPSBR type?}
        AJ -->|Yes| AK[Recalculate PERSON-TREE position]
        AJ -->|No| AL[Skip tree recalc]

        AK --> AM{Check person deactivation}
        AL --> AM

        AM --> AN{person.is_active AND<br/>person.automatic_sync?}
        AN -->|No| AO[Skip person deactivation]
        AN -->|Yes| AP{Any remaining active<br/>PropRelations for person?}

        AP -->|Yes| AQ[Person stays active]
        AP -->|No| AR[Deactivate Person]

        AR --> AS{Person has Odoo user?}
        AS -->|Yes| AT[Create ODOO-PERSON-DEACT task]
        AS -->|No| AU[Skip Odoo task]

        AT --> AV[Set person.is_active = False]
        AU --> AV
        AV --> AW[End - Person Deactivated]
    end

    style PHASE1 fill:#e1f5fe
    style PHASE2 fill:#fff3e0
    style PHASE3 fill:#e8f5e9
    style AR fill:#ffcdd2
    style AW fill:#c8e6c9
    style X fill:#ffcdd2
```

## Key Decision Points

| Condition | Threshold | Result |
|-----------|-----------|--------|
| `pension_date` | > 1 month in past | Deactivate for instNr |
| `isActive` | false | Deactivate for instNr |
| `isOverleden` | true | Deactivate for instNr |
| `assignment.einddatum` | > 1 week in past | Skip assignment PPSBR |
| `automatic_sync` | false | Never auto-deactivate person |

## Process Summary

1. **Per-instNr Deactivation**: Employee conditions are evaluated per institution number
2. **PropRelation Tasks**: Each proprelation gets its own DEACT task
3. **Person Deactivation**: Only happens when ALL proprelations (from ALL instNrs) are inactive
4. **Guard Conditions**: `automatic_sync` must be True for automatic person deactivation
