import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Activiteiten(models.Model):
    _name = 'myschool_activiteiten.record'
    _description = 'Activiteiten'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'myschool.allowed.schools.mixin']

    name = fields.Char(
        string='Referentie',
        copy=False,
        readonly=True,
        default='New',
    )
    titel = fields.Char(string='Titel activiteit')
    description = fields.Text(
        string='Aard van de uitstap / Inhoudelijke verduidelijking',
    )

    # Header: analytische code (op te vullen door boekhouding bij verwerking)
    analytische_code = fields.Char(
        string='Analytische code',
        tracking=True,
        help='Boekhoudkundige analytische code. Wordt door boekhouding '
             'ingevuld bij de verwerking.',
    )

    # Bestemming-details (PDF: naam / adres / telefoon)
    bestemming_naam = fields.Char(
        string='Bestemming — naam',
        help='Naam van de plek waar de activiteit doorgaat (bv. Technopolis, KU Leuven, ...).',
    )
    bestemming_adres = fields.Text(
        string='Bestemming — adres',
        help='Volledig adres van de bestemming.',
    )
    bestemming_telefoon = fields.Char(
        string='Bestemming — telefoon',
        help='Contactnummer van de bestemming.',
    )

    # Leerplandoelstellingen (PDF: vakgebonden / GFL / ICT / financieel-economisch)
    is_doel_vakgebonden = fields.Boolean(
        string='Vakgebonden',
        help='Aanvinken als de activiteit aansluit bij een specifiek vak '
             '(bv. een museumbezoek voor geschiedenis).',
    )
    is_doel_gfl = fields.Boolean(
        string='GFL',
        help='Gemeenschappelijke functionele leerlijn — vakoverschrijdend '
             'doel zoals samenwerken, kritisch denken, ...',
    )
    is_doel_ict = fields.Boolean(
        string='ICT',
        help='ICT-competenties aanvinken als de activiteit digitale '
             'vaardigheden traint (bv. workshop programmeren).',
    )
    is_doel_financieel = fields.Boolean(
        string='Financieel-economisch',
        help='Financieel-economische geletterdheid: aankoop, budget, '
             'consumentengedrag, banken, ...',
    )
    doelstellingen_toelichting = fields.Text(
        string='Leerplandoelstellingen — toelichting',
        help='Korte beschrijving van de doelstellingen die aansluiten bij '
             'de aangeduide categorieën.',
    )
    activity_type = fields.Selection([
        ('binnenschools', 'Binnenschoolse activiteit'),
        ('buitenschools', 'Buitenschoolse activiteit'),
    ], string='Type activiteit', tracking=True)
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
        domain="[('id', 'in', allowed_school_json)]",
    )
    school_company_id = fields.Many2one(
        'res.company', string='Bedrijf (school)',
        compute='_compute_school_company_id', store=True,
    )
    datetime = fields.Datetime(string='Startdatum en tijdstip')
    datetime_end = fields.Datetime(string='Einddatum en tijdstip')
    available_klas_ids = fields.Many2many(
        'myschool.org',
        compute='_compute_available_klas_ids',
        store=False,
    )
    klas_ids = fields.Many2many(
        'myschool.org',
        'myschool_activiteiten_record_klas_rel',
        'record_id', 'org_id',
        string='Klassen',
        domain="[('id', 'in', available_klas_ids)]",
    )
    available_leerkracht_ids = fields.Many2many(
        'myschool.person',
        compute='_compute_available_leerkracht_ids',
        store=False,
    )
    leerkracht_ids = fields.Many2many(
        'myschool.person',
        'myschool_activiteiten_record_leerkracht_rel',
        'record_id', 'person_id',
        string='Leerkrachten',
        domain="[('id', 'in', available_leerkracht_ids)]",
    )
    leerkracht_count = fields.Integer(
        string='Aantal leerkrachten',
        compute='_compute_leerkracht_count',
    )
    price = fields.Monetary(
        string='Geschatte kost', currency_field='currency_id',
        help='Voorlopige schatting van de totale kost (bus, toegang, ...). '
             'Directie gebruikt dit als indicatie bij de goedkeuring. De '
             'echte kost wordt later door boekhouding ingevuld op basis '
             'van de werkelijke facturen.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Valuta',
        default=lambda self: self.env.company.currency_id,
    )
    lokaal = fields.Char(string='Lokaal')
    locatie = fields.Char(string='Locatie')
    locatie_adres = fields.Char(string='Adres')
    is_active = fields.Boolean(string='Actief', default=True)
    state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Concept'),
        ('bus_check', 'Bus controle'),
        ('bus_refused', 'Bus geweigerd'),
        ('pending_approval', 'Wacht op goedkeuring'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('s_code', 'S-Code in te vullen'),
        ('vervanging', 'Vervanging inplannen'),
        ('aanwezigheid', 'Aanwezigheid registreren'),
        ('facturen', 'Facturen opstellen'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', required=True, tracking=True)

    vervoer_type = fields.Selection([
        ('bus', 'Bus (gehuurd via privé-maatschappij)'),
        ('openbaar_vervoer', 'Openbaar vervoer'),
        ('te_voet', 'Te voet'),
        ('fiets', 'Fiets'),
        ('auto', 'Met de wagen'),
        ('anders', 'Anders'),
    ], string='Vervoer',
       help='Hoe verplaatst de groep zich tijdens deze activiteit. '
            'Selectie van "Bus (gehuurd via privé-maatschappij)" triggert '
            'de bus-controle-flow met aankoop. Niet van toepassing voor '
            'binnenschoolse myschool_activiteiten.')
    bus_nodig = fields.Boolean(
        string='Bus nodig',
        default=False,
        help='Aan = bus moet door aankoop besteld worden vóór de '
             'activiteit kan goedgekeurd worden. Uit = ander vervoer '
             '(openbaar, te voet, fiets, wagen).',
    )

    @api.onchange('vervoer_type')
    def _onchange_vervoer_type(self):
        for record in self:
            record.bus_nodig = (record.vervoer_type == 'bus')

    @api.onchange('activity_type')
    def _onchange_activity_type_clear_bus(self):
        """Bij binnenschoolse activiteit is vervoer + bus niet relevant —
        forceer leeg zodat de bus-controle-flow niet ten onrechte triggert
        bij submit. Voor buitenschools laten we de waarden ongemoeid (de
        leerkracht kiest dan zelf het vervoer)."""
        for record in self:
            if record.activity_type == 'binnenschools':
                record.vervoer_type = False
                record.bus_nodig = False

    # --- Openbaar vervoer (PDF: De Lijn / Trein + aantallen reizigers) ---
    ov_type = fields.Selection([
        ('delijn', 'De Lijn — rittenkaart'),
        ('trein', 'Trein NMBS — GO-PASS / GROEPSTICKET'),
    ], string='Type openbaar vervoer',
       help='Subkeuze wanneer Vervoer = Openbaar vervoer. Bij trein moet de '
            'aanvrager 14 dagen vooraf een groepsticket bij de NMBS bestellen.')
    ov_gratis_count = fields.Integer(
        string='Aantal gratis reizigers',
        help='Aantal leerlingen dat gratis gebruik mag maken van het openbaar '
             'vervoer (bv. abonnement). Wordt op de klaslijst genoteerd en '
             'aan boekhouding bezorgd.',
    )
    ov_betalend_count = fields.Integer(
        string='Aantal betalende reizigers',
        help='Aantal leerlingen dat zelf een ticket moet betalen (geen '
             'abonnement). Boekhouding gebruikt dit aantal om de '
             'doorrekening per leerling correct op te maken.',
    )
    ov_totaal_reizigers = fields.Integer(
        string='Totaal aantal reizigers',
        compute='_compute_ov_totaal', store=True,
    )

    @api.depends('ov_gratis_count', 'ov_betalend_count')
    def _compute_ov_totaal(self):
        for record in self:
            record.ov_totaal_reizigers = (
                (record.ov_gratis_count or 0) + (record.ov_betalend_count or 0)
            )

    bus_price = fields.Monetary(
        string='Totale busprijs',
        currency_field='currency_id',
        compute='_compute_bus_price', store=True,
        help='Som van de prijzen per bus. Vul de prijs per bus in op de '
             'busverdeling-lijst hieronder.',
    )
    bus_available = fields.Boolean(
        string='Bus beschikbaar',
        help='Wordt door aankoop gezet wanneer de bus effectief gereserveerd '
             'is. Pas na deze bevestiging gaat de aanvraag verder naar '
             'directie voor goedkeuring.',
    )
    aantal_bussen = fields.Selection([
        ('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'),
        ('6', '6'), ('7', '7'), ('8', '8'), ('9', '9'), ('10', '10'),
    ], string='Aantal bussen', default='1',
        help='Standaard 1. Verhoog wanneer meer leerlingen meegaan dan '
             'in één bus passen, of wanneer aankoop meerdere bussen '
             'tegelijk wil bestellen. Per bus wordt een aparte regel '
             'voor de prijs aangemaakt onder Busverdeling.')
    bus_ids = fields.One2many(
        'myschool_activiteiten.bus', 'activiteit_id', string='Busverdeling',
    )

    @api.depends('bus_ids.prijs')
    def _compute_bus_price(self):
        for record in self:
            record.bus_price = sum(record.bus_ids.mapped('prijs'))

    @api.onchange('aantal_bussen')
    def _onchange_aantal_bussen(self):
        """UI-side: synchroniseer bus_ids met aantal_bussen door een nieuwe
        recordset op te bouwen — zo verwijdert Odoo de te-veel regels (zowel
        bestaande DB-records als NewId-records uit deze onchange-sessie)."""
        target = int(self.aantal_bussen or '1')
        sorted_buses = self.bus_ids.sorted(key=lambda b: b.bus_nummer)
        current = len(sorted_buses)

        if current == target:
            return

        # Bouw de nieuwe set commando's expliciet op zodat Odoo elke gewenste
        # bus-regel kent (en de overige eruit haalt).
        keep = sorted_buses[:target]
        commands = []
        for bus in keep:
            if isinstance(bus.id, int):
                # Bestaand DB-record: link + behoud zoals het is
                commands.append((4, bus.id))
            else:
                # NewId-record uit een eerdere onchange — heropbouwen zodat
                # de prijs-waarde niet verloren gaat
                commands.append((0, 0, {
                    'bus_nummer': bus.bus_nummer,
                    'prijs': bus.prijs or 0,
                }))

        # Voeg ontbrekende rijen toe als we hoger gaan
        if current < target:
            existing_nrs = set(keep.mapped('bus_nummer'))
            nr = 1
            while len([c for c in commands if c[0] in (0, 4)]) < target:
                if nr not in existing_nrs:
                    commands.append((0, 0, {'bus_nummer': nr}))
                    existing_nrs.add(nr)
                nr += 1

        # (5,) wist de relatie eerst, daarna voegen onze commando's de juiste
        # set weer toe. Dit zorgt dat te-veel regels écht verdwijnen uit het UI.
        self.bus_ids = [(5, 0, 0)] + commands

    def _sync_bus_lines(self):
        """Server-side helper voor write/action — gebruikt ORM-acties direct
        i.p.v. onchange-commands, zodat dit ook werkt bij batch-write of in
        submit-flow.

        sudo() is nodig omdat de leerkracht (personeelslid) zelf geen
        create/unlink-rechten heeft op myschool_activiteiten.bus, maar de bus-regels
        moeten wel klaargezet worden bij het indienen zodat aankoop later
        prijzen kan invullen.
        """
        self.ensure_one()
        target = int(self.aantal_bussen or '1')
        existing = self.bus_ids.sorted(key=lambda b: b.bus_nummer)
        current = len(existing)
        if current > target:
            existing[target:].sudo().unlink()
        elif current < target:
            existing_nrs = set(existing.mapped('bus_nummer'))
            nr = 1
            added = 0
            Bus = self.env['myschool_activiteiten.bus'].sudo()
            while added < target - current:
                if nr not in existing_nrs:
                    Bus.create({
                        'activiteit_id': self.id,
                        'bus_nummer': nr,
                    })
                    existing_nrs.add(nr)
                    added += 1
                nr += 1
    document_ids = fields.Many2many(
        'ir.attachment', string='Documenten',
    )
    document_notitie = fields.Html(
        string='Notitie bij documenten',
        sanitize=True,
        help='Vrije tekst — bv. een korte uitleg, of een link naar een '
             'Google Drive document of spreadsheet.',
    )
    s_code_name = fields.Char(
        string='S-Code',
        help='Boekhoudkundige S-Code voor deze activiteit (bv. S-1234). '
             'Wordt door boekhouding toegekend nadat de activiteit '
             'goedgekeurd is. Pas na bevestiging van deze code start '
             'de aanwezigheidsfase.',
    )
    s_code_price = fields.Monetary(
        string='S-Code bedrag',
        currency_field='currency_id',
        help='Effectief totaalbedrag dat onder deze S-Code valt. '
             'Wordt door boekhouding ingevuld.',
    )
    kosten_ids = fields.One2many(
        'myschool_activiteiten.kosten.line', 'activiteit_id',
        string='Kosten',
    )
    kosten_vast_ids = fields.One2many(
        'myschool_activiteiten.kosten.line', 'activiteit_id',
        string='Vaste kosten',
        domain=[('kosten_type', '=', 'vast')],
    )
    kosten_variabel_ids = fields.One2many(
        'myschool_activiteiten.kosten.line', 'activiteit_id',
        string='Variabele kosten',
        domain=[('kosten_type', '=', 'variabel')],
    )
    totale_kost = fields.Monetary(
        string='Totale kost',
        currency_field='currency_id',
        compute='_compute_totale_kost',
        store=True,
    )
    kost_vast_total = fields.Monetary(
        string='Vaste kosten totaal',
        currency_field='currency_id',
        compute='_compute_kost_per_leerling',
    )
    kost_variabel_total = fields.Monetary(
        string='Variabele kosten totaal',
        currency_field='currency_id',
        compute='_compute_kost_per_leerling',
    )
    kost_per_aanwezig = fields.Monetary(
        string='Per aanwezige leerling',
        currency_field='currency_id',
        compute='_compute_kost_per_leerling',
        help='Bedrag dat een leerling die mee was betaalt: vaste kosten '
             'verdeeld over alle opgegeven leerlingen, plus variabele '
             'kosten verdeeld over enkel de aanwezigen.',
    )
    kost_per_afwezig = fields.Monetary(
        string='Per afwezige leerling',
        currency_field='currency_id',
        compute='_compute_kost_per_leerling',
        help='Bedrag dat een afwezige leerling betaalt: enkel zijn aandeel '
             'in de vaste kosten (bus, verzekering, ...). Variabele kosten '
             '(toegang, gids, ...) vallen weg.',
    )
    kosten_display = fields.Html(
        string='Kosten overzicht',
        compute='_compute_kosten_display',
        sanitize=False,
    )
    bijdragen_regeling = fields.Boolean(
        string='Bijdragen regeling',
        default=True,
        help='Aan = de activiteit valt onder de schoolbijdragenregeling. '
             'In dat geval wordt de 2% annulatieverzekering NIET extra '
             'aangerekend bij meerdaagse uitstappen mét overnachting — '
             'die zit al in de bijdragenregeling vervat. Uit = de '
             'verzekering wordt apart aangerekend.',
    )
    bijdrageregeling_bedrag = fields.Monetary(
        string='Bedrag in bijdrageregeling',
        currency_field='currency_id',
        help='Concrete eurowaarde uit de bijdrageregeling voor deze activiteit.',
    )
    is_gratis = fields.Boolean(
        string='Gratis activiteit',
        default=False,
        help='Vink aan als deze activiteit volledig gratis is (geen bus, '
             'geen toegangsticket, geen kosten). De Kosten-stap wordt dan '
             'overgeslagen en boekhouding hoeft geen S-Code in te vullen.',
    )
    # Inkomgeld gestructureerd: prijs per persoon × aantal betalend = totaal
    inkomgeld_per_persoon = fields.Monetary(
        string='Inkomgeld per persoon',
        currency_field='currency_id',
        help='Inkomgeld per betalende deelnemer (bv. ticketprijs).',
    )
    inkomgeld_aantal_betalend = fields.Integer(
        string='Aantal betalende deelnemers',
        help='Aantal leerlingen of deelnemers dat inkomgeld moet betalen.',
    )
    inkomgeld_totaal = fields.Monetary(
        string='Inkomgeld totaal',
        currency_field='currency_id',
        compute='_compute_inkomgeld_totaal', store=True,
    )
    # Cash bedrag dat boekhouding minstens een week vooraf moet voorzien
    cash_bedrag_nodig = fields.Monetary(
        string='Cash benodigd',
        currency_field='currency_id',
        help='Bedrag aan cash geld dat de aanvrager nodig heeft. Minstens '
             'één week vóór de activiteit aan boekhouding aanvragen.',
    )
    # Overnachting flag — bepaalt of annulatieverzekering 2% nog wordt
    # toegepast (PDF zegt: enkel meerdaags MET overnachting).
    heeft_overnachting = fields.Boolean(
        string='Met overnachting',
        help='Aanvinken bij meerdaagse uitstappen waar leerlingen ter plaatse '
             'overnachten — triggert de annulatieverzekering bij '
             'S-Code bevestiging, tenzij Bijdragenregeling aangevinkt staat. '
             'Bij meerdaagse uitstappen zonder overnachting (bv. dag-tot-dag '
             'over middernacht) laat je dit uit.',
    )
    verzekering_done = fields.Boolean(string='Verzekering geregeld', default=False)
    reminder_aanwezigheid_sent_at = fields.Date(
        string='Laatste aanwezigheid-herinnering',
        help='Datum waarop de laatste reminder naar de leerkracht werd '
             'gestuurd. Wordt door de cron gebruikt om niet dagelijks '
             'te spammen.',
    )
    reminder_facturen_sent_at = fields.Date(
        string='Laatste facturen-herinnering',
        help='Datum waarop de laatste reminder naar boekhouding werd '
             'gestuurd.',
    )
    verzekering_pct = fields.Float(
        string='Verzekering %',
        default=2.0,
        digits=(5, 2),
        help='Percentage annulatieverzekering. Standaard 2%, maar boekhouding '
             'kan dit per activiteit aanpassen indien nodig (bv. duurder '
             'voor specifieke bestemmingen).',
    )

    @api.depends('inkomgeld_per_persoon', 'inkomgeld_aantal_betalend')
    def _compute_inkomgeld_totaal(self):
        for record in self:
            record.inkomgeld_totaal = (
                (record.inkomgeld_per_persoon or 0)
                * (record.inkomgeld_aantal_betalend or 0)
            )
    wizard_step = fields.Selection([
        ('1', 'Begeleiders'),
        ('2', 'Opmerkingen'),
        ('3', 'Kosten'),
        ('4', 'Documenten'),
    ], default='1', copy=False)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    invite_ids = fields.One2many(
        'myschool_activiteiten.invite', 'activiteit_id', string='Uitnodigingen',
    )
    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    snapshot_line_ids = fields.One2many(
        'myschool_activiteiten.snapshot.line', 'activiteit_id',
        string='Deelnemers snapshot',
    )
    snapshot_student_count = fields.Integer(
        string='Leerlingen (ingediend)',
        compute='_compute_snapshot_counts',
    )
    snapshot_leerkracht_count = fields.Integer(
        string='Leerkrachten (ingediend)',
        compute='_compute_snapshot_counts',
    )
    aanwezig_count = fields.Integer(
        string='Aanwezig',
        compute='_compute_aanwezig_count',
    )
    aanwezig_total = fields.Integer(
        string='Totaal',
        compute='_compute_aanwezig_count',
    )
    aanwezig_display = fields.Char(
        string='Aanwezigen',
        compute='_compute_aanwezig_count',
        help='Aantal aanwezige leerlingen / totaal aantal opgegeven leerlingen.',
    )
    is_owner = fields.Boolean(compute='_compute_is_owner')
    can_edit_s_code = fields.Boolean(
        compute='_compute_can_edit_s_code',
        help='True wanneer de huidige gebruiker de S-Code mag bewerken: '
             'enkel boekhouding/admin in de status S-Code controle.',
    )

    @api.depends_context('uid')
    @api.depends('state')
    def _compute_can_edit_s_code(self):
        is_boekhouding_or_admin = (
            self.env.user.has_group('myschool_activiteiten.group_activiteiten_boekhouding')
            or self.env.user.has_group('myschool_activiteiten.group_activiteiten_admin')
        )
        for record in self:
            record.can_edit_s_code = (
                is_boekhouding_or_admin and record.state == 's_code'
            )
    can_manage_invites = fields.Boolean(compute='_compute_can_manage_invites')
    display_state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Formulier invullen'),
        ('bus_check', 'Controle bus'),
        ('bus_refused', 'Bus geweigerd'),
        ('pending_approval', 'Wacht op goedkeuring'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('aanwezigheid', 'Aanwezigheid registreren'),
        ('done', 'Afgerond'),
    ], string='Status', compute='_compute_display_state')

    @api.depends('school_id')
    def _compute_school_company_id(self):
        companies = self.env['res.company'].sudo().search([('school_id', '!=', False)])
        school_to_company = {c.school_id.id: c.id for c in companies}
        for record in self:
            record.school_company_id = school_to_company.get(record.school_id.id, False)

    @api.depends('state')
    @api.depends_context('uid')
    def _compute_display_state(self):
        """Voor leerkrachten: backstage-states (S-Code, vervanging, facturen)
        afronden als "Goedgekeurd". Aanwezigheid blijft zichtbaar omdat zij
        die zelf moeten invullen."""
        is_manager = self.env.user.has_group('myschool_activiteiten.group_activiteiten_directie') or \
                     self.env.user.has_group('myschool_activiteiten.group_activiteiten_admin') or \
                     self.env.user.has_group('myschool_activiteiten.group_activiteiten_boekhouding') or \
                     self.env.user.has_group('myschool_activiteiten.group_activiteiten_vervangingen') or \
                     self.env.user.has_group('myschool_activiteiten.group_activiteiten_aankoop')
        backstage_states = ('s_code', 'vervanging', 'facturen')
        for record in self:
            if not is_manager and record.state in backstage_states:
                record.display_state = 'approved'
            else:
                record.display_state = record.state

    @api.depends('klas_ids')
    def _compute_student_count(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for record in self:
            if person_tree_type and record.klas_ids:
                record.student_count = PropRelation.search_count([
                    ('proprelation_type_id', '=', person_tree_type.id),
                    ('id_org', 'in', record.klas_ids.ids),
                    ('id_person', '!=', False),
                    ('is_active', '=', True),
                ])
            else:
                record.student_count = 0

    @api.depends('snapshot_line_ids')
    def _compute_snapshot_counts(self):
        for record in self:
            lines = record.snapshot_line_ids.filtered(lambda l: not l.date_to)
            record.snapshot_student_count = len(
                lines.filtered(lambda l: l.snapshot_type == 'student'))
            record.snapshot_leerkracht_count = len(
                lines.filtered(lambda l: l.snapshot_type == 'leerkracht'))

    @api.depends('snapshot_line_ids.aanwezig', 'snapshot_line_ids.snapshot_type')
    def _compute_aanwezig_count(self):
        for record in self:
            students = record.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == 'student' and not l.date_to)
            present = students.filtered('aanwezig')
            record.aanwezig_count = len(present)
            record.aanwezig_total = len(students)
            record.aanwezig_display = (
                f'{len(present)} / {len(students)}' if students else '-'
            )

    def action_aanwezigheid_alles_aan(self):
        """Vink alle leerlingen op aanwezig (snapshot)."""
        self.ensure_one()
        self.snapshot_line_ids.filtered(
            lambda l: l.snapshot_type == 'student').write({'aanwezig': True})

    def action_aanwezigheid_alles_uit(self):
        """Vink alle leerlingen op afwezig (snapshot)."""
        self.ensure_one()
        self.snapshot_line_ids.filtered(
            lambda l: l.snapshot_type == 'student').write({'aanwezig': False})

    def action_open_aanwezigheid(self):
        """Open de lijst-view om aanwezigheid te registreren."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Aanwezigheid — {self.name}',
            'res_model': 'myschool_activiteiten.snapshot.line',
            'view_mode': 'list',
            'domain': [
                ('activiteit_id', '=', self.id),
                ('snapshot_type', '=', 'student'),
                ('date_to', '=', False),
            ],
            'context': {
                'create': False,
                'delete': False,
                'default_activiteit_id': self.id,
            },
            'target': 'new',
        }

    def action_open_aanwezig_present(self):
        """Open de lijst van leerlingen die effectief mee zijn geweest."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Mee geweest — {self.name}',
            'res_model': 'myschool_activiteiten.snapshot.line',
            'view_mode': 'list',
            'domain': [
                ('activiteit_id', '=', self.id),
                ('snapshot_type', '=', 'student'),
                ('date_to', '=', False),
                ('aanwezig', '=', True),
            ],
            'context': {
                'create': False,
                'delete': False,
                'default_activiteit_id': self.id,
            },
            'target': 'new',
        }

    def action_open_aanwezig_total(self):
        """Open de lijst van alle opgegeven leerlingen (snapshot)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Opgegeven leerlingen — {self.name}',
            'res_model': 'myschool_activiteiten.snapshot.line',
            'view_mode': 'list',
            'domain': [
                ('activiteit_id', '=', self.id),
                ('snapshot_type', '=', 'student'),
                ('date_to', '=', False),
            ],
            'context': {
                'create': False,
                'delete': False,
                'default_activiteit_id': self.id,
            },
            'target': 'new',
        }

    def _get_current_students(self):
        """Get the current student person records for the selected classes."""
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not person_tree_type or not self.klas_ids:
            return self.env['myschool.person']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', person_tree_type.id),
            ('id_org', 'in', self.klas_ids.ids),
            ('id_person', '!=', False),
            ('is_active', '=', True),
        ])
        return rels.mapped('id_person')

    def _create_snapshot(self):
        """Create snapshot lines for current students and teachers."""
        SnapshotLine = self.env['myschool_activiteiten.snapshot.line']
        today = fields.Date.context_today(self)
        for record in self:
            # Remove old snapshot lines (fresh snapshot on each submit)
            record.snapshot_line_ids.sudo().unlink()
            vals_list = []
            # Students
            students = record._get_current_students()
            for student in students:
                vals_list.append({
                    'activiteit_id': record.id,
                    'person_id': student.id,
                    'snapshot_type': 'student',
                    'date_from': today,
                })
            # Teachers
            for teacher in record.leerkracht_ids:
                vals_list.append({
                    'activiteit_id': record.id,
                    'person_id': teacher.id,
                    'snapshot_type': 'leerkracht',
                    'date_from': today,
                })
            if vals_list:
                SnapshotLine.create(vals_list)

    def action_update_snapshot(self):
        """Update snapshot: mark people no longer in the class/activity."""
        today = fields.Date.context_today(self)
        for record in self:
            current_students = record._get_current_students()
            current_teachers = record.leerkracht_ids
            for line in record.snapshot_line_ids.filtered(lambda l: not l.date_to):
                if line.snapshot_type == 'student' and line.person_id not in current_students:
                    line.date_to = today
                elif line.snapshot_type == 'leerkracht' and line.person_id not in current_teachers:
                    line.date_to = today
            # Add new people that weren't in the snapshot yet
            existing_student_ids = record.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == 'student' and not l.date_to
            ).mapped('person_id').ids
            existing_teacher_ids = record.snapshot_line_ids.filtered(
                lambda l: l.snapshot_type == 'leerkracht' and not l.date_to
            ).mapped('person_id').ids
            vals_list = []
            for student in current_students:
                if student.id not in existing_student_ids:
                    vals_list.append({
                        'activiteit_id': record.id,
                        'person_id': student.id,
                        'snapshot_type': 'student',
                        'date_from': today,
                    })
            for teacher in current_teachers:
                if teacher.id not in existing_teacher_ids:
                    vals_list.append({
                        'activiteit_id': record.id,
                        'person_id': teacher.id,
                        'snapshot_type': 'leerkracht',
                        'date_from': today,
                    })
            if vals_list:
                self.env['myschool_activiteiten.snapshot.line'].create(vals_list)

    def _open_snapshot_wizard(self, snapshot_type):
        """Open the snapshot wizard for the given type."""
        self.ensure_one()
        # Auto-update snapshot when opening
        if self.state not in ('draft', 'form_invullen'):
            self.action_update_snapshot()
        wiz = self.env['myschool_activiteiten.snapshot.wizard'].create({
            'activiteit_id': self.id,
            'snapshot_type': snapshot_type,
        })
        label = 'Leerlingen' if snapshot_type == 'student' else 'Leerkrachten'
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'myschool_activiteiten.snapshot.wizard',
            'view_mode': 'form',
            'res_id': wiz.id,
            'target': 'new',
        }

    def action_open_snapshot_students(self):
        return self._open_snapshot_wizard('student')

    def action_open_snapshot_leerkrachten(self):
        return self._open_snapshot_wizard('leerkracht')

    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = not record.create_uid or record.create_uid.id == self.env.uid

    @api.depends_context('uid')
    def _compute_can_manage_invites(self):
        is_admin = self.env.user.has_group('myschool_activiteiten.group_activiteiten_admin')
        for record in self:
            record.can_manage_invites = is_admin or record.is_owner


    dates_display = fields.Html(
        string='Datum',
        compute='_compute_dates_display',
        sanitize=False,
    )

    @api.depends('datetime', 'datetime_end')
    def _compute_dates_display(self):
        wrap = '<span style="display:inline-flex;flex-wrap:wrap;gap:2px 4px;align-items:center">%s</span>'
        for record in self:
            if record.datetime and record.datetime_end:
                start = fields.Datetime.context_timestamp(record, record.datetime)
                end = fields.Datetime.context_timestamp(record, record.datetime_end)
                if start.date() == end.date():
                    parts = (
                        '<span>%s</span>'
                        '<span>%s</span>'
                        '<span>→</span>'
                        '<span>%s</span>'
                    ) % (
                        start.strftime('%d %b %Y'),
                        start.strftime('%H:%M'),
                        end.strftime('%H:%M'),
                    )
                else:
                    parts = (
                        '<span>%s</span>'
                        '<span>→</span>'
                        '<span>%s</span>'
                    ) % (
                        start.strftime('%d %b %Y %H:%M'),
                        end.strftime('%d %b %Y %H:%M'),
                    )
                record.dates_display = wrap % parts
            elif record.datetime:
                dt = fields.Datetime.context_timestamp(record, record.datetime)
                record.dates_display = wrap % ('<span>%s</span>' % dt.strftime('%d %b %Y %H:%M'))
            else:
                record.dates_display = ''

    def _get_verzekering_pct(self):
        """Geef het verzekering-percentage. Als het record zelf een waarde
        heeft (bv. boekhouding heeft het aangepast), gebruik die. Anders
        val terug op de globale config-parameter (default 2%)."""
        if self and self[:1].verzekering_pct:
            return self[:1].verzekering_pct
        pct = self.env['ir.config_parameter'].sudo().get_param(
            'myschool_activiteiten.verzekering_pct', '2.0')
        try:
            return float(pct)
        except (ValueError, TypeError):
            return 2.0

    def _get_details_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Extra info',
            'res_model': 'myschool_activiteiten.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('myschool_activiteiten.view_activiteiten_form_details').id, 'form')],
            'target': 'new',
        }

    def action_open_details(self):
        self.ensure_one()
        self.wizard_step = '1'
        return self._get_details_action()

    def action_open_details_step_1(self):
        self.ensure_one()
        self.wizard_step = '1'
        return self._get_details_action()

    def action_open_details_step_2(self):
        self.ensure_one()
        self.wizard_step = '2'
        return self._get_details_action()

    def action_open_details_step_3(self):
        self.ensure_one()
        self.wizard_step = '3'
        return self._get_details_action()

    def action_open_details_step_4(self):
        self.ensure_one()
        self.wizard_step = '4'
        return self._get_details_action()

    def action_wizard_next(self):
        self.ensure_one()
        next_step = {'1': '2', '2': '3', '3': '4'}.get(self.wizard_step)
        if next_step:
            self.wizard_step = next_step
        return self._get_details_action()

    def action_wizard_prev(self):
        self.ensure_one()
        prev_step = {'2': '1', '3': '2', '4': '3'}.get(self.wizard_step)
        if prev_step:
            self.wizard_step = prev_step
        return self._get_details_action()

    def action_submit_from_dialog(self):
        self.ensure_one()
        self.action_submit_form()
        return {'type': 'ir.actions.act_window_close'}

    @api.depends('kosten_ids.bedrag')
    def _compute_totale_kost(self):
        for record in self:
            record.totale_kost = sum(record.kosten_ids.mapped('bedrag'))

    @api.depends('kosten_ids.bedrag', 'kosten_ids.kosten_type',
                 'aanwezig_count', 'aanwezig_total')
    def _compute_kost_per_leerling(self):
        """Verdeel de kosten op basis van aanwezigheid.

        Vaste kosten (bus, verzekering, ...) worden gedragen door ALLE
        opgegeven leerlingen, ook de afwezigen — die betalen mee voor wat
        sowieso besteld werd. Variabele kosten (toegangsticket, gids per
        groep, ...) betalen alleen de aanwezigen — wie er niet bij was
        gebruikt niets.
        """
        for record in self:
            vast = sum(
                l.bedrag for l in record.kosten_ids
                if l.kosten_type == 'vast'
            )
            variabel = sum(
                l.bedrag for l in record.kosten_ids
                if l.kosten_type == 'variabel'
            )
            record.kost_vast_total = vast
            record.kost_variabel_total = variabel
            total = record.aanwezig_total
            present = record.aanwezig_count
            if total:
                vast_share = vast / total
            else:
                vast_share = 0
            if present:
                variabel_share = variabel / present
            else:
                variabel_share = 0
            record.kost_per_aanwezig = vast_share + variabel_share
            record.kost_per_afwezig = vast_share

    @api.onchange('bus_price', 'kosten_ids')
    def _onchange_recalculate_verzekering(self):
        pct = self._get_verzekering_pct() / 100.0
        verzekering_line = None
        other_total = 0
        for line in self.kosten_ids:
            if line.is_auto and 'Verzekering' in (line.omschrijving or ''):
                verzekering_line = line
            elif line.is_auto and line.omschrijving == 'Bus' and self.bus_price:
                line.bedrag = self.bus_price
                other_total += line.bedrag or 0
            else:
                other_total += line.bedrag or 0
        if verzekering_line:
            verzekering_line.bedrag = other_total * pct

    @api.depends('kosten_ids.bedrag', 'kosten_ids.omschrijving')
    def _compute_kosten_display(self):
        for record in self:
            lines = []
            for line in record.kosten_ids:
                lines.append('%s: € %.2f' % (line.omschrijving or '', line.bedrag or 0))
            record.kosten_display = '<br/>'.join(lines) if lines else ''

    @api.depends('school_id')
    def _compute_available_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        for record in self:
            if not record.school_id or not dept_type:
                record.available_klas_ids = False
                continue
            # Find lln departments under the school
            lln_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'lln'),
            ])
            lln_ids = lln_rels.mapped('id_org').ids
            if not lln_ids:
                record.available_klas_ids = False
                continue
            # Find all children of lln departments
            klas_rels = PropRel.search([
                ('id_org_parent', 'in', lln_ids),
                ('id_org', '!=', False),
            ])
            record.available_klas_ids = klas_rels.mapped('id_org')

    @api.depends('school_id')
    def _expand_org_descendants(self, root_org_ids):
        """Geef root_org_ids + alle descendants terug, gevonden via ORG-TREE
        proprelations (id_org_parent → id_org). Itereert breadth-first tot er
        geen nieuwe kinderen meer gevonden worden."""
        PropRel = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type or not root_org_ids:
            return list(root_org_ids)
        visited = set(root_org_ids)
        frontier = list(root_org_ids)
        while frontier:
            children_rels = PropRel.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', frontier),
                ('id_org', '!=', False),
            ])
            children_ids = children_rels.mapped('id_org').ids
            new_ids = [cid for cid in children_ids if cid not in visited]
            if not new_ids:
                break
            visited.update(new_ids)
            frontier = new_ids
        return list(visited)

    def _compute_available_leerkracht_ids(self):
        PropRel = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        OrgType = self.env['myschool.org.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        for record in self:
            if not record.school_id or not person_tree_type or not dept_type:
                record.available_leerkracht_ids = False
                continue
            # Find pers departments under the school
            pers_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'pers'),
            ])
            pers_ids = pers_rels.mapped('id_org').ids
            if not pers_ids:
                record.available_leerkracht_ids = False
                continue
            # Expand pers naar alle nakomelingen (lkr, adm, dir, ...) zodat
            # leerkrachten gekoppeld aan een sub-departement ook gevonden worden.
            org_ids = record._expand_org_descendants(pers_ids)
            # Find all persons linked to pers (or any descendant) via PERSON-TREE
            person_rels = PropRel.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_org', 'in', org_ids),
                ('id_person', '!=', False),
                ('is_active', '=', True),
            ])
            record.available_leerkracht_ids = person_rels.mapped('id_person')

    @api.depends('leerkracht_ids')
    def _compute_leerkracht_count(self):
        for record in self:
            record.leerkracht_count = len(record.leerkracht_ids)

    def action_view_leerkrachten(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerkrachten - {self.titel or self.name}',
            'res_model': 'myschool.person',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.leerkracht_ids.ids)],
            'context': {'create': False},
        }

    @api.constrains('datetime', 'datetime_end')
    def _check_datetime(self):
        now = fields.Datetime.now()
        for record in self:
            if record.datetime and record.datetime < now:
                raise UserError("De startdatum en tijdstip mag niet in het verleden liggen.")
            if record.datetime and record.datetime_end and record.datetime_end <= record.datetime:
                raise UserError("De einddatum en tijdstip moet na de startdatum en tijdstip liggen.")

    @api.onchange('school_id')
    def _onchange_school_id(self):
        self.klas_ids = [(5, 0, 0)]
        self.leerkracht_ids = [(5, 0, 0)]

    @api.depends('name', 'titel')
    def _compute_display_name(self):
        for record in self:
            if record.titel:
                record.display_name = f'{record.name} - {record.titel}'
            else:
                record.display_name = record.name or ''

    _rec_names_search = ['name', 'titel']

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'De referentie moet uniek zijn.'),
    ]

    def _auto_init(self):
        res = super()._auto_init()
        # Fix any existing records with missing references
        self.env.cr.execute("""
            SELECT id FROM myschool_activiteiten_record
            WHERE name IS NULL OR name IN ('', 'New', 'new')
        """)
        broken_ids = [r[0] for r in self.env.cr.fetchall()]
        if broken_ids:
            for record_id in broken_ids:
                ref = self.env['ir.sequence'].sudo().next_by_code('myschool_activiteiten.record')
                if ref:
                    self.env.cr.execute(
                        "UPDATE myschool_activiteiten_record SET name = %s WHERE id = %s",
                        (ref, record_id)
                    )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New' or not vals.get('name'):
                vals['name'] = self._next_reference()
            if vals.get('activity_type') and vals.get('state', 'draft') == 'draft':
                vals['state'] = 'form_invullen'
            # Houd bus_nodig synchroon met vervoer_type wanneer dat laatste
            # programmatisch gezet wordt zonder expliciete bus_nodig waarde.
            if 'vervoer_type' in vals and 'bus_nodig' not in vals:
                vals['bus_nodig'] = (vals.get('vervoer_type') == 'bus')
        records = super().create(vals_list)
        # Fix any records that still ended up without a proper reference
        for record in records:
            if not record.name or record.name == 'New':
                record.sudo().name = self._next_reference()
        # Auto-add the creator as a teacher with an accepted invite
        for record in records:
            person = self.env['myschool.person'].sudo().search(
                [('odoo_user_id', '=', record.create_uid.id)], limit=1)
            if person:
                record.sudo().leerkracht_ids = [(4, person.id)]
                self.env['myschool_activiteiten.invite'].sudo().create({
                    'activiteit_id': record.id,
                    'person_id': person.id,
                })
        return records

    def write(self, vals):
        if 'vervoer_type' in vals and 'bus_nodig' not in vals:
            vals['bus_nodig'] = (vals.get('vervoer_type') == 'bus')
        res = super().write(vals)
        for record in self:
            if not record.name or record.name == 'New':
                record.sudo().name = self._next_reference()
        # Sync bus_ids count met aantal_bussen wanneer dat aantal verandert.
        if 'aantal_bussen' in vals:
            for record in self:
                record._sync_bus_lines()
        return res

    def _next_reference(self):
        """Get next unique reference, syncing the sequence if needed."""
        last_record = self.sudo().search(
            [('name', 'like', 'ACT-')],
            order='name desc', limit=1,
        )
        last_number = 0
        if last_record:
            try:
                last_number = int(last_record.name.replace('ACT-', ''))
            except ValueError:
                pass
        # Search without company filter to find the sequence regardless
        seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'myschool_activiteiten.record'),
        ], limit=1)
        if not seq:
            seq = self.env['ir.sequence'].sudo().create({
                'name': 'Activiteiten',
                'code': 'myschool_activiteiten.record',
                'prefix': 'ACT-',
                'padding': 5,
                'number_next': last_number + 1,
                'number_increment': 1,
                'company_id': False,
            })
            _logger.info('[ACT] Auto-created ir.sequence for myschool_activiteiten.record')
        if seq.number_next <= last_number:
            seq.sudo().write({'number_next': last_number + 1})
        # Call _next() directly on the sequence to bypass company filtering
        ref = seq.sudo()._next()
        _logger.info('[ACT] Generated reference: %s', ref)
        return ref

    # --- Personeelslid actions ---

    @api.onchange('activity_type')
    def _onchange_activity_type(self):
        if self.activity_type and self.state == 'draft':
            self.state = 'form_invullen'

    def action_submit_form(self):
        for record in self:
            if record.state not in ('draft', 'form_invullen', 'bus_refused'):
                raise UserError("Het formulier kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een titel in.")
            if not record.datetime:
                raise UserError("Vul een datum en tijdstip in.")
            # Geen-kosten-waarschuwing: als de leerkracht geen enkele
            # kost ingegeven heeft EN geen "Gratis"-vinkje aangezet, dan
            # is dat waarschijnlijk een vergetelheid. Blokkeer met een
            # duidelijke melding die vraagt om expliciet te bevestigen.
            heeft_kosten = bool(record.kosten_ids) or bool(record.bus_price)
            if not heeft_kosten and not record.is_gratis:
                raise UserError(
                    "Er zijn geen kosten ingevuld. Als dit een gratis "
                    "activiteit is, vink dan 'Gratis activiteit' aan in "
                    "het hoofdformulier en dien opnieuw in. Zo niet, voeg "
                    "de kosten toe via Extra info → Kosten."
                )
            # Veiligheidsnet: binnenschoolse myschool_activiteiten hebben geen bus.
            # Een vergeten bus_nodig=True zou anders ten onrechte de bus-flow
            # triggeren.
            if record.activity_type == 'binnenschools':
                record.bus_nodig = False
                record.vervoer_type = False
            # Snapshot students and teachers at submission time
            record._create_snapshot()
            if record.bus_nodig:
                # Zorg dat er bus-regels klaar staan voor aankoop, één per
                # bus volgens aantal_bussen (default 1). Aankoop kan dan
                # meteen prijs per bus invullen.
                record._sync_bus_lines()
                record.state = 'bus_check'
            else:
                record.state = 'pending_approval'
        # _schedule_directie_activity() schedulet een todo per directie-user,
        # en Odoo stuurt zelf de notificatie-mail per assignment. Geen aparte
        # email_template_notify_directie meer nodig (had toch geen recipients).
        pending_records = self.filtered(lambda r: r.state == 'pending_approval')
        if pending_records:
            pending_records._schedule_directie_activity()

    # --- Aankoop actions ---

    def action_bus_approved(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = True
            record.state = 'pending_approval'
        # Mail naar leerkracht dat bus bevestigd is (heeft email_to → werkt).
        self._send_notification('bus_approved')
        # Activity per directie-user; Odoo stuurt automatisch per todo
        # een notificatie-mail. Geen aparte 'submit'-mail meer nodig.
        self._schedule_directie_activity()

    def action_bus_refused(self):
        for record in self:
            if record.state != 'bus_check':
                raise UserError("Bus controle is niet van toepassing.")
            record.bus_available = False
            record.state = 'bus_refused'
        self._send_notification('bus_refused')

    def action_open_busverdeling(self):
        self.ensure_one()
        # Auto-create bus records if they don't exist yet
        aantal = int(self.aantal_bussen or '1')
        existing = self.bus_ids.mapped('bus_nummer')
        for nr in range(1, aantal + 1):
            if nr not in existing:
                self.env['myschool_activiteiten.bus'].create({
                    'activiteit_id': self.id,
                    'bus_nummer': nr,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': f'Busverdeling — {self.name}',
            'res_model': 'myschool_activiteiten.bus',
            'view_mode': 'list,form',
            'domain': [('activiteit_id', '=', self.id)],
            'context': {
                'default_activiteit_id': self.id,
                'allowed_klas_ids': self.klas_ids.ids,
                'allowed_leerkracht_ids': self.leerkracht_ids.ids,
            },
        }

    # --- Directie actions ---

    def action_approve(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen goedgekeurd worden.")
            # Voeg alle uitgenodigde leerkrachten toe aan leerkracht_ids en breng hen op de hoogte
            persons_to_add = record.invite_ids.mapped('person_id').filtered(
                lambda p: p not in record.leerkracht_ids
            )
            if persons_to_add:
                record.write({
                    'leerkracht_ids': [(4, p.id) for p in persons_to_add],
                })
            record.invite_ids._notify_invited_person()
            record.state = 's_code'
        self._send_notification('approved')
        self._schedule_owner_approved_activity()
        self._schedule_boekhouding_activity()

    def action_reject(self):
        for record in self:
            if record.state != 'pending_approval':
                raise UserError("Alleen aanvragen in afwachting kunnen afgekeurd worden.")
            if not (record.rejection_reason or '').strip():
                raise UserError("Vul eerst een reden voor afkeuring in voordat u de aanvraag afkeurt.")
            record.state = 'rejected'
        self._send_notification('rejected')
        bus_records = self.filtered(lambda r: r.bus_nodig and r.bus_available)
        if bus_records:
            bus_records._schedule_aankoop_bus_vrijgekomen()

    # --- Boekhouding actions ---

    def _is_multiday(self):
        """Check if the activity spans 2 or more days."""
        self.ensure_one()
        if not self.datetime or not self.datetime_end:
            return False
        return self.datetime.date() != self.datetime_end.date()

    def action_confirm_s_code(self):
        pct = self._get_verzekering_pct()
        for record in self:
            if record.state != 's_code':
                raise UserError("S-Code kan alleen in de S-Code fase bevestigd worden.")
            if not record.s_code_name:
                raise UserError("Vul eerst de S-Code in.")
            # Remove any existing auto lines and recreate them
            auto_lines_to_remove = record.kosten_ids.filtered(lambda l: l.is_auto)
            if auto_lines_to_remove:
                auto_lines_to_remove.with_context(force_unlink_auto=True).unlink()
            auto_lines = []
            if record.bus_price:
                auto_lines.append({
                    'activiteit_id': record.id,
                    'omschrijving': 'Bus',
                    'bedrag': record.bus_price,
                    'kosten_type': 'vast',
                    'is_auto': True,
                })
            # Annulatieverzekering — enkel bij meerdaagse uitstappen MET
            # overnachting EN als de bijdragenregeling NIET aangevinkt is.
            # Bijdragenregeling dekt de annulatieverzekering al af, dus geen
            # dubbel aanrekenen.
            if (record._is_multiday() and record.heeft_overnachting
                    and not record.bijdragen_regeling):
                manual_total = sum(
                    l.bedrag for l in record.kosten_ids if not l.is_auto)
                basis_bedrag = (record.bus_price or 0) + manual_total
                verzekering_bedrag = basis_bedrag * (pct / 100.0)
                auto_lines.append({
                    'activiteit_id': record.id,
                    'omschrijving': 'Verzekering (%.1f%%)' % pct,
                    'bedrag': verzekering_bedrag,
                    'kosten_type': 'vast',
                    'is_auto': True,
                })
                record.verzekering_done = True
            else:
                record.verzekering_done = False
            if auto_lines:
                self.env['myschool_activiteiten.kosten.line'].create(auto_lines)
            # Nieuwe workflow: na S-code-bevestiging gaan we rechtstreeks naar
            # 'aanwezigheid'. De leerkracht vult aanwezigheid in, en daarna
            # is het aan boekhouding om facturen op te stellen.
            record.state = 'aanwezigheid'
        self._schedule_vervangingen_activity()

    def action_aanwezigheid_klaar(self):
        """Leerkracht heeft de aanwezigheid ingevuld → state naar 'facturen'."""
        for record in self:
            if record.state != 'aanwezigheid':
                raise UserError(
                    "Aanwezigheid kan alleen afgesloten worden vanuit de aanwezigheid-fase."
                )
            record.state = 'facturen'

    def action_kosten_afsluiten(self):
        """Boekhouding sluit de kosten af → state naar 'done'.
        Pas vanaf hier kunnen de kosten niet meer aangepast worden."""
        for record in self:
            if record.state not in ('facturen', 'aanwezigheid'):
                raise UserError(
                    "Kosten kunnen pas afgesloten worden nadat de S-code is toegekend."
                )
            record.state = 'done'

    # --- Shared actions ---

    def action_reset_to_form(self):
        """Zet een afgekeurde of bus-geweigerde aanvraag terug op invul-state
        zodat de leerkracht alle velden (hoofdform én extra info) opnieuw
        kan aanpassen. De gebruiker bepaalt zelf wanneer hij/zij via
        'Volgende' naar de wizard gaat om opnieuw in te dienen."""
        for record in self:
            if record.state not in ('rejected', 'bus_refused'):
                raise UserError(
                    "Alleen afgekeurde of bus-geweigerde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'form_invullen'
            record.rejection_reason = False

    def _check_done(self):
        for record in self:
            if record.verzekering_done:
                record.state = 'done'

    def write(self, vals):
        res = super().write(vals)
        # bus_price is een computed-stored field op basis van bus_ids.prijs.
        # Wijzigingen aan bus_price komen dus binnen via bus_ids of via een
        # directe write hier — in beide gevallen herberekenen.
        if 'bus_price' in vals or 'bus_ids' in vals:
            self._recalculate_auto_lines()
        return res

    def _recalculate_auto_lines(self):
        pct = self._get_verzekering_pct() / 100.0
        for record in self:
            record.invalidate_recordset(['kosten_ids'])
            verzekering_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and 'Verzekering' in (l.omschrijving or ''))
            bus_line = record.kosten_ids.filtered(
                lambda l: l.is_auto and l.omschrijving == 'Bus')
            if bus_line and record.bus_price:
                bus_line.write({'bedrag': record.bus_price})
            if not verzekering_line:
                continue
            other_total = sum(
                l.bedrag for l in record.kosten_ids if l.id != verzekering_line.id)
            verzekering_line.write({'bedrag': other_total * pct})

    def unlink(self):
        is_admin = self.env.user.has_group('myschool_activiteiten.group_activiteiten_admin')
        for record in self:
            if not is_admin:
                if record.state not in ('draft', 'form_invullen'):
                    raise UserError("U kunt alleen aanvragen verwijderen die nog niet ingediend zijn.")
                if record.create_uid.id != self.env.uid:
                    raise UserError("U kunt alleen uw eigen aanvragen verwijderen.")
        return super().unlink()

    def action_delete(self):
        self.unlink()
        # Generieke client-action die terugkeert naar de vorige controller
        # zodat filters/sortering/scroll behouden blijven (zie myschool_core).
        return {
            'type': 'ir.actions.client',
            'tag': 'myschool_back_to_previous',
            'params': {
                'fallback_action': 'myschool_activiteiten.action_activiteiten_main',
            },
        }

    def _schedule_owner_approved_activity(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            if record.create_uid:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Activiteit goedgekeurd',
                    note=f'Uw activiteit "{record.titel}" is goedgekeurd.',
                    user_id=record.create_uid.id,
                )

    def _schedule_vervangingen_activity(self):
        vervangingen_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        vervangingen_users = vervangingen_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in vervangingen_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging inplannen via Planner',
                    note=f'De S-Code voor activiteit "{record.titel}" is ingevuld. '
                         f'Maak een inhaalplan aan in de Planner en dien het in om de vervanging af te ronden.',
                    user_id=user.id,
                )

    def _notify_vervangingen_new_invites(self, invites):
        """Notify vervangingen team when new teachers are invited after activity is past approval."""
        vervangingen_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        vervangingen_users = vervangingen_group.user_ids
        if not vervangingen_users:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        names = ', '.join(invites.mapped('person_id.name'))
        for record in self:
            partner_ids = vervangingen_users.mapped('partner_id').ids
            record.message_post(
                body=(
                    '<p><strong>Vervanging update:</strong> Nieuwe uitnodiging(en) verstuurd '
                    'voor activiteit <strong>%s</strong> aan: %s. '
                    'De vervanging moet mogelijk aangepast worden.</p>'
                ) % (record.titel, names),
                partner_ids=partner_ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            for user in vervangingen_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging aanpassen: %s' % record.titel,
                    note='Nieuwe leerkracht(en) uitgenodigd: %s. Controleer de vervanging.' % names,
                    user_id=user.id,
                )

    def _schedule_directie_activity(self):
        directie_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_directie', raise_if_not_found=False)
        if not directie_group:
            return
        directie_users = directie_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in directie_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Activiteit goedkeuren',
                    note=f'Er is een nieuwe aanvraag "{record.titel}" ingediend door {record.create_uid.name}. Gelieve deze te beoordelen.',
                    user_id=user.id,
                )

    def _schedule_boekhouding_activity(self):
        boekhouding_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_boekhouding', raise_if_not_found=False)
        if not boekhouding_group:
            return
        boekhouding_users = boekhouding_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in boekhouding_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='S-Code invullen',
                    note=f'De activiteit "{record.titel}" is goedgekeurd. Gelieve de S-Code in te vullen.',
                    user_id=user.id,
                )

    def _schedule_aankoop_bus_vrijgekomen(self):
        aankoop_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_aankoop', raise_if_not_found=False)
        if not aankoop_group:
            return
        aankoop_users = aankoop_group.user_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in aankoop_users:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Bus vrijgekomen',
                    note=f'De activiteit "{record.titel}" is afgekeurd. De bus die hiervoor was gereserveerd is weer beschikbaar.',
                    user_id=user.id,
                )

    _NOTIFICATION_TEMPLATES = {
        'submit': 'myschool_activiteiten.email_template_notify_directie',
        'approved': 'myschool_activiteiten.email_template_approved',
        'rejected': 'myschool_activiteiten.email_template_rejected',
        'bus_refused': 'myschool_activiteiten.email_template_bus_refused',
        'bus_approved': 'myschool_activiteiten.email_template_bus_approved',
        'reminder_aanwezigheid': 'myschool_activiteiten.email_template_reminder_aanwezigheid',
        'reminder_facturen': 'myschool_activiteiten.email_template_reminder_facturen',
    }

    def _get_reminder_days(self, key, default):
        """Lees configureerbaar aantal dagen uit ir.config_parameter."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            f'myschool_activiteiten.{key}', default)
        try:
            return int(param)
        except (ValueError, TypeError):
            return default

    @api.model
    def _auto_archive_old_done(self, cutoff_date):
        """Markeer afgeronde myschool_activiteiten ouder dan cutoff_date als inactief.
        Wordt aangeroepen door de centrale auto-archive cron in
        myschool_core. Records blijven in de DB, maar verdwijnen uit de
        standaardlijst (filter "Inclusief gearchiveerd" toont ze terug)."""
        records = self.search([
            ('state', '=', 'done'),
            ('is_active', '=', True),
            ('datetime', '<', cutoff_date),
        ])
        if records:
            records.write({'is_active': False})
        return len(records)

    @api.model
    def _cron_reminder_aanwezigheid(self):
        """Stuur reminder naar de aanvrager X dagen na het einde van de
        activiteit als aanwezigheid nog niet ingevuld is.
        Herhaalt elke 7 dagen zolang state == 'aanwezigheid'."""
        days_after = self._get_reminder_days('reminder_aanwezigheid_days', 3)
        repeat_interval = self._get_reminder_days('reminder_repeat_days', 7)
        today = fields.Date.today()
        cutoff = fields.Datetime.now() - timedelta(days=days_after)
        records = self.search([
            ('state', '=', 'aanwezigheid'),
            ('datetime_end', '<=', cutoff),
        ])
        for rec in records:
            last = rec.reminder_aanwezigheid_sent_at
            if last and (today - last).days < repeat_interval:
                continue
            rec._send_notification('reminder_aanwezigheid')
            rec.reminder_aanwezigheid_sent_at = today

    @api.model
    def _cron_reminder_facturen(self):
        """Stuur reminder naar boekhouding X dagen nadat een activiteit in
        de facturen-fase zit. Eén mail per record, naar alle boekhouders
        van de school van de activiteit."""
        days_after = self._get_reminder_days('reminder_facturen_days', 7)
        repeat_interval = self._get_reminder_days('reminder_repeat_days', 7)
        today = fields.Date.today()
        cutoff = today - timedelta(days=days_after)
        records = self.search([
            ('state', '=', 'facturen'),
            ('write_date', '<=', cutoff),
        ])
        for rec in records:
            last = rec.reminder_facturen_sent_at
            if last and (today - last).days < repeat_interval:
                continue
            rec._notify_boekhouding_facturen()
            rec.reminder_facturen_sent_at = today

    def _notify_boekhouding_facturen(self):
        """Stuur de facturen-herinnering naar elke boekhoudgebruiker. Anders
        dan _send_notification (die naar de aanvrager stuurt), gaat deze
        naar de hele boekhouding-groep."""
        self.ensure_one()
        template = self.env.ref(
            'myschool_activiteiten.email_template_reminder_facturen',
            raise_if_not_found=False)
        if not template:
            return
        boekhouding_group = self.env.ref(
            'myschool_activiteiten.group_activiteiten_boekhouding',
            raise_if_not_found=False)
        if not boekhouding_group:
            return
        partners = boekhouding_group.user_ids.mapped('partner_id').filtered('email')
        if not partners:
            return
        try:
            # Chatter-nota
            rendered = template._render_template(
                template.body_html, template.render_model, [self.id],
                engine='inline_template', options={'post_process': True})
            body = rendered.get(self.id, '')
            if body:
                self.message_post(
                    body=Markup(body), subtype_xmlid='mail.mt_note',
                    partner_ids=partners.ids)
        except Exception as e:
            _logger.warning(
                'Failed to render facturen-reminder for %s: %s', self.name, e)
        if not self.env['ir.mail_server'].sudo().search_count([('active', '=', True)]):
            return
        try:
            template.send_mail(
                self.id,
                force_send=False,
                email_values={
                    'email_to': ','.join(p.email for p in partners),
                    'recipient_ids': [(6, 0, partners.ids)],
                },
            )
        except Exception as e:
            _logger.warning(
                'Failed to queue facturen-reminder for %s: %s', self.name, e)

    def _send_notification(self, notification_type):
        """Verstuur een mail naar de aanvrager (en plaats een chatter-nota
        op het record). Defensief: skip als geen geldig e-mailadres of geen
        outgoing mailserver. force_send=False zodat de mail in de queue
        komt en SMTP-fouten de actie niet blokkeren."""
        template_xmlid = self._NOTIFICATION_TEMPLATES.get(notification_type)
        if not template_xmlid:
            return
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        has_mail_server = self.env['ir.mail_server'].sudo().search_count([('active', '=', True)])
        for record in self:
            # 1) Chatter-nota — altijd, zodat de history zichtbaar is
            try:
                rendered = template._render_template(
                    template.body_html, template.render_model, [record.id],
                    engine='inline_template',
                    options={'post_process': True},
                )
                body = rendered.get(record.id, '')
                if body:
                    record.message_post(body=Markup(body), subtype_xmlid='mail.mt_note')
            except Exception as e:
                _logger.warning('Failed to render chatter note %s for %s: %s',
                                template_xmlid, record.name, e)
            # 2) Echte mail naar de aanvrager — enkel als er een mailserver is
            if not has_mail_server:
                continue
            recipient_partner = record.create_uid.partner_id
            recipient = (recipient_partner.email or record.create_uid.email or '').strip()
            if not recipient:
                _logger.info('Skipping mail %s for activiteit %s: aanvrager has no email',
                             template_xmlid, record.name)
                continue
            try:
                # Forceer de ontvanger via email_values — de template's eigen
                # email_to-veld kan leeg zijn of niet correct renderen, dus
                # we zetten het hier expliciet zodat de mail niet zonder
                # geadresseerde in de queue belandt.
                template.send_mail(
                    record.id,
                    force_send=False,
                    email_values={
                        'email_to': recipient,
                        'recipient_ids': [(6, 0, recipient_partner.ids)] if recipient_partner else False,
                    },
                )
            except Exception as e:
                _logger.warning('Failed to queue mail %s for activiteit %s: %s',
                                template_xmlid, record.name, e)
