# -*- coding: utf-8 -*-
"""
Smartschool Web Services Client
===============================

Thin AbstractModel that wraps the Smartschool SOAP API
(``https://<platform>.smartschool.be/Webservices/V3?wsdl``).

Design parity with ``myschool.google.directory.service``:
  * Stateless AbstractModel — no DB table.
  * Client cache keyed on (url, api_key) so a long-running worker
    doesn't reparse the WSDL on every call.
  * Every method returns ``{'success': bool, 'message': str, ...}`` so
    callers (config UI test-button, betask handlers) can render
    diagnostics uniformly.

Smartschool error model: each SOAP method returns an integer
``returncode`` (string in the WSDL). 0 = OK, anything else = error with
a matching message in the Smartschool ``error codes`` table. Network or
auth issues come up as ``zeep.exceptions.Fault`` instead.
"""

import json
import logging
import threading

from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Module-level cache: {(url, api_key): zeep.Client}. Threading lock guards
# the dict because Odoo dispatches HTTP requests on a thread pool.
_CLIENT_CACHE = {}
_CACHE_LOCK = threading.Lock()

# Read-only SOAP methods — never blocked by dry-run / read-only safeguard.
# Everything not in this set is treated as mutating.
_READ_ONLY_METHODS = frozenset({
    'getAllAccounts',
    'getAllAccountsExtended',
    'getUserDetails',
    'getUserDetailsByUsername',
    'getUserDetailsByScannableCode',
    'getUserDetailsByNumber',
    'getClasses',
    'getClassTeachers',
    'getAllGroupsAndClasses',
    'getAccountsFromGroup',
    'getStudents',
    'getSchoolyearDataOfClass',
    'getCoursesByClassname',
})

# Global safeguard parameter key — set via Settings UI or directly on
# ``ir.config_parameter``. Accepted values:
#   'live'        — per-config dry_run decides per platform (default)
#   'dry_run_all' — force all platforms into dry-run regardless of config
#   'read_only'   — reject every mutating call hard (raises in service)
_SAFEGUARD_PARAM = 'myschool.safeguard_mode'


class SmartschoolService(models.AbstractModel):
    _name = 'myschool.smartschool.service'
    _description = 'Smartschool Web Services Client'

    # =========================================================================
    # Client construction
    # =========================================================================

    @api.model
    def _get_client(self, config):
        """Return a cached ``zeep.Client`` for the given config.

        Raises ``UserError`` if zeep is not installed or the WSDL cannot
        be fetched — both are admin-actionable.
        """
        try:
            from zeep import Client
            from zeep.transports import Transport
            from requests import Session
        except ImportError as e:
            raise UserError(_(
                'Python package "zeep" is not installed. Run: '
                'pip install zeep'
            )) from e

        # api_key lives behind base.group_system — read with sudo so the
        # service works from any user context (betask cron runs as the
        # cron user, which is not group_system by default).
        cfg_sudo = config.sudo()
        url = cfg_sudo.get_wsdl_url()
        api_key = cfg_sudo.api_key or ''

        cache_key = (url, api_key)
        with _CACHE_LOCK:
            client = _CLIENT_CACHE.get(cache_key)
            if client is not None:
                return client

        try:
            session = Session()
            session.headers.update({'User-Agent': 'MySchool-Odoo/1.0'})
            transport = Transport(session=session, timeout=30, operation_timeout=60)
            client = Client(url, transport=transport)
        except Exception as e:
            raise UserError(_(
                'Could not fetch Smartschool WSDL from %s — %s'
            ) % (url, e)) from e

        with _CACHE_LOCK:
            _CLIENT_CACHE[cache_key] = client
        return client

    @api.model
    def _invalidate_cache(self, config=None):
        """Drop cached client(s). Called when config changes."""
        with _CACHE_LOCK:
            if config is None:
                _CLIENT_CACHE.clear()
                return
            cfg_sudo = config.sudo()
            url = cfg_sudo.get_wsdl_url()
            api_key = cfg_sudo.api_key or ''
            _CLIENT_CACHE.pop((url, api_key), None)

    # =========================================================================
    # Safeguard helpers
    # =========================================================================

    @api.model
    def _get_safeguard_mode(self):
        """Read the global safeguard mode from ir.config_parameter.

        Returns one of ``live`` / ``dry_run_all`` / ``read_only``. Unset
        or invalid values fall back to ``live`` (backwards-compat —
        existing DBs keep working until an admin opts in to the safer
        modes).
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            _SAFEGUARD_PARAM, 'live')
        if param not in ('live', 'dry_run_all', 'read_only'):
            return 'live'
        return param

    @api.model
    def _is_dry_run(self, config):
        """True when mutating ops should be simulated for this config.

        Order of precedence:
          1. Context flag ``smartschool_force_dry_run`` → True. Used by
             the Smartschool test runner so a single ad-hoc click can
             simulate without touching ir.config_parameter or the
             config record itself.
          2. Global ``read_only`` → mutating ops are *rejected* (this
             method returns True so the caller short-circuits, but
             ``_call`` raises instead of writing a dry-run audit).
          3. Global ``dry_run_all`` → True regardless of per-config flag.
          4. Otherwise → per-config ``dry_run`` field.
        """
        if self.env.context.get('smartschool_force_dry_run'):
            return True
        mode = self._get_safeguard_mode()
        if mode in ('dry_run_all', 'read_only'):
            return True
        return bool(config.dry_run)

    @api.model
    def _audit_dry_run(self, config, method, kwargs, person=None, reason='dry_run'):
        """Write a sys_event recording what the SOAP call would have done.

        ``reason`` is one of ``dry_run`` (simulated as configured),
        ``read_only_reject`` (global read-only mode), or
        ``ownership_skip`` (ownership-check failed). The data field
        carries a JSON blob with method, kwargs (api_key redacted),
        config name and person id.
        """
        try:
            safe_kwargs = {k: v for k, v in kwargs.items() if k != 'accesscode'}
            payload = {
                'reason': reason,
                'config': config.name,
                'platform_url': config.platform_url,
                'method': method,
                'kwargs': safe_kwargs,
            }
            if person is not None:
                payload['person_id'] = getattr(person, 'id', None)
                payload['person_name'] = getattr(person, 'name', None)
            self.env['myschool.sys.event.service'].create_sys_event(
                f'SMARTSCHOOL-SAFEGUARD-{reason.upper()}',
                json.dumps(payload, default=str),
                log_to_screen=False,
                source='SMARTSCHOOL',
            )
        except Exception:
            # Audit must never break the safeguard. Log and move on.
            _logger.exception('Smartschool safeguard audit failed')

    # =========================================================================
    # API discovery — list SOAP signatures + error codes
    # =========================================================================

    @api.model
    def discover_api(self, config):
        """Inspect the WSDL and dump everything useful for debugging.

        Returns a single text blob with:
          1. All SOAP operations + their parameter signatures
          2. The platform's error-code table via ``returnCsvErrorCodes``
             (read-only call; never blocked by safeguards)

        Stored on ``last_discovery_report`` so admins can grep through it
        when a saveUser/setAccountStatus/... call surfaces an unknown
        return code. Both halves are wrapped in try/except so a broken
        WSDL still gives the half that does work.
        """
        config.ensure_one()
        lines = []
        try:
            client = self._get_client(config)
        except UserError as e:
            return f'ERROR: WSDL fetch failed — {e}'
        except Exception as e:
            return f'ERROR: WSDL fetch raised — {e}'

        # ---- 1) SOAP signatures ---------------------------------------------
        lines.append('=' * 72)
        lines.append('SOAP OPERATIONS')
        lines.append('=' * 72)
        try:
            for service in client.wsdl.services.values():
                for port in service.ports.values():
                    ops = port.binding._operations
                    for name in sorted(ops):
                        op = ops[name]
                        sig = op.input.signature() if op.input else ''
                        lines.append(f'{name}({sig})')
        except Exception as e:
            lines.append(f'(failed to enumerate operations: {e})')

        # ---- 2) Error codes ------------------------------------------------
        # Try the three known variants in order; ``returnCsvErrorCodes``
        # is parameter-less per the WSDL on OLVP platforms — do NOT inject
        # accesscode.
        lines.append('')
        lines.append('=' * 72)
        lines.append('ERROR CODES')
        lines.append('=' * 72)
        for method in ('returnCsvErrorCodes', 'returnJsonErrorCodes',
                       'returnErrorCodes'):
            op = getattr(client.service, method, None)
            if op is None:
                continue
            try:
                raw = op()
                text = str(raw or '')
                if text:
                    lines.append(f'--- {method} ---')
                    lines.append(text)
                    break
            except Exception as e:
                lines.append(f'({method} failed: {e})')
        else:
            lines.append('(no error-code endpoint returned data)')

        return '\n'.join(lines)

    # =========================================================================
    # Ownership check (layer C)
    # =========================================================================

    @api.model
    def _get_user_internnumber(self, config, username):
        """Look up the ``internnumber`` of an existing Smartschool user.

        Returns ``None`` when the user does not exist (so callers can
        treat that as "safe to create"). Read-only call — never blocked
        by safeguards.
        """
        if not username:
            return None
        try:
            raw = self._get_client(config).service.getUserDetailsByUsername(
                accesscode=config.sudo().api_key,
                username=username,
            )
        except Exception as e:
            _logger.info('Smartschool getUserDetailsByUsername(%s) failed (treating as absent): %s',
                         username, e)
            return None
        # When the user does not exist, Smartschool returns a numeric
        # error code (typically 2 = "user does not exist"). Treat that
        # as None so the caller can proceed with ADD.
        if isinstance(raw, (int, str)) and str(raw).strip().lstrip('-').isdigit():
            return None
        # Otherwise raw is an XML string with the user's details.
        # ``internnumber`` lives inside; do a cheap substring extraction
        # rather than parsing the full XML — the field always appears
        # as ``<internnumber>…</internnumber>``.
        text = str(raw)
        marker_open = '<internnumber>'
        marker_close = '</internnumber>'
        i = text.find(marker_open)
        if i == -1:
            return None
        j = text.find(marker_close, i)
        if j == -1:
            return None
        return text[i + len(marker_open):j].strip() or None

    @api.model
    def check_ownership(self, config, username, expected_internnumber, person=None):
        """Verify a pre-existing Smartschool account was created by MySchool.

        Returns ``{'success': True, 'owned': bool, 'existing_internnumber': str|None}``.

        Use before any UPD/DEACT/DEL on a username we did not just
        create: if the remote user's ``internnumber`` does not match the
        expected MySchool ``sap_ref``, the account belongs to someone
        else — skip + audit.
        """
        existing = self._get_user_internnumber(config, username)
        if existing is None:
            # No remote user → ownership question doesn't apply.
            return {'success': True, 'owned': True, 'existing_internnumber': None,
                    'message': 'no remote user'}
        owned = (existing == (expected_internnumber or ''))
        if not owned:
            self._audit_dry_run(
                config,
                method='check_ownership',
                kwargs={
                    'username': username,
                    'expected_internnumber': expected_internnumber,
                    'existing_internnumber': existing,
                },
                person=person,
                reason='ownership_skip',
            )
        return {
            'success': True,
            'owned': owned,
            'existing_internnumber': existing,
            'message': 'OK' if owned else (
                f'internnumber mismatch: remote={existing!r}, '
                f'expected={expected_internnumber!r}'),
        }

    # =========================================================================
    # Low-level call helper
    # =========================================================================

    @api.model
    def _call(self, config, method, mutating=None, person=None, **kwargs):
        """Invoke a Smartschool SOAP method.

        Always injects ``accesscode`` from the config so callers don't
        have to. Honours dry-run / read-only / per-config safeguards
        for mutating ops.

        :param mutating: None ⇒ auto-detect via ``_READ_ONLY_METHODS``.
                         True/False ⇒ explicit override (used by callers
                         that wrap methods that aren't in the static set).
        :param person:   optional ``myschool.person`` record — only used
                         for richer audit-trail entries.
        """
        if mutating is None:
            mutating = method not in _READ_ONLY_METHODS

        # Safeguard short-circuit: handle dry-run / read-only BEFORE we
        # touch the network. Read calls always pass through.
        if mutating:
            mode = self._get_safeguard_mode()
            if mode == 'read_only':
                self._audit_dry_run(config, method, kwargs, person=person,
                                    reason='read_only_reject')
                return {
                    'success': False,
                    'message': _('Mutating call %s blocked — '
                                 'safeguard_mode=read_only') % method,
                    'safeguard': 'read_only',
                }
            if self._is_dry_run(config):
                self._audit_dry_run(config, method, kwargs, person=person,
                                    reason='dry_run')
                _logger.info('[SMARTSCHOOL-DRYRUN] %s skipped — payload=%r',
                             method, {k: v for k, v in kwargs.items()
                                      if k != 'accesscode'})
                return {
                    'success': True,
                    'message': _('Dry run — %s call simulated') % method,
                    'dry_run': True,
                }

        client = self._get_client(config)
        op = getattr(client.service, method, None)
        if op is None:
            return {
                'success': False,
                'message': _('Smartschool method %s does not exist on this platform') % method,
            }

        api_key = config.sudo().api_key or ''
        call_kwargs = dict(kwargs)
        call_kwargs.setdefault('accesscode', api_key)

        # Log the outgoing payload (without secrets) BEFORE the call so
        # that diagnose error 23 ("onbekende fout") becomes possible: the
        # server's response is unhelpful, only the exact request body
        # tells us which field was rejected.
        if mutating:
            safe_payload = {
                k: ('***' if 'passwd' in k.lower() or 'password' in k.lower()
                    else v)
                for k, v in call_kwargs.items()
                if k != 'accesscode'
            }
            _logger.info('[SMARTSCHOOL-CALL] %s payload=%r',
                         method, safe_payload)

        try:
            raw = op(**call_kwargs)
        except Exception as e:
            _logger.warning('Smartschool %s failed: %s', method, e)
            return {'success': False, 'message': str(e)}

        # Smartschool returns either an integer/string returncode for
        # mutating ops, or a payload (XML string / list) for read ops.
        # Treat non-zero integer-like returns as failure.
        if isinstance(raw, (int, str)) and str(raw).strip().lstrip('-').isdigit():
            code = int(raw)
            if code == 0:
                return {'success': True, 'message': 'OK', 'returncode': 0}
            return {
                'success': False,
                'message': _SS_RETURNCODES.get(code, _('Smartschool error %s') % code),
                'returncode': code,
            }

        # Non-numeric response → assume payload, success.
        return {'success': True, 'message': 'OK', 'data': raw}

    # =========================================================================
    # Connection test (used by config UI)
    # =========================================================================

    @api.model
    def test_connection(self, config):
        """Two-step probe:
          1. WSDL fetch (proves URL + connectivity)
          2. Authenticated call ``getAllAccounts`` with an empty class
             code, which Smartschool documents as a lightweight probe
             for the access key.

        Returns ``{success, message}``. The config's test fields are
        written by the caller (``action_test_connection`` on the model).
        """
        config.ensure_one()
        _logger.info('Smartschool test_connection START url=%s key_set=%s',
                     config.platform_url, bool(config.sudo().api_key))

        if not config.platform_url:
            _logger.info('Smartschool test_connection: empty URL')
            return {'success': False, 'message': _('Platform URL is empty')}
        if not config.sudo().api_key:
            _logger.info('Smartschool test_connection: empty API key')
            return {'success': False, 'message': _('API key is empty')}

        # Step 1: WSDL reachability
        try:
            client = self._get_client(config)
            _logger.info('Smartschool test_connection: WSDL loaded OK')
        except UserError as e:
            _logger.warning('Smartschool WSDL fetch failed: %s', e)
            return {'success': False, 'message': str(e)}
        except Exception as e:
            _logger.exception('Smartschool WSDL fetch raised unexpected error')
            return {'success': False, 'message': _('WSDL fetch failed: %s') % e}

        # Step 2: lightweight auth probe.
        # ``getAllAccounts`` with code='' and recursive='0' returns the
        # root-level accounts. Any wrong key gives returncode 1 ("Geen
        # toegang") which we surface verbatim.
        try:
            raw = client.service.getAllAccounts(
                accesscode=config.sudo().api_key,
                code='',
                recursive='0',
            )
            _logger.info('Smartschool test_connection: getAllAccounts raw type=%s preview=%r',
                         type(raw).__name__, str(raw)[:200] if raw is not None else None)
        except Exception as e:
            _logger.exception('Smartschool getAllAccounts failed')
            return {'success': False, 'message': _('Auth probe failed: %s') % e}

        # On success the API returns an XML string; on failure a numeric
        # returncode. Reuse the same normalization as ``_call``.
        if isinstance(raw, (int, str)) and str(raw).strip().lstrip('-').isdigit():
            code = int(raw)
            if code == 0:
                return {'success': True, 'message': _('Connection OK')}
            return {
                'success': False,
                'message': _SS_RETURNCODES.get(code, _('Smartschool error %s') % code),
            }

        return {
            'success': True,
            'message': _('Connection OK — WSDL reachable, auth accepted'),
        }


# =============================================================================
# Smartschool error code dictionary
# =============================================================================
# Source: Smartschool Web Services V3 public documentation. Keep only
# the codes the betask handlers can actually surface; unknown codes
# fall through to a generic "Smartschool error N" message.

_SS_RETURNCODES = {
    1:  'De naam dient minimaal uit 2 karakters te bestaan.',
    2:  'De voornaam dient uit minimaal 2 karakters te bestaan.',
    3:  'De gebruikersnaam dient minimaal uit 2 karakters bestaan.',
    4:  'Het nieuwe wachtwoord is niet complex genoeg.',
    5:  'Er is geen groep geselecteerd.',
    6:  'De gebruikersnaam bestaat reeds.',
    7:  'De wachtwoorden zijn niet identiek.',
    8:  'Het opgegeven webserviceswachtwoord is niet correct.',
    9:  'Deze gebruiker bestaat niet.',
    10: 'Er is een fout gebeurd tijdens het verwerken van de gegevens.',
    11: 'Er is een fout opgetreden tijdens het bewaren van de klasgegevens.',
    12: 'Deze gebruiker bestaat niet.',
    13: 'Fout bij kopiëren/verplaatsen van gebruikers naar opgegeven klas.',
    14: 'Onvoldoende gegevens aangeleverd.',
    15: 'Dubbele gebruikersnaam.',
    16: 'Dubbel intern nummer.',
    17: 'Fout bij bewaren van profielvelden.',
    18: 'Fout bij versturen van het bericht.',
    19: 'Parent-ID bestaat niet.',
    20: 'Cursus toevoegen mislukt.',
    21: 'Cursus met dezelfde naam bestaat al.',
    22: 'Cursus niet gevonden.',
    23: 'Onbekende fout tijdens de verwerking (mogelijk: ontbrekend verplicht veld, '
        'ongeldige basisrol, of wachtwoord/karakter-validatie).',
    24: 'Er is reeds een gebruiker met dit intern nummer.',
    25: 'Gebruiker bestaat niet in Smartschool — kan niet gewijzigd worden.',
    26: 'Gebruiker bestaat reeds in Smartschool — kan niet toegevoegd worden.',
    27: 'Het instellingsnummer komt niet voor in Smartschool.',
    28: 'Het selecteren van een basisrol is verplicht.',
    29: 'U mag de basisrol van deze account niet meer wijzigen.',
    30: 'Enkel leerlingen mogen lid zijn van officiële klassen.',
    31: 'Leerling mag maar lid zijn van één officiële klas.',
    32: 'Leerling dient lid te zijn van één officiële klas.',
    33: 'Registreren van klasbeweging is mislukt.',
    34: 'Leerling kan niet geactiveerd worden — niet in officiële klas.',
    35: 'Instellingsnummer is verplicht bij officiële klas.',
    36: 'Type van officiële klas mag niet gewijzigd worden.',
    37: 'Type-wijziging niet toegestaan: leden hebben geen basisrol "Leerling".',
    38: 'Type-wijziging niet toegestaan: leden zitten in andere officiële klas.',
    39: 'Vormingscomponent selecteren is verplicht.',
    40: 'Naam van klas mag niet meer gewijzigd worden.',
    41: 'Administratiefnummer mag niet meer gewijzigd worden.',
    42: 'Instellingsnummer mag niet meer gewijzigd worden.',
    43: 'Vormingscomponent mag niet meer gewijzigd worden.',
    44: 'Vormingscomponent is verplicht.',
    45: 'Type van klas mag niet gewijzigd worden.',
    46: 'Type van groep selecteren is verplicht.',
    47: 'Klas/groepcode bestaat al.',
    48: 'Intern nummer bestaat reeds.',
    49: 'Datum is niet geldig.',
    50: 'Module "Skore" is niet geactiveerd.',
    51: 'Fout bij uitschrijven van leerling.',
    52: 'Wachtwoord werd niet toegestaan.',
    53: 'Bovenliggende groep werd niet gevonden.',
    54: 'Bovenliggende groep mag geen officiële klas zijn.',
    55: 'Officiële klas kan geen subgroepen bevatten.',
    56: 'Geldige datum vereist voor schooljaar.',
    57: 'Roostercode dient uniek te zijn.',
}
