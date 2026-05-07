from odoo import models, fields, api
from odoo.exceptions import UserError


class ActiviteitenKostenLine(models.Model):
    _name = 'activiteiten.kosten.line'
    _description = 'Activiteiten Kostenlijn'

    activiteit_id = fields.Many2one(
        'activiteiten.record', string='Activiteit',
        required=True, ondelete='cascade',
    )
    omschrijving = fields.Char(string='Omschrijving', required=True)
    bedrag = fields.Monetary(
        string='Bedrag (totaal)',
        currency_field='currency_id',
        help='Totaalbedrag voor de volledige activiteit, niet per leerling. '
             'Bijvoorbeeld: voor een busrit van € 250 vul je 250 in, niet 10 '
             '(per leerling). De kost-per-leerling wordt automatisch berekend.',
    )
    currency_id = fields.Many2one(
        related='activiteit_id.currency_id',
    )
    kosten_type = fields.Selection([
        ('vast', 'Vaste kosten'),
        ('variabel', 'Variabele kosten'),
    ], string='Type', default='vast', required=True)
    is_auto = fields.Boolean(string='Automatisch', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # Recalculate verzekering for non-auto lines
        activiteiten = lines.filtered(lambda l: not l.is_auto).mapped('activiteit_id')
        if activiteiten:
            activiteiten._recalculate_auto_lines()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'bedrag' in vals:
            activiteiten = self.filtered(lambda l: not l.is_auto).mapped('activiteit_id')
            if activiteiten:
                activiteiten._recalculate_auto_lines()
        return res

    def unlink(self):
        if not self.env.context.get('force_unlink_auto') and self.filtered('is_auto'):
            raise UserError("Automatische kostenlijnen (bv. Verzekering) kunnen niet verwijderd worden.")
        activiteiten = self.filtered(lambda l: not l.is_auto).mapped('activiteit_id')
        res = super().unlink()
        if activiteiten:
            activiteiten._recalculate_auto_lines()
        return res
