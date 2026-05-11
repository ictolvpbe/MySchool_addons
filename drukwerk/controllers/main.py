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
        kleur_label = 'Kleur' if rec.kleur == 'kleur' else 'Zwart-wit'
        formaat_label = rec.formaat.upper() if rec.formaat else 'A4'

        # Printernaam komt uit drukwerk.config (eenmalig per omgeving in
        # te stellen). Fallback: 'Drukkerij'.
        printer_naam = request.env['ir.config_parameter'].sudo().get_param(
            'drukwerk.printer_naam', 'Drukkerij')

        # Papierkleur-label
        papier_kleur_map = {
            'geen': 'Wit (standaard)',
            'groen': 'Groen',
            'geel': 'Geel',
            'blauw': 'Blauw',
        }
        papier_kleur_label = papier_kleur_map.get(rec.papier_kleur, 'Wit')

        # Welke finishing-opties zijn aangevinkt
        finishing = []
        if rec.nieten:
            finishing.append('NIETEN')
        if rec.perforeren:
            finishing.append('PERFOREREN')
        if rec.sorteren:
            finishing.append('SORTEREN')
        if rec.a3_plooien:
            finishing.append('A3 PLOOIEN')
        if rec.boekje_a4:
            finishing.append('BOEKJE A4')
        if rec.liggend:
            finishing.append('LIGGEND')
        if rec.dik_papier:
            finishing.append('DIK PAPIER')
        if rec.papier_kleur and rec.papier_kleur != 'geen':
            finishing.append(f'PAPIER: {papier_kleur_label.upper()}')

        # Printer code prominent
        printer_code = rec.printer_code or '-'

        # Render row per setting
        def row(label, value, color='secondary'):
            return (
                f'<div class="setting-row">'
                f'<span class="setting-label">{label}</span>'
                f'<span class="badge badge-{color}">{value}</span>'
                f'</div>'
            )

        rows_html = ''
        rows_html += row('Afdrukker', printer_naam, 'printer')
        if printer_code != '-':
            rows_html += row('Printer code', printer_code, 'code')
        rows_html += row('Formaat', formaat_label, 'formaat')
        rows_html += row('Kleur', kleur_label,
                         'kleur' if rec.kleur == 'kleur' else 'zw')
        rows_html += row('Kopieën', str(copies), 'copies')
        rows_html += row(
            'Dubbelzijdig', 'Ja' if rec.dubbelzijdig else 'Nee',
            'yes' if rec.dubbelzijdig else 'no')
        rows_html += row(
            'Papier', papier_kleur_label,
            'paper' if rec.papier_kleur and rec.papier_kleur != 'geen' else 'no')
        rows_html += row(
            'Kopie leerkracht', 'Ja' if rec.kopie_leerkracht else 'Nee',
            'yes' if rec.kopie_leerkracht else 'no')

        # Finishing alert prominent
        finishing_html = ''
        if finishing or rec.opmerking:
            parts = []
            if finishing:
                parts.append(
                    '<strong>Finishing:</strong> ' + ' &middot; '.join(finishing))
            if rec.opmerking:
                parts.append(
                    f'<strong>Opmerking:</strong> {rec.opmerking}')
            finishing_html = (
                '<div class="finishing-alert">'
                '<span class="finish-icon">&#9888;</span> '
                + ' &mdash; '.join(parts)
                + ' &mdash; gebruik <strong>Ctrl+Shift+P</strong> voor '
                'het systeemdialoogvenster met alle printeropties'
                '</div>'
            )

        iframe_offset = 220 + (40 if finishing_html else 0)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Afdrukken - {filename}</title>
    <style>
        body {{ margin: 0; font-family: Arial, sans-serif; }}
        .print-header {{
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
            padding: 12px 25px;
        }}
        .print-header h1 {{
            margin: 0 0 8px 0;
            font-size: 18px;
            color: #007d8c;
        }}
        .print-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 8px 24px;
        }}
        .setting-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 14px;
        }}
        .setting-label {{
            color: #555;
            min-width: 110px;
        }}
        .badge {{
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 13px;
        }}
        .badge-printer {{ background: #007d8c; color: white; }}
        .badge-code {{
            background: #6f42c1;
            color: white;
            font-family: monospace;
            letter-spacing: 1px;
        }}
        .badge-formaat {{ background: #17a2b8; color: white; }}
        .badge-kleur {{ background: #007bff; color: white; }}
        .badge-zw {{ background: #343a40; color: white; }}
        .badge-copies {{ background: #dc3545; color: white; }}
        .badge-yes {{ background: #28a745; color: white; }}
        .badge-no {{ background: #6c757d; color: white; }}
        .badge-paper {{ background: #fd7e14; color: white; }}
        .finishing-alert {{
            background: #f8d7da;
            border: 2px solid #dc3545;
            border-radius: 6px;
            padding: 10px 20px;
            margin: 12px 25px;
            font-size: 14px;
            color: #721c24;
        }}
        .finishing-alert .finish-icon {{ font-size: 18px; }}
        iframe {{
            width: 100%;
            height: calc(100vh - {iframe_offset}px);
            border: none;
        }}
        @media print {{
            .print-header, .finishing-alert {{ display: none !important; }}
            iframe {{ height: 100vh; }}
        }}
    </style>
</head>
<body>
    <div class="print-header">
        <h1>Afdrukinstellingen — {rec.name or ''}</h1>
        <div class="print-grid">{rows_html}</div>
    </div>
    {finishing_html}
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
