from odoo import models, fields, api, _
from odoo.exceptions import UserError

MANAGER_GROUP = 'myschool_servermanager.group_servermanager_manager'

# Groepen die een geprovisionde gebruiker minimaal/optioneel krijgt.
_BASE_USER_GROUP = 'base.group_user'        # interne gebruiker
_ADMIN_GROUP = 'base.group_system'          # Settings / administrator


class MyschoolServerProvisionUser(models.Model):
    """Sjabloon voor een default-gebruiker die bij provisioning op een verse
    instance wordt aangemaakt (SRVMGR-6).

    Hoort bij een rol, zodat het sjabloon herbruikbaar is over alle servers met
    die rol. Provisioning is idempotent: bestaat de login al op de remote, dan
    wordt de gebruiker overgeslagen (geen duplicaten, geen wachtwoord-overschrijving).
    """

    _name = 'myschool.server.provision.user'
    _description = 'Server Provisioning — Default User'
    _order = 'sequence, name'

    role_id = fields.Many2one(
        'myschool.server.role', string='Role', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string='Name', required=True)
    login = fields.Char(
        string='Login', required=True,
        help='Login waarop idempotent gematcht wordt op de remote.')
    email = fields.Char(string='Email')
    lang = fields.Char(
        string='Language', help='Taalcode (bv. nl_BE); leeg = remote-default.')
    password = fields.Char(
        string='Initial Password', groups=MANAGER_GROUP,
        help='Wordt enkel bij het aanmaken gezet. Manager-only.')
    is_admin = fields.Boolean(
        string='Administrator',
        help='Voegt de gebruiker toe aan de Settings/administrator-groep.')

    _login_role_unique = models.Constraint(
        'UNIQUE(role_id, login)', 'Login must be unique within a role.')


class MyschoolServer(models.Model):
    """Provisioning-laag (SRVMGR-6): voorziet een (ge-enrollde) instance van
    base-data + een of meer default-gebruikers via dezelfde Odoo JSON-RPC-laag
    als enrollment (SRVMGR-5).

    Idempotent en herhaalbaar zonder duplicaten:
    * **Company** — de hoofd-company van de remote krijgt de geconfigureerde
      naam (alleen geschreven als ze verschilt).
    * **Default users** — per login gematcht; enkel ontbrekende worden aangemaakt.

    Scope-afbakening: de MySchool **org/structuur**-masterdata (org-boom) wordt
    NIET hier gekopieerd — dat is replicatie van master→slave en hoort bij
    ``myschool_sync`` (SRVMGR-7), aansluitend op de data-locatie-keuze (SRVMGR-4).
    """

    _inherit = 'myschool.server'

    # --- Provisioning-config (per server) ---
    provision_company_name = fields.Char(
        string='Company Name',
        help='Naam die de hoofd-company van de remote krijgt bij provisioning. '
             'Leeg = company-naam ongemoeid laten.')
    provision_user_ids = fields.One2many(
        related='role_id.provision_user_ids', string='Default Users (from role)',
        readonly=True)

    # --- Provisioning-status ---
    provision_state = fields.Selection([
        ('pending', 'Not provisioned'),
        ('done', 'Provisioned'),
        ('error', 'Error'),
    ], string='Provisioning', default='pending', readonly=True, copy=False,
        tracking=True)
    last_provisioned = fields.Datetime(
        string='Last Provisioned', readonly=True, copy=False)
    provision_log = fields.Text(string='Provisioning Log', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Actie
    # ------------------------------------------------------------------

    def action_provision(self):
        """Voorzie de remote idempotent van base-data + default-gebruikers."""
        self.ensure_one()
        log = []
        try:
            uid = self._rpc_authenticate()
            log.append(_("Geauthenticeerd als uid %s.") % uid)
            self._provision_company(uid, log)
            self._provision_users(uid, log)
            state = 'done'
        except UserError as exc:
            log.append(_("FOUT: %s") % (exc.args[0] if exc.args else exc))
            state = 'error'

        vals = {'provision_state': state, 'provision_log': '\n'.join(log)}
        if state == 'done':
            vals['last_provisioned'] = fields.Datetime.now()
        self.write(vals)
        self.message_post(body=_("Provisioning (%s):") % state
                          + '<br/>' + '<br/>'.join(log))
        level = 'success' if state == 'done' else 'danger'
        return self._rpc_notify(_("Provisioning %s") % state,
                                _("Zie het provisioning-logboek."), level)

    # ------------------------------------------------------------------
    # Provisioning-stappen (idempotent)
    # ------------------------------------------------------------------

    def _provision_company(self, uid, log):
        name = (self.provision_company_name or '').strip()
        if not name:
            log.append(_("Geen company-naam ingesteld — overgeslagen."))
            return
        ids = self._rpc_execute(uid, 'res.company', 'search', [[]],
                                {'order': 'id', 'limit': 1})
        if not ids:
            log.append(_("Geen hoofd-company gevonden op remote."))
            return
        recs = self._rpc_execute(uid, 'res.company', 'read', [ids, ['name']])
        current = recs[0].get('name') if recs else None
        if current == name:
            log.append(_("Company-naam al '%s'.") % name)
        else:
            self._rpc_execute(uid, 'res.company', 'write', [ids, {'name': name}])
            log.append(_("Company hernoemd naar '%s'.") % name)

    def _provision_users(self, uid, log):
        users = self.provision_user_ids.filtered('active')
        if not users:
            log.append(_("Geen default-gebruikers gedefinieerd op de rol."))
            return
        for pu in users:
            self._provision_one_user(uid, pu, log)

    def _provision_one_user(self, uid, pu, log):
        existing = self._rpc_execute(
            uid, 'res.users', 'search', [[['login', '=', pu.login]]],
            {'context': {'active_test': False}})
        if existing:
            log.append(_("Gebruiker '%s' bestaat al — overgeslagen.") % pu.login)
            return
        group_ids = [self._rpc_xmlid(uid, _BASE_USER_GROUP)]
        if pu.is_admin:
            group_ids.append(self._rpc_xmlid(uid, _ADMIN_GROUP))
        group_ids = [g for g in group_ids if g]
        vals = {'name': pu.name, 'login': pu.login}
        if pu.email:
            vals['email'] = pu.email
        if pu.lang:
            vals['lang'] = pu.lang
        if pu.password:
            vals['password'] = pu.password
        if group_ids:
            vals['group_ids'] = [(6, 0, group_ids)]
        self._rpc_execute(uid, 'res.users', 'create', [vals])
        log.append(_("Gebruiker '%s' aangemaakt%s.")
                   % (pu.login, _(" (administrator)") if pu.is_admin else ''))

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _rpc_xmlid(self, uid, xmlid):
        """Zoek het res_id van een externe identifier (module.name) op de remote."""
        self.ensure_one()
        module, name = xmlid.split('.', 1)
        recs = self._rpc_execute(
            uid, 'ir.model.data', 'search_read',
            [[['module', '=', module], ['name', '=', name]], ['res_id']],
            {'limit': 1})
        return recs[0]['res_id'] if recs else False
