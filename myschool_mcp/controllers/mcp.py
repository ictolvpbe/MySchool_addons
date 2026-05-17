# -*- coding: utf-8 -*-
"""
MCP HTTP Controller.

Implementeert het Model Context Protocol over HTTP (POST /mcp,
JSON-RPC 2.0). Authentificatie via header ``X-API-Key`` tegen
``res.users.apikeys`` — bij succes wordt de request afgehandeld onder
die gebruiker (acties verschijnen in chatter onder hun naam).

Ondersteunde MCP-methoden voor v1:
  * ``initialize``      — handshake + capability advertising
  * ``notifications/initialized`` — client-side ack (no-op)
  * ``ping``            — keep-alive
  * ``tools/list``      — geef alle geregistreerde tools terug
  * ``tools/call``      — voer één tool uit

SSE-stream (server→client notifications) zit niet in v1 — onze tools
zijn synchroon en hebben geen progress-events nodig.
"""

import json
import logging

from odoo import http
from odoo.http import request, Response

from ..models.mcp_registry import McpRegistry, McpToolError, get_rate_limiter

# Importing the providers package triggers tool-registration via decorators.
from .. import providers  # noqa: F401

_logger = logging.getLogger(__name__)


# Codes uit de JSON-RPC 2.0 spec + onze eigen extensies (range -32000..-32099)
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_UNAUTHORIZED = -32001
JSONRPC_RATE_LIMITED = -32002
JSONRPC_FORBIDDEN = -32003

MCP_PROTOCOL_VERSION = '2025-03-26'
MCP_SERVER_NAME = 'myschool-mcp'
MCP_SERVER_VERSION = '0.1.0'


class McpController(http.Controller):
    # State: heeft de in-memory rate-limiter zijn config al gelezen?
    _rate_limit_initialised = False

    # ------------------------------------------------------------------
    # Endpoint
    # ------------------------------------------------------------------

    @http.route('/mcp', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False)
    def mcp(self, **kw):
        """Streamable HTTP MCP endpoint — JSON-RPC 2.0 over POST."""
        # Init rate-limit op de eerste call (kan niet bij module-laad
        # omdat ir.config_parameter dan nog niet beschikbaar is).
        if not McpController._rate_limit_initialised:
            try:
                request.env['myschool.mcp.config']._load_rate_limit_at_startup()
            except Exception:
                _logger.exception('MCP: rate-limit init faalde — fallback default')
            McpController._rate_limit_initialised = True

        # ---- Parse body ----
        try:
            raw = request.httprequest.data
            body = json.loads(raw) if raw else {}
        except (ValueError, TypeError) as e:
            return self._jsonrpc_error(JSONRPC_PARSE_ERROR,
                                       f'Parse error: {e}', request_id=None)

        if not isinstance(body, dict):
            return self._jsonrpc_error(JSONRPC_INVALID_REQUEST,
                                       'Request must be a JSON object',
                                       request_id=None)

        method = body.get('method')
        request_id = body.get('id')
        params = body.get('params') or {}

        # ---- Auth ----
        api_key = (request.httprequest.headers.get('X-API-Key') or
                   self._extract_bearer_token(request.httprequest))
        user_id = self._authenticate(api_key) if api_key else None

        # Initialise + notifications zijn niet-authenticated toegestaan
        # zodat een client de capabilities kan ontdekken vóór auth.
        # tools/call en tools/list eisen WEL auth.
        public_methods = ('initialize', 'notifications/initialized', 'ping')
        if method not in public_methods and not user_id:
            return self._jsonrpc_error(
                JSONRPC_UNAUTHORIZED,
                'Unauthorized: provide a valid Odoo API key via the '
                'X-API-Key header.',
                request_id=request_id, status=401)

        # ---- Dispatch ----
        try:
            if method == 'initialize':
                return self._handle_initialize(body, request_id)
            if method == 'notifications/initialized':
                # Notification — no response per JSON-RPC spec
                return Response('', status=204)
            if method == 'ping':
                return self._jsonrpc_ok({}, request_id)
            if method == 'tools/list':
                return self._handle_tools_list(user_id, request_id)
            if method == 'tools/call':
                return self._handle_tools_call(user_id, params, request_id)
            return self._jsonrpc_error(
                JSONRPC_METHOD_NOT_FOUND,
                f'Method not found: {method}',
                request_id=request_id)
        except Exception as e:
            _logger.exception('MCP: handler crashed for method %r', method)
            return self._jsonrpc_error(
                JSONRPC_INTERNAL_ERROR, f'Internal error: {e}',
                request_id=request_id, status=500)

    # ------------------------------------------------------------------
    # MCP method handlers
    # ------------------------------------------------------------------

    def _handle_initialize(self, body, request_id):
        # Client mag protocolVersion meesturen; wij accepteren onze
        # eigen versie en negeren downgrade-onderhandeling voor v1.
        return self._jsonrpc_ok({
            'protocolVersion': MCP_PROTOCOL_VERSION,
            'capabilities': {
                'tools': {'listChanged': False},
            },
            'serverInfo': {
                'name': MCP_SERVER_NAME,
                'version': MCP_SERVER_VERSION,
            },
        }, request_id)

    def _handle_tools_list(self, user_id, request_id):
        env = self._env_for(user_id)
        # Filter provider-toggles uit ir.config_parameter — als een
        # provider uitstaat verbergen we zijn tools volledig.
        enabled = self._enabled_providers(env)
        tools = []
        for t in McpRegistry.list_tools():
            prefix = t['name'].split('_', 1)[0]
            if prefix not in enabled:
                continue
            tools.append(t)
        return self._jsonrpc_ok({'tools': tools}, request_id)

    def _handle_tools_call(self, user_id, params, request_id):
        env = self._env_for(user_id)
        if not env.user.has_group('myschool_mcp.group_mcp_user'):
            return self._jsonrpc_error(
                JSONRPC_FORBIDDEN,
                'User lacks group_mcp_user — MCP access is disabled.',
                request_id=request_id, status=403)

        name = params.get('name')
        arguments = params.get('arguments') or {}
        if not name or not isinstance(name, str):
            return self._jsonrpc_error(
                JSONRPC_INVALID_PARAMS,
                'tools/call requires `name` (string).',
                request_id=request_id)

        # Provider-toggle check
        prefix = name.split('_', 1)[0]
        if prefix not in self._enabled_providers(env):
            return self._jsonrpc_error(
                JSONRPC_METHOD_NOT_FOUND,
                f'Tool {name!r} is disabled by the server administrator.',
                request_id=request_id)

        try:
            result = McpRegistry.call(env, name, arguments)
        except McpToolError as e:
            self._log_error(env, name, str(e))
            return self._jsonrpc_error(
                e.code, str(e), request_id=request_id)

        self._log_call(env, name, arguments)

        # Wrap in MCP-conforme content-structuur (text-only voor v1)
        return self._jsonrpc_ok({
            'content': [{
                'type': 'text',
                'text': json.dumps(result, default=self._json_default),
            }],
        }, request_id)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _authenticate(self, api_key):
        """Geef user_id terug bij geldige key, anders None."""
        if not api_key:
            return None
        try:
            user_id = request.env['res.users.apikeys'].sudo()._check_credentials(
                scope='rpc', key=api_key)
            return user_id
        except Exception:
            _logger.exception('MCP: apikey credential check faalde')
            return None

    def _extract_bearer_token(self, httprequest):
        """Sta ``Authorization: Bearer <key>`` toe als alternatief."""
        auth = httprequest.headers.get('Authorization') or ''
        if auth.lower().startswith('bearer '):
            return auth[7:].strip()
        return None

    def _env_for(self, user_id):
        """Build env onder de geauthentificeerde gebruiker."""
        return request.env(user=user_id, su=False)

    # ------------------------------------------------------------------
    # Provider toggles
    # ------------------------------------------------------------------

    def _enabled_providers(self, env):
        """Lees ir.config_parameter en geef een set van provider-prefixes."""
        ICP = env['ir.config_parameter'].sudo()
        out = set()
        if ICP.get_param('myschool_mcp.provider_appfoundry', 'True') in (
                'True', 'true', '1', True, 1):
            out.add('appfoundry')
        return out

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    def _jsonrpc_ok(self, result, request_id):
        body = {
            'jsonrpc': '2.0',
            'id': request_id,
            'result': result,
        }
        return Response(json.dumps(body, default=self._json_default),
                        content_type='application/json',
                        status=200)

    def _jsonrpc_error(self, code, message, request_id=None, status=200,
                       data=None):
        err = {'code': code, 'message': message}
        if data is not None:
            err['data'] = data
        body = {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': err,
        }
        return Response(json.dumps(body, default=self._json_default),
                        content_type='application/json',
                        status=status)

    @staticmethod
    def _json_default(obj):
        # Datetimes & date naar ISO; recordsets als ids.
        try:
            return obj.isoformat()
        except AttributeError:
            pass
        if hasattr(obj, 'ids'):
            return obj.ids
        return str(obj)

    # ------------------------------------------------------------------
    # Audit-logging via sys_event
    # ------------------------------------------------------------------

    def _log_call(self, env, name, arguments):
        try:
            # Korte args-summary, geen volledige payload
            summary = ', '.join(
                f'{k}={self._short(v)}' for k, v in (arguments or {}).items()
            ) or '(no args)'
            env['myschool.sys.event.service'].sudo().create_sys_event(
                'MCP-CALL',
                f'tool={name} user={env.user.login} args={summary}',
                False, source='MCP')
        except Exception:
            _logger.exception('MCP: sys_event logging faalde')

    def _log_error(self, env, name, message):
        try:
            env['myschool.sys.event.service'].sudo().create_sys_error(
                'MCP-ERROR',
                f'tool={name} user={env.user.login} error={message}',
                'ERROR-NONBLOCKING', False, source='MCP')
        except Exception:
            _logger.exception('MCP: sys_event error-logging faalde')

    @staticmethod
    def _short(value):
        s = str(value)
        return s if len(s) <= 80 else s[:77] + '...'
