import base64

from odoo import http
from odoo.http import request


class DrukwerkPrintController(http.Controller):

    @http.route('/drukwerk/print/<int:line_id>', type='http', auth='user')
    def print_document(self, line_id):
        """Serve the PDF with print metadata embedded for copies."""
        line = request.env['drukwerk.line'].browse(line_id)
        if not line.exists() or not line.document_file:
            return request.not_found()

        filename = line.document_filename or 'document.pdf'
        copies = line.aantal_kopies or 1

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
        }}
        .print-info .copies {{
            background: #dc3545;
            color: white;
            padding: 4px 14px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 16px;
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
        <strong>Stel het aantal kopieën in op:</strong>
        <span class="copies">{copies}</span>
    </div>
    <iframe id="pdf-frame" src="/drukwerk/print/{line_id}/pdf"
            onload="setTimeout(function(){{ document.getElementById('pdf-frame').contentWindow.print(); }}, 500);">
    </iframe>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/drukwerk/print/<int:line_id>/pdf', type='http', auth='user')
    def print_pdf(self, line_id):
        line = request.env['drukwerk.line'].browse(line_id)
        if not line.exists() or not line.document_file:
            return request.not_found()

        pdf_data = base64.b64decode(line.document_file)
        filename = line.document_filename or 'document.pdf'

        return request.make_response(pdf_data, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'inline; filename="{filename}"'),
        ])
