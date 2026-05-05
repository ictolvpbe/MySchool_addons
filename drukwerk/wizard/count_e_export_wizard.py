import base64
import io
import csv
from datetime import date, datetime, time

from odoo import models, fields, api
from odoo.exceptions import UserError


class CountEExportWizard(models.TransientModel):
    _name = 'drukwerk.count.e.export.wizard'
    _description = 'Count-e export wizard'

    datum_van = fields.Date(
        string='Vanaf',
        required=True,
        default=lambda self: self._default_school_year_start(),
    )
    datum_tot = fields.Date(
        string='Tot en met',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        required=True,
        default=lambda self: self.env.company.school_id,
    )
    include_gestockeerd = fields.Boolean(
        string='Inclusief gestockeerde records',
        default=True,
        help='Records die naar stockage zijn verplaatst worden ook meegenomen',
    )

    csv_file = fields.Binary(string='CSV bestand', readonly=True)
    csv_filename = fields.Char(string='Bestandsnaam', readonly=True)
    record_count = fields.Integer(string='Aantal regels', readonly=True)
    skipped_count = fields.Integer(string='Overgeslagen leerlingen', readonly=True)
    skipped_details = fields.Text(string='Overgeslagen (geen SAP-referentie)', readonly=True)

    @api.model
    def _default_school_year_start(self):
        today = fields.Date.context_today(self)
        # Schooljaar start op 1 september. Als we voor 1 sept zitten → vorig jaar.
        year = today.year if today.month >= 9 else today.year - 1
        return date(year, 9, 1)

    def _get_page_price(self, record, prijs_per_pagina, prijs_kleur, prijs_a3, prijs_dik):
        """Bereken de eenheidsprijs per pagina, zelfde logica als drukwerk._compute_totals."""
        page_price = prijs_per_pagina
        if record.kleur == 'kleur':
            page_price += prijs_kleur
        if record.formaat == 'a3':
            page_price += prijs_a3
        if record.dik_papier:
            page_price += prijs_dik
        return page_price

    def _format_decimal(self, value):
        """Belgisch formaat: komma als decimaal, geen duizendtallen."""
        return ('%.4f' % value).rstrip('0').rstrip('.').replace('.', ',') or '0'

    def action_export(self):
        self.ensure_one()
        if self.datum_van > self.datum_tot:
            raise UserError("Datum 'Vanaf' moet vóór 'Tot en met' liggen.")

        param = self.env['ir.config_parameter'].sudo()
        prijs_per_pagina = float(param.get_param('drukwerk.prijs_per_pagina', '0.03'))
        prijs_kleur = float(param.get_param('drukwerk.prijs_kleur', '0.05'))
        prijs_a3 = float(param.get_param('drukwerk.prijs_a3', '0.02'))
        prijs_dik = float(param.get_param('drukwerk.prijs_dik_papier', '0.04'))
        artikel_zw = param.get_param('drukwerk.count_e_artikel', 'KOPIES') or 'KOPIES'
        artikel_kl = param.get_param('drukwerk.count_e_artikel_kleur', 'KOPIES') or 'KOPIES'
        analytisch = param.get_param('drukwerk.count_e_analytisch', '') or ''

        # Datum-bereik op done_date (datetime → vergelijken met datum)
        dt_from = datetime.combine(self.datum_van, time.min)
        dt_to = datetime.combine(self.datum_tot, time.max)

        states = ['done']
        if self.include_gestockeerd:
            states.append('gestockeerd')

        Drukwerk = self.env['drukwerk.record'].sudo()
        records = Drukwerk.search([
            ('school_id', '=', self.school_id.id),
            ('state', 'in', states),
            ('done_date', '>=', dt_from),
            ('done_date', '<=', dt_to),
        ])

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=';', lineterminator='\n')
        header = ['#ExterneCode', '#Artikel', '#Aantal', '#Prijs', '#Bedrag']
        if analytisch:
            header.append('#Analytisch1')
        writer.writerow(header)

        # Aggregeer per (ext_code, artikel, prijs): tel aantal en bedrag op.
        # Prijs is afgerond op 4 decimalen om floating-point-mismatches te vermijden.
        aggregated = {}  # (ext_code, artikel, prijs_key) -> {'aantal': int, 'bedrag': float, 'prijs': float}
        skipped_pairs = []  # (drukwerk_name, student_name)
        for record in records:
            page_price = self._get_page_price(record, prijs_per_pagina, prijs_kleur, prijs_a3, prijs_dik)
            artikel = artikel_kl if record.kleur == 'kleur' else artikel_zw
            aantal = record.aantal_paginas or 0
            if aantal <= 0 or page_price <= 0:
                continue
            prijs_key = round(page_price, 4)
            for student in record.student_ids:
                ext_code = (student.sap_ref or '').strip()
                if not ext_code:
                    skipped_pairs.append((record.name, student.name))
                    continue
                key = (ext_code, artikel, prijs_key)
                bucket = aggregated.setdefault(key, {'aantal': 0, 'bedrag': 0.0, 'prijs': page_price})
                bucket['aantal'] += aantal
                bucket['bedrag'] += aantal * page_price

        # Sorteer voor stabiele output (ExterneCode, dan Artikel, dan Prijs).
        line_count = 0
        for (ext_code, artikel, _), bucket in sorted(aggregated.items()):
            row = [
                ext_code,
                artikel,
                str(bucket['aantal']),
                self._format_decimal(bucket['prijs']),
                self._format_decimal(bucket['bedrag']),
            ]
            if analytisch:
                row.append(analytisch)
            writer.writerow(row)
            line_count += 1

        if line_count == 0:
            raise UserError(
                "Geen exporteerbare records gevonden in dit bereik. "
                "(Records moeten status 'Afgedrukt' of 'Gestockeerd' hebben, een ingevulde "
                "afdrukdatum en leerlingen met een ingevulde SAP-referentie.)"
            )

        csv_bytes = buf.getvalue().encode('utf-8-sig')
        filename = f"counte_drukwerk_{self.datum_van}_{self.datum_tot}.csv"

        details_lines = [
            f"  • {dw} → {name}" for dw, name in skipped_pairs
        ]
        skipped_text = "\n".join(details_lines) if details_lines else False

        self.write({
            'csv_file': base64.b64encode(csv_bytes),
            'csv_filename': filename,
            'record_count': line_count,
            'skipped_count': len(skipped_pairs),
            'skipped_details': skipped_text,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
