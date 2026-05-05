import ast
import logging

import requests

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geocoding & route-distance helpers (Nominatim + OSRM, beide gratis/no-key)
# ---------------------------------------------------------------------------
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
OSRM_URL = 'https://router.project-osrm.org/route/v1/driving'
HTTP_USER_AGENT = 'OLVP-MySchool-Odoo/1.0 (ict@olvp.be)'
HTTP_TIMEOUT = 10


def _geocode_address(query):
    """Vraagt Nominatim om lat/lon voor `query`. Returnt (lat, lon) of (0, 0)."""
    if not query or not query.strip():
        return 0.0, 0.0
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'be'},
            headers={'User-Agent': HTTP_USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        _logger.warning('Nominatim geocoding failed for %r: %s', query, e)
    return 0.0, 0.0


def _osrm_distance_km(lat1, lon1, lat2, lon2):
    """Vraagt OSRM om de wegafstand in km tussen twee punten. Returnt 0.0 bij fout."""
    if not all([lat1, lon1, lat2, lon2]):
        return 0.0
    try:
        url = f'{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}'
        resp = requests.get(
            url,
            params={'overview': 'false'},
            headers={'User-Agent': HTTP_USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json()
        if data.get('routes'):
            return round(data['routes'][0]['distance'] / 1000.0, 1)
    except Exception as e:
        _logger.warning('OSRM routing failed (%s,%s -> %s,%s): %s',
                        lat1, lon1, lat2, lon2, e)
    return 0.0


class ProfessionaliseringAddress(models.Model):
    _name = 'professionalisering.address'
    _description = 'Professionalisering Adres / Locatie'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'organization, name'

    name = fields.Char(string='Naam locatie', required=True, tracking=True,
                       help='bv. "Sint-Baafshuis Gent", "Boogkeers 5, Antwerpen", "Online"')
    organization = fields.Char(string='Organisatie / Aanbieder',
                               help='bv. "Katholiek Onderwijs Vlaanderen", "CNO", "VVKSO"')
    is_online = fields.Boolean(string='Online / Webinar', default=False,
                               help='Voor online opleidingen, webinars, Teams-sessies, ...')
    # Location address
    street = fields.Char(string='Straat')
    number = fields.Char(string='Nr.')
    postal_code = fields.Char(string='Postcode')
    city = fields.Char(string='Gemeente')
    country_id = fields.Many2one(
        'res.country', string='Land',
        default=lambda self: self.env['res.country'].search([('code', '=', 'BE')], limit=1),
    )
    # Billing address (per organisatie)
    billing_street = fields.Char(string='Facturatieadres',
                                 help='Adres voor facturatie (per organisatie).')
    billing_postal_code = fields.Char(string='Facturatiepostcode')
    billing_city = fields.Char(string='Facturatiegemeente')
    note = fields.Char(string='Opmerking', help='Optionele info, bv. zaalnaam of verdieping.')
    display_address = fields.Char(
        string='Volledig adres', compute='_compute_display_address', store=True,
    )
    active = fields.Boolean(default=True)
    needs_review = fields.Boolean(
        string='Te bevestigen door directie',
        default=False,
        tracking=True,
        help='Toegevoegd door een medewerker via de adres-picker. '
             'Directie moet de details (straat, postcode, ...) aanvullen.',
    )
    latitude = fields.Float(string='Lat', digits=(10, 7), copy=False)
    longitude = fields.Float(string='Lon', digits=(10, 7), copy=False)

    def _geocode_query(self):
        """Bouwt een query voor Nominatim op basis van straat + nr + postcode + gemeente."""
        self.ensure_one()
        if self.is_online:
            return ''
        parts = [
            f'{self.street or ""} {self.number or ""}'.strip(),
            f'{self.postal_code or ""} {self.city or ""}'.strip(),
        ]
        return ', '.join(p for p in parts if p)

    def action_geocode(self):
        """Manueel of automatisch — geocodeer dit adres via Nominatim."""
        for rec in self:
            if rec.is_online:
                continue
            query = rec._geocode_query()
            if not query:
                continue
            lat, lon = _geocode_address(query)
            if lat and lon:
                rec.write({'latitude': lat, 'longitude': lon})
        return True

    def action_mark_reviewed(self):
        """Door directie aangeklikt om de placeholder als bevestigd te markeren."""
        for rec in self:
            rec.needs_review = False
            # Sluit eventuele openstaande activiteiten af
            rec.activity_ids.filtered(
                lambda a: a.activity_type_id.xml_id == 'mail.mail_activity_data_todo'
            ).action_done()
        return True

    def _notify_directie_for_review(self, source_record=None):
        """Stuur TODO-activity + clickable bus-popup naar directie zodat ze het adres kunnen aanvullen.
        De bus-popup gebruikt een aangepast kanaal zodat we een knop kunnen toevoegen die
        direct de gefilterde lijst opent."""
        directie_group = self.env.ref(
            'professionalisering.group_professionalisering_directie',
            raise_if_not_found=False,
        )
        if not directie_group:
            return
        # URL naar de gefilterde-variant action — heeft een hard-coded domain dus
        # automatisch alleen 'needs_review' records.
        list_url = (
            '/odoo/action-professionalisering.action_professionalisering_addresses_review'
        )
        for rec in self:
            if source_record and source_record.school_id:
                directie_users = directie_group.user_ids.filtered(
                    lambda u: source_record.school_id in u.school_ids
                )
            else:
                directie_users = directie_group.user_ids
            origin = (
                f' voor de aanvraag "{source_record.titel}" van {source_record.employee_id.name}'
                if source_record else ''
            )
            note = (
                f'Een nieuw adres is via de picker toegevoegd{origin}: '
                f'<strong>{rec.name}</strong>'
                f'{f" — organisatie: {rec.organization}" if rec.organization else ""}.'
                f'<br/>Gelieve straat, postcode en gemeente aan te vullen en te bevestigen.'
                f'<br/><a href="{list_url}" class="btn btn-primary btn-sm mt-2">'
                f'Open de te bevestigen adressen</a>'
            )
            for user in directie_users:
                rec.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary='Adres aanvullen / bevestigen',
                    note=note,
                )
                # Aangepast bus-kanaal — JS-listener toont notif met "Naar adressen"-knop
                self.env['bus.bus']._sendone(
                    user.partner_id,
                    'professionalisering_address_review',
                    {
                        'title': 'Nieuw adres toegevoegd',
                        'message': f'"{rec.name}" wacht op bevestiging.',
                    },
                )
            if source_record:
                rec.sudo().message_post(
                    body=note,
                    subtype_xmlid='mail.mt_note',
                )

    @api.depends('street', 'number', 'postal_code', 'city', 'is_online')
    def _compute_display_address(self):
        for rec in self:
            if rec.is_online:
                rec.display_address = 'Online'
                continue
            line1 = ' '.join(p for p in [rec.street, rec.number] if p)
            line2 = ' '.join(p for p in [rec.postal_code, rec.city] if p)
            rec.display_address = ', '.join(p for p in [line1, line2] if p)

    @api.depends('name', 'organization', 'city', 'is_online')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.organization:
                parts.append(rec.organization)
            if rec.is_online:
                parts.append('Online')
            elif rec.name:
                label = rec.name
                if rec.city and rec.city.lower() not in label.lower():
                    label = f'{label} ({rec.city})'
                parts.append(label)
            elif rec.city:
                parts.append(rec.city)
            rec.display_name = ' — '.join(parts) or '—'

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Zoekt over naam + organisatie + gemeente + postcode + straat + nummer
        zodat 'Antwerpen', 'CNO', '9000', 'Boogkeers' allemaal werken."""
        if name and operator in ('ilike', '=ilike', '=', 'like', '=like'):
            search_domain = ['|', '|', '|', '|', '|',
                ('name', operator, name),
                ('organization', operator, name),
                ('city', operator, name),
                ('postal_code', operator, name),
                ('street', operator, name),
                ('number', operator, name),
            ]
            if domain:
                search_domain = ['&'] + search_domain + list(domain)
            records = self.search(search_domain, limit=limit)
            return [(r.id, r.display_name) for r in records]
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

    def _get_picker(self):
        Picker = self.env['professionalisering.address.picker']
        picker_id = self.env.context.get('picker_id')
        picker = Picker.browse(picker_id) if picker_id else Picker
        if not picker.exists():
            picker = Picker.search(
                [('create_uid', '=', self.env.uid)],
                order='id desc', limit=1,
            )
        if not picker:
            raise UserError("Geen actieve picker-sessie gevonden.")
        return picker

    def action_select_for_picker(self):
        """Stap 2 — selecteert dit adres en sluit de wizard met bevestiging."""
        self.ensure_one()
        picker = self._get_picker()
        picker.address_id = self.id
        return picker.action_confirm()

    def action_select_organization_for_picker(self):
        """Stap 1 — gebruikt de organisatie van dit adres en gaat naar stap 2."""
        self.ensure_one()
        picker = self._get_picker()
        return picker.action_select_organization(self.organization)


class MyschoolOrgGeocoded(models.Model):
    """Voegt lat/lon toe aan myschool.org zodat we afstand kunnen berekenen."""
    _inherit = 'myschool.org'

    latitude = fields.Float(string='Lat', digits=(10, 7), copy=False)
    longitude = fields.Float(string='Lon', digits=(10, 7), copy=False)

    def action_geocode(self):
        for rec in self:
            parts = [
                f'{rec.street or ""} {rec.street_nr or ""}'.strip(),
                f'{rec.postal_code or ""} {rec.community or ""}'.strip(),
            ]
            query = ', '.join(p for p in parts if p)
            if not query:
                continue
            lat, lon = _geocode_address(query)
            if lat and lon:
                rec.sudo().write({'latitude': lat, 'longitude': lon})
        return True


class HrEmployeeProfessionalisering(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('professionalisering_directie_search'):
            return self.sudo().with_context(professionalisering_directie_search=False).name_search(
                name=name, domain=domain, operator=operator, limit=limit)
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _get_action_dict(self):
        result = super()._get_action_dict()
        if result.get('res_model') == 'professionalisering.record':
            raw_ctx = result.get('context') or '{}'
            if isinstance(raw_ctx, str):
                try:
                    ctx = ast.literal_eval(raw_ctx)
                except (ValueError, SyntaxError):
                    ctx = {}
            else:
                ctx = dict(raw_ctx)
            if not any(k.startswith('search_default_') for k in ctx):
                user = self.env.user
                if user.has_group('professionalisering.group_professionalisering_admin'):
                    pass
                elif user.has_group('professionalisering.group_professionalisering_boekhouding'):
                    ctx['search_default_state_done'] = 1
                elif user.has_group('professionalisering.group_professionalisering_directie'):
                    pass
                elif user.has_group('professionalisering.group_professionalisering_vervangingen'):
                    ctx['search_default_replacement_pending'] = 1
                else:
                    ctx['search_default_my_requests'] = 1
                result['context'] = ctx
        return result


class ProfessionaliseringRecord(models.Model):
    _name = 'professionalisering.record'
    _description = 'Professionalisering'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'myschool.allowed.schools.mixin']

    def _auto_init(self):
        res = super()._auto_init()
        Sequence = self.env['ir.sequence'].sudo()
        if not Sequence.with_context(active_test=False).search_count([('code', '=', 'professionalisering.record')]):
            Sequence.create({
                'name': 'Professionalisering',
                'code': 'professionalisering.record',
                'prefix': 'PR-',
                'padding': 5,
                'number_next': 1,
                'number_increment': 1,
                'implementation': 'standard',
                'company_id': False,
            })
        return res

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    type = fields.Selection([
        ('individueel', 'Individuele'),
        # ('teamleren', 'Teamleren'), # tijdelijk uitgeschakeld
    ], string='Type', required=True, default='individueel')
    subtype_individueel = fields.Selection([
        ('nascholing', 'Nascholing'),
        ('lezen', 'Lezen'),
        ('video', 'Video'),
        ('podcast', 'Podcast'),
    ], string='Vorm')
    subtype_teamleren = fields.Selection([
        ('plc', 'Professional Learning Community (PLC)'),
        ('samen_studie', 'Samen studie'),
        ('intervisie', 'Intervisie'),
        ('co_teaching', 'Co-teaching'),
    ], string='Vorm')
    titel = fields.Char(string='Titel opleiding')
    location_type = fields.Selection([
        ('address', 'Op locatie'),
        ('online', 'Online'),
    ], string='Type locatie', default='address')
    address_id = fields.Many2one(
        'professionalisering.address',
        string='Adres / Locatie',
        domain="[('is_online', '=', False)]",
        help='Kies een bestaand adres of typ een nieuw adres in.',
    )
    afstand_km = fields.Float(
        string='Afstand (km)',
        compute='_compute_afstand_km',
        store=True,
        digits=(10, 1),
        help='Wegafstand heen en terug tussen de school en de locatie (via OSRM).',
    )
    link = fields.Char(
        string='Link',
        help='URL naar de video of podcast (optioneel).',
    )
    invite_ids = fields.One2many('professionalisering.invite', 'professionalisering_id', string='Uitnodigingen')
    wizard_step = fields.Selection([
        ('1', 'Datums'),
        ('2', 'Motivatie'),
    ], default='1', copy=False)
    show_invites = fields.Boolean(compute='_compute_show_invites')
    description = fields.Text(string='Beschrijving (legacy)')

    # Gestructureerde motivatie (vervangt het oude vrije description-veld)
    motivatie_aanleiding = fields.Text(
        string='Aanleiding',
        help='Wat triggerde deze keuze voor professionalisering?',
    )
    motivatie_doelstelling = fields.Text(
        string='Doelstelling',
        help='Wat wil je concreet behalen met deze opleiding?',
    )
    motivatie_toepassing = fields.Text(
        string='Toepassing',
        help='Hoe ga je het geleerde in de praktijk brengen?',
    )
    motivatie_effect = fields.Text(
        string='Verwacht effect op leerlingen',
        help='Wat zou deze opleiding moeten opleveren voor de klas / leerlingen?',
    )

    # Vervoersmiddel — hoe ga je naar de opleiding
    vervoersmiddel = fields.Selection([
        ('auto_alleen', 'Met de wagen (alleen)'),
        ('auto_carpool', 'Met de wagen (carpool)'),
        ('trein', 'Trein'),
        ('fiets', 'Fiets'),
        ('ov', 'Openbaar vervoer (bus/tram/metro)'),
        ('te_voet', 'Te voet'),
        ('andere', 'Andere'),
    ], string='Vervoersmiddel',
        help='Hoe ga je naar de opleiding?')
    # Legacy carpool Boolean — blijft bestaan voor backwards-compat. Wordt door
    # @api.onchange gesynchroniseerd met vervoersmiddel.
    carpool = fields.Boolean(
        string='Carpool',
        help='True als gebruiker carpoolt naar de opleiding.',
    )
    carpool_employee_ids = fields.Many2many(
        'hr.employee',
        'professionalisering_carpool_rel',
        'professionalisering_id', 'employee_id',
        string='Carpool met',
        help='Collega(s) waarmee je samen rijdt.',
    )

    @api.onchange('vervoersmiddel')
    def _onchange_vervoersmiddel(self):
        self.carpool = self.vervoersmiddel == 'auto_carpool'
        if self.vervoersmiddel != 'auto_carpool':
            self.carpool_employee_ids = [(5,)]
    employee_id = fields.Many2one(
        'hr.employee',
        string='Medewerker',
        required=True,
        default=lambda self: self.env.user.employee_ids[:1],
    )
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        required=True,
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
        domain="[('id', 'in', allowed_school_json)]",
    )
    school_company_id = fields.Many2one(
        'res.company', string='Bedrijf (school)',
        compute='_compute_school_company_id', store=True,
    )
    is_owner = fields.Boolean(compute='_compute_is_owner', compute_sudo=True)
    is_admin = fields.Boolean(compute='_compute_is_admin')
    can_edit_s_code = fields.Boolean(
        compute='_compute_can_edit_s_code',
        help='True wanneer de huidige gebruiker de S-Code mag bewerken: '
             'enkel boekhouding/admin in de fases waarin S-Code relevant is.',
    )

    @api.depends_context('uid')
    @api.depends('state')
    def _compute_can_edit_s_code(self):
        is_boekhouding_or_admin = (
            self.env.user.has_group('professionalisering.group_professionalisering_boekhouding')
            or self.env.user.has_group('professionalisering.group_professionalisering_admin')
        )
        for record in self:
            record.can_edit_s_code = (
                is_boekhouding_or_admin
                and record.state in ('bevestiging', 'bewijs', 'done')
            )
    is_directie = fields.Boolean(compute='_compute_is_directie')
    allowed_directie_json = fields.Json(compute='_compute_allowed_directie_json')
    start_date = fields.Date(string='Startdatum')
    end_date = fields.Date(string='Einddatum')
    duur = fields.Selection([
        ('hele_dag', 'Hele dag'),
        ('voormiddag', 'Voormiddag'),
        ('namiddag', 'Namiddag'),
        ('meerdere_dagen', 'Meerdere dagen'),
    ], string='Duur', default='hele_dag', required=True)
    verschillende_dagen = fields.Boolean(
        string='Niet-aaneensluitende dagen',
        help='Vink aan voor losstaande dagen, bv. 4 woensdagen verspreid over enkele weken.',
    )
    date_line_ids = fields.One2many('professionalisering.date.line', 'professionalisering_id', string='Datums')
    dates_display = fields.Html(string='Datums', compute='_compute_dates_display', sanitize=False)
    currency_id = fields.Many2one(
        'res.currency', string='Munteenheid',
        default=lambda self: self.env.company.currency_id,
    )
    total_cost = fields.Monetary(
        string='Totale kost', currency_field='currency_id',
        compute='_compute_total_cost',
        help='Totaal van eventuele losstaande dagen-kosten. Geschatte kost is verwijderd: de werkelijke kost komt uit het bewijsdocument.',
    )
    s_code_name = fields.Char(string='S-Code')
    s_code_price = fields.Monetary(
        string='S-Code bedrag', currency_field='currency_id',
    )
    kosten_ids = fields.One2many(
        'professionalisering.kosten.line', 'professionalisering_id',
        string='Kosten',
    )
    totale_kost = fields.Monetary(
        string='Totale kost (S-Code + extra)',
        currency_field='currency_id',
        compute='_compute_totale_kost',
    )
    vak_id = fields.Many2one(
        'professionalisering.vak',
        string='Vak',
        ondelete='restrict',
    )
    vak_is_other = fields.Boolean(
        related='vak_id.is_other', string='Vak is "Andere"',
    )
    vak_andere = fields.Char(
        string='Vermelding vak',
        help='Specificeer het vak of geef een korte toelichting bij "Andere".',
    )
    state = fields.Selection([
        ('selection_of_form', 'Concept'),
        ('fill_in_form_individueel', 'Goed te keuren'),
        ('fill_in_form_teamleren', 'Goed te keuren'),
        ('bevestiging', 'Goedgekeurd'),
        ('bewijs', 'Bewijs'),
        ('weigering', 'Afgekeurd'),
        ('done', 'Afgerond'),
    ], string='Status', default='selection_of_form', tracking=True)
    rejection_reason = fields.Text(string='Reden voor afkeuring')
    assigned_to = fields.Many2one(
        'hr.employee',
        string='Toegewezen aan',
        tracking=True,
        domain="[('id', 'in', allowed_directie_json)]",
        context={'professionalisering_directie_search': True},
    )
    directie_id = fields.Many2one(
        'hr.employee',
        string='Beoordeeld door',
        readonly=True,
    )
    payment_done = fields.Boolean(string='Betaling bevestigd', default=False)
    bewijs_link = fields.Char(string='Link (video, podcast, ...)')
    bewijs_beschrijving = fields.Text(string='Beschrijving bewijs')
    bewijs_document_ids = fields.Many2many(
        'ir.attachment', string='Documenten',
        help='Upload een attest, certificaat of ander bewijs.',
    )
    bewijs_ingediend = fields.Boolean(string='Bewijs ingediend', default=False)
    needs_approval = fields.Boolean(compute='_compute_needs_approval')
    needs_payment = fields.Boolean(compute='_compute_needs_payment')
    vorm_display = fields.Char(string='Vorm', compute='_compute_vorm_display')

    @api.depends('school_id')
    def _compute_school_company_id(self):
        companies = self.env['res.company'].sudo().search([('school_id', '!=', False)])
        school_to_company = {c.school_id.id: c.id for c in companies}
        for record in self:
            record.school_company_id = school_to_company.get(record.school_id.id, False)

    @api.depends_context('uid')
    def _compute_allowed_directie_json(self):
        group = self.env.ref('professionalisering.group_professionalisering_directie', raise_if_not_found=False)
        if group:
            employees = self.env['hr.employee'].sudo().search([
                ('user_id', 'in', group.all_user_ids.ids),
            ])
            ids = employees.ids
        else:
            ids = []
        for record in self:
            record.allowed_directie_json = ids

    @api.depends('type', 'subtype_individueel')
    def _compute_show_invites(self):
        for record in self:
            record.show_invites = (
                record.type == 'teamleren'
                or (record.type == 'individueel'
                    and record.subtype_individueel == 'nascholing')
            )

    # Subtypes that skip directie approval and go straight to done
    _NO_APPROVAL_SUBTYPES = ('lezen', 'video', 'podcast')
    # Subtypes that require S-Code / payment confirmation
    _PAYMENT_SUBTYPES = ('nascholing',)

    @api.depends('type', 'subtype_individueel')
    def _compute_needs_approval(self):
        for record in self:
            record.needs_approval = not (
                record.type == 'individueel'
                and record.subtype_individueel in self._NO_APPROVAL_SUBTYPES
            )

    @api.depends('type', 'subtype_individueel')
    def _compute_needs_payment(self):
        for record in self:
            record.needs_payment = (
                record.type == 'individueel'
                and record.subtype_individueel in self._PAYMENT_SUBTYPES
            )

    @api.depends('type', 'subtype_individueel', 'subtype_teamleren')
    def _compute_vorm_display(self):
        ind_labels = dict(self._fields['subtype_individueel'].selection)
        team_labels = dict(self._fields['subtype_teamleren'].selection)
        for record in self:
            if record.type == 'individueel' and record.subtype_individueel:
                record.vorm_display = ind_labels.get(record.subtype_individueel, '')
            elif record.type == 'teamleren' and record.subtype_teamleren:
                record.vorm_display = team_labels.get(record.subtype_teamleren, '')
            else:
                record.vorm_display = ''

    @api.onchange('type')
    def _onchange_type(self):
        self.subtype_individueel = False
        self.subtype_teamleren = False

    @api.onchange('duur')
    def _onchange_duur(self):
        if self.duur != 'meerdere_dagen':
            self.verschillende_dagen = False
            self.end_date = False

    @api.onchange('location_type')
    def _onchange_location_type(self):
        if self.location_type == 'online':
            self.address_id = False

    @api.depends('employee_id')
    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = record.employee_id and record.employee_id.user_id == self.env.user

    @api.depends_context('uid')
    def _compute_is_admin(self):
        is_admin = self.env.user.has_group('professionalisering.group_professionalisering_admin')
        for record in self:
            record.is_admin = is_admin

    @api.depends_context('uid')
    def _compute_is_directie(self):
        is_directie = self.env.user.has_group('professionalisering.group_professionalisering_directie')
        for record in self:
            record.is_directie = is_directie

    @api.depends('school_id', 'school_id.latitude', 'school_id.longitude',
                 'address_id', 'address_id.latitude', 'address_id.longitude',
                 'location_type', 'address_id.is_online')
    def _compute_afstand_km(self):
        """Berekent de wegafstand (km) tussen school en locatie via OSRM.
        Geocodeert lazy als lat/lon nog niet ingevuld zijn."""
        for record in self:
            if record.location_type == 'online' or not record.address_id or not record.school_id:
                record.afstand_km = 0
                continue
            if record.address_id.is_online:
                record.afstand_km = 0
                continue
            school = record.school_id
            addr = record.address_id
            # Lazy-geocode wanneer nog geen coördinaten
            if not (school.latitude and school.longitude):
                school.sudo().action_geocode()
            if not (addr.latitude and addr.longitude):
                addr.sudo().action_geocode()
            if school.latitude and addr.latitude:
                # Heen en terug = enkele afstand × 2
                one_way = _osrm_distance_km(
                    school.latitude, school.longitude,
                    addr.latitude, addr.longitude,
                )
                record.afstand_km = round(one_way * 2, 1)
            else:
                record.afstand_km = 0

    def action_recompute_afstand(self):
        """Knop om afstand te (her)berekenen — forceert ook re-geocoding."""
        for rec in self:
            if rec.address_id and not rec.address_id.is_online:
                rec.address_id.sudo().action_geocode()
            if rec.school_id:
                rec.school_id.sudo().action_geocode()
            rec._compute_afstand_km()
        return True

    @api.depends('verschillende_dagen', 'start_date', 'end_date', 'date_line_ids.date', 'date_line_ids.cost')
    def _compute_dates_display(self):
        for record in self:
            if record.verschillende_dagen:
                all_dates = []
                if record.start_date:
                    all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                        record.start_date.strftime('%d %b %Y'), record.cost or 0,
                    ))
                for line in record.date_line_ids.sorted('date'):
                    if line.date:
                        all_dates.append('%s &nbsp;-&nbsp; €%.2f' % (
                            line.date.strftime('%d %b %Y'), line.cost or 0,
                        ))
                record.dates_display = '<br/>'.join(all_dates)
            elif record.start_date and record.end_date and record.end_date != record.start_date:
                record.dates_display = '%s → %s' % (
                    record.start_date.strftime('%d %b %Y'),
                    record.end_date.strftime('%d %b %Y'),
                )
            elif record.start_date:
                record.dates_display = record.start_date.strftime('%d %b %Y')
            else:
                record.dates_display = ''

    @api.depends('verschillende_dagen', 'date_line_ids.cost')
    def _compute_total_cost(self):
        for record in self:
            if record.verschillende_dagen:
                record.total_cost = sum(record.date_line_ids.mapped('cost'))
            else:
                record.total_cost = 0

    @api.depends('s_code_price', 'kosten_ids.bedrag')
    def _compute_totale_kost(self):
        for record in self:
            record.totale_kost = (record.s_code_price or 0) + sum(record.kosten_ids.mapped('bedrag'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code('professionalisering.record')
                if not sequence:
                    raise UserError("Sequentie 'professionalisering.record' niet gevonden.")
                vals['name'] = sequence
        return super().create(vals_list)

    @api.model
    def _get_submitted_states(self):
        return ['fill_in_form_individueel', 'fill_in_form_teamleren']

    def action_submit(self):
        type_state_map = {
            'individueel': 'fill_in_form_individueel',
            'teamleren': 'fill_in_form_teamleren',
        }
        needs_notification = self.env['professionalisering.record']
        for record in self:
            if record.state != 'selection_of_form':
                raise UserError("Alleen conceptaanvragen kunnen ingediend worden.")
            if not record.type:
                raise UserError("Selecteer eerst een type professionalisering.")
            # Types that skip approval go straight to bewijs (user can upload bewijs)
            if not record.needs_approval:
                record.state = 'bewijs'
                record._schedule_bewijs_activity_single()
            else:
                new_state = type_state_map.get(record.type)
                record.state = new_state
                needs_notification |= record
        if needs_notification:
            needs_notification._send_notification('professionalisering.email_template_notify_directie')
            needs_notification._notify_directie_popup()

    def _get_details_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Extra info',
            'res_model': 'professionalisering.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('professionalisering.view_professionalisering_form_details').id, 'form')],
            'target': 'new',
        }

    def action_open_details(self):
        self.ensure_one()
        self.wizard_step = '1'
        return self._get_details_action()

    def action_wizard_next(self):
        self.ensure_one()
        next_step = {'1': '2'}.get(self.wizard_step)
        if next_step:
            self.wizard_step = next_step
        return self._get_details_action()

    def action_wizard_prev(self):
        self.ensure_one()
        prev_step = {'2': '1'}.get(self.wizard_step)
        if prev_step:
            self.wizard_step = prev_step
        return self._get_details_action()

    def action_submit_from_dialog(self):
        self.ensure_one()
        self._validate_for_submit()
        self.action_submit()
        return {'type': 'ir.actions.act_window_close'}

    def _validate_for_submit(self):
        """Server-side check op alle 'verplichte' velden bij indienen.
        Tijdens drafting hoeven ze niet ingevuld te zijn — pas bij indienen
        wordt alles gecontroleerd."""
        self.ensure_one()
        # Zorg dat eventueel openstaande UI-wijzigingen (bv. motivatie-velden uit
        # de wizard-dialog) écht naar DB geschreven zijn voor we ze valideren.
        self.flush_recordset()
        missing = []
        if not (self.titel or '').strip():
            missing.append("Titel opleiding")
        if self.vak_id.is_other and not (self.vak_andere or '').strip():
            missing.append("Vermelding vak")
        # Adres alleen verplicht voor nascholing of teamleren met "Op locatie"
        needs_address = (
            self.location_type == 'address'
            and (self.subtype_individueel == 'nascholing' or self.type == 'teamleren')
        )
        if needs_address and not self.address_id:
            missing.append("Adres / Locatie")
        # Datum-validatie
        not_a_reading = self.subtype_individueel not in ('lezen', 'video', 'podcast')
        if not_a_reading:
            if self.duur == 'meerdere_dagen' and self.verschillende_dagen:
                if not self.date_line_ids:
                    missing.append("Minstens één datum (Datums-tab)")
            else:
                if not self.start_date:
                    missing.append("Startdatum")
                if self.duur == 'meerdere_dagen' and not self.end_date:
                    missing.append("Einddatum")
        # Motivatie: minstens één van de 4 gestructureerde velden invullen
        # (legacy `description` blijft als fallback voor oude records).
        # Strip whitespace zodat enkel-spaties niet meetellen.
        motivatie_values = [
            (self.motivatie_aanleiding or '').strip(),
            (self.motivatie_doelstelling or '').strip(),
            (self.motivatie_toepassing or '').strip(),
            (self.motivatie_effect or '').strip(),
            (self.description or '').strip(),
        ]
        if not any(motivatie_values):
            missing.append(
                "Motivatie — vul minstens één van de 4 velden in "
                "(Aanleiding, Doelstelling, Toepassing, Verwacht effect)"
            )
        if missing:
            raise UserError(
                "De volgende velden moeten ingevuld zijn voor het indienen:\n• "
                + "\n• ".join(missing)
            )

    def action_open_address_picker(self):
        self.ensure_one()
        # Maak de picker direct aan zodat zijn id beschikbaar is in de m2m-rij-buttons.
        picker = self.env['professionalisering.address.picker'].create({
            'record_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Geavanceerd kiezen',
            'res_model': 'professionalisering.address.picker',
            'res_id': picker.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_approve(self):
        submitted_states = self._get_submitted_states()
        for record in self:
            if record.state not in submitted_states:
                raise UserError("Alleen ingediende aanvragen kunnen goedgekeurd worden.")
            record.directie_id = self.env.user.employee_ids[:1]
            # Notify all invited colleagues now that directie has approved
            record.invite_ids._notify_invited_employee()
            record.state = 'bevestiging'
            # Bewijs activity is scheduled later (via _cron_advance_to_bewijs)
            # when the start_date has passed.
            # Inform boekhouding about new approved professionalisering with costs
            if record.needs_payment:
                record._notify_boekhouding_new()
        self._send_notification('professionalisering.email_template_notify_employee_approved')
        self._schedule_vervangingen_activity()

    def _notify_boekhouding_new(self):
        """Inform boekhouding via activity that a new approved professionalisering exists."""
        self.ensure_one()
        boekhouding_group = self.env.ref(
            'professionalisering.group_professionalisering_boekhouding',
            raise_if_not_found=False,
        )
        if not boekhouding_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for user in boekhouding_group.user_ids:
            self.activity_schedule(
                activity_type_id=activity_type.id if activity_type else False,
                summary='Nieuwe professionalisering goedgekeurd: %s' % self.titel,
                note=(
                    'Een nieuwe professionalisering is goedgekeurd door directie. '
                    'Geschatte kost: %s. Controleer of er financiële opvolging nodig is.'
                ) % (self.total_cost or 0),
                user_id=user.id,
            )

    def action_reject(self):
        submitted_states = self._get_submitted_states()
        for record in self:
            if record.state not in submitted_states:
                raise UserError("Alleen ingediende aanvragen kunnen afgekeurd worden.")
            if not (record.rejection_reason or '').strip():
                raise UserError("Vul eerst een reden voor afkeuring in voordat u de aanvraag afkeurt.")
            record.state = 'weigering'
            record.directie_id = self.env.user.employee_ids[:1]
        self._send_notification('professionalisering.email_template_notify_employee_rejected')

    def action_reset_draft(self):
        for record in self:
            if record.state != 'weigering':
                raise UserError("Alleen afgekeurde aanvragen kunnen opnieuw ingediend worden.")
            record.state = 'selection_of_form'
            record.rejection_reason = False
            record.directie_id = False

    def _schedule_bewijs_activity(self):
        """Notify the owner to upload proof after completion."""
        for record in self:
            record._schedule_bewijs_activity_single()

    def _schedule_bewijs_activity_single(self):
        """Schedule bewijs activity for a single record."""
        self.ensure_one()
        if not self.employee_id.user_id:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        self.activity_schedule(
            activity_type_id=activity_type.id if activity_type else False,
            summary='Bewijs uploaden: %s' % self.titel,
            note='Uw professionalisering "%s" is afgerond. '
                 'Gelieve een bewijs te uploaden (attest, link naar video/podcast, ...).' % self.titel,
            user_id=self.employee_id.user_id.id,
        )

    def action_submit_bewijs(self):
        for record in self:
            if record.state not in ('bevestiging', 'bewijs'):
                raise UserError("Bewijs kan alleen ingediend worden vanaf de status 'Goedgekeurd'.")
            subtype = record.subtype_individueel
            if subtype in ('video', 'podcast') and not record.bewijs_link:
                raise UserError("Voeg een link toe als bewijs.")
            elif subtype == 'lezen' and not record.bewijs_beschrijving:
                raise UserError("Voeg een beschrijving toe als bewijs.")
            elif subtype == 'nascholing' and not record.bewijs_document_ids:
                raise UserError("Upload een attest of certificaat als bewijs.")
            elif record.type == 'teamleren' and not record.bewijs_beschrijving and not record.bewijs_document_ids:
                raise UserError("Voeg een verslag of document toe als bewijs.")
            record.bewijs_ingediend = True
            record.state = 'done'
            # Mark the bewijs activity as done
            activities = record.activity_ids.filtered(
                lambda a: a.user_id == record.employee_id.user_id
                and 'Bewijs uploaden' in (a.summary or '')
            )
            activities.action_done()

    @api.model
    def _cron_advance_to_bewijs(self):
        """Move records from 'bevestiging' (Goedgekeurd) to 'bewijs' once the
        last training date has passed, and schedule the bewijs upload activity."""
        today = fields.Date.today()
        records = self.search([('state', '=', 'bevestiging')])
        for rec in records:
            last_date = rec._latest_training_date()
            if last_date and last_date < today:
                rec.state = 'bewijs'
                rec._schedule_bewijs_activity_single()

    def _latest_training_date(self):
        """Return the latest date of the training (start_date or last date_line)."""
        self.ensure_one()
        if self.verschillende_dagen and self.date_line_ids:
            return max(self.date_line_ids.mapped('date'))
        return self.start_date

    def _schedule_vervangingen_activity(self):
        vervangingen_group = self.env.ref(
            'professionalisering.group_professionalisering_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in vervangingen_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging inplannen via Planner',
                    note='De professionalisering "%s" van %s is goedgekeurd. '
                         'Maak een vervangingsplan aan in de Planner.' % (record.titel, record.employee_id.name),
                    user_id=user.id,
                )

    @api.constrains('date_line_ids', 'start_date')
    def _check_date_lines(self):
        today = fields.Date.context_today(self)
        for record in self:
            for line in record.date_line_ids:
                if record.start_date and line.date < record.start_date:
                    raise ValidationError(
                        f"Datum {line.date.strftime('%d/%m/%Y')} ligt vóór de startdatum "
                        f"({record.start_date.strftime('%d/%m/%Y')}). Verwijder deze datum of pas de startdatum aan."
                    )
                if line.date < today:
                    raise ValidationError(
                        f"Datum {line.date.strftime('%d/%m/%Y')} ligt in het verleden. "
                        f"Elke datum moet vandaag of in de toekomst liggen."
                    )

    @api.constrains('start_date', 'end_date', 'verschillende_dagen')
    def _check_end_date(self):
        for record in self:
            if not record.verschillende_dagen and record.end_date and record.start_date:
                if record.end_date < record.start_date:
                    raise ValidationError("De einddatum moet op of na de startdatum liggen.")

    def action_delete(self):
        self.unlink()
        # Roep de generieke JS-client-action op die de gebruiker terugzet op
        # de vorige controller in de breadcrumb-stack. Op die manier blijven
        # alle frontend-filters (ook handmatig aangezette zoals "Concept"),
        # sortering, scrollpositie en groeperingen behouden.
        return {
            'type': 'ir.actions.client',
            'tag': 'myschool_back_to_previous',
            'params': {
                'fallback_action': 'professionalisering.action_professionalisering_main',
            },
        }

    def action_open_add_date_wizard(self):
        """Open een eenvoudige datum-dialog om snel een losse datum toe te voegen."""
        self.ensure_one()
        wiz = self.env['professionalisering.add.date.wizard'].create({
            'record_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Datum toevoegen',
            'res_model': 'professionalisering.add.date.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _send_notification(self, template_xmlid):
        """Verstuur een mail-template naar de medewerker. Defensief:
        - Skip als de medewerker geen geldig e-mailadres heeft
        - Skip als geen actieve uitgaande mailserver geconfigureerd is
        - force_send=False: mail komt in de queue (geen blocking popups bij SMTP-fouten)"""
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        has_mail_server = self.env['ir.mail_server'].sudo().search_count([('active', '=', True)])
        for record in self:
            recipient = (record.employee_id.work_email
                         or record.employee_id.user_id.email
                         or '')
            if not recipient:
                _logger.info(
                    'Skipping mail %s for prof %s: no recipient email',
                    template_xmlid, record.name,
                )
                continue
            if not has_mail_server:
                _logger.info(
                    'Skipping mail %s for prof %s: no outgoing mail server configured',
                    template_xmlid, record.name,
                )
                continue
            try:
                template.send_mail(record.id, force_send=False)
            except Exception as e:
                _logger.warning('Failed to queue mail %s for prof %s: %s',
                                template_xmlid, record.name, e)

    def _notify_directie_popup(self):
        """Send a popup notification to directie users of the same school."""
        directie_group = self.env.ref(
            'professionalisering.group_professionalisering_directie', raise_if_not_found=False)
        if not directie_group:
            return
        for record in self:
            directie_users = directie_group.user_ids.filtered(
                lambda u: record.school_id in u.school_ids
            )
            for user in directie_users:
                record.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary='Nieuwe aanvraag professionalisering',
                    note='%s heeft een aanvraag ingediend: "%s". Gelieve deze te beoordelen.' % (
                        record.employee_id.name, record.titel),
                )
                # Send bus notification for instant popup
                self.env['bus.bus']._sendone(
                    user.partner_id,
                    'simple_notification',
                    {
                        'title': 'Nieuwe professionalisering aanvraag',
                        'message': '%s heeft "%s" ingediend ter goedkeuring.' % (
                            record.employee_id.name, record.titel),
                        'type': 'warning',
                        'sticky': True,
                    },
                )


class ProfessionaliseringInvite(models.Model):
    _name = 'professionalisering.invite'
    _description = 'Professionalisering Uitnodiging'
    _inherit = ['mail.thread']
    _rec_name = 'employee_id'

    professionalisering_id = fields.Many2one(
        'professionalisering.record', required=True, ondelete='cascade',
    )
    professionalisering_titel = fields.Char(
        related='professionalisering_id.titel', string='Opleiding',
    )
    professionalisering_state = fields.Selection(
        related='professionalisering_id.state', string='Status aanvraag',
    )
    invited_by = fields.Many2one(
        related='professionalisering_id.employee_id', string='Uitgenodigd door',
    )
    employee_id = fields.Many2one(
        'hr.employee.public', string='Collega', required=True,
    )
    employee_school_names = fields.Char(
        string='School', compute='_compute_employee_school_names',
    )
    @api.depends('employee_id.user_id.school_ids')
    def _compute_employee_school_names(self):
        for invite in self:
            schools = invite.employee_id.user_id.school_ids
            names = []
            for s in schools:
                name = s.name or ''
                if ',' in name:
                    name = name.split(',', 1)[1].strip()
                names.append(name)
            invite.employee_school_names = ', '.join(n for n in names if n)

    def _notify_invited_employee(self):
        """Send an Odoo notification (chatter) to the invited employee — only after directie approval."""
        for invite in self:
            if not invite.employee_id.user_id:
                continue
            prof = invite.professionalisering_id
            prof.message_post(
                body=(
                    '<p>Beste %s,</p>'
                    '<p>U bent door <strong>%s</strong> opgegeven voor de opleiding '
                    '<strong>%s</strong>, en de directie heeft dit goedgekeurd.</p>'
                ) % (invite.employee_id.name, prof.employee_id.name, prof.titel),
                partner_ids=invite.employee_id.user_id.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )


class ProfessionaliseringKostenLine(models.Model):
    _name = 'professionalisering.kosten.line'
    _description = 'Professionalisering Kostenlijn'

    professionalisering_id = fields.Many2one(
        'professionalisering.record', string='Professionalisering',
        required=True, ondelete='cascade',
    )
    omschrijving = fields.Char(string='Omschrijving', required=True)
    bedrag = fields.Monetary(string='Bedrag', currency_field='currency_id')
    currency_id = fields.Many2one(related='professionalisering_id.currency_id')
    is_auto = fields.Boolean(string='Automatisch', default=False)

    def unlink(self):
        if not self.env.context.get('force_unlink_auto') and self.filtered('is_auto'):
            raise UserError("Automatische kostenlijnen (bv. Verzekering) kunnen niet verwijderd worden.")
        return super().unlink()


class ProfessionaliseringDateLine(models.Model):
    _name = 'professionalisering.date.line'
    _description = 'Professionalisering Datum'
    _order = 'date'

    professionalisering_id = fields.Many2one('professionalisering.record', required=True, ondelete='cascade')
    professionalisering_titel = fields.Char(related='professionalisering_id.titel', string='Professionalisering')
    date = fields.Date(string='Datum', required=True)
    cost = fields.Float(string='Kost (€)')

    @api.constrains('date', 'professionalisering_id')
    def _check_unique_date_per_record(self):
        for line in self:
            if not line.date or not line.professionalisering_id:
                continue
            duplicates = self.search_count([
                ('professionalisering_id', '=', line.professionalisering_id.id),
                ('date', '=', line.date),
                ('id', '!=', line.id),
            ])
            if duplicates:
                raise ValidationError(
                    f"Datum {line.date.strftime('%d/%m/%Y')} bestaat al voor deze aanvraag."
                )

    @api.onchange('date')
    def _onchange_date_validate(self):
        """Client-side check zodra de gebruiker een datum kiest in de editable
        list. Bij ongeldige datum: leeg het veld en toon een waarschuwing zodat
        de gebruiker niet pas bij submit een foutmelding krijgt."""
        if not self.date:
            return
        chosen = self.date
        today = fields.Date.context_today(self)
        # 1. Datum mag niet in het verleden liggen
        if chosen < today:
            self.date = False
            return {
                'warning': {
                    'title': "Datum in het verleden",
                    'message': (
                        f"De datum {chosen.strftime('%d/%m/%Y')} ligt in het verleden. "
                        f"Kies een datum vanaf vandaag ({today.strftime('%d/%m/%Y')})."
                    ),
                }
            }
        # 2. Datum mag niet eerder dan de startdatum van de aanvraag liggen
        parent = self.professionalisering_id
        if parent and parent.start_date and chosen < parent.start_date:
            self.date = False
            return {
                'warning': {
                    'title': "Datum vóór startdatum",
                    'message': (
                        f"De datum {chosen.strftime('%d/%m/%Y')} ligt vóór de "
                        f"startdatum ({parent.start_date.strftime('%d/%m/%Y')}). "
                        f"Kies een datum op of na de startdatum."
                    ),
                }
            }
        # 3. Geen duplicaat van een bestaande sibling-datum
        if parent:
            for sibling in parent.date_line_ids:
                if sibling == self:
                    continue
                if sibling.date == chosen:
                    self.date = False
                    return {
                        'warning': {
                            'title': "Datum bestaat al",
                            'message': (
                                f"De datum {chosen.strftime('%d/%m/%Y')} "
                                f"is al toegevoegd aan deze aanvraag. Kies een andere datum."
                            ),
                        }
                    }

    def action_unlink_self(self):
        """Verwijder deze datumregel."""
        self.unlink()


class ProfessionaliseringAddressPicker(models.TransientModel):
    _name = 'professionalisering.address.picker'
    _description = 'Geavanceerd adres kiezen'

    record_id = fields.Many2one(
        'professionalisering.record', string='Aanvraag', required=True,
    )
    step = fields.Selection([
        ('1', 'Organisatie'),
        ('2', 'Locatie'),
    ], default='1', required=True)

    # Step 1 — organisatie
    organization_filter = fields.Char(string='Zoek organisatie')
    organization = fields.Char(string='Organisatie',
        help='Gekozen organisatie. Wordt overgenomen naar de nieuwe locatie als je er een aanmaakt.')
    available_org_address_ids = fields.Many2many(
        'professionalisering.address', 'pp_picker_org_rel', 'picker_id', 'address_id',
        compute='_compute_available_org_address_ids',
    )
    can_use_typed_organization = fields.Boolean(
        compute='_compute_can_use_typed_organization',
    )

    # Step 2 — locatie
    location_filter = fields.Char(string='Zoek locatie')
    online_filter = fields.Selection([
        ('all', 'Alle locaties'),
        ('physical', 'Enkel fysieke locaties'),
        ('online', 'Enkel online'),
    ], string='Soort', default='all')
    available_address_ids = fields.Many2many(
        'professionalisering.address', 'pp_picker_loc_rel', 'picker_id', 'address_id',
        compute='_compute_available_address_ids',
    )
    can_create_placeholder = fields.Boolean(
        compute='_compute_can_create_placeholder',
    )
    placeholder_label = fields.Char(compute='_compute_placeholder_label')

    address_id = fields.Many2one(
        'professionalisering.address', string='Geselecteerd adres',
    )

    # ---- Step 1 ----

    @api.depends('organization_filter')
    def _compute_available_org_address_ids(self):
        """Toont één representatieve adres-rij per unieke organisatie."""
        Address = self.env['professionalisering.address']
        for rec in self:
            domain = [('organization', '!=', False)]
            if rec.organization_filter:
                domain.append(('organization', 'ilike', rec.organization_filter))
            all_addrs = Address.search(domain, order='organization')
            seen = set()
            picks = []
            for a in all_addrs:
                key = (a.organization or '').strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    picks.append(a.id)
            rec.available_org_address_ids = Address.browse(picks)

    @api.depends('organization_filter', 'available_org_address_ids')
    def _compute_can_use_typed_organization(self):
        for rec in self:
            term = (rec.organization_filter or '').strip()
            if not term:
                rec.can_use_typed_organization = False
                continue
            existing = rec.available_org_address_ids.mapped(
                lambda a: (a.organization or '').strip().lower()
            )
            rec.can_use_typed_organization = term.lower() not in existing

    def action_use_typed_organization(self):
        self.ensure_one()
        org = (self.organization_filter or '').strip()
        if not org:
            raise UserError("Typ eerst een organisatienaam.")
        self.write({
            'organization': org,
            'step': '2',
            'organization_filter': False,
        })
        return self._refresh()

    def action_select_organization(self, org_name):
        self.ensure_one()
        self.write({
            'organization': org_name or False,
            'step': '2',
            'organization_filter': False,
        })
        return self._refresh()

    # ---- Step 2 ----

    @api.depends('organization', 'location_filter', 'online_filter')
    def _compute_available_address_ids(self):
        Address = self.env['professionalisering.address']
        for rec in self:
            domain = []
            if rec.organization:
                domain.append(('organization', '=ilike', rec.organization))
            if rec.location_filter:
                term = rec.location_filter
                domain += ['|', '|', '|',
                    ('name', 'ilike', term),
                    ('city', 'ilike', term),
                    ('street', 'ilike', term),
                    ('postal_code', 'ilike', term),
                ]
            if rec.online_filter == 'physical':
                domain.append(('is_online', '=', False))
            elif rec.online_filter == 'online':
                domain.append(('is_online', '=', True))
            rec.available_address_ids = Address.search(domain)

    @api.depends('location_filter', 'available_address_ids')
    def _compute_can_create_placeholder(self):
        for rec in self:
            rec.can_create_placeholder = bool(rec.location_filter) and not rec.available_address_ids

    @api.depends('organization', 'location_filter', 'online_filter')
    def _compute_placeholder_label(self):
        for rec in self:
            loc = rec.location_filter or '(geen naam)'
            org = rec.organization or '(geen organisatie)'
            if rec.online_filter == 'online':
                rec.placeholder_label = f"Voeg '{loc}' (online) toe voor {org} en bevestig"
            else:
                rec.placeholder_label = f"Voeg '{loc}' toe voor {org} en bevestig"

    def action_back_to_step_1(self):
        self.ensure_one()
        self.write({'step': '1', 'location_filter': False})
        return self._refresh()

    def action_create_placeholder(self):
        self.ensure_one()
        loc = (self.location_filter or '').strip()
        if not loc:
            raise UserError("Typ een locatienaam.")
        # sudo: medewerkers mogen geen adressen rechtstreeks aanmaken (ACL),
        # maar via de picker-wizard mogen ze wel een placeholder toevoegen
        # die directie/admin later kunnen verfijnen.
        address = self.env['professionalisering.address'].sudo().create({
            'name': loc,
            'organization': self.organization or False,
            'is_online': self.online_filter == 'online',
            'needs_review': True,
        })
        # Notify directie zodat zij het adres kunnen aanvullen
        address._notify_directie_for_review(self.record_id)
        self.address_id = address.id
        return self.action_confirm()

    def action_confirm(self):
        self.ensure_one()
        if not self.address_id:
            raise UserError("Selecteer een adres of voeg een nieuw adres toe.")
        address = self.address_id
        if address.is_online:
            self.record_id.write({
                'address_id': False,
                'location_type': 'online',
            })
        else:
            self.record_id.write({
                'address_id': address.id,
                'location_type': 'address',
            })
        return {'type': 'ir.actions.act_window_close'}

    def _refresh(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
