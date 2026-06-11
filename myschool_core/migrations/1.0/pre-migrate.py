# -*- coding: utf-8 -*-
"""Migration 0.9 → 1.0 (myschool_core) — DATA-BEHOUDENDE module/model-rename.

Achtergrond
-----------
Commit 8fced02 ("Rename update myschool_...") hernoemde drie modules én al
hun model-``_name``s door een ``myschool_``-prefix toe te voegen, maar leverde
GEEN migratie-script. Gevolg op de test-DB:

  * ``ir_module_module`` heeft nog de OUDE namen (``drukwerk`` /
    ``activiteiten`` / ``professionalisering``) als *installed*; de nieuwe
    ``myschool_*`` staan *uninstalled*.
  * ``ir_model`` heeft nog de oude model-namen; alle data-tabellen dragen de
    oude naam.
  * 72 ``mail_activity``-records wijzen naar de oude modellen
    (``drukwerk.record`` enz.). Bij login doet
    ``res.users._get_activity_groups`` ``self.env['drukwerk.record']`` →
    ``KeyError`` → testserver onbruikbaar.

Waarom hier (myschool_core) en niet in de hernoemde modules zelf
----------------------------------------------------------------
De oude modules staan niet meer op het addons-path → worden niet
"ge-upgrade", dus hún migratie-scripts draaien niet. De nieuwe ``myschool_*``
staan *uninstalled* → een fresh *install* draait ook geen migraties en zou
botsen op de bestaande tabellen. ``myschool_core`` is een common dependency,
is *installed*, staat op disk en wordt vóór de drie hernoemde modules geladen.
Door de rename in een **pre-migration van myschool_core** te doen, worden de
``ir_module_module``-rijen ``myschool_*`` (state *installed*) en de modellen +
tabellen hernoemd VOORDAT Odoo de drie modules in dezelfde upgrade-pass laadt.
Odoo ziet ze dan als een gewone upgrade van een installed module i.p.v. een
fresh install op een bezette tabel.

Deze migratie is volledig in SQL geschreven (geen ``openupgradelib`` — die zit
niet in de role-image en wordt nergens in de repo gebruikt). Ze repliceert wat
``openupgrade.update_module_names`` + ``rename_models`` + ``rename_tables`` +
``rename_columns`` zouden doen, INCLUSIEF de m2m-relatie-kolommen.

Derde iteratie (na partiële apply op SCHONE pre-rename DB)
---------------------------------------------------------
De tweede versie liep de hele pre-migrate door (vak_data.xml-crash weg), maar
het laden van de hernoemde modules crashte op de m2m relatie-tabellen:

  ``column "myschool_activiteiten_bus_id" referenced in foreign key constraint
  does not exist``

Drie wortelproblemen, hier opgelost:

  1. **m2m relatie-tabel werd hernoemd maar de KOLOMMEN erin niet.** Odoo
     noemt m2m-kolommen ``<comodel_tabel>_id``; na het hernoemen van de
     model-hoofdtabel moeten de kolommen in élke relatie-tabel mee. Opgelost
     met ``_rename_m2m_columns`` (expliciete kolom-map).

  2. **``carpool_rel`` werd DUBBEL.** De oude generieke tabel-rename pakte
     ALLES wat met ``professionalisering_`` begon → hernoemde óók
     ``professionalisering_carpool_rel`` (die in de nieuwe code zijn oude naam
     ZONDER prefix houdt). Daarna creëerde de module-load de verse
     ``professionalisering_carpool_rel`` → beide bestonden. Opgelost:
     ``_rename_model_main_tables`` pakt nu UITSLUITEND de model-HOOFDtabellen
     (één per ir_model.model, _auto=True), NOOIT relatie-tabellen. Relatie-
     tabellen lopen 100 % via ``REL_TABLES`` met een expliciete EXCLUDE-set.

  3. **Version-trap.** ``myschool_core``'s pre-migrate committe (version→1.0)
     vóór de afhankelijke modules laadden en crashten → een herstart
     re-triggert de 1.0-migratie niet meer (version al 1.0) én de oude
     ``legacy_modules``-early-return short-circuitte. Opgelost: de re-run-guard
     kijkt nu naar ELKE resterende oude-prefix-referentie (module, ir_model,
     fysieke tabel, of m2m-kolom). Zolang er íets oud is, draait de volledige
     idempotente migratie opnieuw. Een half-gemigreerde DB kan zo met een
     herhaalde ``-u myschool_core`` (na version-reset) afgemaakt worden i.p.v.
     restore-per-iteratie.

Vierde iteratie (REL_TABLES afgeleid uit de ECHTE field-definities)
-------------------------------------------------------------------
De derde versie hernoemde de m2m-kolommen via een MENGELING van een
hand-onderhouden map én een generieke ``<tabel>_id``-afleiding. Beide bevatten
foute AANNAMES over relatie-tabel- en kolomnamen. Op een schone pre-rename-DB
liep de pre-migrate volledig door, maar het laden crashte op:

  ``ALTER TABLE "professionalisering_carpool_rel" ADD FOREIGN KEY
    ("professionalisering_id") ... column "professionalisering_id" does not
    exist``

— want de generieke stap had ``professionalisering_id`` →
``myschool_professionalisering_id`` hernoemd, terwijl
``carpool_employee_ids`` die kolomnaam EXPLICIET als oude naam hardcodeert.

Wortelprobleem: de ENIGE bron van waarheid is wat elk ``fields.Many2many`` in
de NIEUWE code declareert (``relation``/``column1``/``column2``), aangevuld met
Odoo-19's default-afleiding voor velden zonder die args. REL_TABLES is nu
mechanisch uit die field-defs afgeleid (zie de per-veld audit bij REL_TABLES),
NIET meer uit prefix-aannames. Concrete correcties t.o.v. iteratie 3:

  * ``activiteiten.record.document_ids`` (DEFAULT): de sorteer-volgorde van de
    twee modeltabellen FLIPT bij de rename →
    ``activiteiten_record_ir_attachment_rel`` wordt
    ``ir_attachment_myschool_activiteiten_record_rel`` (iteratie 3 mikte op het
    niet-bestaande ``myschool_activiteiten_record_ir_attachment_rel``).
  * ``professionalisering.record.bewijs_document_ids`` (DEFAULT):
    ``ir_attachment_professionalisering_record_rel`` MOET hernoemd naar
    ``ir_attachment_myschool_professionalisering_record_rel`` (iteratie 3 liet
    de tabelnaam staan).
  * ``activiteiten.bus.klas_ids`` (DEFAULT):
    ``activiteiten_bus_myschool_org_rel`` MOET hernoemd naar
    ``myschool_activiteiten_bus_myschool_org_rel`` (iteratie 3 liet hem staan).
  * ``*.record.klas_ids/leerkracht_ids/student_ids`` (EXPLICIETE cols
    ``record_id``/``org_id``/``person_id``): die kolommen bevatten GEEN prefix
    → blijven ongewijzigd (iteratie 3 mikte fout op ``activiteiten_record_id``
    enz., die nooit bestonden).
  * ``professionalisering.record.carpool_employee_ids`` (oud == nieuw): tabel
    én beide kolommen blijven ONGEMOEID. Staat in ``REL_TABLES_UNTOUCHED`` en
    is uit de legacy-guard (c) uitgesloten zodat de her-draaibare guard niet
    eindeloos op ``professionalisering_carpool_rel`` blijft hangen.
  * Non-stored m2m (compute + ``store=False``, ook mét ``relation=``) maken in
    Odoo-19 GEEN fysieke tabel → niet in de map (bus ``beschikbare_*``,
    alle ``available_*``, de twee ``pp_picker_*`` picker-velden, org_students
    ``student_ids``).

De generieke kolom-afleiding is volledig verwijderd; alleen de field-afgeleide
``REL_TABLES['cols']`` bepaalt nog kolom-renames.

Idempotent
----------
Veilig her-draaien: elke stap checkt ``to_regclass`` / bestaande naam/kolom en
slaat over wat al gemigreerd is. Version blijft 1.0 zodat de migratie
her-triggert zolang ze nog niet volledig is doorgelopen.

Auteur: Claude Opus 4.8 (1M context)
"""

import logging

_logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 1. Module-rename  (oud  ->  nieuw)
# --------------------------------------------------------------------------
MODULE_RENAMES = {
    'drukwerk': 'myschool_drukwerk',
    'activiteiten': 'myschool_activiteiten',
    'professionalisering': 'myschool_professionalisering',
}

# Oude model-prefix  ->  nieuwe model-prefix. Alle modellen onder deze
# prefixen krijgen generiek de nieuwe prefix; zo dekken we persistent-,
# transient- én _auto=False (SQL-view) modellen zonder ze stuk voor stuk te
# moeten hardcoden.
MODEL_PREFIX_RENAMES = {
    'drukwerk.': 'myschool_drukwerk.',
    'activiteiten.': 'myschool_activiteiten.',
    'professionalisering.': 'myschool_professionalisering.',
}

# Tabel-prefix-vorm van bovenstaande (punt -> underscore). Gebruikt om m2m-
# kolomnamen <comodel_tabel>_id af te leiden en hoofdtabel-namen te matchen.
TABLE_PREFIX_RENAMES = {
    old.replace('.', '_'): new.replace('.', '_')
    for old, new in MODEL_PREFIX_RENAMES.items()
}  # {'drukwerk_': 'myschool_drukwerk_', ...}

# --------------------------------------------------------------------------
# 2. m2m RELATIE-tabellen — AFGELEID UIT DE ECHTE field-definities.
#
#    Vierde iteratie. De vorige REL_TABLES gebruikte generieke prefix-aannames
#    ("<comodel_tabel>_id", "tabel begint met activiteiten_ -> hernoem") die
#    FUNDAMENTEEL fout zijn: de ENIGE bron van waarheid is wat elk
#    ``fields.Many2many`` in de NIEUWE code letterlijk declareert
#    (``relation``, ``column1``, ``column2``), gecombineerd met Odoo-19's
#    default-afleiding voor velden zonder expliciete args.
#
#    Odoo-19 default-afleiding (orm/fields_relational.py Many2many
#    .setup_nonrelated, GEVERIFIEERD):
#       * ALLEEN voor STORED velden wordt een relatie-tabel aangemaakt.
#         Non-stored (compute + store=False) m2m -> relation/column1/column2
#         = None -> GEEN fysieke tabel, ook NIET met expliciete ``relation=``.
#       * relation = '%s_%s_rel' % tuple(sorted([model._table, comodel._table]))
#         (ALFABETISCHE sort van de twee MODEL-tabelnamen!)
#       * column1 = '%s_id' % model._table   (eigen model)
#       * column2 = '%s_id' % comodel._table (comodel)
#
#    Per-veld AUDIT (veld -> oud (relation, col1, col2) -> nieuw), waaruit
#    onderstaande map mechanisch volgt. model._table: activiteiten.record ->
#    (myschool_)activiteiten_record, activiteiten.bus -> (..)activiteiten_bus,
#    drukwerk.record -> (..)drukwerk_record, professionalisering.record ->
#    (..)professionalisering_record. comodels: myschool.org -> myschool_org,
#    myschool.person -> myschool_person, hr.employee -> hr_employee,
#    ir.attachment -> ir_attachment.
#
#    STORED, MET tabel (staan hieronder):
#      activiteiten.record.klas_ids        expliciet rel NIEUW; col1='record_id'
#        oud activiteiten_record_klas_rel(record_id,org_id)
#        -> myschool_activiteiten_record_klas_rel(record_id,org_id)  col ONGEW.
#      activiteiten.record.leerkracht_ids  idem, col2='person_id'
#        oud activiteiten_record_leerkracht_rel(record_id,person_id)
#        -> myschool_activiteiten_record_leerkracht_rel(...)        col ONGEW.
#      activiteiten.record.document_ids    DEFAULT (sort-order FLIPT!)
#        oud activiteiten_record_ir_attachment_rel
#              (activiteiten_record_id, ir_attachment_id)
#        -> ir_attachment_myschool_activiteiten_record_rel
#              (myschool_activiteiten_record_id, ir_attachment_id)
#      activiteiten.bus.klas_ids           DEFAULT
#        oud activiteiten_bus_myschool_org_rel
#              (activiteiten_bus_id, myschool_org_id)
#        -> myschool_activiteiten_bus_myschool_org_rel
#              (myschool_activiteiten_bus_id, myschool_org_id)
#      drukwerk.record.klas_ids            expliciet rel NIEUW; col1='record_id'
#        oud drukwerk_record_klas_rel(record_id,org_id)
#        -> myschool_drukwerk_record_klas_rel(record_id,org_id)      col ONGEW.
#      drukwerk.record.student_ids         idem, col2='person_id'
#        oud drukwerk_record_student_rel(record_id,person_id)
#        -> myschool_drukwerk_record_student_rel(...)               col ONGEW.
#      professionalisering.record.carpool_employee_ids  expliciet OUD==NIEUW
#        professionalisering_carpool_rel(professionalisering_id, employee_id)
#        -> ONGEWIJZIGD. NIET aanraken (was de FK-crash). Staat hier NIET in
#           de map: oud==nieuw -> geen tabel-rename, geen kolom-rename.
#      professionalisering.record.bewijs_document_ids   DEFAULT
#        oud ir_attachment_professionalisering_record_rel
#              (professionalisering_record_id, ir_attachment_id)
#        -> ir_attachment_myschool_professionalisering_record_rel
#              (myschool_professionalisering_record_id, ir_attachment_id)
#
#    NON-STORED, GEEN tabel (worden NIET in de map opgenomen — er is fysiek
#    niets om te hernoemen, ook al staat er een ``relation=`` arg):
#      activiteiten.record.available_klas_ids / available_leerkracht_ids
#      activiteiten.bus.beschikbare_klas_ids (relation=..._beschikbare_klas_rel)
#      activiteiten.bus.beschikbare_leerkracht_ids (relation=..._beschikbare_lk_rel)
#      myschool.org(activiteiten).student_ids
#      drukwerk.record.available_klas_ids
#      professionalisering.address.picker.available_org_address_ids
#        (relation='pp_picker_org_rel')   -> transient + non-stored
#      professionalisering.address.picker.available_address_ids
#        (relation='pp_picker_loc_rel')   -> transient + non-stored
#
#    De map bevat dus UITSLUITEND de stored velden waarvoor oud != nieuw
#    (relation OF een kolom verandert). Schema:
#       'new'  : nieuwe relatie-tabelnaam
#       'cols' : { oude_kolomnaam : nieuwe_kolomnaam }  (alleen veranderende)
#    Een veld waar oud==nieuw (carpool) komt NIET voor -> nooit aangeraakt.
# --------------------------------------------------------------------------
REL_TABLES = {
    # --- activiteiten.record (expliciete cols 'record_id' -> ONGEWIJZIGD) ---
    'activiteiten_record_klas_rel': {
        'new': 'myschool_activiteiten_record_klas_rel',
        'cols': {},  # 'record_id'/'org_id' bevatten geen prefix -> ongewijzigd
    },
    'activiteiten_record_leerkracht_rel': {
        'new': 'myschool_activiteiten_record_leerkracht_rel',
        'cols': {},  # 'record_id'/'person_id' -> ongewijzigd
    },
    # activiteiten.record.document_ids: DEFAULT, sort-order flipt
    # (activiteiten_record < ir_attachment, maar ir_attachment < myschool_...).
    'activiteiten_record_ir_attachment_rel': {
        'new': 'ir_attachment_myschool_activiteiten_record_rel',
        'cols': {
            'activiteiten_record_id': 'myschool_activiteiten_record_id',
        },
    },
    # --- activiteiten.bus.klas_ids: DEFAULT --------------------------------
    'activiteiten_bus_myschool_org_rel': {
        'new': 'myschool_activiteiten_bus_myschool_org_rel',
        'cols': {
            'activiteiten_bus_id': 'myschool_activiteiten_bus_id',
            # 'myschool_org_id' (comodel) -> ongewijzigd
        },
    },
    # --- drukwerk.record (expliciete cols 'record_id' -> ONGEWIJZIGD) ------
    'drukwerk_record_klas_rel': {
        'new': 'myschool_drukwerk_record_klas_rel',
        'cols': {},  # 'record_id'/'org_id' -> ongewijzigd
    },
    'drukwerk_record_student_rel': {
        'new': 'myschool_drukwerk_record_student_rel',
        'cols': {},  # 'record_id'/'person_id' -> ongewijzigd
    },
    # --- professionalisering.record.bewijs_document_ids: DEFAULT -----------
    # ir_attachment < (myschool_)professionalisering_record -> ir_attachment
    # blijft VOORAAN; alleen het professionalisering-deel + de col schuiven mee.
    'ir_attachment_professionalisering_record_rel': {
        'new': 'ir_attachment_myschool_professionalisering_record_rel',
        'cols': {
            'professionalisering_record_id':
                'myschool_professionalisering_record_id',
            # 'ir_attachment_id' (comodel) -> ongewijzigd
        },
    },
    # professionalisering.record.carpool_employee_ids: OUD == NIEUW
    # ('professionalisering_carpool_rel', professionalisering_id, employee_id)
    # -> BEWUST AFWEZIG. Niet hernoemen, niet kolom-renamen (was de FK-crash).
}

# Relatie-tabellen die hun OUDE tabelnaam houden (new is None). Met de
# field-afgeleide map zijn dat er GEEN — elke entry verandert van naam.
# Behouden als (lege) set voor de helper-aanroepen.
REL_TABLES_KEEP_NAME = {
    old for old, spec in REL_TABLES.items() if spec['new'] is None
}

# Alle relatie-tabelnamen (oud) die we ACTIEF beheren. Gebruikt om in
# _rename_model_main_tables elke beheerde relatie-tabel uit te sluiten van de
# hoofdtabel-sweep.
ALL_REL_TABLE_NAMES = set(REL_TABLES.keys())

# Relatie-tabellen die met RUST gelaten moeten worden (oud == nieuw): tabelnaam
# én kolommen blijven exact zoals ze in de pre-rename-DB staan, omdat de NIEUWE
# field-definitie diezelfde namen hardcodeert. _rename_model_main_tables en de
# legacy-guard moeten deze NOOIT als "te hernoemen" of "legacy remnant" zien.
#     professionalisering_carpool_rel -> carpool_employee_ids hardcodeert
#         relation='professionalisering_carpool_rel', col1='professionalisering_id'
REL_TABLES_UNTOUCHED = {
    'professionalisering_carpool_rel',
}

# NB: tabellen die via een FK naar ir_model.id wijzen (ir_model_access,
# ir_rule, ir_model_fields.model_id, ir_cron/ir_act_server.model_id,
# ir_default.field_id, mail_alias.alias_model_id, mail_template.model_id,
# base_automation.model_id, ...) volgen de ir_model-rename AUTOMATISCH en
# worden hier NIET aangeraakt.
# Enkel kolommen die de model-naam als platte STRING opslaan, worden in
# _fix_model_string_references bijgewerkt. LET OP: ondanks hun naam zijn
# ``ir_filters.model_id`` (Selection) en ``ir_model_fields.model`` (owner)
# TEKST-kolommen, GEEN FK's — die zitten dus wél in de string-sweep.


def migrate(cr, version):
    if not version:
        # Fresh install van myschool_core: niets te migreren.
        return

    _logger.info('[myschool_core 1.0] start data-behoudende module-rename')

    # ------------------------------------------------------------------
    # RE-RUN-GUARD (version-trap fix): draai zolang er ÉÉN oude-prefix-
    # referentie bestaat — kijk niet enkel naar modulenamen (die in een
    # half-gemigreerde DB al hernoemd zijn) maar naar de gehéle staat:
    #   (a) ir_module_module met oude naam, of
    #   (b) ir_model.model met oude prefix, of
    #   (c) een fysieke hoofdtabel met oude prefix, of
    #   (d) een m2m relatie-kolom die nog oud heet.
    # Zo lang íéts oud is -> volledige idempotente migratie opnieuw.
    # ------------------------------------------------------------------
    if not _has_legacy_remnants(cr):
        _logger.info(
            '[myschool_core 1.0] geen enkele oude-prefix-referentie meer '
            '(module/model/tabel/m2m-kolom) — rename volledig voltooid, '
            'niets te doen')
        return

    _rename_modules(cr)
    _rename_models(cr)
    _rename_model_main_tables(cr)
    _rename_rel_tables(cr)
    _rename_m2m_columns(cr)
    _fix_model_string_references(cr)
    _drop_stale_report_views(cr)

    if _has_legacy_remnants(cr):
        # Niet fataal (de module-load die hierna volgt kan nog falen op een
        # niet-voorzien overblijfsel), maar log nadrukkelijk zodat een tweede
        # -u myschool_core (na version-reset) gericht kan afmaken.
        _logger.warning(
            '[myschool_core 1.0] migratie liep door maar er resteren nog '
            'oude-prefix-referenties; her-draai -u myschool_core na een '
            'version-reset om af te maken (zie module-docstring).')
    else:
        _logger.info('[myschool_core 1.0] module-rename voltooid (geen '
                     'oude-prefix-referenties meer)')


# --------------------------------------------------------------------------
def _has_legacy_remnants(cr):
    """True zolang ergens nog een oude-prefix-referentie bestaat.

    Robuuster dan een loutere ``legacy_modules``-check: in een half-gemigreerde
    DB zijn de modulenamen al hernoemd terwijl een tabel of m2m-kolom nog oud
    is. Deze guard maakt de migratie écht her-draaibaar.
    """
    # (a) Module-namen.
    cr.execute(
        "SELECT 1 FROM ir_module_module WHERE name IN %s LIMIT 1",
        (tuple(MODULE_RENAMES.keys()),),
    )
    if cr.fetchone():
        return True

    # (b) ir_model met oude prefix.
    like_clauses = ' OR '.join("model LIKE %s" for _ in MODEL_PREFIX_RENAMES)
    cr.execute(
        "SELECT 1 FROM ir_model WHERE %s LIMIT 1" % like_clauses,
        tuple(p + '%' for p in MODEL_PREFIX_RENAMES),
    )
    if cr.fetchone():
        return True

    # (c) Fysieke hoofdtabel met oude prefix (relatie-tabellen uitgesloten:
    #     sommige houden bewust hun oude naam).
    for old_pref in TABLE_PREFIX_RENAMES:
        cr.execute(
            "SELECT tablename FROM pg_tables "
            " WHERE schemaname = current_schema() AND tablename LIKE %s",
            (old_pref + '%',),
        )
        for (tbl,) in cr.fetchall():
            new_pref = TABLE_PREFIX_RENAMES[old_pref]
            if tbl.startswith(new_pref):
                continue  # al hernoemd
            if tbl in ALL_REL_TABLE_NAMES:
                continue  # beheerde relatie-tabel, apart afgehandeld
            if tbl in REL_TABLES_UNTOUCHED:
                # carpool_rel: tabelnaam blijft BEWUST oud (nieuwe code
                # hardcodeert die) -> GEEN legacy remnant, anders loopt de
                # her-draaibare guard eindeloos.
                continue
            return True

    # (d) m2m relatie-kolom die nog oud heet.
    for old_tbl, spec in REL_TABLES.items():
        cur_tbl = old_tbl if spec['new'] is None else spec['new']
        for old_col in spec['cols']:
            if _column_exists(cr, old_tbl, old_col) or \
                    _column_exists(cr, cur_tbl, old_col):
                return True

    return False


# --------------------------------------------------------------------------
def _rename_modules(cr):
    """Hernoem de modulenaam overal waar hij als STRING is opgeslagen:
    ir_module_module.name, ir_model_data.module en
    ir_module_module_dependency.name.
    """
    for old, new in MODULE_RENAMES.items():
        # Botsing voorkomen: de uninstalled placeholder-rij van de nieuwe
        # module (door de Apps-scan aangemaakt) moet weg vóór we de oude
        # installed-rij omdopen, anders unique-violation op name.
        cr.execute(
            "DELETE FROM ir_module_module "
            " WHERE name = %s AND state = 'uninstalled'",
            (new,),
        )
        if cr.rowcount:
            _logger.info(
                '[1.0] placeholder uninstalled-module %s verwijderd', new)

        cr.execute(
            "UPDATE ir_module_module SET name = %s "
            " WHERE name = %s",
            (new, old),
        )
        if cr.rowcount:
            _logger.info('[1.0] ir_module_module %s -> %s', old, new)

        cr.execute(
            "UPDATE ir_model_data SET module = %s WHERE module = %s",
            (new, old),
        )
        if cr.rowcount:
            _logger.info(
                '[1.0] ir_model_data.module %s -> %s (%d rijen)',
                old, new, cr.rowcount)

        # Dependency-rijen die naar de oude modulenaam verwijzen.
        cr.execute(
            "UPDATE ir_module_module_dependency SET name = %s "
            " WHERE name = %s",
            (new, old),
        )
        if cr.rowcount:
            _logger.info(
                '[1.0] ir_module_module_dependency %s -> %s', old, new)


# --------------------------------------------------------------------------
def _rename_models(cr):
    """Hernoem elke ir_model.model met een oude prefix naar de nieuwe prefix,
    en hernoem de auto-gegenereerde xmlid (model_<oud> -> model_<nieuw>) zodat
    de bestaande ir_model-rij her-gebonden wordt aan het xmlid dat de nieuwe
    code declareert (anders maakt Odoo een DUPLICAAT model aan).
    """
    cr.execute("SELECT id, model FROM ir_model")
    rows = cr.fetchall()
    for model_id, model in rows:
        new_model = _apply_prefix(model)
        if new_model == model:
            continue

        # Mogelijke botsing: bestaat de nieuwe model-naam al? (bv. door een
        # eerdere half-gelukte run). Zo ja: verwijder de zojuist door de scan
        # aangemaakte lege nieuwe rij en behoud de oude (met data-binding).
        cr.execute("SELECT id FROM ir_model WHERE model = %s", (new_model,))
        dup = cr.fetchone()
        if dup and dup[0] != model_id:
            # Ruim de lege duplicaat-rij + zijn afhankelijke metadata op
            # (ir_model_fields heeft ondelete='cascade' op model_id; de
            # bijbehorende ir_model_data laten we expliciet vallen om geen
            # dangling xmlids te houden).
            cr.execute(
                "DELETE FROM ir_model_data "
                " WHERE model = 'ir.model.fields' AND res_id IN "
                "   (SELECT id FROM ir_model_fields WHERE model_id = %s)",
                (dup[0],))
            cr.execute(
                "DELETE FROM ir_model_data "
                " WHERE model = 'ir.model' AND res_id = %s", (dup[0],))
            cr.execute("DELETE FROM ir_model WHERE id = %s", (dup[0],))
            _logger.info('[1.0] dubbele ir_model-rij %s opgeruimd', new_model)

        cr.execute(
            "UPDATE ir_model SET model = %s WHERE id = %s",
            (new_model, model_id),
        )

        # Auto-xmlid voor het model: model_<naam met . en _ -> _>.
        old_xmlid = 'model_' + model.replace('.', '_')
        new_xmlid = 'model_' + new_model.replace('.', '_')
        cr.execute(
            "UPDATE ir_model_data SET name = %s "
            " WHERE name = %s AND model = 'ir.model'",
            (new_xmlid, old_xmlid),
        )
        _logger.info('[1.0] ir_model %s -> %s', model, new_model)

    # Velden-xmlids (field_<model>_<field>) volgen via FK model_id automatisch
    # voor de ir_model_fields-rij zelf, maar hun ir_model_data.name bevat de
    # oude model-naam. Die hernoemen we generiek per prefix.
    for old_pref, new_pref in MODEL_PREFIX_RENAMES.items():
        old_token = 'field_' + old_pref.replace('.', '_')      # field_drukwerk_
        new_token = 'field_' + new_pref.replace('.', '_')      # field_myschool_drukwerk_
        cr.execute(
            "UPDATE ir_model_data "
            "   SET name = %s || substring(name from %s) "
            " WHERE model = 'ir.model.fields' "
            "   AND name LIKE %s",
            (new_token, len(old_token) + 1, old_token + '%'),
        )
        if cr.rowcount:
            _logger.info(
                '[1.0] %d ir.model.fields-xmlids %s* -> %s*',
                cr.rowcount, old_token, new_token)

        # Selectie-xmlids (selection_<model>_<field>_<value>) idem.
        old_sel = 'selection_' + old_pref.replace('.', '_')
        new_sel = 'selection_' + new_pref.replace('.', '_')
        cr.execute(
            "UPDATE ir_model_data "
            "   SET name = %s || substring(name from %s) "
            " WHERE model = 'ir.model.fields.selection' "
            "   AND name LIKE %s",
            (new_sel, len(old_sel) + 1, old_sel + '%'),
        )
        if cr.rowcount:
            _logger.info(
                '[1.0] %d selection-xmlids %s* -> %s*',
                cr.rowcount, old_sel, new_sel)


# --------------------------------------------------------------------------
def _rename_model_main_tables(cr):
    """Hernoem elke fysieke MODEL-HOOFDtabel met oude prefix naar nieuwe prefix.

    UITSLUITEND hoofdtabellen: voor elk ir_model met de nieuwe prefix berekenen
    we oude/nieuwe tabelnaam en hernoemen we als de oude tabel bestaat en de
    nieuwe nog niet. Relatie-tabellen (ALL_REL_TABLE_NAMES) worden HIER nooit
    aangeraakt — die lopen 100 % via _rename_rel_tables. Dat voorkomt o.a. de
    dubbele carpool_rel (die zijn oude naam houdt).

    We leiden de hoofdtabellen af uit ir_model i.p.v. uit een naïeve pg_tables-
    prefix-scan, zodat we per ir_model precies één hoofdtabel raken en geen
    relatie-/view-tabel per ongeluk meepakken.
    """
    cr.execute("SELECT model FROM ir_model")
    for (model,) in cr.fetchall():
        # ir_model is op dit punt al hernoemd (nieuwe prefix). Leid de oude
        # tabelnaam af door de nieuwe model-prefix terug te mappen.
        new_tbl = model.replace('.', '_')
        old_tbl = _reverse_table_prefix(new_tbl)
        if old_tbl is None or old_tbl == new_tbl:
            continue  # model zonder te-hernoemen prefix
        if old_tbl in ALL_REL_TABLE_NAMES or old_tbl in REL_TABLES_KEEP_NAME \
                or old_tbl in REL_TABLES_UNTOUCHED:
            continue  # relatie-tabel: nooit hier
        _rename_table(cr, old_tbl, new_tbl)


# --------------------------------------------------------------------------
def _rename_rel_tables(cr):
    """Hernoem de m2m relatie-tabellen volgens REL_TABLES (100 % expliciet).

    Voor tabellen met ``new is None`` blijft de naam ongewijzigd (carpool_rel,
    ir_attachment_*-zijde, activiteiten_bus_myschool_org_rel). Alleen tabellen
    met een echte nieuwe naam worden hernoemd; een eventuele reeds-bestaande
    nieuwe (lege) duplicaat wordt idempotent opgeruimd.
    """
    for old, spec in REL_TABLES.items():
        new = spec['new']
        if new is None:
            continue  # tabel houdt zijn naam

        old_exists = _table_exists(cr, old)
        new_exists = _table_exists(cr, new)

        if old_exists and new_exists:
            # Beide bestaan -> de module-load (of een vorige run) creëerde al
            # de nieuwe. Droppen we de LEGE van de twee. Voorkeur: drop de
            # nieuwe als die leeg is en de oude data heeft; anders drop de
            # oude als die leeg is.
            new_cnt = _row_count(cr, new)
            old_cnt = _row_count(cr, old)
            if new_cnt == 0:
                cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % new)
                _logger.info(
                    '[1.0] lege duplicaat-rel-tabel %s gedropt, %s wordt '
                    'hernoemd (%d rijen)', new, old, old_cnt)
                new_exists = False
            elif old_cnt == 0:
                cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % old)
                _logger.info(
                    '[1.0] lege oude-rel-tabel %s gedropt; %s (%d rijen) '
                    'behouden', old, new, new_cnt)
                old_exists = False
            else:
                _logger.warning(
                    '[1.0] ZOWEL %s (%d) als %s (%d) bevat data — handmatig '
                    'samenvoegen vereist, geen automatische merge',
                    old, old_cnt, new, new_cnt)
                continue

        if old_exists and not new_exists:
            cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (old, new))
            _logger.info('[1.0] rel-tabel %s -> %s', old, new)

        # ir_model_relation.name bijwerken (module/model-FK volgen automatisch).
        if _table_exists(cr, 'ir_model_relation'):
            cr.execute(
                "DELETE FROM ir_model_relation WHERE name = %s "
                "  AND EXISTS (SELECT 1 FROM ir_model_relation WHERE name = %s)",
                (new, old),
            )
            cr.execute(
                "UPDATE ir_model_relation SET name = %s WHERE name = %s",
                (new, old),
            )
            if cr.rowcount:
                _logger.info('[1.0] ir_model_relation %s -> %s', old, new)


# --------------------------------------------------------------------------
def _rename_m2m_columns(cr):
    """Hernoem de m2m relatie-kolommen volgens de EXPLICIETE, uit de
    field-definities afgeleide map in REL_TABLES['cols']. Dit is de fix voor de
    FK-crash:

      ``column "professionalisering_id" does not exist`` /
      ``column "myschool_activiteiten_bus_id" ... does not exist``

    GEEN generieke ``<tabel>_id``-afleiding meer: die hernoemde o.a. de
    expliciet-NIET-prefixte kolom ``professionalisering_id`` op carpool_rel
    (crash) en deed aannames over kolomnamen die simpelweg fout zijn. De ENIGE
    bron van waarheid is wat de Many2many in de NIEUWE code declareert
    (column1/column2), reeds neergelegd in REL_TABLES['cols'] als
    {oude_kolom: nieuwe_kolom} — UITSLUITEND voor kolommen die echt veranderen.
    Kolommen die in oud én nieuw identiek zijn (bv. 'record_id', 'org_id',
    'employee_id', 'ir_attachment_id', 'myschool_org_id') staan niet in de map
    en worden dus met rust gelaten.
    """
    for old_tbl, spec in REL_TABLES.items():
        if not spec['cols']:
            continue  # geen enkele kolom verandert voor deze tabel
        cur_tbl = old_tbl if spec['new'] is None else spec['new']
        # Tabel kan onder oude of nieuwe naam bestaan (afhankelijk van waar de
        # run zit). Bepaal de fysiek bestaande naam.
        phys_tbl = None
        for cand in (cur_tbl, old_tbl):
            if _table_exists(cr, cand):
                phys_tbl = cand
                break
        if phys_tbl is None:
            continue

        for old_col, new_col in spec['cols'].items():
            _rename_column(cr, phys_tbl, old_col, new_col)


# --------------------------------------------------------------------------
def _fix_model_string_references(cr):
    """Werk alle plaatsen bij waar de model-NAAM als string is opgeslagen en
    NIET via een FK naar ir_model meegaat. Dit fixt o.a. de crash-oorzaak:
    mail_activity.res_model.
    """
    for old_pref, new_pref in MODEL_PREFIX_RENAMES.items():
        # ALLE updates hieronder lopen via _update_prefix_col, dat per
        # tabel/kolom een to_regclass + information_schema-guard doet en
        # ontbrekende tabellen/kolommen overslaat i.p.v. te crashen. Zo is het
        # script robuust over Odoo-versies (bv. ir_property is in Odoo 17+
        # verwijderd; mail_activity hoort niet tot base en kan in theorie
        # ontbreken). Een platte-prefix-replace werkt voor zowel de pure
        # model-string-kolommen als voor ir_property.res_id ('<model>,<id>')
        # — in beide gevallen wordt enkel het prefix-deel vervangen.
        #
        # ----------------------------------------------------------------
        # UITPUTTENDE LIJST: elke tabel.kolom hieronder slaat een Odoo-MODEL
        # naam als platte TEKST op (geen FK naar ir_model.id). FK-kolommen
        # (ir_rule.model_id, ir_default.field_id, mail_alias.alias_model_id,
        # mail_template.model_id, base_automation.model_id, ir_act_server.
        # model_id, ir_cron via ir_act_server, ir_model_constraint.model,
        # ir_model_relation.model, ir_filters.action_id ...) volgen de
        # ir_model-rename AUTOMATISCH omdat ir_model.id STABIEL blijft en
        # worden hier dus NIET aangeraakt.
        #
        # Doel: NA deze sweep mag NERGENS nog een TEKST-verwijzing
        # 'drukwerk.*' / 'activiteiten.*' / 'professionalisering.*' (zonder
        # myschool_-prefix) bestaan. Geverifieerd tegen het Odoo-19-schema
        # (information_schema-scan op alle char/text kolommen die een
        # model-naam kunnen dragen).
        # ----------------------------------------------------------------

        # --- META-tabellen (base) — KRITISCH, waren de nieuwe crash-oorzaak --
        # ir_model_data.model  <- KeyError 'professionalisering.vak' bij het
        # herladen van <record>-xmlids (Odoo doet env[ir_model_data.model]).
        _update_prefix_col(cr, 'ir_model_data', 'model', old_pref, new_pref)
        # ir_model_fields.model  <- owner-model TEKST-kolom (NIET .relation!);
        # ~636 rijen droegen nog de oude naam.
        _update_prefix_col(cr, 'ir_model_fields', 'model', old_pref, new_pref)
        # ir_model_fields.relation (comodel-string van x2many/related velden)
        _update_prefix_col(
            cr, 'ir_model_fields', 'relation', old_pref, new_pref)

        # --- mail.* (mail-stack) -----------------------------------------
        # mail_activity.res_model  <- oorspronkelijke crash-oorzaak (KeyError)
        _update_prefix_col(cr, 'mail_activity', 'res_model', old_pref, new_pref)
        # mail_activity_type.res_model (config; ook via XML herladen, maar
        # idempotent meenemen kan geen kwaad)
        _update_prefix_col(
            cr, 'mail_activity_type', 'res_model', old_pref, new_pref)
        # mail_activity_plan.res_model (persistente activity-plan config)
        _update_prefix_col(
            cr, 'mail_activity_plan', 'res_model', old_pref, new_pref)
        # mail_message.model
        _update_prefix_col(cr, 'mail_message', 'model', old_pref, new_pref)
        # mail_followers.res_model
        _update_prefix_col(cr, 'mail_followers', 'res_model', old_pref, new_pref)
        # mail_message_subtype.res_model
        _update_prefix_col(
            cr, 'mail_message_subtype', 'res_model', old_pref, new_pref)
        # mail_template.model (stored related van model_id; FK herstelt dit ook,
        # maar idempotent meenemen voorkomt een stale read vóór de recompute)
        _update_prefix_col(cr, 'mail_template', 'model', old_pref, new_pref)
        # sms_template.model (analoog aan mail_template, indien sms geïnstalleerd)
        _update_prefix_col(cr, 'sms_template', 'model', old_pref, new_pref)
        # snailmail_letter.model (indien snailmail geïnstalleerd)
        _update_prefix_col(cr, 'snailmail_letter', 'model', old_pref, new_pref)
        # rating_rating.res_model / parent_res_model (persistente ratings)
        _update_prefix_col(cr, 'rating_rating', 'res_model', old_pref, new_pref)
        _update_prefix_col(
            cr, 'rating_rating', 'parent_res_model', old_pref, new_pref)

        # --- ir.attachment + actions -------------------------------------
        # ir_attachment.res_model
        _update_prefix_col(cr, 'ir_attachment', 'res_model', old_pref, new_pref)
        # ir_act_window.res_model / src_model
        _update_prefix_col(cr, 'ir_act_window', 'res_model', old_pref, new_pref)
        _update_prefix_col(cr, 'ir_act_window', 'src_model', old_pref, new_pref)
        # ir_act_client.res_model (client-actions, persistent)
        _update_prefix_col(cr, 'ir_act_client', 'res_model', old_pref, new_pref)
        # ir_act_report_xml.model  <- LET OP: de report-action-tabel heet in
        # Odoo 19 fysiek 'ir_act_report_xml' (niet 'ir_actions_report'); de
        # model-naam staat als TEKST in kolom 'model'.
        _update_prefix_col(cr, 'ir_act_report_xml', 'model', old_pref, new_pref)
        # ir_act_server.model_name: in Odoo 19 een NIET-opgeslagen related
        # (geen fysieke kolom) → de guard slaat dit over. Defensief behouden
        # voor oudere versies waar het wél een kolom was.
        _update_prefix_col(
            cr, 'ir_act_server', 'model_name', old_pref, new_pref)

        # --- ir_filters + embedded actions -------------------------------
        # ir_filters.model_id: ONDANKS de naam '_id' is dit een Selection-veld
        # dat de model-NAAM als TEKST (character varying) opslaat, GEEN FK.
        _update_prefix_col(cr, 'ir_filters', 'model_id', old_pref, new_pref)
        # ir_embedded_actions.parent_res_model (TEKST model-naam)
        _update_prefix_col(
            cr, 'ir_embedded_actions', 'parent_res_model', old_pref, new_pref)
        # ir_ui_view.model
        _update_prefix_col(cr, 'ir_ui_view', 'model', old_pref, new_pref)

        # --- MySchool-eigen model-tekstkolommen --------------------------
        # myschool_letter_template.model (stored related van model_id; FK
        # herstelt ook, idempotent meenemen kan geen kwaad).
        _update_prefix_col(
            cr, 'myschool_letter_template', 'model', old_pref, new_pref)
        # sync_log.model_name + sap_sync_change.target_model: Odoo-model-naam-
        # tekstkolommen. De sync/sap-laag raakt de 3 hernoemde modules niet
        # aan → in de praktijk 0 rijen, maar prefix-guarded meenemen is veilig
        # en idempotent (false-match onmogelijk: geen ander model deelt deze
        # prefixen). NB: myschool_asset.model_name is BEWUST UITGESLOTEN —
        # dat is een HARDWARE-modelstring ("Chromebook"), GEEN Odoo-model.
        _update_prefix_col(cr, 'sync_log', 'model_name', old_pref, new_pref)
        _update_prefix_col(
            cr, 'sap_sync_change', 'target_model', old_pref, new_pref)

        # ir_property.res_id  ==  '<model>,<id>'  (alleen prefix-deel).
        # LET OP: ir_property bestaat NIET MEER in Odoo 17+ (vervangen door
        # company-dependent kolom-opslag). De to_regclass-guard in
        # _update_prefix_col slaat de update over als de tabel ontbreekt,
        # zodat dit op Odoo 19 niet langer crasht.
        _update_prefix_col(cr, 'ir_property', 'res_id', old_pref, new_pref)

        # ir_translation bestaat NIET MEER in Odoo 16+ (vertalingen zitten nu
        # als jsonb in de kolom zelf). Guard slaat over indien afwezig; we
        # nemen de kolom defensief mee voor oudere DB's.
        _update_prefix_col(cr, 'ir_translation', 'name', old_pref, new_pref)


# --------------------------------------------------------------------------
def _drop_stale_report_views(cr):
    """De twee drukwerk-rapportmodellen zijn _auto=False (SQL-VIEWS).
    Hun oude view drukwerk_class_report / drukwerk_student_report blijft als
    relation achter na de tabel-rename-loop (het zijn views, geen tables, dus
    _rename_model_main_tables raakt ze niet via pg_tables). We droppen de oude
    views; Odoo (re)creëert de nieuwe ``myschool_drukwerk_*_report`` view bij
    het laden van de module via de ``init()``-override.
    """
    for view in ('drukwerk_class_report', 'drukwerk_student_report'):
        cr.execute("SELECT to_regclass(%s)", ('public.' + view,))
        if cr.fetchone()[0] is not None:
            cr.execute("DROP VIEW IF EXISTS %s CASCADE" % view)
            _logger.info('[1.0] stale SQL-view %s gedropt (wordt herbouwd)', view)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _apply_prefix(model):
    for old_pref, new_pref in MODEL_PREFIX_RENAMES.items():
        if model.startswith(old_pref):
            return new_pref + model[len(old_pref):]
    return model


def _reverse_table_prefix(new_tbl):
    """Geef de OUDE tabelnaam terug voor een nieuwe (myschool_-prefixed)
    hoofdtabel, of None als er geen te-hernoemen prefix op slaat.
    """
    for old_pref, new_pref in TABLE_PREFIX_RENAMES.items():
        if new_tbl.startswith(new_pref):
            return old_pref + new_tbl[len(new_pref):]
    return None


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", ('public.' + table,))
    return cr.fetchone()[0] is not None


def _column_exists(cr, table, column):
    if not _table_exists(cr, table):
        return False
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        " WHERE table_schema = current_schema() "
        "   AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _row_count(cr, table):
    cr.execute('SELECT COUNT(*) FROM "%s"' % table)
    return cr.fetchone()[0]


def _rename_table(cr, old, new):
    """Hernoem tabel ``old`` naar ``new`` als old bestaat en new nog niet."""
    old_exists = _table_exists(cr, old)
    new_exists = _table_exists(cr, new)

    if not old_exists:
        return
    if new_exists:
        _logger.warning(
            '[1.0] tabel %s bestaat al; %s niet hernoemd (handmatig nazien)',
            new, old)
        return
    cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (old, new))
    _logger.info('[1.0] tabel %s -> %s', old, new)


def _rename_column(cr, table, old_col, new_col):
    """Hernoem ``table.old_col`` -> ``new_col`` als old_col bestaat en new_col
    nog niet (idempotent / her-draaibaar)."""
    if not _table_exists(cr, table):
        return
    if not _column_exists(cr, table, old_col):
        return  # al hernoemd of nooit aanwezig
    if _column_exists(cr, table, new_col):
        # Beide kolommen bestaan -> de nieuwe is door de module-load al
        # aangemaakt naast de oude. Dat zou tot een verkeerde (lege) FK leiden.
        # Veilig: droppen we de (vermoedelijk lege) nieuwe en hernoemen de oude
        # met data. Als de nieuwe NIET leeg is, laten we hem staan en droppen
        # we de oude i.p.v. te raden.
        cr.execute(
            'SELECT COUNT(*) FROM "%s" WHERE "%s" IS NOT NULL'
            % (table, new_col))
        new_filled = cr.fetchone()[0]
        if new_filled == 0:
            cr.execute(
                'ALTER TABLE "%s" DROP COLUMN "%s"' % (table, new_col))
            cr.execute(
                'ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                % (table, old_col, new_col))
            _logger.info(
                '[1.0] lege nieuwe kolom %s.%s gedropt; %s -> %s hernoemd',
                table, new_col, old_col, new_col)
        else:
            cr.execute(
                'ALTER TABLE "%s" DROP COLUMN "%s"' % (table, old_col))
            _logger.warning(
                '[1.0] %s.%s bestond al met data; oude %s gedropt',
                table, new_col, old_col)
        return
    cr.execute(
        'ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
        % (table, old_col, new_col))
    _logger.info('[1.0] kolom %s.%s -> %s', table, old_col, new_col)


def _update_prefix_col(cr, table, col, old_pref, new_pref):
    """Vervang de prefix in ``table.col`` voor waarden die met old_pref
    beginnen. Slaat over als de tabel/kolom niet bestaat (idempotent / robuust
    over Odoo-versies).
    """
    if not _column_exists(cr, table, col):
        return
    cr.execute(
        'UPDATE "%s" SET "%s" = %%s || substring("%s" from %%s) '
        ' WHERE "%s" LIKE %%s' % (table, col, col, col),
        (new_pref, len(old_pref) + 1, old_pref + '%'),
    )
    if cr.rowcount:
        _logger.info(
            '[1.0] %s.%s %s* -> %s* (%d)',
            table, col, old_pref, new_pref, cr.rowcount)
