import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# 1x1 transparent GIF pixel
TRACKING_PIXEL = base64.b64decode(
    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
)

LANDING_PAGE_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Inloggen</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .login-box {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
        }}
        .login-box h2 {{
            margin-top: 0;
            color: #1a1a2e;
            text-align: center;
        }}
        .form-group {{
            margin-bottom: 16px;
        }}
        .form-group label {{
            display: block;
            margin-bottom: 4px;
            font-weight: 600;
            color: #333;
        }}
        .form-group input {{
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            box-sizing: border-box;
        }}
        .btn-login {{
            width: 100%;
            padding: 12px;
            background: #4a69bd;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
        }}
        .btn-login:hover {{
            background: #3c5aa6;
        }}
        .alert {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 16px;
            border-radius: 4px;
            text-align: center;
            margin-top: 20px;
        }}
        .alert h3 {{
            color: #856404;
            margin-top: 0;
        }}
        .alert p {{
            color: #856404;
            margin-bottom: 0;
        }}
    </style>
</head>
<body>
    <div class="login-box">
        {content}
    </div>
</body>
</html>"""

LOGIN_FORM = """
<h2>Inloggen</h2>
<form method="post" action="/phishing/landing/{token}">
    <input type="hidden" name="csrf_token" value="{csrf_token}"/>
    <div class="form-group">
        <label for="login">E-mailadres</label>
        <input type="email" id="login" name="login" required="required"
               placeholder="uw.email@bedrijf.nl"/>
    </div>
    <div class="form-group">
        <label for="password">Wachtwoord</label>
        <input type="password" id="password" name="password" required="required"
               placeholder="Wachtwoord"/>
    </div>
    <button type="submit" class="btn-login">Inloggen</button>
</form>
"""

AWARENESS_MESSAGE = """
<h2>Phishing Bewustwording</h2>
<div class="alert">
    <h3>Dit was een phishing simulatie</h3>
    <p>
        U heeft zojuist inloggegevens ingevoerd op een nep-inlogpagina.
        In een echte aanval zouden uw gegevens nu in handen van een aanvaller zijn.
    </p>
    <p style="margin-top: 12px;">
        <strong>Tip:</strong> Controleer altijd de URL in de adresbalk voordat u
        inloggegevens invoert. Neem bij twijfel contact op met de IT-helpdesk.
    </p>
</div>
"""

REPORT_CONFIRMATION = """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Bedankt voor uw melding</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .box {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 500px;
            text-align: center;
        }}
        .success {{
            background: #d4edda;
            border: 1px solid #28a745;
            padding: 16px;
            border-radius: 4px;
        }}
        .success h3 {{
            color: #155724;
            margin-top: 0;
        }}
        .success p {{
            color: #155724;
            margin-bottom: 0;
        }}
    </style>
</head>
<body>
    <div class="box">
        <div class="success">
            <h3>Bedankt voor uw melding!</h3>
            <p>
                U heeft correct een verdachte e-mail gerapporteerd.
                Dit was een phishing simulatie als onderdeel van ons bewustwordingsprogramma.
            </p>
            <p style="margin-top: 12px;">
                <strong>Goed gedaan!</strong> Blijf alert op verdachte e-mails.
            </p>
        </div>
    </div>
</body>
</html>"""


class PhishingController(http.Controller):

    def _get_target_by_token(self, token):
        """Zoek een phishing doelwit op basis van token."""
        if not token or len(token) != 32:
            return None
        return (
            request.env['phishing.target']
            .sudo()
            .search([('token', '=', token)], limit=1)
        )

    @http.route(
        '/phishing/track/<string:token>',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def track(self, token, **kwargs):
        """Trackingpixel endpoint — registreert dat de e-mail is geopend/geklikt."""
        target = self._get_target_by_token(token)
        if target:
            try:
                target.action_record_click()
                _logger.info('Phishing click recorded for target %s.', target.id)
            except Exception:
                _logger.exception('Error recording phishing click.')

        return request.make_response(
            TRACKING_PIXEL,
            headers=[
                ('Content-Type', 'image/gif'),
                ('Content-Length', str(len(TRACKING_PIXEL))),
                ('Cache-Control', 'no-store, no-cache, must-revalidate'),
                ('Pragma', 'no-cache'),
            ],
        )

    @http.route(
        '/phishing/report/<string:token>',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def report(self, token, **kwargs):
        """Rapporteer-endpoint — medewerker meldt een verdachte e-mail."""
        target = self._get_target_by_token(token)
        if target:
            try:
                target.action_record_report()
                _logger.info('Phishing report recorded for target %s.', target.id)
            except Exception:
                _logger.exception('Error recording phishing report.')

        return request.make_response(
            REPORT_CONFIRMATION,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )

    @http.route(
        '/phishing/landing/<string:token>',
        type='http', auth='public', methods=['GET', 'POST'], csrf=False,
    )
    def landing(self, token, **kwargs):
        """Nep-inlogpagina — registreert poging tot invoer van inloggegevens."""
        target = self._get_target_by_token(token)

        if request.httprequest.method == 'POST':
            # Record credential submission — we never store actual credentials
            if target:
                try:
                    target.action_record_credentials()
                    _logger.info(
                        'Phishing credentials attempt recorded for target %s.',
                        target.id,
                    )
                except Exception:
                    _logger.exception('Error recording credentials attempt.')

            html = LANDING_PAGE_HTML.format(content=AWARENESS_MESSAGE)
            return request.make_response(
                html,
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )

        # GET — show fake login form
        if target:
            try:
                target.action_record_click()
            except Exception:
                _logger.exception('Error recording landing page click.')

        csrf_token = request.csrf_token()
        form = LOGIN_FORM.format(token=token, csrf_token=csrf_token)
        html = LANDING_PAGE_HTML.format(content=form)
        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
