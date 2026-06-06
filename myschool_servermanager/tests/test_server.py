from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'myschool_servermanager')
class TestServerModel(TransactionCase):
    """Unit tests voor het myschool.server(.role/.property) datamodel:
    eigenschap-overerving via de rol, unieke codes/FQDN en poort-constraint.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Server = cls.env['myschool.server']
        cls.Role = cls.env['myschool.server.role']
        cls.Prop = cls.env['myschool.server.property']

    # ---------------- rol samengesteld uit eigenschappen ----------------

    def test_effective_properties_inherited_from_role(self):
        p1 = self.Prop.create({'name': 'Host webapps', 'code': 'host_webapps'})
        p2 = self.Prop.create({'name': 'API aanbieden', 'code': 'offer_api'})
        role = self.Role.create({
            'name': 'Webapps server', 'code': 'webapps',
            'property_ids': [(6, 0, (p1 | p2).ids)],
        })
        srv = self.Server.create({
            'name': 'srvv-web-01', 'environment': 'prod', 'role_id': role.id})
        self.assertEqual(srv.property_ids, p1 | p2)

    def test_property_change_propagates_to_server(self):
        p1 = self.Prop.create({'name': 'A', 'code': 'a'})
        p2 = self.Prop.create({'name': 'B', 'code': 'b'})
        role = self.Role.create({
            'name': 'R', 'code': 'r', 'property_ids': [(6, 0, p1.ids)]})
        srv = self.Server.create({
            'name': 's', 'environment': 'dev', 'role_id': role.id})
        self.assertEqual(srv.property_ids, p1)
        role.property_ids = [(6, 0, (p1 | p2).ids)]
        srv.invalidate_recordset()
        self.assertEqual(srv.property_ids, p1 | p2)

    def test_role_counts(self):
        p1 = self.Prop.create({'name': 'A', 'code': 'a'})
        role = self.Role.create({
            'name': 'R', 'code': 'r', 'property_ids': [(6, 0, p1.ids)]})
        self.Server.create({'name': 's1', 'environment': 'dev', 'role_id': role.id})
        self.Server.create({'name': 's2', 'environment': 'test', 'role_id': role.id})
        role.invalidate_recordset()
        self.assertEqual(role.property_count, 1)
        self.assertEqual(role.server_count, 2)
        p1.invalidate_recordset()
        self.assertEqual(p1.role_count, 1)

    # ---------------- constraints ----------------

    def test_fqdn_must_be_unique(self):
        self.Server.create({
            'name': 's1', 'environment': 'prod', 'fqdn': 'host.olvp.be'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Server.create({
                'name': 's2', 'environment': 'test', 'fqdn': 'host.olvp.be'})

    def test_server_code_must_be_unique(self):
        self.Server.create({'name': 's1', 'environment': 'prod', 'code': 'X'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Server.create({'name': 's2', 'environment': 'test', 'code': 'X'})

    def test_invalid_port_rejected(self):
        with self.assertRaises(ValidationError):
            self.Server.create({
                'name': 's', 'environment': 'dev', 'http_port': 70000})

    def test_property_code_must_be_unique(self):
        self.Prop.create({'name': 'A', 'code': 'dup'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Prop.create({'name': 'B', 'code': 'dup'})
