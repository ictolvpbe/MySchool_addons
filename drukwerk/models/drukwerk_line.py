import base64
import io
import logging

from odoo import models, fields, api

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
        help='Aantal kopieën per leerling. Wordt vermenigvuldigd met het aantal leerlingen.',
    )
    prijs_per_pagina = fields.Float(
        string='Prijs per pagina',
        digits=(10, 4),
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param(
                'drukwerk.prijs_per_pagina', '0.03')),
    )
    kleur = fields.Boolean(string='Kleur', default=False)
    dubbelzijdig = fields.Boolean(string='Dubbelzijdig', default=False)
    opmerking = fields.Char(string='Opmerking')
    currency_id = fields.Many2one(related='drukwerk_id.currency_id')
    subtotaal = fields.Monetary(
        string='Subtotaal',
        currency_field='currency_id',
        compute='_compute_subtotaal',
        store=True,
    )

    @api.depends('aantal_paginas', 'aantal_kopies', 'prijs_per_pagina')
    def _compute_subtotaal(self):
        for line in self:
            pages = (line.aantal_paginas or 0) * (line.aantal_kopies or 0)
            line.subtotaal = pages * (line.prijs_per_pagina or 0)

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
