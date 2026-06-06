from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'myschool_servermanager')
class TestDataLocation(TransactionCase):
    """Unit tests voor de data-locatie/privacy-matrix (SRVMGR-4)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Server = cls.env['myschool.server']
        cls.Domain = cls.env['myschool.data.domain']
        cls.Loc = cls.env['myschool.server.data.location']
        cls.s1 = cls.Server.create({'name': 'web', 'environment': 'prod'})
        cls.s2 = cls.Server.create({'name': 'account', 'environment': 'prod'})
        cls.pii = cls.Domain.create({'name': 'PII', 'code': 'pii', 'is_pii': True})
        cls.orgs = cls.Domain.create({'name': 'Org', 'code': 'org'})

    def test_local_location_ok(self):
        loc = self.Loc.create({
            'server_id': self.s1.id, 'domain_id': self.orgs.id, 'location': 'local'})
        self.assertFalse(loc.source_server_id)

    def test_remote_requires_source(self):
        with self.assertRaises(ValidationError):
            self.Loc.create({
                'server_id': self.s1.id, 'domain_id': self.pii.id,
                'location': 'remote'})

    def test_remote_source_must_differ(self):
        with self.assertRaises(ValidationError):
            self.Loc.create({
                'server_id': self.s1.id, 'domain_id': self.pii.id,
                'location': 'remote', 'source_server_id': self.s1.id})

    def test_remote_ok_and_pii_related(self):
        loc = self.Loc.create({
            'server_id': self.s1.id, 'domain_id': self.pii.id,
            'location': 'remote', 'source_server_id': self.s2.id})
        self.assertTrue(loc.is_pii)
        self.assertEqual(loc.source_server_id, self.s2)

    def test_unique_domain_per_server(self):
        self.Loc.create({
            'server_id': self.s1.id, 'domain_id': self.orgs.id, 'location': 'local'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Loc.create({
                'server_id': self.s1.id, 'domain_id': self.orgs.id,
                'location': 'local'})

    def test_server_counts(self):
        self.Loc.create({
            'server_id': self.s1.id, 'domain_id': self.orgs.id, 'location': 'local'})
        self.Loc.create({
            'server_id': self.s1.id, 'domain_id': self.pii.id,
            'location': 'remote', 'source_server_id': self.s2.id})
        self.s1.invalidate_recordset()
        self.assertEqual(self.s1.data_location_count, 2)
        self.assertEqual(self.s1.remote_data_count, 1)

    def test_domain_code_unique(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Domain.create({'name': 'Dup', 'code': 'pii'})
