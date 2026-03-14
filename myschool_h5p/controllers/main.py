import base64
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class H5PController(http.Controller):

    @http.route('/h5p/download/<int:content_id>', type='http', auth='user')
    def h5p_download(self, content_id):
        """Serve the raw .h5p file for h5p-standalone to fetch and extract."""
        content = request.env['h5p.content'].browse(content_id)
        if not content.exists() or not content.h5p_file:
            return request.not_found()

        file_data = base64.b64decode(content.h5p_file)
        filename = content.h5p_filename or 'content.h5p'
        return request.make_response(file_data, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Length', str(len(file_data))),
            ('Content-Disposition', f'inline; filename="{filename}"'),
            ('Cache-Control', 'public, max-age=3600'),
        ])

    @http.route('/h5p/play/<int:content_id>', type='http', auth='user')
    def h5p_player(self, content_id):
        """Render a standalone H5P player page."""
        content = request.env['h5p.content'].browse(content_id)
        if not content.exists() or not content.h5p_file:
            return request.not_found()

        h5p_file_url = f'/h5p/download/{content_id}'
        xapi_url = f'/h5p/xapi/{content_id}'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{self._esc(content.name)} — H5P Player</title>
    <script src="https://cdn.jsdelivr.net/npm/h5p-standalone@3.7.2/dist/main.bundle.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0; padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
        }}
        .h5p-page-header {{
            background: #1a237e; color: #fff;
            padding: 16px 24px;
            display: flex; align-items: center; gap: 16px;
        }}
        .h5p-page-header h1 {{ margin: 0; font-size: 20px; font-weight: 500; }}
        .h5p-page-header .back-link {{
            color: #bbdefb; text-decoration: none; font-size: 14px;
        }}
        .h5p-page-header .back-link:hover {{ color: #fff; }}
        #h5p-container {{
            max-width: 960px; margin: 24px auto;
            background: #fff; border-radius: 8px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            padding: 24px; min-height: 400px;
        }}
        .h5p-loading {{
            text-align: center; padding: 60px 20px; color: #666;
        }}
        .h5p-error {{
            text-align: center; padding: 40px 20px; color: #c62828;
            background: #ffebee; border-radius: 8px; margin: 20px;
        }}
        .h5p-result-banner {{
            max-width: 960px; margin: 0 auto 24px;
            padding: 16px 24px; border-radius: 8px;
            background: #e8f5e9; border: 1px solid #a5d6a7;
            display: none; text-align: center; font-size: 16px;
        }}
        .h5p-result-banner.show {{ display: block; }}
    </style>
</head>
<body>
    <div class="h5p-page-header">
        <a href="/odoo/h5p-learning" class="back-link">&#8592; Back</a>
        <h1>{self._esc(content.name)}</h1>
    </div>

    <div id="h5p-result-banner" class="h5p-result-banner"></div>

    <div id="h5p-container">
        <div class="h5p-loading">Loading H5P content&hellip;</div>
    </div>

    <script>
    (function() {{
        var el = document.getElementById('h5p-container');
        var banner = document.getElementById('h5p-result-banner');
        var resultSent = false;

        new H5PStandalone.H5P(el, '{h5p_file_url}')
            .then(function() {{
                console.log('H5P content loaded successfully');
                // Listen for xAPI events
                if (window.H5P && window.H5P.externalDispatcher) {{
                    window.H5P.externalDispatcher.on('xAPI', function(event) {{
                        var stmt = event.data.statement;
                        if (!stmt || !stmt.verb) return;

                        var verb = stmt.verb.id || '';
                        var verbName = verb.split('/').pop();
                        console.log('xAPI event:', verbName, stmt);

                        // Only record scored/completed/answered events
                        if (stmt.result && (stmt.result.score || stmt.result.completion)) {{
                            var score = (stmt.result.score && stmt.result.score.raw) || 0;
                            var maxScore = (stmt.result.score && stmt.result.score.max) || 0;
                            var completion = stmt.result.completion || false;
                            var duration = 0;
                            if (stmt.result.duration) {{
                                // Parse ISO 8601 duration (e.g. PT12.34S)
                                var m = stmt.result.duration.match(/PT(?:(\\d+)H)?(?:(\\d+)M)?(?:([\\d.]+)S)?/);
                                if (m) {{
                                    duration = (parseInt(m[1]||0) * 3600)
                                             + (parseInt(m[2]||0) * 60)
                                             + Math.round(parseFloat(m[3]||0));
                                }}
                            }}

                            // Show result banner
                            if (maxScore > 0) {{
                                var pct = Math.round((score / maxScore) * 100);
                                banner.innerHTML = 'Score: ' + score + ' / ' + maxScore
                                                 + ' (' + pct + '%)';
                                banner.className = 'h5p-result-banner show';
                            }}

                            // Send to Odoo (only send the final/best result)
                            if (!resultSent || completion) {{
                                resultSent = completion;
                                fetch('{xapi_url}', {{
                                    method: 'POST',
                                    headers: {{'Content-Type': 'application/json'}},
                                    body: JSON.stringify({{
                                        jsonrpc: '2.0',
                                        method: 'call',
                                        params: {{
                                            score: score,
                                            max_score: maxScore,
                                            completion: completion,
                                            duration: duration,
                                            xapi_verb: verbName,
                                            xapi_data: JSON.stringify(stmt)
                                        }}
                                    }})
                                }}).then(function(r) {{ return r.json(); }})
                                  .then(function(data) {{
                                    if (data.result && data.result.success) {{
                                        console.log('Result saved to Odoo');
                                    }}
                                }}).catch(function(err) {{
                                    console.warn('Failed to save result:', err);
                                }});
                            }}
                        }}
                    }});
                }}
            }})
            .catch(function(err) {{
                console.error('H5P load error:', err);
                el.innerHTML = '<div class="h5p-error">'
                    + '<h2>Failed to load H5P content</h2>'
                    + '<p>' + err.message + '</p>'
                    + '<p>Make sure the .h5p file is valid.</p></div>';
            }});
    }})();
    </script>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/h5p/xapi/<int:content_id>', type='json', auth='user')
    def h5p_xapi(self, content_id, score=0, max_score=0, completion=False,
                 duration=0, xapi_verb='', xapi_data=''):
        """Receive xAPI result from the H5P player and store it."""
        content = request.env['h5p.content'].browse(content_id)
        if not content.exists():
            return {'success': False, 'error': 'Content not found'}

        try:
            request.env['h5p.result'].create({
                'content_id': content_id,
                'user_id': request.env.uid,
                'score': float(score),
                'max_score': float(max_score),
                'completion': bool(completion),
                'duration': int(duration),
                'xapi_verb': str(xapi_verb)[:64] if xapi_verb else '',
                'xapi_data': str(xapi_data)[:10000] if xapi_data else '',
            })
            return {'success': True}
        except Exception as e:
            _logger.exception('Failed to save H5P result for content %s', content_id)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _esc(text):
        """Basic HTML escaping for the player page."""
        if not text:
            return ''
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))
