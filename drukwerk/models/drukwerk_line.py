import base64
import io
import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DrukwerkLine(models.Model):
    _name = 'drukwerk.line'
    _description = 'Drukwerk Item'

    drukwerk_id = fields.Many2one(
        'drukwerk.record', string='Aanvraag',
        required=True, ondelete='cascade',
    )
    document_file = fields.Binary(string='Document', required=True, attachment=True)
    document_filename = fields.Char(string='Bestandsnaam')
    aantal_paginas = fields.Integer(string='Pagina\'s', default=1)
    aantal_kopies = fields.Integer(
        string='Kopieën',
        compute='_compute_aantal_kopies',
        store=True,
    )
    prijs_per_pagina = fields.Float(
        string='Prijs per pagina',
        digits=(10, 4),
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param(
                'drukwerk.prijs_per_pagina', '0.03')),
    )
    kleur = fields.Selection([
        ('zw', 'Zwart-wit'),
        ('kleur', 'Kleur'),
    ], string='Kleur', default='zw', required=True)
    formaat = fields.Selection([
        ('a4', 'A4'),
        ('a3', 'A3'),
    ], string='Formaat', default='a4', required=True)
    prijs_kleur = fields.Float(
        string='Toeslag kleur',
        digits=(10, 4),
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param(
                'drukwerk.prijs_kleur', '0.05')),
    )
    prijs_a3 = fields.Float(
        string='Toeslag A3',
        digits=(10, 4),
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param(
                'drukwerk.prijs_a3', '0.02')),
    )
    kopie_leerkracht = fields.Boolean(string='Kopie leerkracht', default=False)
    opmerking = fields.Char(string='Opmerking')
    currency_id = fields.Many2one(related='drukwerk_id.currency_id')
    subtotaal = fields.Monetary(
        string='Subtotaal',
        currency_field='currency_id',
        compute='_compute_subtotaal',
        store=True,
    )

    @api.depends('aantal_paginas', 'aantal_kopies', 'prijs_per_pagina', 'kleur', 'prijs_kleur', 'formaat', 'prijs_a3')
    def _compute_subtotaal(self):
        for line in self:
            pages = (line.aantal_paginas or 0) * (line.aantal_kopies or 0)
            price = line.prijs_per_pagina or 0
            if line.kleur == 'kleur':
                price += line.prijs_kleur or 0
            if line.formaat == 'a3':
                price += line.prijs_a3 or 0
            line.subtotaal = pages * price

    @api.constrains('document_filename')
    def _check_pdf_only(self):
        for line in self:
            if line.document_filename and not line.document_filename.lower().endswith('.pdf'):
                raise ValidationError("Alleen PDF-bestanden zijn toegestaan. Upload een .pdf bestand.")

    @api.onchange('document_file', 'document_filename')
    def _onchange_document_file(self):
        """Auto-detect page count from uploaded PDF."""
        if not self.document_file or not self.document_filename:
            return
        if not self.document_filename.lower().endswith('.pdf'):
            return
        try:
            pdf_data = base64.b64decode(self.document_file)
            page_count = self._count_pdf_pages(pdf_data)
            if page_count > 0:
                self.aantal_paginas = page_count
        except Exception:
            _logger.warning('Could not count pages for %s', self.document_filename, exc_info=True)

    @api.depends('kopie_leerkracht', 'drukwerk_id.student_ids')
    def _compute_aantal_kopies(self):
        for line in self:
            count = len(line.drukwerk_id.student_ids)
            if line.kopie_leerkracht:
                count += 1
            line.aantal_kopies = count

    def action_download_pdf(self):
        """Open the PDF in a print page with all settings displayed."""
        self.ensure_one()
        if not self.document_file:
            raise ValidationError("Geen document beschikbaar om af te drukken.")
        return {
            'type': 'ir.actions.act_url',
            'url': f'/drukwerk/print/{self.id}',
            'target': 'new',
        }

    @staticmethod
    def _count_pdf_pages(pdf_bytes):
        """Count pages in a PDF using PyPDF2 or pikepdf, fallback to regex."""
        # Try PyPDF2
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            return len(reader.pages)
        except ImportError:
            pass
        except Exception:
            pass
        # Try pikepdf
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))
            count = len(pdf.pages)
            pdf.close()
            return count
        except ImportError:
            pass
        except Exception:
            pass
        # Regex fallback: count /Type /Page entries
        import re
        return len(re.findall(rb'/Type\s*/Page[^s]', pdf_bytes))
