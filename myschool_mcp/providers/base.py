# -*- coding: utf-8 -*-
"""
Gedeelde provider-helpers — serialisatie, lookups, markdown-rendering.

Providers gebruiken deze om consistent JSON-conforme dicts terug te
geven aan de MCP-client en om gebruikersinvoer (display-codes, namen)
om te zetten naar Odoo-records.
"""

import re
import html
import logging

from odoo.exceptions import ValidationError

from ..models.mcp_registry import McpToolError

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Resolvers
# ----------------------------------------------------------------------

def resolve_item(env, ref):
    """Accepteert int-id, str van int, of display-code als 'MSA-42'.
    Geeft een ``appfoundry.item``-recordset met één record terug, of
    raised McpToolError 'not found'."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        item = env['appfoundry.item'].browse(int(ref)).exists()
        if not item:
            raise McpToolError(f'Item id={ref} not found', code=-32004)
        return item

    if isinstance(ref, str):
        m = re.match(r'^([A-Za-z0-9_]+)-(\d+)\s*$', ref.strip())
        if m:
            code, seq = m.group(1).upper(), int(m.group(2))
            item = env['appfoundry.item'].search([
                ('project_id.code', '=', code),
                ('sequence', '=', seq),
            ], limit=1)
            if not item:
                raise McpToolError(
                    f'Item {ref!r} not found (project code + sequence)',
                    code=-32004)
            return item

    raise McpToolError(
        f'Cannot resolve item reference: {ref!r}. Use either the '
        f'numeric id or a display-code like "MSA-42".',
        code=-32602)


def resolve_project(env, ref):
    """Project op id of code."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        proj = env['appfoundry.project'].browse(int(ref)).exists()
        if not proj:
            raise McpToolError(f'Project id={ref} not found', code=-32004)
        return proj
    if isinstance(ref, str):
        proj = env['appfoundry.project'].search(
            [('code', '=', ref.strip().upper())], limit=1)
        if not proj:
            raise McpToolError(
                f'Project code={ref!r} not found', code=-32004)
        return proj
    raise McpToolError(f'Invalid project reference: {ref!r}', code=-32602)


def resolve_stage(env, project, name_or_id):
    """Resolve een stage op id of (case-insensitive) naam.

    AppFoundry stages zijn project-onafhankelijk; ``project`` blijft
    voorlopig informatief (handig als er ooit per-project stages
    komen).
    """
    if isinstance(name_or_id, int) or (isinstance(name_or_id, str)
                                       and str(name_or_id).isdigit()):
        stage = env['appfoundry.item.stage'].browse(
            int(name_or_id)).exists()
        if not stage:
            raise McpToolError(
                f'Stage id={name_or_id} not found', code=-32004)
        return stage
    if isinstance(name_or_id, str):
        # Case-insensitive exact match eerst, dan ilike als fallback
        stages = env['appfoundry.item.stage'].search([])
        target = name_or_id.strip().lower()
        for s in stages:
            if s.name.lower() == target:
                return s
        # Fallback: prefix match
        for s in stages:
            if s.name.lower().startswith(target):
                return s
        names = ', '.join(stages.mapped('name'))
        raise McpToolError(
            f'Stage {name_or_id!r} not found. Available: {names}',
            code=-32004)
    raise McpToolError(f'Invalid stage reference: {name_or_id!r}',
                       code=-32602)


def resolve_user(env, ref):
    """Gebruiker via id of login. ``None``/``"me"`` → env.user."""
    if ref is None or ref == 'me':
        return env.user
    if isinstance(ref, int) or (isinstance(ref, str) and str(ref).isdigit()):
        user = env['res.users'].browse(int(ref)).exists()
        if not user:
            raise McpToolError(f'User id={ref} not found', code=-32004)
        return user
    if isinstance(ref, str):
        user = env['res.users'].search(
            [('login', '=', ref.strip())], limit=1)
        if not user:
            raise McpToolError(
                f'User login={ref!r} not found', code=-32004)
        return user
    raise McpToolError(f'Invalid user reference: {ref!r}', code=-32602)


def resolve_or_create_tags(env, names):
    """Convert een lijst tag-namen naar een lijst tag-ids; maakt
    ontbrekende tags aan."""
    if not names:
        return []
    Tag = env['appfoundry.tag']
    out = []
    for raw in names:
        nm = (raw or '').strip()
        if not nm:
            continue
        tag = Tag.search([('name', '=', nm)], limit=1)
        if not tag:
            tag = Tag.create({'name': nm})
        out.append(tag.id)
    return out


# ----------------------------------------------------------------------
# Serializers
# ----------------------------------------------------------------------

PRIORITY_LABEL = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Critical'}
ITEM_TYPE_LABEL = {'story': 'User Story', 'bug': 'Bug',
                   'task': 'Task', 'improvement': 'Improvement'}


def serialize_item(item, full=False, max_messages=20):
    """Convert een appfoundry.item naar een JSON-conforme dict.

    :param full: True ⇒ inclusief description, chatter, parents/children,
        dependencies. False ⇒ enkel summary-velden (voor lijst-views).
    """
    base = {
        'id': item.id,
        'display_name': item.display_name,
        'name': item.name,
        'project_id': item.project_id.id,
        'project_code': item.project_id.code,
        'item_type': item.item_type,
        'item_type_label': ITEM_TYPE_LABEL.get(item.item_type, item.item_type),
        'priority': item.priority,
        'priority_label': PRIORITY_LABEL.get(item.priority, item.priority),
        'stage_id': item.stage_id.id,
        'stage_name': item.stage_id.name,
        'is_done': bool(item.stage_id.is_done),
        'is_cancelled': bool(item.stage_id.is_cancelled),
        'assigned_id': item.assigned_id.id or False,
        'assigned_login': item.assigned_id.login or '',
        'assigned_name': item.assigned_id.name or '',
        'sprint_id': item.sprint_id.id or False,
        'sprint_name': item.sprint_id.name or '',
        'release_id': item.release_id.id or False,
        'release_name': item.release_id.name or '',
        'story_points': item.story_points,
        'date_deadline': (item.date_deadline.isoformat()
                          if item.date_deadline else None),
        'tag_names': item.tag_ids.mapped('name'),
    }
    if full:
        base.update({
            'description_html': item.description or '',
            'description_text': _html_to_text(item.description or ''),
            'parent_id': item.parent_id.id or False,
            'parent_display_name': (item.parent_id.display_name
                                    if item.parent_id else ''),
            'child_ids': item.child_ids.ids,
            'child_count': len(item.child_ids),
            'depends_on_ids': item.depends_on_ids.ids,
            'depends_on': [
                {'id': d.id, 'display_name': d.display_name}
                for d in item.depends_on_ids
            ],
            'blocked_by_ids': item.blocked_by_ids.ids,
            'blocked_by': [
                {'id': b.id, 'display_name': b.display_name}
                for b in item.blocked_by_ids
            ],
            'reviewer_login': item.reviewer_id.login or '',
            'reviewer_name': item.reviewer_id.name or '',
            'messages': _serialize_messages(item, max_messages),
        })
    return base


def serialize_project(proj):
    return {
        'id': proj.id,
        'code': proj.code,
        'name': proj.name,
        'phase': proj.phase,
        'is_active': bool(proj.is_active),
        'responsible_login': proj.responsible_id.login or '',
        'responsible_name': proj.responsible_id.name or '',
        'member_count': len(proj.member_ids),
        'current_release_id': proj.current_release_id.id or False,
        'current_release_name': proj.current_release_id.name or '',
        'open_bug_count': proj.open_bug_count,
        'item_count': proj.item_count,
    }


def serialize_sprint(sprint, include_items=False):
    base = {
        'id': sprint.id,
        'name': sprint.name,
        'project_id': sprint.project_id.id,
        'project_code': sprint.project_id.code,
        'state': sprint.state,
        'date_start': sprint.date_start.isoformat() if sprint.date_start else None,
        'date_end': sprint.date_end.isoformat() if sprint.date_end else None,
        'goal': sprint.goal or '',
        'total_points': sprint.total_points,
        'completed_points': sprint.completed_points,
        'velocity': sprint.velocity,
        'item_count': sprint.item_count,
    }
    if include_items:
        base['items'] = [serialize_item(i, full=False) for i in sprint.item_ids]
    return base


def serialize_release(release):
    return {
        'id': release.id,
        'name': release.name,
        'project_id': release.project_id.id,
        'project_code': release.project_id.code,
        'state': release.state,
        'date_planned': (release.date_planned.isoformat()
                         if release.date_planned else None),
        'date_released': (release.date_released.isoformat()
                          if release.date_released else None),
        'progress': release.progress,
        'total_items': release.total_items,
        'done_items': release.done_items,
        'notes_text': _html_to_text(release.notes or ''),
    }


def serialize_stage(stage):
    return {
        'id': stage.id,
        'name': stage.name,
        'sequence': stage.sequence,
        'fold': bool(stage.fold),
        'is_done': bool(stage.is_done),
        'is_cancelled': bool(stage.is_cancelled),
        'description': stage.description or '',
    }


def _serialize_messages(item, max_messages):
    """Geef de laatste N chatter-berichten + tracking-entries terug."""
    msgs = item.message_ids.sorted('date', reverse=True)[:max_messages]
    out = []
    for m in msgs:
        out.append({
            'id': m.id,
            'date': m.date.isoformat() if m.date else None,
            'author': m.author_id.name or m.email_from or '',
            'subtype': m.subtype_id.name or '',
            'message_type': m.message_type,
            'subject': m.subject or '',
            'body_text': _html_to_text(m.body or ''),
        })
    return out


# ----------------------------------------------------------------------
# Markdown / HTML
# ----------------------------------------------------------------------

def render_markdown_to_html(text):
    """Heel beperkte markdown → HTML conversie voor chatter-comments.
    Geen externe lib-afhankelijkheid; voldoende voor commit-messages.

    Ondersteund:
      * Paragrafen (lege regels)
      * Backticks ``code`` → <code>
      * **bold** en *italic*
      * Bullet lists (- of *)
      * Lege of None-input → empty string
    """
    if not text:
        return ''
    s = html.escape(str(text))

    # inline code
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    # bold
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    # italic
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)

    # Bullet lists + paragrafen
    lines = s.split('\n')
    out = []
    in_list = False
    paragraph = []

    def flush_paragraph():
        if paragraph:
            joined = '<br/>'.join(p.strip() for p in paragraph if p.strip())
            if joined:
                out.append(f'<p>{joined}</p>')
            paragraph.clear()

    for line in lines:
        stripped = line.strip()
        bullet = re.match(r'^[-*]\s+(.*)', stripped)
        if bullet:
            flush_paragraph()
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{bullet.group(1)}</li>')
        elif not stripped:
            if in_list:
                out.append('</ul>')
                in_list = False
            flush_paragraph()
        else:
            if in_list:
                out.append('</ul>')
                in_list = False
            paragraph.append(stripped)

    if in_list:
        out.append('</ul>')
    flush_paragraph()
    return ''.join(out)


def _html_to_text(html_value):
    """Strip HTML tags + decode entities, voor tekst-only output."""
    if not html_value:
        return ''
    s = str(html_value)
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'</p>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    return s.strip()
