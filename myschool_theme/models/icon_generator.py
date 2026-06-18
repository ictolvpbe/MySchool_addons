import hashlib
import io
import os

from PIL import Image, ImageDraw, ImageFont

ICON_SIZE = 100
RADIUS = 18
_fa_font_path = None


def _find_fa_font():
    """Find the FontAwesome TTF font bundled with Odoo's web module."""
    global _fa_font_path
    if _fa_font_path is not None:
        return _fa_font_path

    base = os.path.dirname(os.path.abspath(__file__))
    for depth in range(1, 6):
        parent = base
        for _ in range(depth):
            parent = os.path.dirname(parent)
        candidate = os.path.join(
            parent, 'odoo', 'addons', 'web', 'static', 'src',
            'libs', 'fontawesome', 'fonts', 'fontawesome-webfont.ttf',
        )
        if os.path.isfile(candidate):
            _fa_font_path = candidate
            return _fa_font_path

    _fa_font_path = ''
    return _fa_font_path


def _hex_to_rgba(hex_color, alpha=255):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r, g, b, alpha)


def _lighten(rgba, factor=0.35):
    r, g, b = rgba[:3]
    return (r + int((255 - r) * factor), g + int((255 - g) * factor),
            b + int((255 - b) * factor), 255)


def _darken(rgba, factor=0.3):
    r, g, b = rgba[:3]
    return (int(r * (1 - factor)), int(g * (1 - factor)), int(b * (1 - factor)), 255)


def _module_hash(name):
    return int(hashlib.md5(name.encode()).hexdigest(), 16)


WHITE = (255, 255, 255, 255)


# ---------------------------------------------------------------------------
# Semantic shape compositions — each tells what the app does
# ---------------------------------------------------------------------------

def _shape_calendar(d, m, a, dk):
    """Calendar / activities — grid of day squares with header bar."""
    # Calendar header bar
    d.rounded_rectangle([10, 8, 90, 30], radius=6, fill=m)
    # Two small "rings" on top
    d.rounded_rectangle([25, 3, 31, 18], radius=3, fill=dk)
    d.rounded_rectangle([69, 3, 75, 18], radius=3, fill=dk)
    # Day grid (3x3)
    for row in range(3):
        for col in range(3):
            x = 15 + col * 25
            y = 36 + row * 20
            color = a if (row + col) % 3 == 0 else m
            d.rounded_rectangle([x, y, x + 20, y + 15], radius=3, fill=color)


def _shape_dashboard(d, m, a, dk):
    """Dashboard / gauge — semicircle gauge with indicator."""
    # Gauge arc
    d.pieslice([10, 20, 90, 100], 200, 340, fill=m)
    d.pieslice([22, 32, 78, 88], 200, 340, fill=WHITE)
    # Needle
    d.polygon([(50, 40), (46, 72), (54, 72)], fill=dk)
    # Base dot
    d.ellipse([42, 64, 58, 80], fill=a)
    # Small bars below
    d.rounded_rectangle([15, 85, 40, 93], radius=3, fill=a)
    d.rounded_rectangle([45, 85, 85, 93], radius=3, fill=m)


def _shape_code(d, m, a, dk):
    """Code / developer hub — angle brackets and slash."""
    # Left bracket <
    d.polygon([(35, 25), (10, 50), (35, 75)], fill=m)
    # Right bracket >
    d.polygon([(65, 25), (90, 50), (65, 75)], fill=a)
    # Center slash
    d.polygon([(55, 18), (62, 18), (45, 82), (38, 82)], fill=dk)


def _shape_monitor(d, m, a, dk):
    """IT / desktop — monitor screen with stand."""
    # Screen
    d.rounded_rectangle([10, 12, 90, 68], radius=8, fill=m)
    # Screen inner
    d.rounded_rectangle([16, 18, 84, 62], radius=4, fill=a)
    # Stand neck
    d.rectangle([42, 68, 58, 78], fill=dk)
    # Stand base
    d.rounded_rectangle([28, 78, 72, 86], radius=4, fill=dk)


def _shape_cog(d, m, a, dk):
    """Admin — person in suit with gear head."""
    import math
    # Suit body (dark trapezoid / shoulders)
    d.polygon([(18, 95), (30, 52), (50, 48), (70, 52), (82, 95)], fill=dk)
    # Shirt / collar (V-shape)
    d.polygon([(38, 52), (50, 70), (62, 52)], fill=_lighten(a, 0.5))
    # Tie
    d.polygon([(47, 58), (53, 58), (51, 80), (49, 80)], fill=a)
    # Gear head
    d.ellipse([30, 8, 70, 48], fill=m)
    d.ellipse([38, 16, 62, 40], fill=WHITE)
    d.ellipse([42, 20, 58, 36], fill=m)
    # Gear teeth
    for i in range(8):
        angle = i * (360 / 8) * math.pi / 180
        cx = 50 + 23 * math.cos(angle)
        cy = 28 + 23 * math.sin(angle)
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=m)


def _shape_laptop(d, m, a, dk):
    """Assets / devices — laptop shape."""
    # Screen
    d.rounded_rectangle([18, 15, 82, 62], radius=6, fill=m)
    # Screen inner glow
    d.rounded_rectangle([24, 21, 76, 56], radius=3, fill=a)
    # Keyboard base
    d.rounded_rectangle([8, 65, 92, 80], radius=6, fill=dk)
    # Trackpad
    d.rounded_rectangle([40, 68, 60, 77], radius=2, fill=_lighten(dk, 0.3))


def _shape_play(d, m, a, dk):
    """H5P / media — play button in circle."""
    # Outer circle
    d.ellipse([10, 10, 90, 90], fill=m)
    # Inner circle
    d.ellipse([18, 18, 82, 82], fill=a)
    # Play triangle
    d.polygon([(40, 28), (40, 72), (75, 50)], fill=WHITE)


def _shape_sync(d, m, a, dk):
    """Sync / refresh — two curved arrows."""
    # Top arc
    d.pieslice([15, 10, 85, 80], 200, 350, fill=m)
    d.pieslice([25, 20, 75, 70], 200, 350, fill=WHITE)
    # Arrow head top
    d.polygon([(70, 15), (82, 30), (62, 30)], fill=m)
    # Bottom arc
    d.pieslice([15, 20, 85, 90], 20, 170, fill=a)
    d.pieslice([25, 30, 75, 80], 20, 170, fill=WHITE)
    # Arrow head bottom
    d.polygon([(30, 85), (18, 70), (38, 70)], fill=a)


def _shape_tasks(d, m, a, dk):
    """Planner / tasks — checklist with checkmarks."""
    # Three rows
    for i, color in enumerate([m, a, dk]):
        y = 15 + i * 28
        # Checkbox
        d.rounded_rectangle([12, y, 30, y + 20], radius=4, fill=color)
        # Checkmark (small V)
        if i < 2:
            d.line([(17, y + 10), (20, y + 15), (27, y + 5)], fill=WHITE, width=3)
        # Line
        d.rounded_rectangle([38, y + 4, 88, y + 16], radius=4, fill=color)


def _shape_graduation(d, m, a, dk):
    """Learning / professionalization — graduation cap."""
    # Cap top (diamond shape)
    d.polygon([(50, 15), (90, 40), (50, 55), (10, 40)], fill=m)
    # Cap brim accent
    d.polygon([(50, 30), (80, 44), (50, 55), (20, 44)], fill=a)
    # Tassel
    d.line([(50, 40), (50, 55), (70, 70)], fill=dk, width=3)
    d.ellipse([66, 66, 76, 76], fill=dk)
    # Base band
    d.rounded_rectangle([22, 55, 78, 65], radius=3, fill=m)
    # Hanging sides
    d.polygon([(22, 55), (22, 75), (30, 65)], fill=a)
    d.polygon([(78, 55), (78, 75), (70, 65)], fill=a)


def _shape_sitemap(d, m, a, dk):
    """Process / workflow — connected nodes."""
    # Top node
    d.ellipse([38, 5, 62, 29], fill=m)
    # Lines down
    d.line([(50, 29), (50, 40)], fill=dk, width=3)
    d.line([(50, 40), (20, 50)], fill=dk, width=3)
    d.line([(50, 40), (80, 50)], fill=dk, width=3)
    d.line([(50, 40), (50, 50)], fill=dk, width=3)
    # Three bottom nodes
    d.ellipse([8, 50, 32, 74], fill=a)
    d.ellipse([38, 50, 62, 74], fill=m)
    d.ellipse([68, 50, 92, 74], fill=a)
    # Bottom sub-nodes
    d.line([(20, 74), (20, 82)], fill=dk, width=2)
    d.line([(80, 74), (80, 82)], fill=dk, width=2)
    d.rounded_rectangle([10, 82, 30, 95], radius=3, fill=dk)
    d.rounded_rectangle([70, 82, 90, 95], radius=3, fill=dk)


def _shape_book(d, m, a, dk):
    """Knowledge / book — open book shape."""
    # Left page
    d.rounded_rectangle([8, 15, 48, 85], radius=6, fill=m)
    # Right page
    d.rounded_rectangle([52, 15, 92, 85], radius=6, fill=a)
    # Spine
    d.rectangle([46, 12, 54, 88], fill=dk)
    # Text lines left
    for y in range(30, 75, 12):
        d.rounded_rectangle([15, y, 42, y + 5], radius=2, fill=_lighten(m, 0.4))
    # Text lines right
    for y in range(30, 75, 12):
        d.rounded_rectangle([58, y, 86, y + 5], radius=2, fill=_lighten(a, 0.4))


def _shape_euro(d, m, a, dk):
    """Costs / finance — euro/currency symbol with chart."""
    # Coin circle
    d.ellipse([5, 20, 55, 70], fill=m)
    d.ellipse([14, 29, 46, 61], fill=WHITE)
    # Euro sign approximation
    d.pieslice([18, 33, 42, 57], 45, 315, fill=a)
    d.pieslice([22, 37, 38, 53], 45, 315, fill=WHITE)
    d.rectangle([16, 42, 38, 46], fill=a)
    d.rectangle([16, 48, 38, 52], fill=a)
    # Rising bar chart on right
    d.rounded_rectangle([60, 55, 72, 85], radius=3, fill=a)
    d.rounded_rectangle([76, 35, 88, 85], radius=3, fill=m)
    d.rounded_rectangle([60, 80, 88, 85], radius=2, fill=dk)


def _shape_shield(d, m, a, dk):
    """Security — shield shape."""
    # Shield outline
    d.polygon([(50, 8), (88, 25), (85, 65), (50, 92), (15, 65), (12, 25)], fill=m)
    # Inner shield
    d.polygon([(50, 18), (78, 32), (76, 62), (50, 82), (24, 62), (22, 32)], fill=a)
    # Checkmark
    d.line([(35, 50), (46, 62), (68, 38)], fill=WHITE, width=5)


def _shape_users(d, m, a, dk):
    """HR / people — group of people silhouettes."""
    # Back person (smaller, offset)
    d.ellipse([22, 10, 42, 30], fill=a)
    d.pieslice([16, 30, 48, 65], 0, 180, fill=a)
    # Front person (larger, centered)
    d.ellipse([50, 8, 74, 32], fill=m)
    d.pieslice([42, 32, 82, 72], 0, 180, fill=m)
    # Third person hint
    d.ellipse([8, 22, 24, 38], fill=dk)
    d.pieslice([4, 38, 28, 62], 0, 180, fill=dk)
    # Base line
    d.rounded_rectangle([5, 68, 95, 78], radius=4, fill=_lighten(m, 0.2))


def _shape_cart(d, m, a, dk):
    """Sales / shopping — cart shape."""
    # Cart body
    d.polygon([(15, 25), (85, 25), (78, 60), (22, 60)], fill=m)
    # Cart inner
    d.polygon([(22, 32), (78, 32), (74, 54), (26, 54)], fill=a)
    # Handle
    d.line([(15, 25), (8, 12)], fill=dk, width=4)
    # Wheels
    d.ellipse([25, 65, 40, 80], fill=dk)
    d.ellipse([60, 65, 75, 80], fill=dk)
    d.ellipse([29, 69, 36, 76], fill=WHITE)
    d.ellipse([64, 69, 71, 76], fill=WHITE)


def _shape_globe(d, m, a, dk):
    """Website / web — globe with meridians."""
    # Globe circle
    d.ellipse([12, 12, 88, 88], fill=m)
    # Horizontal band
    d.ellipse([12, 30, 88, 70], fill=a)
    # Inner circle (creates meridian effect)
    d.ellipse([32, 12, 68, 88], fill=dk)
    d.ellipse([38, 12, 62, 88], fill=m)
    # Center highlight
    d.ellipse([22, 22, 78, 78], outline=_lighten(m, 0.3), width=2)


def _shape_envelope(d, m, a, dk):
    """Mail / messaging — envelope shape."""
    # Envelope body
    d.rounded_rectangle([8, 22, 92, 78], radius=6, fill=m)
    # Flap (triangle)
    d.polygon([(8, 22), (92, 22), (50, 55)], fill=a)
    # Bottom flap accent
    d.polygon([(8, 78), (50, 52), (92, 78)], fill=dk)


def _shape_chart(d, m, a, dk):
    """Reports / charts — bar chart."""
    # Bars
    d.rounded_rectangle([12, 50, 28, 85], radius=4, fill=a)
    d.rounded_rectangle([33, 30, 49, 85], radius=4, fill=m)
    d.rounded_rectangle([54, 42, 70, 85], radius=4, fill=dk)
    d.rounded_rectangle([75, 15, 91, 85], radius=4, fill=a)
    # Base line
    d.rectangle([8, 85, 95, 89], fill=m)


def _shape_database(d, m, a, dk):
    """Data / database — cylinder/stack shape."""
    # Bottom ellipse
    d.ellipse([15, 65, 85, 90], fill=dk)
    # Middle body
    d.rectangle([15, 40, 85, 78], fill=m)
    # Middle ellipse
    d.ellipse([15, 45, 85, 70], fill=a)
    # Top body
    d.rectangle([15, 20, 85, 55], fill=m)
    # Top ellipse
    d.ellipse([15, 12, 85, 37], fill=a)


def _shape_cubes(d, m, a, dk):
    """Stock / inventory — stacked boxes."""
    # Back box
    d.rounded_rectangle([40, 8, 90, 52], radius=6, fill=a)
    d.rounded_rectangle([45, 13, 85, 47], radius=3, fill=_lighten(a, 0.3))
    # Front box
    d.rounded_rectangle([10, 42, 60, 92], radius=6, fill=m)
    d.rounded_rectangle([15, 47, 55, 87], radius=3, fill=_lighten(m, 0.3))
    # Small box
    d.rounded_rectangle([58, 55, 88, 85], radius=5, fill=dk)


def _shape_wrench(d, m, a, dk):
    """Maintenance / tools — wrench shape."""
    # Wrench head
    d.ellipse([12, 8, 50, 46], fill=m)
    d.ellipse([22, 18, 40, 36], fill=WHITE)
    # Handle
    d.polygon([(35, 38), (42, 38), (85, 80), (78, 88)], fill=a)
    # Handle grip
    d.rounded_rectangle([68, 72, 90, 92], radius=4, fill=dk)


def _shape_request(d, m, a, dk):
    """Requests / aanvragen — laptop with checklist document on top."""
    PAPER = (230, 235, 240, 255)  # light grey paper
    # Laptop base
    d.rounded_rectangle([5, 72, 95, 85], radius=6, fill=dk)
    # Laptop screen (behind document)
    d.rounded_rectangle([12, 38, 88, 74], radius=6, fill=m)
    d.rounded_rectangle([16, 42, 84, 70], radius=3, fill=_lighten(m, 0.35))
    # Document paper (on top of laptop)
    d.rounded_rectangle([22, 5, 72, 68], radius=5, fill=PAPER)
    # Folded corner
    d.polygon([(58, 5), (72, 5), (72, 19)], fill=_lighten(a, 0.3))
    d.polygon([(58, 5), (72, 19), (58, 19)], fill=a)
    # Checklist lines with checkmarks
    for i, y in enumerate([24, 38, 52]):
        # Line
        d.rounded_rectangle([30, y + 2, 55, y + 7], radius=2, fill=m)
        # Checkmark
        d.line([(60, y + 3), (63, y + 7), (68, y)], fill=a, width=2)


def _shape_printer(d, m, a, dk):
    """Drukwerk / printing — printer with paper."""
    # Printer body
    d.rounded_rectangle([10, 30, 90, 70], radius=8, fill=m)
    # Paper input (top)
    d.rounded_rectangle([25, 8, 75, 38], radius=4, fill=(230, 235, 240, 255))
    # Text lines on paper
    d.rounded_rectangle([32, 15, 68, 19], radius=2, fill=a)
    d.rounded_rectangle([32, 23, 60, 27], radius=2, fill=a)
    # Paper output (bottom)
    d.rounded_rectangle([25, 62, 75, 92], radius=4, fill=(230, 235, 240, 255))
    # Text lines on output
    d.rounded_rectangle([32, 70, 68, 74], radius=2, fill=dk)
    d.rounded_rectangle([32, 78, 55, 82], radius=2, fill=dk)
    # Printer button
    d.ellipse([42, 45, 58, 58], fill=a)


def _shape_bus(d, m, a, dk):
    """Transport / bus — school bus shape with windows."""
    # Bus body
    d.rounded_rectangle([8, 25, 92, 72], radius=8, fill=m)
    # Roof
    d.rounded_rectangle([12, 18, 88, 35], radius=6, fill=dk)
    # Windows
    for x in range(18, 70, 17):
        d.rectangle([x, 30, x + 12, 48], fill=WHITE)
    # Windshield
    d.rectangle([76, 30, 88, 52], fill=a)
    # Door
    d.rectangle([18, 50, 30, 68], fill=a)
    # Bumper
    d.rectangle([8, 68, 92, 72], fill=dk)
    # Wheels
    d.ellipse([18, 65, 36, 83], fill=dk)
    d.ellipse([22, 69, 32, 79], fill=WHITE)
    d.ellipse([62, 65, 80, 83], fill=dk)
    d.ellipse([66, 69, 76, 79], fill=WHITE)
    # Headlight
    d.rectangle([86, 52, 92, 60], fill=a)


def _shape_generic(d, m, a, dk):
    """Generic fallback — abstract overlapping shapes."""
    d.ellipse([5, 18, 55, 68], fill=m)
    d.rounded_rectangle([40, 10, 92, 55], radius=10, fill=a)
    d.ellipse([30, 50, 75, 92], fill=dk)


# ---------------------------------------------------------------------------
# Module -> shape mapping
# ---------------------------------------------------------------------------

MODULE_SHAPES = {
    'aanvragen': _shape_request,
    'myschool_activiteiten': _shape_calendar,
    'myschool_dashboard': _shape_request,
    'myschool_devhub': _shape_code,
    'myschool_itsm': _shape_monitor,
    'myschool_admin': _shape_cog,
    'school': _shape_cog,
    'myschool_asset': _shape_laptop,
    'myschool_h5p': _shape_play,
    'myschool_sync': _shape_sync,
    'myschool_planner': _shape_tasks,
    'myschool_lessenrooster': _shape_calendar,
    'myschool_professionalisering': _shape_graduation,
    'myschool_process_mapper': _shape_sitemap,
    'myschool_knowledge_builder': _shape_book,
    'myschool_kosten_dashboard': _shape_euro,
    'security_phishing': _shape_shield,
    'myschool_drukwerk': _shape_printer,
    'myschool_bus_seater': _shape_bus,
    'hr': _shape_users,
    'project': _shape_sitemap,
    'sale': _shape_cart,
    'purchase': _shape_cart,
    'stock': _shape_cubes,
    'account': _shape_euro,
    'website': _shape_globe,
    'mail': _shape_envelope,
    'survey': _shape_chart,
    'event': _shape_calendar,
    'fleet': _shape_laptop,
    'maintenance': _shape_wrench,
    'helpdesk': _shape_shield,
}

KEYWORD_SHAPES = {
    'calendar': _shape_calendar, 'event': _shape_calendar,
    'rooster': _shape_calendar, 'lesson': _shape_calendar,
    'schedule': _shape_calendar, 'timetable': _shape_calendar,
    'dash': _shape_dashboard, 'board': _shape_dashboard,
    'code': _shape_code, 'dev': _shape_code,
    'monitor': _shape_monitor, 'desktop': _shape_monitor,
    'config': _shape_cog, 'setting': _shape_cog, 'admin': _shape_cog,
    'asset': _shape_laptop, 'device': _shape_laptop, 'laptop': _shape_laptop,
    'play': _shape_play, 'media': _shape_play, 'video': _shape_play,
    'sync': _shape_sync, 'refresh': _shape_sync,
    'task': _shape_tasks, 'plan': _shape_tasks, 'todo': _shape_tasks,
    'learn': _shape_graduation, 'school': _shape_graduation,
    'teach': _shape_graduation,
    'process': _shape_sitemap, 'workflow': _shape_sitemap,
    'knowledge': _shape_book, 'book': _shape_book, 'doc': _shape_book,
    'cost': _shape_euro, 'budget': _shape_euro, 'money': _shape_euro,
    'finance': _shape_euro, 'account': _shape_euro,
    'security': _shape_shield, 'shield': _shape_shield,
    'hr': _shape_users, 'user': _shape_users, 'employee': _shape_users,
    'leerling': _shape_users, 'student': _shape_users, 'persoon': _shape_users,
    'sale': _shape_cart, 'shop': _shape_cart, 'purchase': _shape_cart,
    'web': _shape_globe, 'website': _shape_globe,
    'mail': _shape_envelope, 'chat': _shape_envelope,
    'message': _shape_envelope,
    'report': _shape_chart, 'chart': _shape_chart, 'analytic': _shape_chart,
    'data': _shape_database, 'import': _shape_database,
    'stock': _shape_cubes, 'warehouse': _shape_cubes,
    'inventory': _shape_cubes,
    'tool': _shape_wrench, 'repair': _shape_wrench,
    'maintenance': _shape_wrench,
    'request': _shape_request, 'aanvra': _shape_request,
    'approval': _shape_request,
    'druk': _shape_printer, 'print': _shape_printer,
    'kopie': _shape_printer,
    'bus': _shape_bus, 'seater': _shape_bus, 'transport': _shape_bus,
}


def _get_shape_func(module_name):
    """Get the shape drawing function for a module."""
    if module_name in MODULE_SHAPES:
        return MODULE_SHAPES[module_name]
    name_lower = module_name.lower()
    for keyword, func in KEYWORD_SHAPES.items():
        if keyword in name_lower:
            return func
    return _shape_generic


# ---------------------------------------------------------------------------
# Calm-tech LINE style — één monochrome stroked glyph op een effen tegel
# (Lucide/Feather-vormtaal: stroke, ronde hoeken/caps). Dezelfde categorie-
# resolutie als de filled stijl wordt hergebruikt via _FILLED_TO_KEY.
# ---------------------------------------------------------------------------

IVORY = (251, 250, 246, 255)
LINE_W = 6


def _scale_xy(xy, s):
    """Schaal coords; ondersteunt zowel platte [x0,y0,x1,y1] als [(x,y), ...]."""
    if not xy:
        return xy
    if isinstance(xy[0], (tuple, list)):
        return [(p[0] * s, p[1] * s) for p in xy]
    return [v * s for v in xy]


class _ScaledDraw:
    """Dunne ImageDraw-wrapper die alle coords/breedtes ×s schaalt, zodat de
    glyphs in 100-ruimte getekend kunnen worden maar op een supersample-canvas
    landen (anti-aliasing via terugschalen)."""

    def __init__(self, draw, s):
        self.d = draw
        self.s = s

    def _w(self, kw):
        if kw.get('width'):
            kw = dict(kw)
            kw['width'] = max(1, int(round(kw['width'] * self.s)))
        return kw

    def rounded_rectangle(self, xy, radius=0, **kw):
        self.d.rounded_rectangle(_scale_xy(xy, self.s), radius=radius * self.s, **self._w(kw))

    def ellipse(self, xy, **kw):
        self.d.ellipse(_scale_xy(xy, self.s), **self._w(kw))

    def arc(self, xy, start, end, **kw):
        self.d.arc(_scale_xy(xy, self.s), start, end, **self._w(kw))

    def line(self, xy, **kw):
        self.d.line(_scale_xy(xy, self.s), **self._w(kw))

    def polygon(self, xy, **kw):
        self.d.polygon(_scale_xy(xy, self.s), **kw)


def _cap(d, x, y, color, w):
    """Ronde eindcap (PIL-lijnen hebben butt-caps)."""
    r = w / 2.0
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _rl(d, pts, color, w=LINE_W):
    """Stroke een polyline met ronde joins + caps."""
    if len(pts) >= 2:
        d.line(pts, fill=color, width=w, joint='curve')
    _cap(d, pts[0][0], pts[0][1], color, w)
    _cap(d, pts[-1][0], pts[-1][1], color, w)


def _line_calendar(d, g, w):
    d.rounded_rectangle([26, 32, 74, 74], radius=6, outline=g, width=w)
    d.line([26, 44, 74, 44], fill=g, width=w)
    _rl(d, [(40, 24), (40, 34)], g, w)
    _rl(d, [(60, 24), (60, 34)], g, w)
    for cx in (38, 50, 62):
        for cy in (56, 66):
            d.ellipse([cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5], fill=g)


def _line_dashboard(d, g, w):
    d.arc([26, 30, 74, 78], 180, 360, fill=g, width=w)
    _rl(d, [(50, 54), (63, 40)], g, w)
    d.ellipse([45, 49, 55, 59], fill=g)


def _line_code(d, g, w):
    _rl(d, [(44, 32), (28, 50), (44, 68)], g, w)
    _rl(d, [(56, 32), (72, 50), (56, 68)], g, w)


def _line_monitor(d, g, w):
    d.rounded_rectangle([24, 28, 76, 60], radius=5, outline=g, width=w)
    _rl(d, [(50, 60), (50, 70)], g, w)
    _rl(d, [(38, 72), (62, 72)], g, w)


def _line_cog(d, g, w):
    import math
    d.ellipse([39, 39, 61, 61], outline=g, width=w)   # tandwiel-ring
    d.ellipse([46, 46, 54, 54], fill=g)               # naaf
    for i in range(8):
        a = i * math.pi / 4
        _rl(d, [(50 + 11 * math.cos(a), 50 + 11 * math.sin(a)),
                (50 + 19 * math.cos(a), 50 + 19 * math.sin(a))], g, w)


def _line_laptop(d, g, w):
    d.rounded_rectangle([30, 30, 70, 58], radius=4, outline=g, width=w)
    d.rounded_rectangle([22, 62, 78, 70], radius=3, outline=g, width=w)


def _line_play(d, g, w):
    d.ellipse([28, 28, 72, 72], outline=g, width=w)
    d.polygon([(45, 39), (45, 61), (65, 50)], fill=g)


def _line_sync(d, g, w):
    d.arc([28, 28, 72, 72], 300, 150, fill=g, width=w)
    d.arc([28, 28, 72, 72], 120, 330, fill=g, width=w)
    _rl(d, [(60, 22), (72, 28), (71, 40)], g, w)
    _rl(d, [(40, 78), (28, 72), (29, 60)], g, w)


def _line_tasks(d, g, w):
    for y in (38, 50, 62):
        _rl(d, [(28, y), (32, y + 4), (39, y - 4)], g, w)
        _rl(d, [(48, y), (72, y)], g, w)


def _line_graduation(d, g, w):
    _rl(d, [(50, 28), (76, 42), (50, 56), (24, 42), (50, 28)], g, w)
    d.arc([34, 50, 66, 74], 0, 180, fill=g, width=w)
    _rl(d, [(66, 49), (66, 66)], g, w)
    d.ellipse([63, 66, 69, 72], fill=g)


def _line_sitemap(d, g, w):
    d.rounded_rectangle([42, 22, 58, 38], radius=3, outline=g, width=w)
    for x0 in (22, 42, 62):
        d.rounded_rectangle([x0, 58, x0 + 16, 74], radius=3, outline=g, width=w)
    _rl(d, [(50, 38), (50, 48)], g, w)
    _rl(d, [(30, 48), (70, 48)], g, w)
    _rl(d, [(30, 48), (30, 58)], g, w)
    _rl(d, [(50, 48), (50, 58)], g, w)
    _rl(d, [(70, 48), (70, 58)], g, w)


def _line_book(d, g, w):
    _rl(d, [(50, 32), (32, 28), (28, 66), (50, 70)], g, w)
    _rl(d, [(50, 32), (68, 28), (72, 66), (50, 70)], g, w)
    _rl(d, [(50, 32), (50, 70)], g, w)


def _line_euro(d, g, w):
    d.ellipse([28, 28, 72, 72], outline=g, width=w)
    d.arc([40, 38, 62, 62], 50, 310, fill=g, width=w)
    _rl(d, [(36, 46), (56, 46)], g, w)
    _rl(d, [(36, 54), (56, 54)], g, w)


def _line_shield(d, g, w):
    _rl(d, [(50, 26), (70, 34), (68, 56), (50, 74), (32, 56), (30, 34), (50, 26)], g, w)
    _rl(d, [(42, 50), (48, 57), (60, 42)], g, w)


def _line_users(d, g, w):
    d.ellipse([38, 28, 54, 44], outline=g, width=w)
    d.arc([30, 48, 62, 82], 180, 360, fill=g, width=w)
    d.ellipse([57, 32, 69, 44], outline=g, width=w)
    d.arc([55, 50, 77, 76], 210, 360, fill=g, width=w)


def _line_cart(d, g, w):
    _rl(d, [(22, 28), (32, 30), (38, 58), (66, 58), (71, 36), (34, 36)], g, w)
    d.ellipse([37, 64, 47, 74], outline=g, width=w)
    d.ellipse([58, 64, 68, 74], outline=g, width=w)


def _line_globe(d, g, w):
    d.ellipse([26, 26, 74, 74], outline=g, width=w)
    d.ellipse([40, 26, 60, 74], outline=g, width=w)
    _rl(d, [(27, 50), (73, 50)], g, w)


def _line_envelope(d, g, w):
    d.rounded_rectangle([24, 32, 76, 68], radius=5, outline=g, width=w)
    _rl(d, [(27, 36), (50, 54), (73, 36)], g, w)


def _line_chart(d, g, w):
    _rl(d, [(28, 72), (72, 72)], g, w)
    _rl(d, [(38, 72), (38, 54)], g, w)
    _rl(d, [(50, 72), (50, 40)], g, w)
    _rl(d, [(62, 72), (62, 48)], g, w)


def _line_database(d, g, w):
    d.ellipse([28, 22, 72, 38], outline=g, width=w)
    _rl(d, [(28, 30), (28, 62)], g, w)
    _rl(d, [(72, 30), (72, 62)], g, w)
    d.arc([28, 38, 72, 54], 0, 180, fill=g, width=w)
    d.arc([28, 54, 72, 70], 0, 180, fill=g, width=w)


def _line_cubes(d, g, w):
    d.rounded_rectangle([30, 30, 58, 58], radius=4, outline=g, width=w)
    d.rounded_rectangle([46, 46, 72, 72], radius=4, outline=g, width=w)


def _line_wrench(d, g, w):
    d.arc([26, 26, 50, 50], 35, 305, fill=g, width=w)
    _rl(d, [(43, 43), (72, 72)], g, w + 1)


def _line_printer(d, g, w):
    d.rounded_rectangle([26, 44, 74, 64], radius=4, outline=g, width=w)
    d.rounded_rectangle([34, 26, 66, 44], radius=2, outline=g, width=w)
    d.rounded_rectangle([34, 62, 66, 76], radius=2, outline=g, width=w)
    d.ellipse([64, 51, 70, 57], fill=g)


def _line_bus(d, g, w):
    d.rounded_rectangle([24, 32, 76, 64], radius=6, outline=g, width=w)
    _rl(d, [(24, 50), (76, 50)], g, w)
    _rl(d, [(50, 34), (50, 50)], g, w)
    d.ellipse([31, 62, 43, 74], outline=g, width=w)
    d.ellipse([57, 62, 69, 74], outline=g, width=w)


def _line_request(d, g, w):
    d.rounded_rectangle([32, 24, 68, 76], radius=4, outline=g, width=w)
    _rl(d, [(58, 24), (58, 34), (68, 34)], g, w)
    for y in (44, 56, 66):
        _rl(d, [(38, y), (41, y + 3), (46, y - 3)], g, w)
        _rl(d, [(50, y), (62, y)], g, w)


def _line_generic(d, g, w):
    for (x0, y0) in [(30, 30), (54, 30), (30, 54), (54, 54)]:
        d.rounded_rectangle([x0, y0, x0 + 16, y0 + 16], radius=3, outline=g, width=w)


LINE_SHAPES = {
    'request': _line_request, 'calendar': _line_calendar, 'dashboard': _line_dashboard,
    'code': _line_code, 'monitor': _line_monitor, 'cog': _line_cog,
    'laptop': _line_laptop, 'play': _line_play, 'sync': _line_sync,
    'tasks': _line_tasks, 'graduation': _line_graduation, 'sitemap': _line_sitemap,
    'book': _line_book, 'euro': _line_euro, 'shield': _line_shield,
    'users': _line_users, 'cart': _line_cart, 'globe': _line_globe,
    'envelope': _line_envelope, 'chart': _line_chart, 'database': _line_database,
    'cubes': _line_cubes, 'wrench': _line_wrench, 'printer': _line_printer,
    'bus': _line_bus, 'generic': _line_generic,
}

# Filled-shape-functie → categorie-key, om dezelfde naam→categorie-resolutie
# (_get_shape_func) te hergebruiken voor de lijn-stijl.
_FILLED_TO_KEY = {
    _shape_request: 'request', _shape_calendar: 'calendar', _shape_dashboard: 'dashboard',
    _shape_code: 'code', _shape_monitor: 'monitor', _shape_cog: 'cog',
    _shape_laptop: 'laptop', _shape_play: 'play', _shape_sync: 'sync',
    _shape_tasks: 'tasks', _shape_graduation: 'graduation', _shape_sitemap: 'sitemap',
    _shape_book: 'book', _shape_euro: 'euro', _shape_shield: 'shield',
    _shape_users: 'users', _shape_cart: 'cart', _shape_globe: 'globe',
    _shape_envelope: 'envelope', _shape_chart: 'chart', _shape_database: 'database',
    _shape_cubes: 'cubes', _shape_wrench: 'wrench', _shape_printer: 'printer',
    _shape_bus: 'bus', _shape_generic: 'generic',
}


def _get_line_func(module_name):
    """Lijn-glyph voor een module, via dezelfde categorie als de filled stijl."""
    key = _FILLED_TO_KEY.get(_get_shape_func(module_name), 'generic')
    return LINE_SHAPES.get(key, _line_generic)


def generate_icon(main_color, accent_color, module_name='', display_name='', style='shapes'):
    """Generate a 100x100 PNG app icon.

    Twee stijlen:
      * 'shapes' (default) — witte tegel + kleurrijke gevulde semantische vorm.
      * 'line' — calm-tech: effen tegel (main_color) + één monochrome ivoor
        lijn-glyph (Lucide/Feather-stijl). accent_color wordt hier genegeerd.

    :param main_color: hex — gevulde vormen ('shapes') / tegel ('line')
    :param accent_color: hex — secundaire vormen ('shapes', genegeerd bij 'line')
    :param module_name: technische modulenaam (bepaalt de vorm/glyph)
    :param display_name: leesbare naam (ongebruikt, API-compat)
    :param style: 'shapes' | 'line'
    :returns: PNG image as bytes
    """
    main = _hex_to_rgba(main_color)
    accent = _hex_to_rgba(accent_color)
    dark = _darken(main)

    # Supersample voor gladde (anti-aliased) randen bij de lijn-stijl.
    ss = 4 if style == 'line' else 1
    size = ICON_SIZE * ss

    # Transparante achtergrond — geen tegel. Het motief wordt direct op een
    # doorzichtig canvas getekend, zodat het icoon zich aanpast aan elke
    # ondergrond (apps-menu-tegel, navbar, light/dark).
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if style == 'line':
        # Monochrome lijn-glyph in de hoofdkleur (geen tegel meer → main i.p.v.
        # ivoor, zodat de glyph contrasteert op een lichte ondergrond).
        _get_line_func(module_name)(_ScaledDraw(draw, ss), main, LINE_W)
    else:
        _get_shape_func(module_name)(draw, main, accent, dark)
        # In de filled-stijl was WIT de 'tegel die doorschijnt' (negatieve
        # ruimte). Nu er geen tegel is, maken we puur wit transparant zodat die
        # uitsnedes echte gaten worden en het icoon zich aan elke ondergrond
        # aanpast. (ss == 1 → geen AA-halo's, dus exact-wit keyen is schoon.)
        px = img.load()
        for y in range(size):
            for x in range(size):
                r, g, b, a = px[x, y]
                if a and r >= 250 and g >= 250 and b >= 250:
                    px[x, y] = (r, g, b, 0)

    if ss != 1:
        img = img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
