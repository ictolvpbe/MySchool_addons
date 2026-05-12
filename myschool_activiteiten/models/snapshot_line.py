from odoo import models, fields, api


class ActiviteitenSnapshotLine(models.Model):
    _name = 'myschool_activiteiten.snapshot.line'
    _description = 'Activiteiten Deelnemer Snapshot'
    _order = 'snapshot_type, klas_name, person_name'

    activiteit_id = fields.Many2one(
        'myschool_activiteiten.record', string='Activiteit',
        required=True, ondelete='cascade',
    )
    person_id = fields.Many2one(
        'myschool.person', string='Persoon',
        required=True, ondelete='cascade',
    )
    person_name = fields.Char(
        related='person_id.name', store=True, string='Naam',
    )
    snapshot_type = fields.Selection([
        ('student', 'Leerling'),
        ('leerkracht', 'Leerkracht'),
    ], string='Type', required=True)
    date_from = fields.Date(
        string='Vanaf',
        required=True,
        help='Datum waarop deze persoon aan de activiteit was gekoppeld.',
    )
    date_to = fields.Date(
        string='Tot',
        help='Datum waarop deze persoon niet meer gekoppeld was. Leeg = nog steeds actief.',
    )
    klas_name = fields.Char(
        string='Klas', compute='_compute_klas_name', store=True,
    )
    aanwezig = fields.Boolean(
        string='Aanwezig',
        default=True,
        help='Vink aan voor leerlingen die effectief op de uitstap waren. '
             'Standaard staat iedereen op aanwezig — vink af wie er niet bij was.',
    )
    factureren = fields.Boolean(
        string='Factureren',
        default=True,
        help='Vink uit als deze leerling niét gefactureerd moet worden '
             '(bv. sociale tegemoetkoming, vrijgestelde leerling). '
             'Enkel boekhouding kan dit aanpassen.',
    )
    aangerekend_bedrag = fields.Monetary(
        string='Aangerekend bedrag',
        currency_field='currency_id',
        compute='_compute_aangerekend_bedrag',
        store=True, readonly=False,
        help='Bedrag dat aan deze leerling aangerekend wordt. Standaard '
             'op basis van aanwezigheid: aanwezigen betalen vast + '
             'variabel, afwezigen betalen enkel vast. Boekhouding kan '
             'het bedrag per leerling overrulen.',
    )
    currency_id = fields.Many2one(
        related='activiteit_id.currency_id', store=False, readonly=True,
    )

    @api.depends('aanwezig', 'snapshot_type', 'factureren',
                 'activiteit_id.kost_per_aanwezig',
                 'activiteit_id.kost_per_afwezig')
    def _compute_aangerekend_bedrag(self):
        """Standaardbedrag op basis van aanwezigheid. Boekhouding kan
        achteraf manueel overrulen — Odoo respecteert dat want het veld
        is store=True + readonly=False (de compute herrekent niet meer
        op een handmatige write)."""
        for line in self:
            if line.snapshot_type != 'student' or not line.factureren:
                line.aangerekend_bedrag = 0.0
                continue
            if line.aanwezig:
                line.aangerekend_bedrag = line.activiteit_id.kost_per_aanwezig
            else:
                line.aangerekend_bedrag = line.activiteit_id.kost_per_afwezig

    @api.depends('person_id', 'activiteit_id.klas_ids')
    def _compute_klas_name(self):
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        for line in self:
            if not person_tree_type or not line.person_id or not line.activiteit_id.klas_ids:
                line.klas_name = ''
                continue
            rel = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('id_person', '=', line.person_id.id),
                ('id_org', 'in', line.activiteit_id.klas_ids.ids),
                ('is_active', '=', True),
            ], limit=1)
            line.klas_name = rel.id_org.name if rel else ''
