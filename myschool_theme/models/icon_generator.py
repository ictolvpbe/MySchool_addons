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
    'activiteiten': _shape_calendar,
    'myschool_dashboard': _shape_request,
    'myschool_devhub': _shape_code,
    'myschool_itsm': _shape_monitor,
    'myschool_admin': _shape_cog,
    'school': _shape_cog,
    'myschool_asset': _shape_laptop,
    'myschool_h5p': _shape_play,
    'myschool_sync': _shape_sync,
    'planner': _shape_tasks,
    'professionalisering': _shape_graduation,
    'process_mapper': _shape_sitemap,
    'myschool_knowledge_builder': _shape_book,
    'kosten_dashboard': _shape_euro,
    'security_phishing': _shape_shield,
    'drukwerk': _shape_printer,
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


def generate_icon(main_color, accent_color, module_name='', display_name=''):
    """Generate a 100x100 PNG icon in Odoo's abstract shape style.

    White rounded background with colorful semantic shapes that
    visually represent what the app does. No text overlay.

    :param main_color: hex color for primary shapes
    :param accent_color: hex color for secondary shapes
    :param module_name: technical module name (for shape selection)
    :param display_name: human-readable name (unused, kept for API compat)
    :returns: PNG image as bytes
    """
    main = _hex_to_rgba(main_color)
    accent = _hex_to_rgba(accent_color)
    dark = _darken(main)

    img = Image.new('RGBA', (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    bg = Image.new('RGBA', (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)

    # White background
    bg_draw.rounded_rectangle(
        [0, 0, ICON_SIZE, ICON_SIZE], radius=RADIUS, fill=WHITE)

    # Draw semantic shapes
    shape_func = _get_shape_func(module_name)
    shape_func(bg_draw, main, accent, dark)

    # Apply rounded-rectangle mask for clean edges
    mask = Image.new('L', (ICON_SIZE, ICON_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, ICON_SIZE, ICON_SIZE], radius=RADIUS, fill=255)

    bg.putalpha(mask)
    img.paste(bg, (0, 0), bg)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
