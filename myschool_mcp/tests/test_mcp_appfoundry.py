# -*- coding: utf-8 -*-
"""
Integratietests voor de MCP-server.

Test-strategie:
  * HTTP-laag via ``HttpCase`` (start een test Werkzeug-server).
  * Init/list/call met geldige + ongeldige API-keys.
  * Happy-path appfoundry-tools (list, get, set_stage, post_comment,
    create).
"""

import json

from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install', 'myschool_mcp')
class TestMcpAppfoundry(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Test-gebruiker met manager-rechten op appfoundry + MCP.
        cls.test_user = cls.env['res.users'].create({
            'name': 'MCP Test User',
            'login': 'mcp_test_user',
            'email': 'mcp@test.local',
            'groups_id': [(4, cls.env.ref(
                'myschool_appfoundry.group_appfoundry_manager').id),
                (4, cls.env.ref('myschool_mcp.group_mcp_user').id)],
        })

        # API-key voor de test-user (scope='rpc' zodat _check_credentials
        # met scope='rpc' hem accepteert). ``.with_user(...).sudo()``
        # zet env.user=test_user + env.su=True zodat
        # ``_check_expiration_date`` ons toelaat een persistent key
        # zonder einddatum aan te maken.
        cls.api_key_value = cls.env['res.users.apikeys'].with_user(
            cls.test_user).sudo()._generate(
                scope='rpc',
                name='MCP Test Key',
                expiration_date=False)

        # Project + huidige release voor item-tests.
        cls.project = cls.env['appfoundry.project'].with_user(
            cls.test_user).create({
                'name': 'MCP Test Project',
                'code': 'MCPT',
                'member_ids': [(4, cls.test_user.id)],
                'responsible_id': cls.test_user.id,
            })
        # create() maakt automatisch een release; haal hem op
        cls.release = cls.project.current_release_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _post(self, body, api_key=None):
        headers = {'Content-Type': 'application/json'}
        if api_key is not None:
            headers['X-API-Key'] = api_key
        return self.url_open(
            '/mcp', data=json.dumps(body).encode('utf-8'),
            headers=headers, timeout=30)

    def _call_tool(self, tool_name, arguments, api_key=None):
        if api_key is None:
            api_key = self.api_key_value
        resp = self._post({
            'jsonrpc': '2.0', 'id': 99, 'method': 'tools/call',
            'params': {'name': tool_name, 'arguments': arguments},
        }, api_key=api_key)
        self.assertEqual(resp.status_code, 200,
                         f'tool {tool_name!r} HTTP {resp.status_code}: {resp.text}')
        body = resp.json()
        if 'error' in body:
            self.fail(f'tool {tool_name!r} returned error: {body["error"]}')
        return json.loads(body['result']['content'][0]['text'])

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def test_initialize_returns_capabilities(self):
        resp = self._post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('result', body)
        self.assertIn('protocolVersion', body['result'])
        self.assertIn('tools', body['result']['capabilities'])
        self.assertEqual(body['result']['serverInfo']['name'], 'myschool-mcp')

    def test_unauthenticated_tools_call_returns_401(self):
        resp = self._post({
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'appfoundry_list_projects', 'arguments': {}},
        })  # geen X-API-Key
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertIn('error', body)
        self.assertEqual(body['error']['code'], -32001)

    def test_tools_list_includes_appfoundry(self):
        resp = self._post({
            'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list',
        }, api_key=self.api_key_value)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        names = [t['name'] for t in body['result']['tools']]
        for expected in ('appfoundry_list_projects',
                         'appfoundry_list_my_items',
                         'appfoundry_get_item',
                         'appfoundry_set_stage',
                         'appfoundry_post_comment',
                         'appfoundry_create_item'):
            self.assertIn(expected, names,
                          f'missing tool {expected!r} in tools/list')

    def test_unknown_tool_returns_method_not_found(self):
        resp = self._post({
            'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
            'params': {'name': 'does_not_exist', 'arguments': {}},
        }, api_key=self.api_key_value)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('error', body)
        # Unknown tool wordt door de registry als -32601 teruggegeven
        self.assertEqual(body['error']['code'], -32601)

    # ------------------------------------------------------------------
    # AppFoundry tools — happy path
    # ------------------------------------------------------------------

    def test_list_my_items_filters_by_user(self):
        # Voor de test-user nog niets toegewezen — verwacht lege lijst.
        result = self._call_tool('appfoundry_list_my_items', {})
        self.assertEqual(result, [],
                         'list_my_items should be empty for fresh user')

        # Maak een item aan en wijs toe.
        item = self.env['appfoundry.item'].with_user(self.test_user).create({
            'name': 'Test story',
            'project_id': self.project.id,
            'release_id': self.release.id,
            'assigned_id': self.test_user.id,
            'item_type': 'story',
        })
        result = self._call_tool('appfoundry_list_my_items', {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], item.id)
        self.assertIn(self.project.code, result[0]['display_name'])

    def test_create_item_validates_project_and_assigns(self):
        result = self._call_tool('appfoundry_create_item', {
            'project': 'MCPT',
            'name': 'Created via MCP',
            'item_type': 'task',
            'description': 'Hello **world**',
            'assign_to_me': True,
            'tag_names': ['mcp-test'],
        })
        self.assertEqual(result['name'], 'Created via MCP')
        self.assertEqual(result['item_type'], 'task')
        self.assertEqual(result['assigned_login'], self.test_user.login)
        self.assertIn('mcp-test', result['tag_names'])
        self.assertIn('<strong>world</strong>', result['description_html'])

    def test_set_stage_writes_chatter_under_user(self):
        item = self.env['appfoundry.item'].with_user(self.test_user).create({
            'name': 'Stage test',
            'project_id': self.project.id,
            'release_id': self.release.id,
            'assigned_id': self.test_user.id,
        })
        result = self._call_tool('appfoundry_set_stage', {
            'item': item.id,
            'stage': 'In Review',
        })
        self.assertEqual(result['new_stage'], 'In Review')
        item.invalidate_recordset()
        self.assertEqual(item.stage_id.name, 'In Review')
        # Stage-tracking moet een chatter-entry hebben gemaakt
        messages = item.message_ids.filtered(
            lambda m: m.tracking_value_ids.filtered(
                lambda t: t.field_id.name == 'stage_id'))
        self.assertTrue(messages, 'expected a stage-change tracking message')

    def test_post_comment_attributes_to_calling_user(self):
        item = self.env['appfoundry.item'].with_user(self.test_user).create({
            'name': 'Comment test',
            'project_id': self.project.id,
            'release_id': self.release.id,
        })
        result = self._call_tool('appfoundry_post_comment', {
            'item': item.id,
            'body': 'Working on this. **Done by EOD.**\n\n- step 1\n- step 2',
        })
        self.assertIn('message_id', result)
        msg = self.env['mail.message'].browse(result['message_id'])
        self.assertEqual(msg.author_id, self.test_user.partner_id)
        body_text = (msg.body or '')
        self.assertIn('<strong>Done by EOD.</strong>', body_text)
        self.assertIn('<li>step 1</li>', body_text)
