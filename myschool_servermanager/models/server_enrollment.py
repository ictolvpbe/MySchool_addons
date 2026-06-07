import logging

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MANAGER_GROUP = 'myschool_servermanager.group_servermanager_manager'

# Module-states die we als "aanwezig" beschouwen (geen herinstallatie nodig).
_INSTALLED_STATES = ('installed', 'to install', 'to upgrade')


class MyschoolServer(models.Model):
    """Enrollment-laag (SRVMGR-5): connectie via Odoo JSON-RPC + idempotente
    toepassing van standaard-instellingen o.b.v. de rol.

    Uitvoeringsstrategie (besloten): servermanager praat rechtstreeks met de
    remote Odoo via de externe API (``/jsonrpc``). Credentials staan per server
    in het register (manager-only). Alle netwerk-IO loopt door één methode,
    ``_jsonrpc``, zodat ze in tests te mocken is.
    """

    _inherit = 'myschool.server'

    # --- Connectie-credentials (manager-only) ---
    use_https = fields.Boolean(string='Use HTTPS', default=True)
    login = fields.Char(
        string='RPC Login', groups=MANAGER_GROUP,
        help='Login van de remote Odoo-gebruiker waarmee enrollment draait.')
    api_key = fields.Char(
        string='API Key / Password', groups=MANAGER_GROUP,
        help='API-key (of wachtwoord) van de RPC-gebruiker. Manager-only.')
    target_admin_password = fields.Char(
        string='Set Admin Password', groups=MANAGER_GROUP,
        help='Indien ingevuld wordt dit als admin-wachtwoord gezet bij de '
             'volgende enrollment, daarna gewist (set-once).')

    # --- Connectie-status ---
    connection_state = fields.Selection([
        ('unknown', 'Unknown'),
        ('ok', 'OK'),
        ('error', 'Error'),
    ], string='Connection', default='unknown', readonly=True, copy=False)
    connection_message = fields.Char(
        string='Connection Message', readonly=True, copy=False)
    last_connection_check = fields.Datetime(
        string='Last Connection Check', readonly=True, copy=False)

    # --- Enrollment-status ---
    enrollment_state = fields.Selection([
        ('pending', 'Not enrolled'),
        ('done', 'Enrolled'),
        ('error', 'Error'),
    ], string='Enrollment', default='pending', readonly=True, copy=False,
        tracking=True)
    last_enrolled = fields.Datetime(string='Last Enrolled', readonly=True, copy=False)
    enrollment_log = fields.Text(string='Enrollment Log', readonly=True, copy=False)

    # --- Plan, afgeleid van de rol (alleen-lezen weergave) ---
    enroll_lang = fields.Char(
        related='role_id.enroll_lang', string='Default Language', readonly=True)
    enroll_module_names = fields.Char(
        related='role_id.enroll_module_names', string='Modules to Install',
        readonly=True)

    # ------------------------------------------------------------------
    # JSON-RPC client — _jsonrpc is de enige netwerk-methode (mockbaar)
    # ------------------------------------------------------------------

    def _rpc_base_url(self):
        self.ensure_one()
        if self.api_endpoint:
            return self.api_endpoint.rstrip('/')
        if not self.fqdn:
            raise UserError(_(
                "Geen FQDN of API-endpoint ingesteld voor server %s.") % self.name)
        scheme = 'https' if self.use_https else 'http'
        default_port = 443 if self.use_https else 80
        port = self.http_port or default_port
        host = self.fqdn if port == default_port else f'{self.fqdn}:{port}'
        return f'{scheme}://{host}'

    def _jsonrpc(self, service, method, args):
        """Roept de remote ``/jsonrpc`` aan en geeft ``result`` terug.
        Enige plek met netwerk-IO → in tests gemockt."""
        self.ensure_one()
        url = self._rpc_base_url() + '/jsonrpc'
        payload = {
            'jsonrpc': '2.0', 'method': 'call',
            'params': {'service': service, 'method': method, 'args': args},
            'id': 1,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — alle netwerk/parse-fouten samen
            raise UserError(_("RPC-call mislukt naar %s: %s") % (url, exc))
        if data.get('error'):
            err = data['error']
            msg = (err.get('data') or {}).get('message') or err.get('message') or err
            raise UserError(_("RPC-fout van %s: %s") % (url, msg))
        return data.get('result')

    def _rpc_authenticate(self):
        self.ensure_one()
        if not (self.db_name and self.login and self.api_key):
            raise UserError(_(
                "Database, RPC-login en API-key zijn vereist voor server %s.")
                % self.name)
        uid = self._jsonrpc('common', 'authenticate',
                            [self.db_name, self.login, self.api_key, {}])
        if not uid:
            raise UserError(_("Authenticatie geweigerd door %s.") % self.name)
        return uid

    def _rpc_execute(self, uid, model, method, args, kwargs=None):
        self.ensure_one()
        return self._jsonrpc('object', 'execute_kw', [
            self.db_name, uid, self.api_key, model, method, args, kwargs or {}])

    # ------------------------------------------------------------------
    # Acties
    # ------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        now = fields.Datetime.now()
        try:
            uid = self._rpc_authenticate()
        except UserError as exc:
            msg = exc.args[0] if exc.args else str(exc)
            self.write({'connection_state': 'error', 'connection_message': msg,
                        'last_connection_check': now})
            return self._rpc_notify(_("Verbinding mislukt"), msg, 'danger')
        msg = _("Verbonden (uid %s).") % uid
        self.write({'connection_state': 'ok', 'connection_message': msg,
                    'last_connection_check': now})
        return self._rpc_notify(_("Verbinding OK"), msg, 'success')

    def action_enroll(self):
        """Pas idempotent de standaard-instellingen van de rol toe op de remote."""
        self.ensure_one()
        log = []
        clear_admin_pw = False
        try:
            uid = self._rpc_authenticate()
            log.append(_("Geauthenticeerd als uid %s.") % uid)
            if self.role_id.enroll_lang:
                self._enroll_apply_language(uid, self.role_id.enroll_lang, log)
            module_names = self.role_id._collect_module_names() if self.role_id else []
            if module_names:
                self._enroll_install_modules(uid, module_names, log)
            else:
                log.append(_("Geen modules om te installeren."))
            if self.target_admin_password:
                self._enroll_set_admin_password(uid, log)
                clear_admin_pw = True
            state = 'done'
        except UserError as exc:
            log.append(_("FOUT: %s") % (exc.args[0] if exc.args else exc))
            state = 'error'

        vals = {'enrollment_state': state, 'enrollment_log': '\n'.join(log)}
        if state == 'done':
            vals['last_enrolled'] = fields.Datetime.now()
            if clear_admin_pw:
                vals['target_admin_password'] = False
        self.write(vals)
        self.message_post(body=_("Enrollment (%s):") % state
                          + '<br/>' + '<br/>'.join(log))
        level = 'success' if state == 'done' else 'danger'
        return self._rpc_notify(_("Enrollment %s") % state,
                                _("Zie het enrollment-logboek."), level)

    # ------------------------------------------------------------------
    # Enrollment-stappen (idempotent)
    # ------------------------------------------------------------------

    def _enroll_apply_language(self, uid, lang, log):
        ids = self._rpc_execute(uid, 'res.lang', 'search', [[['code', '=', lang]]],
                                {'context': {'active_test': False}})
        if not ids:
            log.append(_("Taal %s niet gevonden op remote — handmatig "
                         "installeren.") % lang)
            return
        recs = self._rpc_execute(uid, 'res.lang', 'read', [ids, ['active']])
        if recs and recs[0].get('active'):
            log.append(_("Taal %s al actief.") % lang)
        else:
            self._rpc_execute(uid, 'res.lang', 'write', [ids, {'active': True}])
            log.append(_("Taal %s geactiveerd.") % lang)

    def _enroll_install_modules(self, uid, names, log):
        ids = self._rpc_execute(uid, 'ir.module.module', 'search',
                                [[['name', 'in', names]]])
        recs = self._rpc_execute(uid, 'ir.module.module', 'read',
                                 [ids, ['name', 'state']]) if ids else []
        found = {r['name']: r for r in recs}
        missing = [n for n in names if n not in found]
        if missing:
            log.append(_("Niet gevonden op remote: %s") % ', '.join(missing))
        already = [r['name'] for r in recs if r['state'] in _INSTALLED_STATES]
        if already:
            log.append(_("Al aanwezig: %s") % ', '.join(already))
        to_install = [r for r in recs if r['state'] not in _INSTALLED_STATES]
        if to_install:
            self._rpc_execute(uid, 'ir.module.module', 'button_immediate_install',
                              [[r['id'] for r in to_install]])
            log.append(_("Geïnstalleerd: %s")
                       % ', '.join(r['name'] for r in to_install))
        else:
            log.append(_("Geen nieuwe modules te installeren."))

    def _enroll_set_admin_password(self, uid, log):
        admin_ids = self._rpc_execute(uid, 'res.users', 'search',
                                      [[['login', '=', 'admin']]])
        if not admin_ids:
            log.append(_("Geen 'admin'-gebruiker gevonden; wachtwoord overgeslagen."))
            return
        self._rpc_execute(uid, 'res.users', 'write',
                          [admin_ids, {'password': self.target_admin_password}])
        log.append(_("Admin-wachtwoord bijgewerkt."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rpc_notify(self, title, message, kind):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title, 'message': message, 'type': kind,
                'sticky': kind == 'danger',
            },
        }
