import base64
import io
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DrukwerkPrintController(http.Controller):

    @http.route('/drukwerk/print/<int:record_id>', type='http', auth='user')
    def print_document(self, record_id):
        """Serve the PDF with print settings pre-filled in the print dialog."""
        rec = request.env['drukwerk.record'].browse(record_id)
        if not rec.exists() or not rec.document_file:
            return request.not_found()

        filename = rec.document_filename or 'document.pdf'
        copies = rec.aantal_kopies or 1
        dubbelzijdig = rec.dubbelzijdig
        kleur_label = 'Kleur' if rec.kleur == 'kleur' else 'Zwart-wit'
        formaat_label = rec.formaat.upper() if rec.formaat else 'A4'
        kopie_leerkracht = 'Ja' if rec.kopie_leerkracht else 'Nee'

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Afdrukken - {filename}</title>
    <style>
        body {{ margin: 0; }}
        .print-info {{
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
            padding: 10px 25px;
            font-family: Arial, sans-serif;
            display: flex;
            align-items: center;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .print-info .badge {{
            padding: 4px 14px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 14px;
        }}
        .print-info .badge-copies {{
            background: #dc3545;
            color: white;
        }}
        .print-info .badge-yes {{
            background: #28a745;
            color: white;
        }}
        .print-info .badge-no {{
            background: #6c757d;
            color: white;
        }}
        .print-info .badge-kleur {{
            background: #007bff;
            color: white;
        }}
        .print-info .badge-zw {{
            background: #343a40;
            color: white;
        }}
        .print-info .badge-formaat {{
            background: #17a2b8;
            color: white;
        }}
        .print-info .manual-warning {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 13px;
            color: #856404;
        }}
        .finishing-alert {{
            background: #f8d7da;
            border: 2px solid #dc3545;
            border-radius: 6px;
            padding: 10px 20px;
            margin: 0 25px;
            font-family: Arial, sans-serif;
            font-size: 15px;
            font-weight: bold;
            color: #721c24;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .finishing-alert .finish-icon {{
            font-size: 22px;
        }}
        iframe {{
            width: 100%;
            height: calc(100vh - {90 if (rec.nieten or rec.perforeren) else 50}px);
            border: none;
        }}
        @media print {{
            .print-info, .finishing-alert {{ display: none !important; }}
            iframe {{ height: 100vh; }}
        }}
    </style>
</head>
<body>
    <div class="print-info">
        <span><strong>Formaat:</strong> <span class="badge badge-formaat">{formaat_label}</span></span>
        <span><strong>Kleur:</strong> <span class="badge badge-{'kleur' if rec.kleur == 'kleur' else 'zw'}">{kleur_label}</span></span>
        <span><strong>Kopieën:</strong> <span class="badge badge-copies">{copies}</span></span>
        <span><strong>Dubbelzijdig:</strong> <span class="badge badge-{'yes' if dubbelzijdig else 'no'}">{'Ja' if dubbelzijdig else 'Nee'}</span></span>
        <span><strong>Nieten:</strong> <span class="badge badge-{'yes' if rec.nieten else 'no'}">{'Ja' if rec.nieten else 'Nee'}</span></span>
        <span><strong>Perforeren:</strong> <span class="badge badge-{'yes' if rec.perforeren else 'no'}">{'Ja' if rec.perforeren else 'Nee'}</span></span>
        <span><strong>Kopie leerkracht:</strong> <span class="badge badge-{'yes' if rec.kopie_leerkracht else 'no'}">{kopie_leerkracht}</span></span>
        {'<span class="manual-warning">&#9888; Controleer kleurinstelling in afdrukvenster</span>' if rec.kleur == 'kleur' else ''}
    </div>
    {'<div class="finishing-alert"><span class="finish-icon">&#9888;</span> Stel in het afdrukvenster in: ' + ' + '.join(f for f in [('NIETEN' if rec.nieten else ''), ('PERFOREREN' if rec.perforeren else '')] if f) + ' &mdash; Gebruik <strong>Ctrl+Shift+P</strong> voor het systeemdialoogvenster met alle printeropties</div>' if (rec.nieten or rec.perforeren) else ''}
    <iframe id="pdf-frame" src="/drukwerk/print/{record_id}/pdf"
            onload="setTimeout(function(){{ document.getElementById('pdf-frame').contentWindow.print(); }}, 500);">
    </iframe>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/drukwerk/print/<int:record_id>/pdf', type='http', auth='user')
    def print_pdf(self, record_id):
        """Serve the PDF with ViewerPreferences set for copies and duplex."""
        rec = request.env['drukwerk.record'].browse(record_id)
        if not rec.exists() or not rec.document_file:
            return request.not_found()

        pdf_data = base64.b64decode(rec.document_file)
        filename = rec.document_filename or 'document.pdf'

        # Convert to grayscale if zwart-wit is selected
        if rec.kleur == 'zw':
            pdf_data = self._convert_pdf_to_grayscale(pdf_data)

        # Embed print settings into PDF ViewerPreferences
        pdf_data = self._set_pdf_print_preferences(
            pdf_data,
            copies=rec.aantal_kopies or 1,
            duplex=rec.dubbelzijdig,
            formaat=rec.formaat,
        )

        return request.make_response(pdf_data, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'inline; filename="{filename}"'),
        ])

    # PDF page sizes in points (1 point = 1/72 inch)
    PAGE_SIZES = {
        'a4': (595.28, 841.89),
        'a3': (841.89, 1190.55),
    }

    @classmethod
    def _set_pdf_print_preferences(cls, pdf_bytes, copies=1, duplex=False, formaat='a4'):
        """Embed print preferences (copies, duplex, page size) into the PDF."""
        target_size = cls.PAGE_SIZES.get(formaat)

        # Try pikepdf first
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))

            viewer_prefs = pdf.Root.get('/ViewerPreferences', pikepdf.Dictionary())
            viewer_prefs['/NumCopies'] = copies
            viewer_prefs['/Duplex'] = pikepdf.Name(
                '/DuplexFlipLongEdge' if duplex else '/Simplex'
            )
            pdf.Root['/ViewerPreferences'] = viewer_prefs

            if target_size and formaat != 'a4':
                target_w, target_h = target_size
                for page in pdf.pages:
                    mediabox = page.get('/MediaBox', [0, 0, 595.28, 841.89])
                    orig_w = float(mediabox[2]) - float(mediabox[0])
                    orig_h = float(mediabox[3]) - float(mediabox[1])

                    scale_x = target_w / orig_w
                    scale_y = target_h / orig_h
                    scale = min(scale_x, scale_y)

                    offset_x = (target_w - orig_w * scale) / 2
                    offset_y = (target_h - orig_h * scale) / 2

                    content_transform = f'{scale:.4f} 0 0 {scale:.4f} {offset_x:.4f} {offset_y:.4f} cm\n'
                    original_content = pikepdf.Stream(pdf, b'q\n' + content_transform.encode() + b'\n')
                    end_content = pikepdf.Stream(pdf, b'\nQ\n')

                    existing = page.get('/Contents')
                    if isinstance(existing, pikepdf.Array):
                        page['/Contents'] = pikepdf.Array(
                            [original_content] + list(existing) + [end_content]
                        )
                    elif existing is not None:
                        page['/Contents'] = pikepdf.Array(
                            [original_content, existing, end_content]
                        )

                    page['/MediaBox'] = pikepdf.Array([0, 0, target_w, target_h])
                    if '/CropBox' in page:
                        del page['/CropBox']

            output = io.BytesIO()
            pdf.save(output)
            pdf.close()
            return output.getvalue()
        except ImportError:
            pass
        except Exception:
            _logger.warning('Failed to set PDF preferences with pikepdf', exc_info=True)

        # Try PyPDF2
        try:
            from PyPDF2 import PdfReader, PdfWriter
            from PyPDF2.generic import (
                DictionaryObject, NameObject, NumberObject,
            )
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()
            writer.append_pages_from_reader(reader)

            viewer_prefs = DictionaryObject()
            viewer_prefs[NameObject('/NumCopies')] = NumberObject(copies)
            duplex_val = '/DuplexFlipLongEdge' if duplex else '/Simplex'
            viewer_prefs[NameObject('/Duplex')] = NameObject(duplex_val)
            writer._root_object[NameObject('/ViewerPreferences')] = viewer_prefs

            if target_size and formaat != 'a4':
                target_w, target_h = target_size
                for page in writer.pages:
                    orig_w = float(page.mediabox.width)
                    orig_h = float(page.mediabox.height)
                    scale_x = target_w / orig_w
                    scale_y = target_h / orig_h
                    scale = min(scale_x, scale_y)
                    page.scale(float(scale), float(scale))
                    page.mediabox.upper_right = (target_w, target_h)
                    page.mediabox.lower_left = (0, 0)

            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()
        except ImportError:
            pass
        except Exception:
            _logger.warning('Failed to set PDF preferences with PyPDF2', exc_info=True)

        return pdf_bytes

    @staticmethod
    def _convert_pdf_to_grayscale(pdf_bytes):
        """Convert a PDF to grayscale so it prints in black-and-white."""
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))
            for page in pdf.pages:
                grayscale_prefix = pikepdf.Stream(
                    pdf,
                    b'q\n/DeviceGray cs /DeviceGray CS\n0 g 0 G\n',
                )
                grayscale_suffix = pikepdf.Stream(pdf, b'\nQ\n')

                existing = page.get('/Contents')
                if isinstance(existing, pikepdf.Array):
                    page['/Contents'] = pikepdf.Array(
                        [grayscale_prefix] + list(existing) + [grayscale_suffix]
                    )
                elif existing is not None:
                    page['/Contents'] = pikepdf.Array(
                        [grayscale_prefix, existing, grayscale_suffix]
                    )
            output = io.BytesIO()
            pdf.save(output)
            pdf.close()
            return output.getvalue()
        except ImportError:
            pass
        except Exception:
            _logger.warning('Failed to convert PDF to grayscale', exc_info=True)
        return pdf_bytes
