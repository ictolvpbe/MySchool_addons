# -*- coding: utf-8 -*-
"""Tests voor myschool.ldap.server.config — focus op dupliceren.

Het model bewaakt "max. één actieve config per omgeving" (constraint +
create/write die de bestaande actieve archiveren). Een naïeve ``copy()``
erfde ``active=True`` over en archiveerde daardoor stil het origineel bij het
dupliceren. ``copy_data`` zet de kopie nu inactief met een eigen naam, zodat
de bron ongemoeid blijft.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLdapServerConfigCopy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Cfg = cls.env['myschool.ldap.server.config']
        cls.base_vals = {
            'server_url': 'dc01.olvp.int',
            'base_dn': 'DC=olvp,DC=int',
            'bind_dn': 'CN=bind,DC=olvp,DC=int',
            'bind_password': 'pw',
        }

    def _make(self, **extra):
        return self.Cfg.create({'name': 'Prod-AD', 'environment': 'prod',
                                **self.base_vals, **extra})

    def test_duplicate_is_inactive_and_keeps_source_active(self):
        """Dupliceren mag het actieve origineel niet archiveren."""
        src = self._make()
        self.assertTrue(src.active)

        copy = src.copy()

        self.assertFalse(copy.active,
                         'Een kopie moet inactief zijn (single-active-per-env).')
        self.assertTrue(src.active,
                        'Het origineel moet actief blijven na dupliceren.')
        self.assertNotEqual(copy.name, src.name,
                            'De kopie moet een eigen naam krijgen.')
        self.assertIn('kopie', copy.name)

    def test_duplicate_respects_explicit_name_default(self):
        """Een expliciete naam in default wint van de (kopie)-suffix."""
        src = self._make()
        copy = src.copy({'name': 'Test-AD'})
        self.assertEqual(copy.name, 'Test-AD')
        self.assertFalse(copy.active)

    def test_activating_copy_archives_original(self):
        """Bewust activeren van de kopie archiveert het oude actieve (by design)."""
        src = self._make()
        copy = src.copy()
        copy.active = True
        self.assertTrue(copy.active)
        self.assertFalse(src.active,
                         'Activeren van de kopie hoort het oude actieve te archiveren.')
