# -*- coding: utf-8 -*-
"""
MCP Tool Registry — centrale plek waar providers hun tools registreren.

Gebruik:

    from odoo.addons.myschool_mcp.models.mcp_registry import McpRegistry

    @McpRegistry.tool(
        name='appfoundry_list_my_items',
        description='List items assigned to the calling user',
        input_schema={
            'type': 'object',
            'properties': {
                'project_code': {'type': 'string'},
                'open_only': {'type': 'boolean', 'default': True},
            },
        },
        required_group='myschool_appfoundry.group_appfoundry_user',
    )
    def list_my_items(env, project_code=None, open_only=True):
        ...
        return [...]

De controller importeert ``providers`` (waardoor de decorators runnen) en
roept dan ``McpRegistry.list_tools()`` of ``McpRegistry.call(...)`` aan.
"""

import logging
import time
from collections import defaultdict, deque
from threading import Lock

from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class McpToolError(Exception):
    """Voor handlers die een nette JSON-RPC fout willen teruggeven zonder
    de algemene exception-handler te triggeren."""

    def __init__(self, message, code=-32000):
        super().__init__(message)
        self.code = code


class _RateLimiter:
    """In-memory sliding-window rate-limit per user.

    Niet bedoeld als security-laag — alleen om runaway-loops te
    dempen. Geheugen lekt licht (één deque per ooit-actieve user);
    voor onze schaal (handvol developers) onbelangrijk.
    """

    def __init__(self, max_calls=60, window_seconds=60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls = defaultdict(deque)
        self._lock = Lock()

    def check(self, user_id):
        now = time.monotonic()
        with self._lock:
            q = self._calls[user_id]
            # Verwijder vervallen entries
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.max_calls:
                return False
            q.append(now)
            return True

    def configure(self, max_calls, window_seconds=60):
        with self._lock:
            self.max_calls = max_calls
            self.window = window_seconds


# Singleton rate-limiter; configurable via res.config.settings.
_rate_limiter = _RateLimiter(max_calls=60, window_seconds=60)


def get_rate_limiter():
    return _rate_limiter


class McpRegistry:
    """Singleton: houdt alle geregistreerde tools bij."""

    # name -> dict(handler, description, input_schema, required_group)
    _tools = {}

    @classmethod
    def tool(cls, name, description, input_schema=None, required_group=None):
        """Decorator om een Python-functie als MCP-tool te registreren.

        :param name: globaal-unieke tool-naam (prefix per module, bv. ``appfoundry_*``)
        :param description: korte beschrijving — wordt naar de AI-client gestuurd
        :param input_schema: JSON-Schema dict (object). None ⇒ geen args.
        :param required_group: XML-id van een res.groups die de gebruiker moet
            hebben; ``None`` ⇒ enkel ``group_mcp_user`` is vereist.
        """
        def decorator(fn):
            if name in cls._tools:
                _logger.warning(
                    "MCP-tool %r dubbel-geregistreerd — laatste registratie wint",
                    name)
            cls._tools[name] = {
                'handler': fn,
                'description': description,
                'input_schema': input_schema or {
                    'type': 'object', 'properties': {}},
                'required_group': required_group,
            }
            return fn
        return decorator

    @classmethod
    def list_tools(cls):
        """Geef de tool-lijst terug in MCP-formaat."""
        out = []
        for name, meta in sorted(cls._tools.items()):
            out.append({
                'name': name,
                'description': meta['description'],
                'inputSchema': meta['input_schema'],
            })
        return out

    @classmethod
    def call(cls, env, name, arguments):
        """Roep een tool aan in de naam van ``env.user``.

        :return: Python-resultaat (wordt door de controller naar
            MCP ``content``-structuur ge-wrapped).
        :raises McpToolError: voor expliciete tool-fouten (worden
            ge-mapt naar JSON-RPC errors).
        """
        meta = cls._tools.get(name)
        if not meta:
            raise McpToolError(f"Unknown tool: {name}", code=-32601)

        # Group check
        required_group = meta.get('required_group')
        if required_group and not env.user.has_group(required_group):
            raise McpToolError(
                f"Access denied: tool {name!r} requires group {required_group}",
                code=-32003,
            )

        # Rate limit
        if not _rate_limiter.check(env.user.id):
            raise McpToolError(
                f"Rate limit exceeded ({_rate_limiter.max_calls}/"
                f"{_rate_limiter.window}s). Try again in a moment.",
                code=-32002,
            )

        # Validatie van top-level type — geen volledige JSON-Schema
        # implementatie (niet nodig voor onze tools), maar wel een
        # check dat we een object kregen.
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise McpToolError(
                f"Tool arguments must be an object, got {type(arguments).__name__}",
                code=-32602,
            )

        # Vul defaults uit het schema (lichte heuristiek)
        schema = meta.get('input_schema') or {}
        for key, prop in (schema.get('properties') or {}).items():
            if key not in arguments and 'default' in prop:
                arguments[key] = prop['default']

        try:
            result = meta['handler'](env, **arguments)
        except McpToolError:
            raise
        except AccessError as e:
            raise McpToolError(f"Access error: {e}", code=-32003)
        except (UserError, ValidationError) as e:
            raise McpToolError(f"Validation error: {e}", code=-32004)
        except TypeError as e:
            # Mist een verplicht argument of onbekend kwarg
            raise McpToolError(f"Invalid arguments: {e}", code=-32602)
        except Exception as e:
            _logger.exception("MCP tool %r faalde", name)
            raise McpToolError(f"Internal error: {e}", code=-32603)

        return result

    @classmethod
    def has_tool(cls, name):
        return name in cls._tools

    @classmethod
    def _reset_for_tests(cls):
        cls._tools = {}
