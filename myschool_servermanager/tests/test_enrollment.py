from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

_PATH = ('odoo.addons.myschool_servermanager.models.server_enrollment'
         '.MyschoolServer._jsonrpc')


class FakeRemote:
    """In-memory simulatie van een remote Odoo voor de enroll-tests.

    Houdt module-states bij en beantwoordt de JSON-RPC-calls die de
    enrollment-laag uitvoert. ``calls`` legt alle execute_kw-aanroepen vast.
    """

    def __init__(self, modules=None, langs=None, has_admin=True, uid=7):
        # naam -> (id, state)
        self.modules = modules or {}
        # code -> active
        self.langs = langs or {}
        self.has_admin = has_admin
        self.uid = uid
        self.calls = []

    def __call__(self, service, method, args):
        if service == 'common' and method == 'authenticate':
            return self.uid
        if service == 'object' and method == 'execute_kw':
            model, m, margs = args[3], args[4], args[5]
            self.calls.append((model, m, margs))
            return self._dispatch(model, m, margs)
        raise AssertionError(f'onverwachte call {service}.{method}')

    def _dispatch(self, model, method, margs):
        if model == 'ir.module.module':
            return self._modules(method, margs)
        if model == 'res.lang':
            return self._langs(method, margs)
        if model == 'res.users':
            return self._users(method, margs)
        raise AssertionError(f'onverwacht model {model}')

    def _modules(self, method, margs):
        if method == 'search':
            wanted = margs[0][0][2]  # [['name','in',[...]]]
            return [self.modules[n][0] for n in wanted if n in self.modules]
        if method == 'read':
            ids = margs[0]
            by_id = {v[0]: (n, v[1]) for n, v in self.modules.items()}
            return [{'id': i, 'name': by_id[i][0], 'state': by_id[i][1]}
                    for i in ids]
        if method == 'button_immediate_install':
            ids = margs[0]
            for n, (i, _state) in list(self.modules.items()):
                if i in ids:
                    self.modules[n] = (i, 'installed')
            return True
        raise AssertionError(method)

    def _langs(self, method, margs):
        if method == 'search':
            code = margs[0][0][2]
            return [1] if code in self.langs else []
        if method == 'read':
            code = next(iter(self.langs))
            return [{'id': 1, 'active': self.langs[code]}]
        if method == 'write':
            for code in self.langs:
                self.langs[code] = True
            return True
        raise AssertionError(method)

    def _users(self, method, margs):
        if method == 'search':
            return [2] if self.has_admin else []
        if method == 'write':
            return True
        raise AssertionError(method)


@tagged('post_install', '-at_install', 'myschool_servermanager')
class TestEnrollment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Server = cls.env['myschool.server']
        cls.Role = cls.env['myschool.server.role']
        cls.Prop = cls.env['myschool.server.property']

    def _make_server(self, **role_kw):
        p1 = self.Prop.create({
            'name': 'Assets', 'code': 'assets', 'module_names': 'myschool_assets'})
        p2 = self.Prop.create({
            'name': 'Sync', 'code': 'sync', 'module_names': 'myschool_sync'})
        role = self.Role.create({
            'name': 'Webapps', 'code': 'web',
            'property_ids': [(6, 0, (p1 | p2).ids)], **role_kw})
        srv = self.Server.create({
            'name': 'web01', 'environment': 'prod', 'fqdn': 'web01.olvp.be',
            'db_name': 'web', 'login': 'svc', 'api_key': 'k', 'role_id': role.id})
        return srv, role

    # ---------------- config ----------------

    def test_collect_module_names_dedup_and_union(self):
        _srv, role = self._make_server()
        self.assertEqual(role._collect_module_names(),
                         ['myschool_assets', 'myschool_sync'])
        self.assertEqual(role.enroll_module_names,
                         'myschool_assets,myschool_sync')

    # ---------------- connectie ----------------

    def test_connection_ok(self):
        srv, _role = self._make_server()
        with patch(_PATH, new=FakeRemote()):
            srv.action_test_connection()
        self.assertEqual(srv.connection_state, 'ok')
        self.assertTrue(srv.last_connection_check)

    def test_connection_error_when_auth_refused(self):
        srv, _role = self._make_server()
        with patch(_PATH, new=FakeRemote(uid=False)):
            srv.action_test_connection()
        self.assertEqual(srv.connection_state, 'error')

    # ---------------- enroll ----------------

    def test_enroll_installs_only_missing_modules(self):
        srv, _role = self._make_server()
        remote = FakeRemote(modules={
            'myschool_assets': (10, 'uninstalled'),
            'myschool_sync': (11, 'installed'),
        })
        with patch(_PATH, new=remote):
            srv.action_enroll()
        self.assertEqual(srv.enrollment_state, 'done')
        self.assertTrue(srv.last_enrolled)
        installs = [c for c in remote.calls if c[1] == 'button_immediate_install']
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][2][0], [10])  # alleen de ontbrekende
        self.assertIn('myschool_assets', srv.enrollment_log)

    def test_enroll_is_idempotent(self):
        srv, _role = self._make_server()
        remote = FakeRemote(modules={
            'myschool_assets': (10, 'uninstalled'),
            'myschool_sync': (11, 'installed'),
        })
        with patch(_PATH, new=remote):
            srv.action_enroll()        # installeert assets
            remote.calls.clear()
            srv.action_enroll()        # tweede run: niets meer te doen
        installs = [c for c in remote.calls if c[1] == 'button_immediate_install']
        self.assertFalse(installs)
        self.assertIn('Geen nieuwe modules', srv.enrollment_log)

    def test_enroll_activates_language(self):
        srv, _role = self._make_server(enroll_lang='nl_BE')
        remote = FakeRemote(langs={'nl_BE': False})
        with patch(_PATH, new=remote):
            srv.action_enroll()
        self.assertTrue(remote.langs['nl_BE'])
        self.assertIn('geactiveerd', srv.enrollment_log)

    def test_enroll_sets_and_clears_admin_password(self):
        srv, _role = self._make_server()
        srv.target_admin_password = 'secret'
        remote = FakeRemote()
        with patch(_PATH, new=remote):
            srv.action_enroll()
        self.assertEqual(srv.enrollment_state, 'done')
        self.assertFalse(srv.target_admin_password)
        pw_writes = [c for c in remote.calls
                     if c[0] == 'res.users' and c[1] == 'write']
        self.assertEqual(len(pw_writes), 1)

    def test_enroll_error_persists_log(self):
        srv, _role = self._make_server()
        with patch(_PATH, new=FakeRemote(uid=False)):
            srv.action_enroll()
        self.assertEqual(srv.enrollment_state, 'error')
        self.assertIn('FOUT', srv.enrollment_log)
