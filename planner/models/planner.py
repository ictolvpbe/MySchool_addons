from datetime import datetime, timedelta

from pytz import timezone

from odoo import models, fields, api
from odoo.exceptions import UserError


class PlannerRecord(models.Model):
    _name = 'planner.record'
    _description = 'Inhaalplan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'inhaal_datum asc'

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    titel = fields.Char(string='Onderwerp inhaalmoment', required=True)
    description = fields.Text(string='Beschrijving')
    afwezige_id = fields.Many2one(
        'planner.afwezige.leerkracht',
        string='Afwezige',
        store=False,
    )
    leerkracht_id = fields.Many2one(
        'hr.employee',
        string='Afwezige leerkracht',
    )
    klas_id = fields.Many2one(
        'myschool.org',
        string='Afwezige klas',
    )
    afwezigheid_info = fields.Text(
        string='Afwezigheid',
        compute='_compute_afwezigheid_info',
    )
    inhaal_date = fields.Date(string='Inhaaldatum', required=True)
    tijdslot_ids = fields.Many2many(
        'planner.tijdslot',
        string='Lesuren',
    )
    inhaal_datum = fields.Datetime(
        string='Begin',
        compute='_compute_inhaal_datum',
        store=True,
    )
    inhaal_datum_end = fields.Datetime(
        string='Einde',
        compute='_compute_inhaal_datum',
        store=True,
    )
    tijdslot_display = fields.Char(
        string='Uren',
        compute='_compute_tijdslot_display',
    )
    vervanging_line_ids = fields.One2many(
        'planner.vervanging.line', 'planner_id',
        string='Vervangingen',
    )
    verantwoordelijke_id = fields.Many2one(
        'res.users', string='Verantwoordelijke',
        default=lambda self: self.env.user,
    )
    state = fields.Selection([
        ('gepland', 'Gepland'),
        ('ingediend', 'Ingediend'),
        ('cancelled', 'Geannuleerd'),
    ], string='Status', default='gepland', required=True, tracking=True)

    @staticmethod
    def _float_to_time_str(f):
        h = int(f)
        m = int(round((f % 1) * 60))
        return f'{h:02d}:{m:02d}'

    @staticmethod
    def _group_consecutive_slots(slots):
        """Group slots into consecutive blocks based on sequence."""
        sorted_slots = slots.sorted('sequence')
        blocks = []
        current_block = []
        for slot in sorted_slots:
            if current_block and slot.sequence != current_block[-1].sequence + 1:
                blocks.append(current_block)
                current_block = []
            current_block.append(slot)
        if current_block:
            blocks.append(current_block)
        return blocks

    @api.depends('inhaal_date', 'tijdslot_ids')
    def _compute_inhaal_datum(self):
        tz = timezone(self.env.user.tz or 'Europe/Brussels')
        for record in self:
            if record.inhaal_date and record.tijdslot_ids:
                earliest = min(record.tijdslot_ids.mapped('hour_start'))
                latest = max(record.tijdslot_ids.mapped('hour_end'))
                start_h, start_m = int(earliest), int(round((earliest % 1) * 60))
                end_h, end_m = int(latest), int(round((latest % 1) * 60))
                local_start = tz.localize(datetime.combine(
                    record.inhaal_date,
                    datetime.min.time().replace(hour=start_h, minute=start_m),
                ))
                local_end = tz.localize(datetime.combine(
                    record.inhaal_date,
                    datetime.min.time().replace(hour=end_h, minute=end_m),
                ))
                record.inhaal_datum = local_start.astimezone(timezone('UTC')).replace(tzinfo=None)
                record.inhaal_datum_end = local_end.astimezone(timezone('UTC')).replace(tzinfo=None)
            else:
                record.inhaal_datum = False
                record.inhaal_datum_end = False

    @api.depends('inhaal_date', 'tijdslot_ids')
    def _compute_tijdslot_display(self):
        for record in self:
            if record.inhaal_date and record.tijdslot_ids:
                blocks = self._group_consecutive_slots(record.tijdslot_ids)
                parts = []
                for block in blocks:
                    block_start = min(s.hour_start for s in block)
                    block_end = max(s.hour_end for s in block)
                    parts.append(f'{self._float_to_time_str(block_start)} - {self._float_to_time_str(block_end)}')
                record.tijdslot_display = ' | '.join(parts)
            else:
                record.tijdslot_display = False

    @api.onchange('afwezige_id')
    def _onchange_afwezige_id(self):
        if self.afwezige_id:
            afw = self.afwezige_id
            self.leerkracht_id = afw.employee_id
            self.klas_id = afw.klas_id
            self.titel = f'Vervanging {afw.employee_name or ""} - {afw.titel or ""}'
            if afw.datum:
                self.inhaal_date = afw.datum.date()
        else:
            self.leerkracht_id = False
            self.klas_id = False

    @api.depends('leerkracht_id', 'klas_id')
    def _compute_afwezigheid_info(self):
        tz = timezone(self.env.user.tz or 'Europe/Brussels')
        for record in self:
            if not record.leerkracht_id and not record.klas_id:
                record.afwezigheid_info = False
                continue
            lines = []
            if record.leerkracht_id:
                # Activiteiten (via myschool.person link)
                person = self.env['myschool.person'].search([
                    ('odoo_employee_id', '=', record.leerkracht_id.id),
                ], limit=1)
                if person:
                    activiteiten = self.env['activiteiten.record'].search([
                        ('state', 'in', ('approved', 's_code', 'vervanging', 'done')),
                        ('leerkracht_ids', 'in', [person.id]),
                    ], order='datetime asc')
                    for act in activiteiten:
                        if act.datetime:
                            utc_start = timezone('UTC').localize(act.datetime)
                            local_start = utc_start.astimezone(tz)
                            datum_str = local_start.strftime('%d/%m/%Y %H:%M')
                            if act.datetime_end:
                                utc_end = timezone('UTC').localize(act.datetime_end)
                                local_end = utc_end.astimezone(tz)
                                datum_str += f' - {local_end.strftime("%H:%M")}'
                        else:
                            datum_str = 'Geen datum'
                        lines.append(f'[Activiteit] {datum_str}: {act.titel or act.name}')
                # Professionalisering
                prof_records = self.env['professionalisering.record'].search([
                    ('state', 'in', ('bevestiging', 'done')),
                    '|',
                    ('employee_id', '=', record.leerkracht_id.id),
                    '&', ('invite_ids.employee_id', '=', record.leerkracht_id.id),
                         ('invite_ids.state', '=', 'accepted'),
                ], order='start_date asc')
                for pr in prof_records:
                    datum_str = pr.start_date.strftime('%d/%m/%Y') if pr.start_date else 'Geen datum'
                    if pr.end_date and pr.end_date != pr.start_date:
                        datum_str += f' - {pr.end_date.strftime("%d/%m/%Y")}'
                    lines.append(f'[Professionalisering] {datum_str}: {pr.titel}')
            if record.klas_id:
                # Activiteiten for this class
                activiteiten = self.env['activiteiten.record'].search([
                    ('state', 'in', ('approved', 's_code', 'vervanging', 'done')),
                    ('klas_ids', 'in', [record.klas_id.id]),
                ], order='datetime asc')
                for act in activiteiten:
                    if act.datetime:
                        utc_start = timezone('UTC').localize(act.datetime)
                        local_start = utc_start.astimezone(tz)
                        datum_str = local_start.strftime('%d/%m/%Y %H:%M')
                        if act.datetime_end:
                            utc_end = timezone('UTC').localize(act.datetime_end)
                            local_end = utc_end.astimezone(tz)
                            datum_str += f' - {local_end.strftime("%H:%M")}'
                    else:
                        datum_str = 'Geen datum'
                    lines.append(f'[Activiteit] {datum_str}: {act.titel or act.name}')
            if not lines:
                record.afwezigheid_info = 'Geen afwezigheden gevonden.'
            else:
                record.afwezigheid_info = '\n'.join(lines)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('planner.record')
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            record.state = 'ingediend'

    def action_cancel(self):
        for record in self:
            record.state = 'cancelled'

    def action_replan(self):
        for record in self:
            record.state = 'gepland'
