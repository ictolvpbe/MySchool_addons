# CLAUDE.md — extra-addons code-regels

> Aanvullend op de project-memory. Regels hier zijn bindend voor alle modules
> in deze repo (Odoo 19).

## sudo()-regels

- **Sudo zo smal mogelijk**: rond één statement, nooit als modelhandle bovenaan
  een methode (`X = self.env['model'].sudo()` gevolgd door een hele flow is
  verboden). Schrijf `record.sudo().write(...)` / `Model.sudo().create(...)` op
  precies de regel die het nodig heeft, met een comment wélke ACL/record rule
  gepasseerd wordt.
- **Output naar de client = groepscheck, geen sudo.** Wizards, exports en
  dashboards die data integraal tonen/exporteren gebruiken een expliciete
  `has_group(...)`-check + ACL/record rule op het model. Sudo is daar een
  verkapte autorisatiebeslissing.
- **Brede sudo-reads beperken tot veldlijst**: als sudo onvermijdelijk is voor
  een read die naar de frontend gaat, gebruik `search_read(domain, fields=[...])`
  met expliciete velden — nooit een sudo-recordset doorlussen.
- **M2M-endpoints draaien als technische user, niet als sudo.** Na
  authenticatie (API-key) switchen naar een dedicated user via
  `request.env(user=tech_user.id, su=False)` zodat ACL en audit-trail gelden.
  Goed voorbeeld: `myschool_mcp/controllers/mcp.py` (`_env_for`). Sudo enkel
  voor de config-parameter-reads in de auth-fase.
- **Wél oké zonder discussie** (het bestaande patroon, ~70 sites):
  `ir.config_parameter.sudo().get_param/set_param`, `ir.sequence.sudo()`,
  `ir.logging.sudo().create`, mail-server-counts, password-writes op person,
  api-key-reads op config-records, migrations en tests.

Volledige inventaris + refactorplan: zie [SUDO_REFACTOR_PLAN.md](SUDO_REFACTOR_PLAN.md).
