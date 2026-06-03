# myschool_asset

Asset-management voor school-omgevingen. Tracking van hardware, licenties, infrastructuur-componenten met lifecycle-states (in-use / spare / retired) en owner/locatie-info.

## Status

| Onderdeel | Stand |
|---|---|
| Status | beta |
| Dependencies | `myschool_core`, `mail` |
| Wordt gebruikt door | `myschool_itsm` (ITSM-CMDB-koppeling) |

## Doel

Eerste laag van een CMDB (Configuration Management Database):

- **Asset-records**: hardware (PC, server, switch, AP), licenties (software), netwerk-componenten
- **Lifecycle-tracking**: aankoop → in-use → onderhoud → retired
- **Linking** met `Person` (owner) en `Organization` (locatie) uit `myschool_core`

## ITSM-koppeling

`myschool_itsm` voegt incidents/problems/changes toe die aan assets gekoppeld worden. Asset + Incident-historie geeft full lifecycle-zicht.

`myschool_core` heeft ook `ConfigItem` + `CIRelation` als generieke CMDB-bouwstenen. Verhouding tussen `myschool_asset` (toegankelijk voor admins) en `core/ConfigItem` (technisch/dev) is nog te verduidelijken — mogelijk samen-trekken in toekomstige refactor.

## In-module docs

Geen aparte README (TODO).

## Gerelateerde modules

- [`myschool_itsm`](myschool_itsm.md) — depends op deze
- [`myschool_core`](myschool_core.md) — ConfigItem-laag
