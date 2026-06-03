# Deploy via Semaphore

Hoe Odoo-addons uit deze repo (`MySchool_addons`) automatisch op de OLVP Odoo-VMs terechtkomen via de Semaphore-pipeline.

## Architectuur in één plaatje

```
GitHub                          Semaphore (10.35.0.10)               Odoo-VMs
─────────                       ──────────────────                   ─────────
                                                                     
MySchool_addons   ──pull──▶  "Odoo extra-addons Update"   ──ssh──▶  /opt/odoo-multi-instance/
  ├── master                  template (Ansible playbook)              ├── addons1/  ← addons[1-N]
  ├── Dev                       │                                      ├── addons2/      per Odoo-
  └── Dev-<Topic>               ├── target_env       filter            └── addons3/      instance
                                ├── addons_branch_override
                                └── target_limit
                                                       
                                                       restart Odoo + module-upgrade (manueel)
```

## Semaphore-template parameters

Survey-vars die je instelt bij elke run:

| Var | Default | Effect |
|---|---|---|
| `target_env` | leeg (= alle) | Filter op `instance.env` in `platform-ansible/vars/instances.yml`. Waarden: `prod` / `test` / `dev` / leeg. **Leeg = alle environments worden geüpdated** — gebruik bewust. |
| `addons_branch_override` | leeg | Forceert één branch over alle matched instances. **Leeg = per-instance default** (prod→`master`, test+dev→`Dev`). Gebruik voor feature-branch-tests (bv. `Dev-MCP`). |
| `target_limit` | `webapps` | Ansible `--limit` op inventory-niveau. Default = alle webapps-VMs. Specifieke VM: `srvv-tst-odoo-01` of `srvv-odoo-01`. |

## Typische runs

| Doel | target_env | target_limit | addons_branch_override |
|---|---|---|---|
| Update **prod** (myschool, myschool-ict, id, myschool-acc) | `prod` | leeg of `webapps` | leeg (= master) |
| Update **gebruikers-test-omgeving** myschool-test | `test` | leeg | leeg (= Dev) |
| Update **alle dev-instances** | `dev` | leeg | leeg (= Dev) |
| **Feature-branch testen** op één test-VM | `test` of `dev` | `tst-odoo-01` | `Dev-<Topic>` |
| **Eén specifieke VM** updaten | (leeg) | bv. `tst-odoo-02` | (default per instance) |

## Stap-voor-stap: feature-branch testen

Voorbeeld: branch `Dev-MCP` op myschool-dev valideren vóór merge naar `Dev`.

1. **Lokaal**: commit + push de feature-branch naar GitHub
   ```bash
   git push origin Dev-MCP
   ```

2. **Semaphore UI** (https://semaphore.olvp.int of waar je instance staat):
   - Templates → **Odoo extra-addons Update** → **Run**
   - Survey:
     - `target_env` = `dev`
     - `addons_branch_override` = `Dev-MCP`
     - `target_limit` = `tst-odoo-01` (één VM)
   - **Start**

3. **Verwacht in de log**:
   - "Voor elke inventory-host in target_limit — match op IP en evalueer target_env" → 1 match (tst-odoo-01)
   - "addons_target = ['tst-odoo-01']"
   - Per dev-instance op die VM (8070+8071+8072): `git clone/pull` op branch `Dev-MCP`
   - Geen UNREACHABLE op andere VMs

4. **Op de VM** (handmatige module-install/upgrade — Semaphore doet enkel git-pull):
   ```bash
   ssh ansible@10.200.14.40
   sudo podman exec odoo_instance_2 odoo -d <db> -i myschool_mcp --stop-after-init --no-http
   sudo systemctl restart odoo_instance_2.service
   ```

5. **Verifie in browser** of via curl (zie [`module-install.md`](module-install.md))

## Stap-voor-stap: merge naar prod

Na test-validatie:

1. **Lokaal**: merge feature → Dev (test deze ook nog op `myschool-test`)
   ```bash
   git checkout Dev
   git merge Dev-MCP
   git push origin Dev
   ```

2. **Semaphore**: Run met `target_env=test` (single test-instance valideert)

3. **Bij groen**: merge Dev → master
   ```bash
   git checkout master
   git merge Dev
   git push origin master
   ```

4. **Semaphore**: Run met `target_env=prod`, eventueel `target_limit=srvv-odoo-01` om expliciet één VM te targetten

5. **Op de prod-VM**: module-install (zie [`module-install.md`](module-install.md))

## CI Arguments (Semaphore template)

Het Template heeft **CLI Arguments leeg** — alle Survey-vars worden auto door Semaphore als `-e KEY=VALUE` doorgegeven aan ansible-playbook. Voor host-pattern is `target_limit` Survey-var die in de playbook zelf wordt gelezen via `hosts: "{{ target_limit | default('webapps') }}"`.

Vermijd handmatig `--limit` in CLI Args — multi-line shell-tekst in dat veld geeft `ansible-playbook --help + exit 2` errors. Zie [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md) (gotcha-section) voor details.

## Inventory + per-instance branches

Welke instance bij welke env hoort, en welke branch automatisch wordt gepulled, staat in `platform-ansible/vars/instances.yml`:

```yaml
- name: srvv-odoo-01
  env: prod
  instances:
    - fqdn: myschool.olvp.be
      env: prod
      addons_branch: master
    - fqdn: myschool-ict.olvp.be
      env: prod
      addons_branch: master
    ...

- name: srvv-tst-odoo-01
  env: test
  instances:
    - fqdn: myschool-test.olvp.be
      env: test          # ← per-instance env-filter (afzonderlijk van VM-env)
      addons_branch: Dev
    - fqdn: id-test.olvp.be
      env: dev
      addons_branch: Dev
    ...
```

**Belangrijk**: VM-env en instance-env kunnen verschillen (multi-env-VMs). Filter werkt per-**instance**, niet per-VM.

## Troubleshooting

- **`Failed to install inventory: parsing private key: ssh: no key found`** → Inventory in Semaphore wijst naar verkeerde Key Store-entry. Gebruik `ansible-targets-ssh`, niet `ansible-service-account` (zie [`platform-handbook` memory `feedback_semaphore_key_canonical`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md))

- **`github_pat ontbreekt`** → Variable Group "Default" heeft geen `github_pat` in Extra Variables (JSON). Voeg toe als secret.

- **`Failed to checkout dev/Dev`** → Case-sensitive branch-naam. Gebruik `Dev` (hoofdletter D), niet `dev`. Zie [ADR 0002](../decisions/0002-branch-strategy.md).

- **`remote: Repository not found`** → PAT heeft geen toegang tot private repo. Re-genereer PAT op GitHub met `repo`-scope, update KeePassXC entry `github-pat-semaphore` + Variable Group.

- **UNREACHABLE op prod-VM tijdens dev-run** → Mocht voorbij zijn na two-play-refactor (sept 2026). Indien terug: check of playbook `hosts: addons_target` heeft (niet meer `hosts: webapps`).

## Volledige Ansible-playbook

`platform-ansible/addons-update.yml`. Two-play structuur:
- **Play 1 (localhost)**: bepaalt dynamic `addons_target` group op basis van target_env-filter
- **Play 2 (addons_target)**: git pull per filtered_instance, juiste branch, juiste addons-dir

Details + Semaphore Template-setup: [`platform-handbook/management-tools/semaphore.md`](https://github.com/ictolvpbe/platform-handbook/blob/main/management-tools/semaphore.md).
