from odoo import models, fields, api


class ActiviteitenBus(models.Model):
    _name = 'activiteiten.bus'
    _description = 'Busverdeling'
    _order = 'activiteit_id, bus_nummer'

    activiteit_id = fields.Many2one(
        'activiteiten.record', string='Activiteit',
        required=True, ondelete='cascade',
    )
    bus_nummer = fields.Integer(string='Busnummer', required=True, default=1)

    # Busbezetting
    klas_ids = fields.Many2many(
        'myschool.org', string='Klassen',
    )
    aantal_klassen = fields.Integer(
        string='Aantal klassen', compute='_compute_counts',
    )
    student_count = fields.Integer(
        string='Aantal leerlingen', compute='_compute_counts',
    )
    aantal_leerkrachten = fields.Integer(
        string='Aantal leerkrachten', compute='_compute_aantal_leerkrachten',
    )

    # Verantwoordelijke leerkracht
    busverantwoordelijke_id = fields.Many2one(
        'myschool.person', string='Verantwoordelijke leerkracht',
    )
    busverantwoordelijke_telefoon = fields.Char(
        string='Tel. verantwoordelijke',
        compute='_compute_telefoon', store=True, readonly=False,
    )

    # Leerkracht van de bus = auto-filled with busverantwoordelijke
    leerkracht_bus_id = fields.Many2one(
        'myschool.person', string='Leerkracht van de bus',
        compute='_compute_leerkracht_bus', store=True, readonly=False,
    )

    # Busmaatschappij
    busmaatschappij = fields.Char(string='Busmaatschappij')
    nummerplaat = fields.Char(string='Nummerplaat bus')
    telefoon_chauffeur = fields.Char(string='Tel. buschauffeur')

    # Afwezigen
    afwezigen = fields.Text(string='Afwezigen (naam + klas)')

    @api.depends('busverantwoordelijke_id')
    def _compute_telefoon(self):
        for rec in self:
            phone = ''
            if rec.busverantwoordelijke_id and rec.busverantwoordelijke_id.odoo_user_id:
                partner = rec.busverantwoordelijke_id.odoo_user_id.partner_id
                phone = partner.phone or ''
            rec.busverantwoordelijke_telefoon = phone

    @api.depends('busverantwoordelijke_id')
    def _compute_leerkracht_bus(self):
        for rec in self:
            rec.leerkracht_bus_id = rec.busverantwoordelijke_id

    @api.depends('activiteit_id.leerkracht_ids')
    def _compute_aantal_leerkrachten(self):
        for rec in self:
            rec.aantal_leerkrachten = len(rec.activiteit_id.leerkracht_ids)

    @api.depends('klas_ids')
    def _compute_counts(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for rec in self:
            rec.aantal_klassen = len(rec.klas_ids)
            if person_tree_type and rec.klas_ids:
                rec.student_count = PropRelation.search_count([
                    ('proprelation_type_id', '=', person_tree_type.id),
                    ('id_org', 'in', rec.klas_ids.ids),
                    ('id_person', '!=', False),
                    ('is_active', '=', True),
                ])
            else:
                rec.student_count = 0
