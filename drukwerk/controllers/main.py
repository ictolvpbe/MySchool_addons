import base64
import io
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DrukwerkPrintController(http.Controller):

    @http.route('/drukwerk/print/<int:line_id>', type='http', auth='user')
    def print_document(self, line_id):
        """Serve the PDF with print settings pre-filled in the print dialog."""
        line = request.env['drukwerk.line'].browse(line_id)
        if not line.exists() or not line.document_file:
            return request.not_found()

        filename = line.document_filename or 'document.pdf'
        copies = line.aantal_kopies or 1
        dubbelzijdig = line.dubbelzijdig
        kleur_label = 'Kleur' if line.kleur == 'kleur' else 'Zwart-wit'
        formaat_label = line.formaat.upper() if line.formaat else 'A4'
        kopie_leerkracht = 'Ja' if line.kopie_leerkracht else 'Nee'

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
        iframe {{
            width: 100%;
            height: calc(100vh - 50px);
            border: none;
        }}
        @media print {{
            .print-info {{ display: none !important; }}
            iframe {{ height: 100vh; }}
        }}
    </style>
</head>
<body>
    <div class="print-info">
        <span><strong>Formaat:</strong> <span class="badge badge-formaat">{formaat_label}</span></span>
        <span><strong>Kleur:</strong> <span class="badge badge-{'kleur' if line.kleur == 'kleur' else 'zw'}">{kleur_label}</span></span>
        <span><strong>Kopieën:</strong> <span class="badge badge-copies">{copies}</span></span>
        <span><strong>Dubbelzijdig:</strong> <span class="badge badge-{'yes' if dubbelzijdig else 'no'}">{'Ja' if dubbelzijdig else 'Nee'}</span></span>
        <span><strong>Nieten:</strong> <span class="badge badge-{'yes' if line.nieten else 'no'}">{'Ja' if line.nieten else 'Nee'}</span></span>
        <span><strong>Perforeren:</strong> <span class="badge badge-{'yes' if line.perforeren else 'no'}">{'Ja' if line.perforeren else 'Nee'}</span></span>
        <span><strong>Kopie leerkracht:</strong> <span class="badge badge-{'yes' if line.kopie_leerkracht else 'no'}">{kopie_leerkracht}</span></span>
        {'<span class="manual-warning">&#9888; Controleer kleurinstelling in afdrukvenster</span>' if line.kleur == 'kleur' else ''}
    </div>
    <iframe id="pdf-frame" src="/drukwerk/print/{line_id}/pdf"
            onload="setTimeout(function(){{ document.getElementById('pdf-frame').contentWindow.print(); }}, 500);">
    </iframe>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/drukwerk/print_all/<int:record_id>', type='http', auth='user')
    def print_all_documents(self, record_id):
        """Show a print overview page with all documents and their settings."""
        record = request.env['drukwerk.record'].browse(record_id)
        if not record.exists():
            return request.not_found()
        lines = record.line_ids.filtered(lambda l: l.document_file)
        if not lines:
            return request.not_found()

        rows = ''
        for idx, line in enumerate(lines, 1):
            kleur_label = 'Kleur' if line.kleur == 'kleur' else 'Zwart-wit'
            kleur_class = 'badge-kleur' if line.kleur == 'kleur' else 'badge-zw'
            formaat_label = line.formaat.upper() if line.formaat else 'A4'
            duplex_label = 'Ja' if line.dubbelzijdig else 'Nee'
            duplex_class = 'badge-yes' if line.dubbelzijdig else 'badge-no'
            nieten_label = 'Ja' if line.nieten else 'Nee'
            nieten_class = 'badge-yes' if line.nieten else 'badge-no'
            perforeren_label = 'Ja' if line.perforeren else 'Nee'
            perforeren_class = 'badge-yes' if line.perforeren else 'badge-no'
            kopie_label = 'Ja' if line.kopie_leerkracht else 'Nee'
            kopie_class = 'badge-yes' if line.kopie_leerkracht else 'badge-no'
            rows += f"""
            <tr>
                <td>{idx}</td>
                <td>{line.document_filename or 'document.pdf'}</td>
                <td><span class="badge badge-formaat">{formaat_label}</span></td>
                <td><span class="badge {kleur_class}">{kleur_label}</span></td>
                <td><span class="badge badge-copies">{line.aantal_kopies or 1}</span></td>
                <td><span class="badge {duplex_class}">{duplex_label}</span></td>
                <td><span class="badge {nieten_class}">{nieten_label}</span></td>
                <td><span class="badge {perforeren_class}">{perforeren_label}</span></td>
                <td><span class="badge {kopie_class}">{kopie_label}</span></td>
                <td>
                    <a href="/drukwerk/print/{line.id}" target="_blank" class="btn-print">
                        &#128424; Afdrukken
                    </a>
                </td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Afdrukken - {record.name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 30px;
            background: #f5f5f5;
        }}
        h1 {{
            margin: 0 0 5px 0;
            font-size: 24px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 25px;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th {{
            background: #343a40;
            color: white;
            padding: 12px 15px;
            text-align: left;
            font-size: 13px;
        }}
        td {{
            padding: 10px 15px;
            border-bottom: 1px solid #eee;
            vertical-align: middle;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 13px;
            color: white;
        }}
        .badge-copies {{ background: #dc3545; }}
        .badge-yes {{ background: #28a745; }}
        .badge-no {{ background: #6c757d; }}
        .badge-kleur {{ background: #007bff; }}
        .badge-zw {{ background: #343a40; }}
        .badge-formaat {{ background: #17a2b8; }}
        .btn-print {{
            display: inline-block;
            background: #007bff;
            color: white;
            padding: 6px 16px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: bold;
            font-size: 13px;
        }}
        .btn-print:hover {{
            background: #0056b3;
        }}
    </style>
</head>
<body>
    <h1>&#128424; {record.name}</h1>
    <div class="subtitle">{record.titel or ''} &mdash; {len(lines)} document(en)</div>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Document</th>
                <th>Formaat</th>
                <th>Kleur</th>
                <th>Kopie&#235;n</th>
                <th>Dubbelzijdig</th>
                <th>Nieten</th>
                <th>Perforeren</th>
                <th>Kopie leerkracht</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/drukwerk/print/<int:line_id>/pdf', type='http', auth='user')
    def print_pdf(self, line_id):
        """Serve the PDF with ViewerPreferences set for copies and duplex."""
        line = request.env['drukwerk.line'].browse(line_id)
        if not line.exists() or not line.document_file:
            return request.not_found()

        pdf_data = base64.b64decode(line.document_file)
        filename = line.document_filename or 'document.pdf'

        # Convert to grayscale if zwart-wit is selected
        if line.kleur == 'zw':
            pdf_data = self._convert_pdf_to_grayscale(pdf_data)

        # Embed print settings into PDF ViewerPreferences
        pdf_data = self._set_pdf_print_preferences(
            pdf_data,
            copies=line.aantal_kopies or 1,
            duplex=line.dubbelzijdig,
            formaat=line.formaat,
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
        """Embed print preferences (copies, duplex, page size) into the PDF.

        Sets ViewerPreferences for copies and duplex, and resizes pages
        when the requested format differs from the original (e.g. A4 -> A3).
        """
        target_size = cls.PAGE_SIZES.get(formaat)

        # Try pikepdf first
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))

            # Set ViewerPreferences
            viewer_prefs = pdf.Root.get('/ViewerPreferences', pikepdf.Dictionary())
            viewer_prefs['/NumCopies'] = copies
            viewer_prefs['/Duplex'] = pikepdf.Name(
                '/DuplexFlipLongEdge' if duplex else '/Simplex'
            )
            pdf.Root['/ViewerPreferences'] = viewer_prefs

            # Resize pages to target format if needed
            if target_size and formaat != 'a4':
                target_w, target_h = target_size
                for page in pdf.pages:
                    mediabox = page.get('/MediaBox', [0, 0, 595.28, 841.89])
                    orig_w = float(mediabox[2]) - float(mediabox[0])
                    orig_h = float(mediabox[3]) - float(mediabox[1])

                    # Scale content to fit target size proportionally
                    scale_x = target_w / orig_w
                    scale_y = target_h / orig_h
                    scale = min(scale_x, scale_y)

                    # Center the content on the new page
                    offset_x = (target_w - orig_w * scale) / 2
                    offset_y = (target_h - orig_h * scale) / 2

                    # Create transformation matrix: translate + scale
                    content_transform = f'{scale:.4f} 0 0 {scale:.4f} {offset_x:.4f} {offset_y:.4f} cm\n'
                    # Wrap existing content in a save/restore with the transform
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

                    # Set new page size
                    page['/MediaBox'] = pikepdf.Array([0, 0, target_w, target_h])
                    # Remove CropBox if present so it doesn't override
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

            # Set ViewerPreferences
            viewer_prefs = DictionaryObject()
            viewer_prefs[NameObject('/NumCopies')] = NumberObject(copies)
            duplex_val = '/DuplexFlipLongEdge' if duplex else '/Simplex'
            viewer_prefs[NameObject('/Duplex')] = NameObject(duplex_val)
            writer._root_object[NameObject('/ViewerPreferences')] = viewer_prefs

            # Resize pages to target format if needed
            if target_size and formaat != 'a4':
                target_w, target_h = target_size
                for page in writer.pages:
                    orig_w = float(page.mediabox.width)
                    orig_h = float(page.mediabox.height)
                    scale_x = target_w / orig_w
                    scale_y = target_h / orig_h
                    scale = min(scale_x, scale_y)
                    page.scale(float(scale), float(scale))
                    # Update mediabox to exact target size
                    page.mediabox.upper_right = (target_w, target_h)
                    page.mediabox.lower_left = (0, 0)

            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()
        except ImportError:
            pass
        except Exception:
            _logger.warning('Failed to set PDF preferences with PyPDF2', exc_info=True)

        # No PDF library available, return original
        return pdf_bytes

    @staticmethod
    def _convert_pdf_to_grayscale(pdf_bytes):
        """Convert a PDF to grayscale so it prints in black-and-white.

        Prepends a grayscale color override to each page's content stream,
        forcing all content to render in shades of gray.
        """
        try:
            import pikepdf
            pdf = pikepdf.open(io.BytesIO(pdf_bytes))
            for page in pdf.pages:
                # Prepend a DeviceGray color space override
                # 'q' saves state, set fill and stroke to black in gray colorspace
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
