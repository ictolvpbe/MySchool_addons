# -*- coding: utf-8 -*-
"""
MCP tools voor de AppFoundry-module.

Convenanten:
  * Toolnaam-prefix = ``appfoundry_``.
  * Read-tools vereisen ``group_appfoundry_user`` (read).
  * Write/create tools vereisen ``group_appfoundry_manager``.
  * Items kunnen overal opgehaald worden via int-id of display-code
    ('MSA-42') — zie ``base.resolve_item``.
"""

import logging

from markupsafe import Markup

from ..models.mcp_registry import McpRegistry, McpToolError
from . import base

_logger = logging.getLogger(__name__)


READ_GROUP = 'myschool_appfoundry.group_appfoundry_user'
WRITE_GROUP = 'myschool_appfoundry.group_appfoundry_manager'


# ======================================================================
# READ TOOLS
# ======================================================================

@McpRegistry.tool(
    name='appfoundry_list_projects',
    description=(
        'List AppFoundry projects. By default only projects where the '
        'calling user is a member or project lead.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'member_only': {
                'type': 'boolean',
                'description': 'Only projects where I am member or lead',
                'default': True,
            },
            'include_inactive': {
                'type': 'boolean',
                'description': 'Include archived projects',
                'default': False,
            },
        },
    },
    required_group=READ_GROUP,
)
def list_projects(env, member_only=True, include_inactive=False):
    domain = []
    if not include_inactive:
        domain.append(('is_active', '=', True))
    if member_only:
        domain += ['|', ('member_ids', 'in', env.uid),
                   ('responsible_id', '=', env.uid)]
    projects = env['appfoundry.project'].search(domain, limit=200)
    return [base.serialize_project(p) for p in projects]


@McpRegistry.tool(
    name='appfoundry_list_my_items',
    description=(
        'List items assigned to the calling user. By default only items '
        'in non-done, non-cancelled stages.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'project_code': {
                'type': 'string',
                'description': 'Filter by project code (e.g. "MSA")',
            },
            'open_only': {'type': 'boolean', 'default': True},
            'limit': {'type': 'integer', 'default': 100, 'maximum': 500},
        },
    },
    required_group=READ_GROUP,
)
def list_my_items(env, project_code=None, open_only=True, limit=100):
    domain = [('assigned_id', '=', env.uid)]
    if open_only:
        domain += [('stage_id.is_done', '=', False),
                   ('stage_id.is_cancelled', '=', False)]
    if project_code:
        domain.append(('project_id.code', '=', project_code.strip().upper()))
    items = env['appfoundry.item'].search(
        domain, limit=min(int(limit or 100), 500))
    return [base.serialize_item(i, full=False) for i in items]


@McpRegistry.tool(
    name='appfoundry_list_items',
    description='General-purpose item search with multiple filters.',
    input_schema={
        'type': 'object',
        'properties': {
            'project_code': {'type': 'string'},
            'stage_name': {'type': 'string'},
            'assignee': {'type': 'string',
                         'description': 'User login or "me"'},
            'item_type': {
                'type': 'string',
                'enum': ['story', 'bug', 'task', 'improvement'],
            },
            'priority': {'type': 'string',
                         'enum': ['0', '1', '2', '3']},
            'sprint_id': {'type': 'integer'},
            'release_id': {'type': 'integer'},
            'tag_name': {'type': 'string'},
            'open_only': {'type': 'boolean', 'default': True},
            'limit': {'type': 'integer', 'default': 50, 'maximum': 500},
        },
    },
    required_group=READ_GROUP,
)
def list_items(env, project_code=None, stage_name=None, assignee=None,
               item_type=None, priority=None, sprint_id=None,
               release_id=None, tag_name=None, open_only=True, limit=50):
    domain = []
    if open_only:
        domain += [('stage_id.is_done', '=', False),
                   ('stage_id.is_cancelled', '=', False)]
    if project_code:
        domain.append(('project_id.code', '=', project_code.strip().upper()))
    if stage_name:
        stage = base.resolve_stage(env, None, stage_name)
        domain.append(('stage_id', '=', stage.id))
    if assignee:
        user = base.resolve_user(env, assignee)
        domain.append(('assigned_id', '=', user.id))
    if item_type:
        domain.append(('item_type', '=', item_type))
    if priority:
        domain.append(('priority', '=', priority))
    if sprint_id:
        domain.append(('sprint_id', '=', int(sprint_id)))
    if release_id:
        domain.append(('release_id', '=', int(release_id)))
    if tag_name:
        domain.append(('tag_ids.name', '=', tag_name))
    items = env['appfoundry.item'].search(
        domain, limit=min(int(limit or 50), 500))
    return [base.serialize_item(i, full=False) for i in items]


@McpRegistry.tool(
    name='appfoundry_get_item',
    description=(
        'Full details of one item incl. description, chatter (last N '
        'messages), parent/children, dependencies and tags.'
    ),
    input_schema={
        'type': 'object',
        'required': ['item'],
        'properties': {
            'item': {
                'description': 'Item id (int) or display code (e.g. "MSA-42")',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'max_messages': {'type': 'integer', 'default': 20, 'maximum': 100},
        },
    },
    required_group=READ_GROUP,
)
def get_item(env, item, max_messages=20):
    rec = base.resolve_item(env, item)
    return base.serialize_item(rec, full=True,
                               max_messages=min(int(max_messages or 20), 100))


@McpRegistry.tool(
    name='appfoundry_list_stages',
    description='List all available kanban stages, in sequence order.',
    input_schema={'type': 'object', 'properties': {}},
    required_group=READ_GROUP,
)
def list_stages(env):
    stages = env['appfoundry.item.stage'].search([], order='sequence')
    return [base.serialize_stage(s) for s in stages]


@McpRegistry.tool(
    name='appfoundry_list_active_sprints',
    description='List sprints in state="active". Optionally filter by project.',
    input_schema={
        'type': 'object',
        'properties': {
            'project_code': {'type': 'string'},
            'include_items': {'type': 'boolean', 'default': False},
        },
    },
    required_group=READ_GROUP,
)
def list_active_sprints(env, project_code=None, include_items=False):
    domain = [('state', '=', 'active')]
    if project_code:
        domain.append(('project_id.code', '=', project_code.strip().upper()))
    sprints = env['appfoundry.sprint'].search(domain, limit=50)
    return [base.serialize_sprint(s, include_items=include_items)
            for s in sprints]


@McpRegistry.tool(
    name='appfoundry_get_sprint',
    description='Sprint details incl. all items.',
    input_schema={
        'type': 'object',
        'required': ['sprint_id'],
        'properties': {
            'sprint_id': {'type': 'integer'},
        },
    },
    required_group=READ_GROUP,
)
def get_sprint(env, sprint_id):
    sprint = env['appfoundry.sprint'].browse(int(sprint_id)).exists()
    if not sprint:
        raise McpToolError(f'Sprint id={sprint_id} not found', code=-32004)
    return base.serialize_sprint(sprint, include_items=True)


@McpRegistry.tool(
    name='appfoundry_get_release_progress',
    description=(
        'Release status: progress%, open bugs, items done/total. '
        'Provide release_id, or project_code to fall back to the '
        'current release of that project.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'release_id': {'type': 'integer'},
            'project_code': {'type': 'string'},
        },
    },
    required_group=READ_GROUP,
)
def get_release_progress(env, release_id=None, project_code=None):
    if release_id:
        release = env['appfoundry.release'].browse(int(release_id)).exists()
        if not release:
            raise McpToolError(
                f'Release id={release_id} not found', code=-32004)
    elif project_code:
        project = base.resolve_project(env, project_code)
        release = project.current_release_id
        if not release:
            raise McpToolError(
                f'Project {project.code} has no current release',
                code=-32004)
    else:
        raise McpToolError(
            'Provide release_id or project_code', code=-32602)

    open_bugs = release.item_ids.filtered(
        lambda i: i.item_type == 'bug'
        and not i.stage_id.is_done
        and not i.stage_id.is_cancelled)
    incomplete = release.item_ids.filtered(
        lambda i: not i.stage_id.is_done and not i.stage_id.is_cancelled)
    result = base.serialize_release(release)
    result.update({
        'open_bug_count': len(open_bugs),
        'open_bugs': [{'id': b.id, 'display_name': b.display_name}
                      for b in open_bugs],
        'incomplete_count': len(incomplete),
    })
    return result


# ======================================================================
# WRITE TOOLS
# ======================================================================

@McpRegistry.tool(
    name='appfoundry_set_stage',
    description=(
        'Move an item to a different kanban stage. Stage can be given '
        'by id or by name (case-insensitive, e.g. "In Review").'
    ),
    input_schema={
        'type': 'object',
        'required': ['item', 'stage'],
        'properties': {
            'item': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'stage': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
        },
    },
    required_group=WRITE_GROUP,
)
def set_stage(env, item, stage):
    rec = base.resolve_item(env, item)
    stage_rec = base.resolve_stage(env, rec.project_id, stage)
    old_stage = rec.stage_id.name
    rec.write({'stage_id': stage_rec.id})
    return {
        'item_id': rec.id,
        'display_name': rec.display_name,
        'old_stage': old_stage,
        'new_stage': stage_rec.name,
    }


@McpRegistry.tool(
    name='appfoundry_assign',
    description=(
        'Assign an item to a user. Pass user login, user id, or "me" to '
        'assign to yourself.'
    ),
    input_schema={
        'type': 'object',
        'required': ['item'],
        'properties': {
            'item': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'user': {
                'description': 'Login, id, or "me" (default)',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
        },
    },
    required_group=WRITE_GROUP,
)
def assign(env, item, user=None):
    rec = base.resolve_item(env, item)
    target = base.resolve_user(env, user)
    old = rec.assigned_id.login or ''
    rec.write({'assigned_id': target.id})
    return {
        'item_id': rec.id,
        'display_name': rec.display_name,
        'old_assignee': old,
        'new_assignee': target.login,
    }


@McpRegistry.tool(
    name='appfoundry_post_comment',
    description=(
        'Post a comment in the item chatter. Supports light markdown '
        '(paragraphs, **bold**, *italic*, `code`, - bullets). The '
        'comment is attributed to the calling user.'
    ),
    input_schema={
        'type': 'object',
        'required': ['item', 'body'],
        'properties': {
            'item': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'body': {'type': 'string'},
            'subject': {'type': 'string'},
        },
    },
    required_group=WRITE_GROUP,
)
def post_comment(env, item, body, subject=None):
    rec = base.resolve_item(env, item)
    body_html = base.render_markdown_to_html(body)
    if not body_html.strip():
        raise McpToolError('Comment body is empty', code=-32602)
    msg = rec.message_post(
        body=Markup(body_html),
        subject=subject or False,
        message_type='comment',
        subtype_xmlid='mail.mt_comment',
    )
    return {
        'item_id': rec.id,
        'message_id': msg.id,
        'display_name': rec.display_name,
    }


@McpRegistry.tool(
    name='appfoundry_update_item',
    description=(
        'Update item fields. Pass only the fields you want to change. '
        'Supported: name, description, priority, item_type, '
        'story_points, date_deadline, sprint_id, release_id, '
        'parent_id, reviewer (login/id), tag_names (replaces tags).'
    ),
    input_schema={
        'type': 'object',
        'required': ['item'],
        'properties': {
            'item': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'name': {'type': 'string'},
            'description': {'type': 'string',
                            'description': 'Markdown; rendered to HTML'},
            'priority': {'type': 'string', 'enum': ['0', '1', '2', '3']},
            'item_type': {'type': 'string',
                          'enum': ['story', 'bug', 'task', 'improvement']},
            'story_points': {'type': 'integer'},
            'date_deadline': {'type': 'string',
                              'description': 'YYYY-MM-DD'},
            'sprint_id': {'type': 'integer'},
            'release_id': {'type': 'integer'},
            'parent_id': {'type': 'integer'},
            'reviewer': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'tag_names': {'type': 'array', 'items': {'type': 'string'}},
        },
    },
    required_group=WRITE_GROUP,
)
def update_item(env, item, **kwargs):
    rec = base.resolve_item(env, item)
    vals = {}
    if 'name' in kwargs:
        vals['name'] = kwargs['name']
    if 'description' in kwargs:
        vals['description'] = base.render_markdown_to_html(
            kwargs['description'])
    if 'priority' in kwargs:
        vals['priority'] = kwargs['priority']
    if 'item_type' in kwargs:
        vals['item_type'] = kwargs['item_type']
    if 'story_points' in kwargs:
        vals['story_points'] = int(kwargs['story_points'])
    if 'date_deadline' in kwargs:
        vals['date_deadline'] = kwargs['date_deadline'] or False
    if 'sprint_id' in kwargs:
        vals['sprint_id'] = int(kwargs['sprint_id']) or False
    if 'release_id' in kwargs:
        vals['release_id'] = int(kwargs['release_id']) or False
    if 'parent_id' in kwargs:
        vals['parent_id'] = int(kwargs['parent_id']) or False
    if 'reviewer' in kwargs:
        rev = base.resolve_user(env, kwargs['reviewer'])
        vals['reviewer_id'] = rev.id
    if 'tag_names' in kwargs:
        tag_ids = base.resolve_or_create_tags(env, kwargs['tag_names'] or [])
        vals['tag_ids'] = [(6, 0, tag_ids)]

    if not vals:
        raise McpToolError('No updatable fields provided', code=-32602)

    rec.write(vals)
    return base.serialize_item(rec, full=True, max_messages=5)


@McpRegistry.tool(
    name='appfoundry_link_blocked_by',
    description=(
        'Add a "blocked by" dependency: marks ``item`` as blocked by '
        '``blocked_by``. Use remove=true to unlink instead.'
    ),
    input_schema={
        'type': 'object',
        'required': ['item', 'blocked_by'],
        'properties': {
            'item': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'blocked_by': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'remove': {'type': 'boolean', 'default': False},
        },
    },
    required_group=WRITE_GROUP,
)
def link_blocked_by(env, item, blocked_by, remove=False):
    rec = base.resolve_item(env, item)
    blocker = base.resolve_item(env, blocked_by)
    if rec.id == blocker.id:
        raise McpToolError(
            'An item cannot block itself', code=-32602)
    op = 3 if remove else 4  # 3=unlink, 4=link
    rec.write({'blocked_by_ids': [(op, blocker.id, 0)]})
    return {
        'item_id': rec.id,
        'blocked_by_id': blocker.id,
        'removed': bool(remove),
        'current_blockers': [b.display_name for b in rec.blocked_by_ids],
    }


# ======================================================================
# CREATE
# ======================================================================

@McpRegistry.tool(
    name='appfoundry_create_item',
    description=(
        'Create a new item (story/bug/task/improvement). '
        'Required: project (id or code) + name. Release defaults to '
        'the project\'s current_release_id if not provided.'
    ),
    input_schema={
        'type': 'object',
        'required': ['project', 'name'],
        'properties': {
            'project': {
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
                'description': 'Project id or code (e.g. "MSA")',
            },
            'name': {'type': 'string'},
            'item_type': {
                'type': 'string',
                'enum': ['story', 'bug', 'task', 'improvement'],
                'default': 'story',
            },
            'description': {'type': 'string',
                            'description': 'Markdown; rendered to HTML'},
            'priority': {'type': 'string',
                         'enum': ['0', '1', '2', '3'],
                         'default': '1'},
            'release_id': {'type': 'integer'},
            'sprint_id': {'type': 'integer'},
            'parent_id': {'type': 'integer'},
            'assign_to_me': {'type': 'boolean', 'default': False},
            'assignee': {'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'tag_names': {'type': 'array', 'items': {'type': 'string'}},
            'story_points': {'type': 'integer'},
            'date_deadline': {'type': 'string'},
        },
    },
    required_group=WRITE_GROUP,
)
def create_item(env, project, name, item_type='story', description=None,
                priority='1', release_id=None, sprint_id=None,
                parent_id=None, assign_to_me=False, assignee=None,
                tag_names=None, story_points=None, date_deadline=None):
    proj = base.resolve_project(env, project)

    # Release: gegeven id of fallback naar project.current_release_id
    if release_id:
        release = env['appfoundry.release'].browse(int(release_id)).exists()
        if not release:
            raise McpToolError(
                f'Release id={release_id} not found', code=-32004)
    elif proj.current_release_id:
        release = proj.current_release_id
    else:
        raise McpToolError(
            f'Project {proj.code} has no current release; provide release_id',
            code=-32602)

    vals = {
        'name': name,
        'project_id': proj.id,
        'item_type': item_type,
        'priority': priority,
        'release_id': release.id,
    }
    if description:
        vals['description'] = base.render_markdown_to_html(description)
    if sprint_id:
        vals['sprint_id'] = int(sprint_id)
    if parent_id:
        vals['parent_id'] = int(parent_id)
    if assign_to_me:
        vals['assigned_id'] = env.uid
    elif assignee:
        vals['assigned_id'] = base.resolve_user(env, assignee).id
    if tag_names:
        vals['tag_ids'] = [(6, 0, base.resolve_or_create_tags(env, tag_names))]
    if story_points is not None:
        vals['story_points'] = int(story_points)
    if date_deadline:
        vals['date_deadline'] = date_deadline

    item = env['appfoundry.item'].create(vals)
    return base.serialize_item(item, full=True, max_messages=0)
