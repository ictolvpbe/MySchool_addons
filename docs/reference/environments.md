# Environments

Drie environments voor MySchool: **prod** / **test** / **dev**. Wie hoort tot welke env wordt per-instance geconfigureerd in `platform-ansible/vars/instances.yml` (`env`-veld per instance, niet alleen per VM).

## prod

| FQDN | Doel | VM | Port | Branch |
|---|---|---|---|---|
| `myschool.olvp.be` | Hoofd-school-administratie | SRVV-ODOO-01 | 8069 | `master` |
| `myschool-ict.olvp.be` | ICT-team operationeel + MCP-host (myschool_mcp) | SRVV-ODOO-01 | 8070 | `master` |
| `id.olvp.be` | Identity/auth-instance (Odoo als OAuth-broker) | SRVV-ODOO-01 | 8071 | `master` |
| `myschool-acc.olvp.int` | Account-administratie (intern alleen) | SRVV-ACC-01 | 8069 | `master` |

**Internal-only**: `myschool-acc.olvp.int` is alleen via interne DNS bereikbaar (geen publieke A-record, geen HAProxy-pad). Beveiligings-keuze: account-admin data nooit aan internet exposen.

## test

Test-omgeving voor gebruikers en functionele validatie vóór prod-deploy.

| FQDN | Doel | VM | Port | Branch |
|---|---|---|---|---|
| `myschool-test.olvp.be` | Gebruikers-test-omgeving (school-medewerkers testen nieuwe features) | SRVV-TST-ODOO-01 | 8069 | `Dev` |
| `myschool-acc-test.olvp.int` | Account-admin test (intern alleen) | SRVV-ACC-01 | 8070 | `Dev` |

## dev

Interne developer-test-omgeving, niet voor gebruikers.

| FQDN | Doel | VM | Port | Branch |
|---|---|---|---|---|
| `id-test.olvp.be` | Identity-test (auth-broker tests) | SRVV-TST-ODOO-01 | 8070 | `Dev` |
| `myschool-dev.olvp.be` | Algemene dev-omgeving | SRVV-TST-ODOO-01 | 8071 | `Dev` |
| `myschool-dev2.olvp.be` | Tweede dev-omgeving (parallel testen) | SRVV-TST-ODOO-02 | 8069 | `Dev` |

## Multi-env-VM-pattern

Eén VM kan instances in verschillende environments hosten:

- **SRVV-TST-ODOO-01** host:
  - `myschool-test` (env=test)
  - `id-test` (env=dev)
  - `myschool-dev` (env=dev)

- **SRVV-ACC-01** host:
  - `myschool-acc` (env=prod)
  - `myschool-acc-test` (env=test)

Reden: hardware-efficiency + gerelateerde instances dichtbij elkaar voor netwerk-latency. Env-filter werkt per-instance, niet per-VM.

## Semaphore-impact

Semaphore "Odoo extra-addons Update" template gebruikt het `env`-veld per-instance om te filteren. Voorbeelden:

| Survey | Effect |
|---|---|
| `target_env=prod` | Pulled `master` op 4 instances (myschool, myschool-ict, id, myschool-acc) |
| `target_env=test` | Pulled `Dev` op 2 instances (myschool-test, myschool-acc-test) |
| `target_env=dev` | Pulled `Dev` op 3 instances (id-test, myschool-dev, myschool-dev2) |
| (leeg) | Pulled per-instance default op alle webapps-VMs |

Details: [`../operations/deploy-via-semaphore.md`](../operations/deploy-via-semaphore.md).

## Cert-strategie

| Categorie | Cert-bron | Validity |
|---|---|---|
| Publiek bereikbare FQDN's (myschool.olvp.be, ...) | Let's Encrypt (HAProxy-laag) | 90 dagen, auto-renewed |
| Caddy ↔ Odoo (re-encrypt-laag) | step-ca (intern PKI) | 24u, auto-renewed door cron |
| Internal-only FQDN's (myschool-acc.olvp.int) | step-ca direct (geen LE) | 24u, auto-renewed |

Volledige cert-architectuur: [`platform-handbook/hosting/architecture/`](https://github.com/ictolvpbe/platform-handbook/tree/main/hosting/architecture).
