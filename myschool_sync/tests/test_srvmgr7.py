from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'myschool_sync')
class TestSrvMgr7Migration(TransactionCase):
    """SRVMGR-7: sync-beheer verhuisd naar Server Manager.

    Dekt de koppeling sync.target ↔ myschool.server, de instance-globale
    sync-config en het herhuisvesten van het Sync-menu onder Server Manager.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Server = cls.env['myschool.server']
        cls.Target = cls.env['sync.target']
        cls.ICP = cls.env['ir.config_parameter'].sudo()

    def test_server_target_link(self):
        server = self.Server.create({'name': 'srv-01'})
        target = self.Target.create({
            'name': 'Slave A', 'url': 'https://slave-a.example.com',
            'api_key': 'secret', 'server_id': server.id})
        self.assertIn(target, server.sync_target_ids)
        self.assertEqual(server.sync_target_count, 1)

    def test_server_target_link_optional(self):
        # server_id is optioneel — sync.target blijft werken zonder server.
        target = self.Target.create({
            'name': 'Slave B', 'url': 'https://slave-b.example.com',
            'api_key': 'secret'})
        self.assertFalse(target.server_id)

    def test_server_unlink_sets_null(self):
        # ondelete='set null' — een target overleeft het verwijderen van z'n server.
        server = self.Server.create({'name': 'srv-02'})
        target = self.Target.create({
            'name': 'Slave C', 'url': 'https://slave-c.example.com',
            'api_key': 'secret', 'server_id': server.id})
        server.unlink()
        self.assertFalse(target.server_id)
        self.assertTrue(target.exists())

    def test_action_open_sync_targets_domain(self):
        server = self.Server.create({'name': 'srv-03'})
        self.Target.create({
            'name': 'Slave D', 'url': 'https://slave-d.example.com',
            'api_key': 'secret', 'server_id': server.id})
        action = server.action_open_sync_targets()
        self.assertEqual(action['res_model'], 'sync.target')
        self.assertIn(('server_id', '=', server.id), action['domain'])

    def test_sync_settings_roundtrip(self):
        settings = self.env['res.config.settings'].create({
            'myschool_sync_role': 'master',
            'myschool_sync_api_key': 'shared-secret',
        })
        settings.set_values()
        self.assertEqual(self.ICP.get_param('myschool.sync_role'), 'master')
        self.assertEqual(self.ICP.get_param('myschool.sync_api_key'), 'shared-secret')

    def test_sync_menu_under_servermanager(self):
        menu = self.env.ref('myschool_sync.menu_myschool_sync_root')
        root = self.env.ref('myschool_servermanager.myschool_servermanager_menu_root')
        self.assertEqual(menu.parent_id, root)
