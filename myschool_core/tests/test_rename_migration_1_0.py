# -*- coding: utf-8 -*-
"""Tests voor de data-behoudende module/model-rename (myschool_core 1.0).

Dekt twee zaken:

1. Pure logica van de migratie-helper ``_apply_prefix`` en de volledigheid /
   consistentie van de rename-mappings (geen DB nodig).
2. Een registry-assertie (post_install): elk model dat in de mapping als
   "nieuw" staat moet in de geladen registry bestaan, en GEEN model met een
   oude prefix mag nog resolven. Zo vangen we drift: als iemand later een
   sub-model toevoegt onder een hernoemde module zonder de mapping te
   herzien, faalt deze test.

De migratie-functies zelf (SQL) zijn idempotent en draaien tegen de echte
test-DB; een volledige end-to-end migratie-test vergt een pre-rename fixture-DB
en valt buiten de unit-test-scope.
"""

import importlib.util
import os

from odoo.tests.common import TransactionCase, tagged

# Laad de pre-migrate module dynamisch (migrations/ zit niet op het importpad).
_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'migrations', '1.0', 'pre-migrate.py',
)
_spec = importlib.util.spec_from_file_location('pre_migrate_1_0', _MIG_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


@tagged('post_install', '-at_install', 'myschool_rename')
class TestRenameMigrationLogic(TransactionCase):

    def test_apply_prefix_renames_each_legacy_prefix(self):
        self.assertEqual(
            mig._apply_prefix('drukwerk.record'), 'myschool_drukwerk.record')
        self.assertEqual(
            mig._apply_prefix('activiteiten.snapshot.line'),
            'myschool_activiteiten.snapshot.line')
        self.assertEqual(
            mig._apply_prefix('professionalisering.address.picker'),
            'myschool_professionalisering.address.picker')

    def test_apply_prefix_leaves_unrelated_models_untouched(self):
        for model in ('res.users', 'myschool.person', 'mail.activity',
                      'myschool_core.letter.template'):
            self.assertEqual(mig._apply_prefix(model), model)

    def test_carpool_rel_is_not_renamed(self):
        # professionalisering_carpool_rel had in oud én nieuw een expliciete
        # relation-naam ZONDER prefix → mag NIET in de rename-map staan.
        self.assertNotIn(
            'professionalisering_carpool_rel', mig.M2M_TABLE_RENAMES)

    def test_m2m_map_values_have_new_prefix(self):
        for old, new in mig.M2M_TABLE_RENAMES.items():
            self.assertTrue(
                new.startswith('myschool_'),
                'rel-tabel %s -> %s mist myschool_-prefix' % (old, new))
            self.assertNotEqual(old, new)

    def test_module_map_complete(self):
        self.assertEqual(
            set(mig.MODULE_RENAMES.values()),
            {'myschool_drukwerk', 'myschool_activiteiten',
             'myschool_professionalisering'})


@tagged('post_install', '-at_install', 'myschool_rename')
class TestRenameRegistryState(TransactionCase):
    """Bewijst dat de registry na de rename consistent is met de mapping."""

    def test_new_models_present_and_old_absent(self):
        # Representatieve set hernoemde modellen die data dragen.
        new_models = [
            'myschool_drukwerk.record',
            'myschool_drukwerk.config',
            'myschool_drukwerk.audit.log',
            'myschool_activiteiten.record',
            'myschool_activiteiten.bus',
            'myschool_activiteiten.invite',
            'myschool_professionalisering.record',
            'myschool_professionalisering.address',
            'myschool_professionalisering.vak',
        ]
        for model in new_models:
            self.assertIn(
                model, self.env,
                'nieuw model %s ontbreekt in registry' % model)

        for old_prefix in mig.MODEL_PREFIX_RENAMES:
            stale = [m for m in self.env if m.startswith(old_prefix)]
            self.assertFalse(
                stale, 'oude model-namen nog in registry: %s' % stale)

    def test_no_mail_activity_points_to_legacy_model(self):
        # Direct de crash-conditie: mail_activity.res_model mag geen oude
        # prefix meer bevatten.
        self.env.cr.execute(
            "SELECT DISTINCT res_model FROM mail_activity "
            " WHERE res_model LIKE 'drukwerk.%' "
            "    OR res_model LIKE 'activiteiten.%' "
            "    OR res_model LIKE 'professionalisering.%'")
        rows = [r[0] for r in self.env.cr.fetchall()]
        self.assertFalse(
            rows, 'mail_activity verwijst nog naar oude modellen: %s' % rows)

    # Alle TEKST-model-kolommen die de sweep nu dekt. Per (tabel, kolom): NA
    # de migratie mag geen enkele waarde nog met een oude prefix beginnen.
    # ir_model_data.model en ir_model_fields.model waren de tweede crash-
    # oorzaak (KeyError 'professionalisering.vak' bij XML-herlaad).
    _TEXT_MODEL_COLUMNS = [
        ('ir_model_data', 'model'),
        ('ir_model_fields', 'model'),
        ('ir_model_fields', 'relation'),
        ('ir_filters', 'model_id'),
        ('ir_act_report_xml', 'model'),
        ('ir_act_window', 'res_model'),
        ('ir_act_client', 'res_model'),
        ('ir_embedded_actions', 'parent_res_model'),
        ('ir_ui_view', 'model'),
        ('ir_attachment', 'res_model'),
        ('mail_activity', 'res_model'),
        ('mail_activity_type', 'res_model'),
        ('mail_activity_plan', 'res_model'),
        ('mail_message', 'model'),
        ('mail_followers', 'res_model'),
        ('mail_message_subtype', 'res_model'),
        ('mail_template', 'model'),
        ('myschool_letter_template', 'model'),
    ]

    def _column_exists(self, table, column):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns "
            " WHERE table_schema = current_schema() "
            "   AND table_name = %s AND column_name = %s",
            (table, column))
        return bool(self.env.cr.fetchone())

    def test_no_text_column_points_to_legacy_model(self):
        # Uitputtende guard: scan élke gedekte tekst-model-kolom die fysiek
        # bestaat; geen enkele mag nog 'drukwerk.*' / 'activiteiten.*' /
        # 'professionalisering.*' (zonder myschool_-prefix) bevatten.
        offenders = {}
        for table, column in self._TEXT_MODEL_COLUMNS:
            if not self._column_exists(table, column):
                continue  # tabel/kolom afwezig in deze (versie van de) DB
            self.env.cr.execute(
                'SELECT DISTINCT "%s" FROM "%s" '
                ' WHERE "%s" LIKE %%s OR "%s" LIKE %%s OR "%s" LIKE %%s'
                % (column, table, column, column, column),
                ('drukwerk.%', 'activiteiten.%', 'professionalisering.%'))
            stale = [r[0] for r in self.env.cr.fetchall()]
            if stale:
                offenders['%s.%s' % (table, column)] = stale
        self.assertFalse(
            offenders,
            'tekst-model-kolommen wijzen nog naar oude modellen: %s'
            % offenders)
