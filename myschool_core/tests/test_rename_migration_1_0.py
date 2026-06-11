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

    def test_carpool_rel_keeps_table_name_but_renames_column(self):
        # professionalisering_carpool_rel had in oud én nieuw een expliciete
        # relation-naam ZONDER prefix → de TABELNAAM blijft (new is None), maar
        # de comodel-KOLOM moet WÉL hernoemd worden.
        self.assertIn('professionalisering_carpool_rel', mig.REL_TABLES)
        spec = mig.REL_TABLES['professionalisering_carpool_rel']
        self.assertIsNone(
            spec['new'],
            'carpool_rel-TABELnaam mag NIET hernoemd worden')
        self.assertIn('professionalisering_carpool_rel',
                      mig.REL_TABLES_KEEP_NAME)
        self.assertEqual(
            spec['cols'].get('professionalisering_id'),
            'myschool_professionalisering_id',
            'carpool_rel comodel-KOLOM moet wél hernoemd worden')

    def test_rel_tables_column_maps_have_new_prefix(self):
        # Elke gemapte nieuwe kolomnaam draagt de myschool_-prefix en verschilt
        # van de oude; elke nieuwe tabelnaam (indien gezet) idem.
        for old_tbl, spec in mig.REL_TABLES.items():
            new_tbl = spec['new']
            if new_tbl is not None:
                self.assertTrue(
                    new_tbl.startswith('myschool_'),
                    'rel-tabel %s -> %s mist myschool_-prefix'
                    % (old_tbl, new_tbl))
                self.assertNotEqual(old_tbl, new_tbl)
            self.assertTrue(spec['cols'], 'rel-tabel %s zonder cols' % old_tbl)
            for old_col, new_col in spec['cols'].items():
                self.assertTrue(
                    new_col.startswith('myschool_'),
                    '%s.%s -> %s mist myschool_-prefix'
                    % (old_tbl, old_col, new_col))
                self.assertNotEqual(old_col, new_col)
                self.assertTrue(
                    old_col.endswith('_id') and new_col.endswith('_id'),
                    'm2m-comodel-kolom moet op _id eindigen: %s/%s'
                    % (old_col, new_col))

    def test_live_inventory_columns_covered(self):
        # Exacte inventaris uit de live DB (opdracht): per relatie-tabel de
        # comodel-kolom die nog oud was. Borg dat de map die dekt.
        expected = {
            'activiteiten_bus_myschool_org_rel':
                ('activiteiten_bus_id', 'myschool_activiteiten_bus_id'),
            'activiteiten_record_ir_attachment_rel':
                ('activiteiten_record_id', 'myschool_activiteiten_record_id'),
            'ir_attachment_professionalisering_record_rel':
                ('professionalisering_record_id',
                 'myschool_professionalisering_record_id'),
            'professionalisering_carpool_rel':
                ('professionalisering_id', 'myschool_professionalisering_id'),
        }
        for tbl, (old_col, new_col) in expected.items():
            self.assertIn(tbl, mig.REL_TABLES,
                          'rel-tabel %s ontbreekt in REL_TABLES' % tbl)
            self.assertEqual(
                mig.REL_TABLES[tbl]['cols'].get(old_col), new_col,
                'kolom-map voor %s.%s onjuist/ontbrekend' % (tbl, old_col))

    def test_tables_with_ir_attachment_prefix_keep_name(self):
        # De ir_attachment_-zijde-tabel (begint NIET met een model-prefix)
        # werd door de oude generieke sweep gemist; nu expliciet, tabelnaam
        # blijft, kolom mee.
        spec = mig.REL_TABLES['ir_attachment_professionalisering_record_rel']
        self.assertIsNone(spec['new'])

    def test_reverse_table_prefix(self):
        self.assertEqual(
            mig._reverse_table_prefix('myschool_activiteiten_bus'),
            'activiteiten_bus')
        self.assertEqual(
            mig._reverse_table_prefix('myschool_drukwerk_record'),
            'drukwerk_record')
        self.assertIsNone(mig._reverse_table_prefix('res_partner'))

    def test_apply_table_prefix_to_column(self):
        f = mig._apply_table_prefix_to_column
        self.assertEqual(
            f('activiteiten_bus_id'), 'myschool_activiteiten_bus_id')
        self.assertEqual(
            f('professionalisering_id'), 'myschool_professionalisering_id')
        # Al nieuw -> geen dubbel-rename.
        self.assertIsNone(f('myschool_activiteiten_bus_id'))
        # Geen model-prefix / niet-comodel-kolom -> None.
        self.assertIsNone(f('klas_id'))
        self.assertIsNone(f('myschool_org_id'))
        self.assertIsNone(f('create_uid'))

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

    def test_rel_tables_have_renamed_columns(self):
        # Borg dat NA de migratie elke (bestaande) relatie-tabel de NIEUWE
        # comodel-kolom heeft en GEEN oude meer — dit is de FK-crash-conditie:
        # de m2m-tabel was hernoemd maar de kolom niet.
        missing_new = {}
        stale_old = {}
        for old_tbl, spec in mig.REL_TABLES.items():
            phys = old_tbl if spec['new'] is None else spec['new']
            # Tabel kan onder oude of nieuwe naam bestaan; pak de fysieke.
            for cand in ([phys, old_tbl] if spec['new'] else [old_tbl]):
                self.env.cr.execute(
                    "SELECT to_regclass(%s)", ('public.' + cand,))
                if self.env.cr.fetchone()[0] is not None:
                    phys = cand
                    break
            else:
                continue  # tabel niet aanwezig in deze DB
            for old_col, new_col in spec['cols'].items():
                if not self._column_exists(phys, new_col):
                    missing_new['%s.%s' % (phys, new_col)] = True
                if self._column_exists(phys, old_col):
                    stale_old['%s.%s' % (phys, old_col)] = True
        self.assertFalse(
            missing_new,
            'relatie-tabellen missen de nieuwe comodel-kolom: %s'
            % sorted(missing_new))
        self.assertFalse(
            stale_old,
            'relatie-tabellen dragen nog de OUDE comodel-kolom: %s'
            % sorted(stale_old))

    def test_no_legacy_remnants_after_migration(self):
        # De re-run-guard moet NA een volledige migratie False geven: geen
        # enkele oude-prefix-referentie (module/model/tabel/m2m-kolom) meer.
        self.assertFalse(
            mig._has_legacy_remnants(self.env.cr),
            'er resteren oude-prefix-referenties; migratie niet volledig')


@tagged('post_install', '-at_install', 'myschool_rename')
class TestRenameColumnHelper(TransactionCase):
    """Zelfstandige DB-test van de m2m-kolom-rename op een wegwerp-tabel.

    TransactionCase rolt alles terug, dus deze synthetische tabel raakt geen
    echte data. Bewijst dat _rename_column idempotent is en de
    duplicaat-opruim-logica klopt.
    """

    def _mk(self, ddl):
        self.env.cr.execute(ddl)

    def _col_exists(self, table, col):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns "
            " WHERE table_schema = current_schema() "
            "   AND table_name = %s AND column_name = %s", (table, col))
        return bool(self.env.cr.fetchone())

    def test_rename_column_basic_and_idempotent(self):
        self._mk('CREATE TEMP TABLE _t_rel '
                 '(activiteiten_bus_id int, klas_id int)')
        mig._rename_column(
            self.env.cr, '_t_rel',
            'activiteiten_bus_id', 'myschool_activiteiten_bus_id')
        self.assertTrue(self._col_exists('_t_rel', 'myschool_activiteiten_bus_id'))
        self.assertFalse(self._col_exists('_t_rel', 'activiteiten_bus_id'))
        # Her-draaien: oude kolom weg -> no-op, geen crash.
        mig._rename_column(
            self.env.cr, '_t_rel',
            'activiteiten_bus_id', 'myschool_activiteiten_bus_id')
        self.assertTrue(self._col_exists('_t_rel', 'myschool_activiteiten_bus_id'))

    def test_rename_column_drops_empty_duplicate(self):
        # Simuleer dat de module-load al een (lege) nieuwe kolom aanmaakte
        # naast de oude (met data). De oude moet winnen.
        self._mk('CREATE TEMP TABLE _t_dup '
                 '(professionalisering_id int, myschool_professionalisering_id int)')
        self.env.cr.execute(
            'INSERT INTO _t_dup (professionalisering_id) VALUES (42)')
        mig._rename_column(
            self.env.cr, '_t_dup',
            'professionalisering_id', 'myschool_professionalisering_id')
        self.assertTrue(
            self._col_exists('_t_dup', 'myschool_professionalisering_id'))
        self.assertFalse(self._col_exists('_t_dup', 'professionalisering_id'))
        self.env.cr.execute(
            'SELECT myschool_professionalisering_id FROM _t_dup')
        self.assertEqual(self.env.cr.fetchone()[0], 42,
                         'data uit oude kolom moet behouden blijven')
