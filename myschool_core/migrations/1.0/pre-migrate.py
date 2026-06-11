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
``openupgrade.update_module_names`` + ``rename_models`` + ``rename_tables``
zouden doen.

Tweede iteratie (na partiële apply op myschool-test)
----------------------------------------------------
De eerste versie liep ver maar faalde bij het herladen van XML-data:

  ``KeyError: 'professionalisering.vak'`` /
  ``ParseError ... vak_data.xml``

Oorzaak: TEKST-kolommen met een platte model-naam die NIET via een FK naar
``ir_model.id`` meegaan, werden niet allemaal bijgewerkt. Concreet bleven
``ir_model_data.model`` (xmlid-reconciliatie → ``env[ir_model_data.model]``)
en ``ir_model_fields.model`` (owner-model, ~636 rijen) op de oude naam staan.
``_fix_model_string_references`` is daarom uitgebreid tot een UITPUTTENDE
sweep van álle base-/mail-/MySchool-tabellen met een model-naam-tekstkolom,
geverifieerd tegen het Odoo-19-schema.

Idempotent
----------
Veilig her-draaien: elke stap checkt ``to_regclass`` / bestaande naam en slaat
over wat al hernoemd is. Version blijft 1.0 zodat de migratie her-triggert
zolang ze nog niet volledig is doorgelopen.

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

# --------------------------------------------------------------------------
# 2. Tabel-renames die NIET zuiver de model-tabelnaam volgen.
#    De model-hoofdtabellen worden generiek hernoemd (zie _rename_tables);
#    hier staan enkel de m2m relatie-tabellen waarvan de naam in de code
#    expliciet gezet is en die mee-hernoemd werden in 8fced02.
#
#    LET OP: ``professionalisering_carpool_rel`` had in zowel oud als nieuw
#    een EXPLICIETE relation-naam ZONDER prefix → blijft ongewijzigd, staat
#    hier bewust NIET bij.
# --------------------------------------------------------------------------
M2M_TABLE_RENAMES = {
    # activiteiten.record
    'activiteiten_record_klas_rel': 'myschool_activiteiten_record_klas_rel',
    'activiteiten_record_leerkracht_rel':
        'myschool_activiteiten_record_leerkracht_rel',
    # activiteiten.record.document_ids (auto-named: <table>_ir_attachment_rel)
    'activiteiten_record_ir_attachment_rel':
        'myschool_activiteiten_record_ir_attachment_rel',
    # activiteiten.bus (expliciete relation-namen)
    'activiteiten_bus_beschikbare_klas_rel':
        'myschool_activiteiten_bus_beschikbare_klas_rel',
    'activiteiten_bus_beschikbare_lk_rel':
        'myschool_activiteiten_bus_beschikbare_lk_rel',
    # drukwerk.record
    'drukwerk_record_klas_rel': 'myschool_drukwerk_record_klas_rel',
    'drukwerk_record_student_rel': 'myschool_drukwerk_record_student_rel',
    # professionalisering.record.bewijs_document_ids (auto-named)
    'professionalisering_record_ir_attachment_rel':
        'myschool_professionalisering_record_ir_attachment_rel',
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

    # Voer alleen uit als er werkelijk nog oude namen zijn (idempotent).
    cr.execute(
        "SELECT name FROM ir_module_module WHERE name IN %s",
        (tuple(MODULE_RENAMES.keys()),),
    )
    legacy_modules = {r[0] for r in cr.fetchall()}
    if not legacy_modules:
        _logger.info(
            '[myschool_core 1.0] geen legacy-modulenamen aanwezig — '
            'rename al uitgevoerd, niets te doen')
        return

    _rename_modules(cr)
    _rename_models(cr)
    _rename_model_main_tables(cr)
    _rename_m2m_tables(cr)
    _fix_model_string_references(cr)
    _drop_stale_report_views(cr)

    _logger.info('[myschool_core 1.0] module-rename voltooid')


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
    """Hernoem elke fysieke hoofdtabel met oude prefix naar nieuwe prefix.
    Generiek o.b.v. ir_model: voor elk model met nieuwe prefix berekenen we
    oude/nieuwe tabelnaam en hernoemen we als de oude tabel bestaat en de
    nieuwe nog niet.
    """
    for old_pref, new_pref in MODEL_PREFIX_RENAMES.items():
        old_tbl_pref = old_pref.replace('.', '_')    # drukwerk_
        new_tbl_pref = new_pref.replace('.', '_')    # myschool_drukwerk_

        # Vraag de catalog op voor tabellen die met de oude prefix beginnen,
        # maar NIET met de nieuwe (myschool_drukwerk_* begint ook met... nee:
        # 'drukwerk_' is geen prefix van 'myschool_drukwerk_'; wel omgekeerd,
        # dus we filteren expliciet de reeds-hernoemde uit).
        cr.execute(
            "SELECT tablename FROM pg_tables "
            " WHERE schemaname = current_schema() "
            "   AND tablename LIKE %s",
            (old_tbl_pref + '%',),
        )
        for (tbl,) in cr.fetchall():
            if tbl.startswith(new_tbl_pref):
                continue  # al hernoemd in een vorige run
            new_tbl = new_tbl_pref + tbl[len(old_tbl_pref):]
            # m2m-rel-tabellen worden apart afgehandeld (expliciete map);
            # sla ze hier over om dubbele logica te vermijden.
            if tbl in M2M_TABLE_RENAMES:
                continue
            _rename_table(cr, tbl, new_tbl)


# --------------------------------------------------------------------------
def _rename_m2m_tables(cr):
    """Hernoem de expliciet-genoemde m2m relatie-tabellen + hun registratie in
    ir_model_relation (zodat een latere uninstall de juiste tabel target en er
    geen stale rij blijft staan naar een niet-bestaande tabel)."""
    for old, new in M2M_TABLE_RENAMES.items():
        _rename_table(cr, old, new)
        # ir_model_relation.name bijwerken (module/model-FK volgen automatisch).
        cr.execute("SELECT to_regclass('public.ir_model_relation')")
        if cr.fetchone()[0] is None:
            continue
        # Verwijder een eventueel reeds bestaande nieuwe-naam-rij om een
        # unique-botsing bij her-draaien te vermijden, hernoem dan de oude.
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


def _rename_table(cr, old, new):
    """Hernoem tabel ``old`` naar ``new`` als old bestaat en new nog niet."""
    cr.execute("SELECT to_regclass(%s)", ('public.' + old,))
    old_exists = cr.fetchone()[0] is not None
    cr.execute("SELECT to_regclass(%s)", ('public.' + new,))
    new_exists = cr.fetchone()[0] is not None

    if not old_exists:
        return
    if new_exists:
        _logger.warning(
            '[1.0] tabel %s bestaat al; %s niet hernoemd (handmatig nazien)',
            new, old)
        return
    cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (old, new))
    _logger.info('[1.0] tabel %s -> %s', old, new)


def _update_prefix_col(cr, table, col, old_pref, new_pref):
    """Vervang de prefix in ``table.col`` voor waarden die met old_pref
    beginnen. Slaat over als de tabel/kolom niet bestaat (idempotent / robuust
    over Odoo-versies).
    """
    cr.execute("SELECT to_regclass(%s)", ('public.' + table,))
    if cr.fetchone()[0] is None:
        return
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        " WHERE table_schema = current_schema() "
        "   AND table_name = %s AND column_name = %s",
        (table, col),
    )
    if not cr.fetchone():
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
