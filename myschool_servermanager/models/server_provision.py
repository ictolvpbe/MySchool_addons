from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

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


class MyschoolServerProvisionCompany(models.Model):
    """Sjabloon voor een company (incl. sub-companies) die bij provisioning op
    een instance wordt aangemaakt (SRVMGR-6).

    De boom hangt aan een server (per-instance identiteit). Eén knoop kan als
    ``is_main`` gemarkeerd worden: die **hernoemt** de bestaande hoofd-company
    van de remote i.p.v. een nieuwe aan te maken (zo blijft er geen lege
    "My Company" achter). Sub-companies verwijzen via ``parent_id`` naar een
    andere knoop in dezelfde boom; bij provisioning worden parents vóór kinderen
    verwerkt en wordt op naam gematcht (idempotent, geen duplicaten).
    """

    _name = 'myschool.server.provision.company'
    _description = 'Server Provisioning — Company'
    _order = 'sequence, name'
    _parent_name = 'parent_id'

    server_id = fields.Many2one(
        'myschool.server', string='Server', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string='Company Name', required=True)
    is_main = fields.Boolean(
        string='Main Company',
        help='Hernoemt de bestaande hoofd-company van de remote i.p.v. een '
             'nieuwe aan te maken. Max. één per server.')
    parent_id = fields.Many2one(
        'myschool.server.provision.company', string='Parent Company',
        ondelete='set null',
        domain="[('server_id', '=', parent.id), ('id', '!=', id)]",
        help='Bovenliggende company in de boom (een andere knoop van dezelfde '
             'server).')
    child_ids = fields.One2many(
        'myschool.server.provision.company', 'parent_id', string='Sub-companies')

    @api.constrains('parent_id')
    def _check_company_hierarchy(self):
        for rec in self:
            if rec.parent_id and rec.parent_id.server_id != rec.server_id:
                raise ValidationError(_(
                    "Een parent-company moet bij dezelfde server horen."))
            if rec.is_main and rec.parent_id:
                raise ValidationError(_(
                    "De hoofd-company kan geen parent hebben."))
        if self._has_cycle():
            raise ValidationError(_("Company-boom mag geen lus bevatten."))

    @api.constrains('is_main', 'active')
    def _check_single_main(self):
        for rec in self.filtered(lambda r: r.is_main and r.active):
            others = self.search_count([
                ('server_id', '=', rec.server_id.id), ('is_main', '=', True),
                ('active', '=', True), ('id', '!=', rec.id)])
            if others:
                raise ValidationError(_(
                    "Er kan maar één hoofd-company per server zijn."))


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
    provision_company_ids = fields.One2many(
        'myschool.server.provision.company', 'server_id', string='Companies',
        help='Company-boom (hoofd-company + sub-companies) die op de remote '
             'voorzien wordt bij provisioning.')
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
            self._provision_companies(uid, log)
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

    def _provision_companies(self, uid, log):
        seeds = self.provision_company_ids.filtered('active')
        if not seeds:
            log.append(_("Geen companies gedefinieerd — overgeslagen."))
            return
        # Cache: company-naam -> remote id (vermijdt herhaalde lookups).
        name_to_id = {}
        main_id = False

        # 1) Hoofd-company: hernoem de bestaande (geen nieuwe), idempotent.
        main_seed = seeds.filtered('is_main')[:1]
        if main_seed:
            main_id = self._rpc_main_company_id(uid)
            if not main_id:
                log.append(_("Geen hoofd-company gevonden op remote."))
            else:
                recs = self._rpc_execute(uid, 'res.company', 'read',
                                         [[main_id], ['name']])
                current = recs[0].get('name') if recs else None
                if current == main_seed.name:
                    log.append(_("Hoofd-company al '%s'.") % main_seed.name)
                else:
                    self._rpc_execute(uid, 'res.company', 'write',
                                      [[main_id], {'name': main_seed.name}])
                    log.append(_("Hoofd-company hernoemd naar '%s'.")
                               % main_seed.name)
                name_to_id[main_seed.name] = main_id

        # 2) Overige companies, parents vóór kinderen (op boom-diepte).
        others = (seeds - main_seed).sorted(key=lambda s: self._seed_depth(s))
        for seed in others:
            existing = self._rpc_execute(
                uid, 'res.company', 'search', [[['name', '=', seed.name]]],
                {'context': {'active_test': False}})
            if existing:
                name_to_id[seed.name] = existing[0]
                log.append(_("Company '%s' bestaat al.") % seed.name)
                continue
            vals = {'name': seed.name}
            parent_id = self._resolve_parent_company(
                uid, seed, main_id, name_to_id, log)
            if parent_id:
                vals['parent_id'] = parent_id
            new_id = self._rpc_execute(uid, 'res.company', 'create', [vals])
            name_to_id[seed.name] = new_id
            suffix = (_(" onder '%s'") % seed.parent_id.name
                      if seed.parent_id else '')
            log.append(_("Company '%s' aangemaakt%s.") % (seed.name, suffix))

    def _resolve_parent_company(self, uid, seed, main_id, name_to_id, log):
        """Geef het remote id van de parent-company van ``seed`` (of False)."""
        parent = seed.parent_id
        if not parent:
            return False
        if parent.is_main:
            return main_id or self._rpc_main_company_id(uid)
        if parent.name in name_to_id:
            return name_to_id[parent.name]
        ids = self._rpc_execute(
            uid, 'res.company', 'search', [[['name', '=', parent.name]]],
            {'context': {'active_test': False}})
        if ids:
            name_to_id[parent.name] = ids[0]
            return ids[0]
        log.append(_("Parent-company '%s' voor '%s' niet gevonden — zonder "
                     "parent aangemaakt.") % (parent.name, seed.name))
        return False

    def _seed_depth(self, seed):
        """Aantal voorouders binnen de seed-boom (parents krijgen lagere diepte)."""
        depth, parent, seen = 0, seed.parent_id, set()
        while parent and parent.id not in seen:
            seen.add(parent.id)
            depth += 1
            parent = parent.parent_id
        return depth

    def _rpc_main_company_id(self, uid):
        ids = self._rpc_execute(uid, 'res.company', 'search', [[]],
                                {'order': 'id', 'limit': 1})
        return ids[0] if ids else False

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
