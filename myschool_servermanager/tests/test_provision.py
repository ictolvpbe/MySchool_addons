from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

_PATH = ('odoo.addons.myschool_servermanager.models.server_enrollment'
         '.MyschoolServer._jsonrpc')

# xmlid -> res_id zoals de fake-remote ze "kent"
_XMLIDS = {('base', 'group_user'): 1, ('base', 'group_system'): 3}


class FakeProvisionRemote:
    """In-memory remote voor de provisioning-tests (SRVMGR-6).

    Simuleert res.company (incl. parent_id), res.users en ir.model.data en legt
    alle execute_kw-aanroepen vast in ``calls``. De remote start met één
    hoofd-company (id 1).
    """

    def __init__(self, company_name='YourCompany', users=None, companies=None,
                 uid=7):
        # id -> {'name', 'parent_id'}
        self.companies = companies or {1: {'name': company_name, 'parent_id': False}}
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
            domain = margs[0]
            if not domain:                       # [[]] -> hoofd-company (laagste id)
                return [min(self.companies)] if self.companies else []
            name = domain[0][2]                  # [['name','=',x]]
            return [cid for cid, c in self.companies.items() if c['name'] == name]
        if method == 'read':
            ids = margs[0]
            return [{'id': i, 'name': self.companies[i]['name']} for i in ids]
        if method == 'write':
            ids, vals = margs[0], margs[1]
            for i in ids:
                self.companies[i].update(vals)
            return True
        if method == 'create':
            vals = margs[0]
            self._next_id += 1
            self.companies[self._next_id] = {
                'name': vals['name'], 'parent_id': vals.get('parent_id', False)}
            return self._next_id
        raise AssertionError(method)

    def _users(self, method, margs):
        if method == 'search':
            login = margs[0][0][2]               # [['login','=',x]]
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
            module, name = domain[0][2], domain[1][2]
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
        cls.Company = cls.env['myschool.server.provision.company']

    def _make_server(self, users=None, companies=None):
        role = self.Role.create({'name': 'Account', 'code': 'acc'})
        for u in (users or []):
            self.env['myschool.server.provision.user'].create(
                dict(u, role_id=role.id))
        srv = self.Server.create({
            'name': 'acc01', 'environment': 'prod', 'fqdn': 'acc01.olvp.be',
            'db_name': 'acc', 'login': 'svc', 'api_key': 'k', 'role_id': role.id})
        by_name = {}
        for c in (companies or []):
            vals = {'server_id': srv.id, 'name': c['name'],
                    'is_main': c.get('is_main', False)}
            if c.get('parent_name'):
                vals['parent_id'] = by_name[c['parent_name']].id
            by_name[c['name']] = self.Company.create(vals)
        return srv, role

    def _creates(self, remote, model):
        return [c for c in remote.calls if c[0] == model and c[1] == 'create']

    # ---------------- company ----------------

    def test_provision_renames_main_company_when_different(self):
        srv, _role = self._make_server(
            companies=[{'name': 'OLVP Brugge', 'is_main': True}])
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'done')
        self.assertEqual(remote.companies[1]['name'], 'OLVP Brugge')
        writes = [c for c in remote.calls
                  if c[0] == 'res.company' and c[1] == 'write']
        self.assertEqual(len(writes), 1)

    def test_provision_main_company_idempotent_when_equal(self):
        srv, _role = self._make_server(
            companies=[{'name': 'OLVP Brugge', 'is_main': True}])
        remote = FakeProvisionRemote(company_name='OLVP Brugge')
        with patch(_PATH, new=remote):
            srv.action_provision()
        writes = [c for c in remote.calls
                  if c[0] == 'res.company' and c[1] == 'write']
        self.assertFalse(writes)
        self.assertIn("Hoofd-company al 'OLVP Brugge'", srv.provision_log)

    def test_provision_skips_companies_when_none(self):
        srv, _role = self._make_server()
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'done')
        self.assertFalse([c for c in remote.calls if c[0] == 'res.company'])
        self.assertIn("Geen companies", srv.provision_log)

    def test_provision_creates_subcompany_under_main(self):
        srv, _role = self._make_server(companies=[
            {'name': 'OLVP Brugge', 'is_main': True},
            {'name': 'OLVP SO', 'parent_name': 'OLVP Brugge'}])
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()
        creates = self._creates(remote, 'res.company')
        self.assertEqual(len(creates), 1)
        vals = creates[0][2][0]
        self.assertEqual(vals['name'], 'OLVP SO')
        self.assertEqual(vals['parent_id'], 1)        # = hernoemde hoofd-company

    def test_provision_creates_deep_hierarchy_parents_first(self):
        srv, _role = self._make_server(companies=[
            {'name': 'Root', 'is_main': True},
            {'name': 'Child', 'parent_name': 'Root'},
            {'name': 'Grandchild', 'parent_name': 'Child'}])
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()
        creates = self._creates(remote, 'res.company')
        names = [c[2][0]['name'] for c in creates]
        self.assertEqual(names, ['Child', 'Grandchild'])   # parent vóór kind
        child_vals = [c[2][0] for c in creates if c[2][0]['name'] == 'Child'][0]
        gc_vals = [c[2][0] for c in creates if c[2][0]['name'] == 'Grandchild'][0]
        self.assertEqual(child_vals['parent_id'], 1)       # onder hoofd-company
        self.assertEqual(gc_vals['parent_id'], 101)        # onder Child (remote id 101)

    def test_provision_skips_existing_company(self):
        srv, _role = self._make_server(companies=[
            {'name': 'Bestaat', 'is_main': False}])
        remote = FakeProvisionRemote(companies={
            1: {'name': 'Main', 'parent_id': False},
            5: {'name': 'Bestaat', 'parent_id': False}})
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertFalse(self._creates(remote, 'res.company'))
        self.assertIn("Company 'Bestaat' bestaat al", srv.provision_log)

    # ---------------- users ----------------

    def test_provision_creates_missing_user_with_base_group(self):
        srv, _role = self._make_server(users=[
            {'name': 'Directie', 'login': 'directie', 'email': 'd@olvp.be'}])
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        creates = self._creates(remote, 'res.users')
        self.assertEqual(len(creates), 1)
        vals = creates[0][2][0]
        self.assertEqual(vals['login'], 'directie')
        self.assertEqual(vals['email'], 'd@olvp.be')
        self.assertEqual(vals['group_ids'], [(6, 0, [1])])

    def test_provision_admin_user_gets_admin_group(self):
        srv, _role = self._make_server(users=[
            {'name': 'Beheerder', 'login': 'beheer', 'is_admin': True}])
        remote = FakeProvisionRemote()
        with patch(_PATH, new=remote):
            srv.action_provision()
        vals = self._creates(remote, 'res.users')[0][2][0]
        self.assertEqual(vals['group_ids'], [(6, 0, [1, 3])])
        self.assertIn('administrator', srv.provision_log)

    def test_provision_skips_existing_user(self):
        srv, _role = self._make_server(users=[
            {'name': 'Directie', 'login': 'directie'}])
        remote = FakeProvisionRemote(users={'directie': 42})
        with patch(_PATH, new=remote):
            srv.action_provision()
        self.assertFalse(self._creates(remote, 'res.users'))
        self.assertIn("bestaat al", srv.provision_log)

    # ---------------- combinatie ----------------

    def test_provision_is_idempotent(self):
        srv, _role = self._make_server(
            companies=[{'name': 'OLVP Brugge', 'is_main': True},
                       {'name': 'OLVP SO', 'parent_name': 'OLVP Brugge'}],
            users=[{'name': 'Directie', 'login': 'directie'}])
        remote = FakeProvisionRemote(company_name='YourCompany')
        with patch(_PATH, new=remote):
            srv.action_provision()          # write main + create sub + create user
            remote.calls.clear()
            srv.action_provision()          # tweede run: niets meer te doen
        self.assertFalse([c for c in remote.calls if c[1] in ('write', 'create')])

    def test_provision_error_persists_log(self):
        srv, _role = self._make_server(
            companies=[{'name': 'X', 'is_main': True}])
        with patch(_PATH, new=FakeProvisionRemote(uid=False)):
            srv.action_provision()
        self.assertEqual(srv.provision_state, 'error')
        self.assertIn('FOUT', srv.provision_log)
