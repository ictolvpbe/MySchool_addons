from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

_PATH = ('odoo.addons.myschool_servermanager.models.server_enrollment'
         '.MyschoolServer._jsonrpc')

# xmlid -> res_id zoals de fake-remote ze "kent"
_XMLIDS = {('base', 'group_user'): 1, ('base', 'group_system'): 3}


class FakeProvisionRemote:
    """In-memory remote voor de provisioning-tests (SRVMGR-6).

    Simuleert res.company, res.users en ir.model.data en legt alle execute_kw-
    aanroepen vast in ``calls``. ``next_uid`` telt aangemaakte gebruikers door.
    """

    def __init__(self, company_name='YourCompany', users=None, uid=7):
        self.company_name = company_name
        # login -> id
        self.users = dict(users or {})
        self.uid = uid
        self.calls = []
        self._next_id = 100

    def __call__(self, service, method, args):
        if service == 'common' and method == 'authenticate':
            return self.uid
        if service == 'object' and method == 'execute_kw':
            model, m, margs = args[3], args[4], args[5]
            self.calls.append((model, m, margs))
            return self._dispatch(model, m, margs)
        raise AssertionError(f'onverwachte call {service}.{method}')

    def _dispatch(self, model, method, margs):
        if model == 'res.company':
            return self._company(method, margs)
        if model == 'res.users':
            return self._users(method, margs)
        if model == 'ir.model.data':
            return self._imd(method, margs)
        raise AssertionError(f'onverwacht model {model}')

    def _company(self, method, margs):
        if method == 'search':
            return [1]
        if method == 'read':
            return [{'id': 1, 'name': self.company_name}]
        if method == 'write':
            self.company_name = margs[1]['name']
            return True
        raise AssertionError(method)

    def _users(self, method, margs):
        if method == 'search':
            login = margs[0][0][2]  # [['login','=',x]]
            return [self.users[login]] if login in self.users else []
        if method == 'create':
            vals = margs[0]
            self._next_id += 1
            self.users[vals['login']] = self._next_id
            return self._next_id
        raise AssertionError(method)

    def _imd(self, method, margs):
        if method == 'search_read':
            domain = margs[0]
            module = domain[0][2]
            name = domain[1][2]
            rid = _XMLIDS.get((module, name))
            return [{'res_id': rid}] if rid else []
        raise AssertionError(method)


@tagged('post_install', '-at_install', 'myschool_servermanager')
class TestProvision(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Server = cls.env['myschool.server']
        cls.Role = cls.env['myschool.server.role']

    def _make_server(self, users=None, company_name=None):
        role = self.Role.create({'name': 'Account', 'code': 'acc'})
        for u in (users or []):
            self.env['myschool.server.provision.user'].create(
                dict(u, role_id=role.id))
        srv = self.Server.create({
            'name': 'acc01', 'environment': 'prod', 'fqdn': 'acc01.olvp.be',
            'db_name': 'acc', 'login': 'svc', 'api_key': 'k', 'role_id': role.id,
            'provision_company_name': company_name})
        return srv, role

    # ---------------- company ----------------

    def test_provision_renames_company_when_different(self):
        srv, _role = self._make_server(company_name='OLVP Brugge')
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'done')
        self.assertEqual(remote.company_name, 'OLVP Brugge')
        writes = [c for c in remote.calls
                  if c[0] == 'res.company' and c[1] == 'write']
        self.assertEqual(len(writes), 1)

    def test_provision_company_idempotent_when_equal(self):
        srv, _role = self._make_server(company_name='OLVP Brugge')
        remote = FakeProvisionRemote(company_name='OLVP Brugge')
        with patch(_PATH, new=remote):
            srv.action_provision()
        writes = [c for c in remote.calls
                  if c[0] == 'res.company' and c[1] == 'write']
        self.assertFalse(writes)
        self.assertIn("al 'OLVP Brugge'", srv.provision_log)

    def test_provision_skips_company_when_no_name(self):
        srv, _role = self._make_server()
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'done')
        self.assertFalse([c for c in remote.calls if c[0] == 'res.company'])

    # ---------------- users ----------------

    def test_provision_creates_missing_user_with_base_group(self):
        srv, _role = self._make_server(users=[
            {'name': 'Directie', 'login': 'directie', 'email': 'd@olvp.be'}])
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        creates = [c for c in remote.calls
                   if c[0] == 'res.users' and c[1] == 'create']
        self.assertEqual(len(creates), 1)
        vals = creates[0][2][0]
        self.assertEqual(vals['login'], 'directie')
        self.assertEqual(vals['email'], 'd@olvp.be')
        # base.group_user (res_id 1), geen admin
        self.assertEqual(vals['group_ids'], [(6, 0, [1])])

    def test_provision_admin_user_gets_admin_group(self):
        srv, _role = self._make_server(users=[
            {'name': 'Beheerder', 'login': 'beheer', 'is_admin': True}])
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        vals = [c for c in remote.calls
                if c[0] == 'res.users' and c[1] == 'create'][0][2][0]
        self.assertEqual(vals['group_ids'], [(6, 0, [1, 3])])
        self.assertIn('administrator', srv.provision_log)

    def test_provision_skips_existing_user(self):
        srv, _role = self._make_server(users=[
            {'name': 'Directie', 'login': 'directie'}])
        remote = FakeProvisionRemote(users={'directie': 42})
        with patch(_PATH, new=remote):
            srv.action_provision()
        creates = [c for c in remote.calls
                   if c[0] == 'res.users' and c[1] == 'create']
        self.assertFalse(creates)
        self.assertIn("bestaat al", srv.provision_log)

    def test_provision_is_idempotent(self):
        srv, _role = self._make_server(
            company_name='OLVP Brugge',
            users=[{'name': 'Directie', 'login': 'directie'}])
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()          # maakt company-write + user
            remote.calls.clear()
            srv.action_provision()          # tweede run: niets meer te doen
        self.assertFalse([c for c in remote.calls if c[1] in ('write', 'create')])

    def test_provision_error_persists_log(self):
        srv, _role = self._make_server(company_name='X')
        with patch(_PATH, new=FakeProvisionRemote(uid=False)):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'error')
        self.assertIn('FOUT', srv.provision_log)
