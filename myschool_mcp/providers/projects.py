# -*- coding: utf-8 -*-
"""
MCP tools voor de MySchool Projects-app (``myschool.project``).

Conventies:
  * Toolnaam-prefix = ``projects_``.
  * Read-tools vereisen ``group_projects_user``.
  * Write/create tools vereisen ``group_projects_manager``.
  * Projecten resolven via int-id of (case-insensitive) code.
"""

import logging

from ..models.mcp_registry import McpRegistry, McpToolError
from . import base

_logger = logging.getLogger(__name__)


READ_GROUP = 'myschool_projects.group_projects_user'
WRITE_GROUP = 'myschool_projects.group_projects_manager'


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _resolve_project(env, ref):
    """int-id, str-van-int, of code (case-insensitive) → myschool.project (1 record)."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        proj = env['myschool.project'].browse(int(ref)).exists()
        if not proj:
            raise McpToolError(f'Project id={ref} not found', code=-32004)
        return proj
    if isinstance(ref, str):
        proj = env['myschool.project'].search(
            [('code', '=ilike', ref.strip())], limit=1)
        if not proj:
            raise McpToolError(f'Project code={ref!r} not found', code=-32004)
        return proj
    raise McpToolError(f'Invalid project reference: {ref!r}', code=-32602)


def _serialize(project, with_children=False):
    data = {
        'id': project.id,
        'name': project.name,
        'code': project.code or '',
        'parent_id': project.parent_id.id or False,
        'parent_name': project.parent_id.name or '',
        'state': project.state,
        'progress': round(project.progress, 1),
        'progress_own': round(project.progress_own, 1),
        'responsible_login': project.responsible_id.login or '',
        'responsible_name': project.responsible_id.name or '',
        'member_logins': project.member_ids.mapped('login'),
        'date_start': project.date_start.isoformat() if project.date_start else None,
        'date_end': project.date_end.isoformat() if project.date_end else None,
        'child_count': project.child_count,
        'milestone_count': project.milestone_count,
    }
    if with_children:
        data['children'] = [_serialize(c) for c in project.child_ids]
        data['milestones'] = [
            {
                'id': m.id,
                'name': m.name,
                'date': m.date_deadline.isoformat() if m.date_deadline else None,
                'state': m.state,
            }
            for m in project.milestone_ids
        ]
        data['depends_on'] = [
            {'id': d.id, 'code': d.code or '', 'name': d.name}
            for d in project.depends_on_ids
        ]
        data['blocks'] = [
            {'id': d.id, 'code': d.code or '', 'name': d.name}
            for d in project.dependent_ids
        ]
    return data


def _tree(project):
    """Recursieve geneste WBS-boom van een project + al zijn sub-projecten."""
    return {
        'id': project.id,
        'code': project.code or '',
        'name': project.name,
        'state': project.state,
        'progress': round(project.progress, 1),
        'children': [_tree(c) for c in project.child_ids],
    }


def _resolve_item(env, ref):
    """int-id of str-van-int → myschool.project.task (1 record)."""
    if isinstance(ref, int) or (isinstance(ref, str) and str(ref).isdigit()):
        item = env['myschool.project.task'].browse(int(ref)).exists()
        if not item:
            raise McpToolError(f'Work item id={ref} not found', code=-32004)
        return item
    raise McpToolError(
        f'Invalid work item reference: {ref!r} (use the numeric id)', code=-32602)


def _resolve_milestone(env, project, ref):
    """Milestone op id of (case-insensitive) naam binnen het project."""
    Task = env['myschool.project.task']
    if isinstance(ref, int) or (isinstance(ref, str) and str(ref).isdigit()):
        m = Task.browse(int(ref)).exists()
    else:
        m = Task.search([
            ('project_id', '=', project.id),
            ('item_type', '=', 'milestone'),
            ('name', '=ilike', str(ref).strip()),
        ], limit=1)
    if not m or m.item_type != 'milestone':
        raise McpToolError(f'Milestone {ref!r} not found in project', code=-32004)
    return m


def _serialize_item(item):
    return {
        'id': item.id,
        'name': item.name,
        'item_type': item.item_type,
        'project_id': item.project_id.id,
        'project_code': item.project_id.code or '',
        'parent_id': item.parent_id.id or False,
        'parent_name': item.parent_id.name or '',
        'state': item.state,
        'priority': item.priority,
        'assigned_login': item.assigned_id.login or '',
        'assigned_name': item.assigned_id.name or '',
        'date_start': item.date_start.isoformat() if item.date_start else None,
        'date_deadline': item.date_deadline.isoformat() if item.date_deadline else None,
        'planned_hours': item.planned_hours,
        'milestone_id': item.milestone_id.id or False,
        'milestone_name': item.milestone_id.name or '',
        'child_count': item.child_count,
        'depends_on': [{'id': d.id, 'name': d.name} for d in item.depends_on_ids],
    }


# ======================================================================
# READ TOOLS
# ======================================================================

@McpRegistry.tool(
    name='projects_list',
    description=(
        'List MySchool projects. By default only top-level projects (no '
        'parent). Pass `parent` to list the direct sub-projects of a given '
        'project instead.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'parent': {
                'description': 'Parent project id or code; lists its direct sub-projects',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'top_level_only': {'type': 'boolean', 'default': True},
            'my_only': {
                'type': 'boolean', 'default': False,
                'description': 'Only projects where I am responsible or member',
            },
            'limit': {'type': 'integer', 'default': 100, 'maximum': 500},
        },
    },
    required_group=READ_GROUP,
)
def list_projects(env, parent=None, top_level_only=True, my_only=False, limit=100):
    domain = []
    if parent is not None:
        p = _resolve_project(env, parent)
        domain.append(('parent_id', '=', p.id))
    elif top_level_only:
        domain.append(('parent_id', '=', False))
    if my_only:
        domain += ['|', ('responsible_id', '=', env.uid),
                   ('member_ids', 'in', env.uid)]
    projects = env['myschool.project'].search(
        domain, limit=min(int(limit or 100), 500))
    return [_serialize(p) for p in projects]


@McpRegistry.tool(
    name='projects_get',
    description=(
        'Full details of one project incl. its direct sub-projects and '
        'rolled-up progress.'
    ),
    input_schema={
        'type': 'object',
        'required': ['project'],
        'properties': {
            'project': {
                'description': 'Project id or code (e.g. "OLVP-ICT")',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
        },
    },
    required_group=READ_GROUP,
)
def get_project(env, project):
    p = _resolve_project(env, project)
    return _serialize(p, with_children=True)


@McpRegistry.tool(
    name='projects_tree',
    description=(
        'Nested WBS tree of a project and all its sub-projects (recursive). '
        'Omit `project` to get the forest of all top-level projects.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'project': {
                'description': 'Root project id or code; omit for all top-level projects',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
        },
    },
    required_group=READ_GROUP,
)
def project_tree(env, project=None):
    if project is not None:
        return _tree(_resolve_project(env, project))
    roots = env['myschool.project'].search([('parent_id', '=', False)])
    return [_tree(r) for r in roots]


# ======================================================================
# CREATE
# ======================================================================

@McpRegistry.tool(
    name='projects_create_subproject',
    description=(
        'Create a new project, optionally as a sub-project of an existing '
        'one. Returns the created project incl. its (empty) children list.'
    ),
    input_schema={
        'type': 'object',
        'required': ['name'],
        'properties': {
            'name': {'type': 'string'},
            'parent': {
                'description': 'Parent project id or code (omit for a top-level project)',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'code': {'type': 'string', 'description': 'Optional unique short code'},
            'responsible': {
                'description': 'User login, id, or "me"',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'state': {
                'type': 'string',
                'enum': ['new', 'active', 'on_hold', 'done', 'cancelled'],
                'default': 'new',
            },
            'date_start': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'date_end': {'type': 'string', 'description': 'YYYY-MM-DD'},
        },
    },
    required_group=WRITE_GROUP,
)
def create_subproject(env, name, parent=None, code=None, responsible=None,
                      state='new', date_start=None, date_end=None):
    vals = {'name': name, 'state': state}
    if parent is not None:
        vals['parent_id'] = _resolve_project(env, parent).id
    if code:
        vals['code'] = code
    if responsible is not None:
        vals['responsible_id'] = base.resolve_user(env, responsible).id
    if date_start:
        vals['date_start'] = date_start
    if date_end:
        vals['date_end'] = date_end
    project = env['myschool.project'].create(vals)
    return _serialize(project, with_children=True)


@McpRegistry.tool(
    name='projects_add_milestone',
    description=(
        'Add a milestone (a dated work item of type "milestone") to a project.'
    ),
    input_schema={
        'type': 'object',
        'required': ['project', 'name'],
        'properties': {
            'project': {
                'description': 'Project id or code',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'name': {'type': 'string'},
            'date': {'type': 'string', 'description': 'Target date YYYY-MM-DD'},
            'state': {
                'type': 'string',
                'enum': ['todo', 'done', 'cancelled'],
                'default': 'todo',
            },
            'description': {'type': 'string'},
        },
    },
    required_group=WRITE_GROUP,
)
def add_milestone(env, project, name, date=None, state='todo', description=None):
    p = _resolve_project(env, project)
    vals = {
        'project_id': p.id, 'name': name,
        'item_type': 'milestone', 'state': state,
    }
    if date:
        vals['date_deadline'] = date
    if description:
        vals['description'] = description
    milestone = env['myschool.project.task'].create(vals)
    return {
        'id': milestone.id,
        'project_id': p.id,
        'project_name': p.name,
        'name': milestone.name,
        'date': milestone.date_deadline.isoformat() if milestone.date_deadline else None,
        'state': milestone.state,
    }


@McpRegistry.tool(
    name='projects_set_dependency',
    description=(
        'Add (or remove) a dependency: marks `project` as depending on '
        '`depends_on` (predecessor). Use remove=true to unlink.'
    ),
    input_schema={
        'type': 'object',
        'required': ['project', 'depends_on'],
        'properties': {
            'project': {
                'description': 'Project id or code',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'depends_on': {
                'description': 'Predecessor project id or code',
                'oneOf': [{'type': 'integer'}, {'type': 'string'}],
            },
            'remove': {'type': 'boolean', 'default': False},
        },
    },
    required_group=WRITE_GROUP,
)
def set_dependency(env, project, depends_on, remove=False):
    p = _resolve_project(env, project)
    pred = _resolve_project(env, depends_on)
    if p.id == pred.id:
        raise McpToolError('Een project kan niet van zichzelf afhangen.', code=-32602)
    op = 3 if remove else 4  # 3=unlink, 4=link
    p.write({'depends_on_ids': [(op, pred.id, 0)]})
    return {
        'project_id': p.id,
        'depends_on_id': pred.id,
        'removed': bool(remove),
        'current_depends_on': [
            {'id': d.id, 'code': d.code or '', 'name': d.name}
            for d in p.depends_on_ids
        ],
    }


# ======================================================================
# WORK ITEM TOOLS (tasks / milestones / phases / …)
# ======================================================================

@McpRegistry.tool(
    name='projects_list_items',
    description=(
        'List work items of a project, optionally filtered by type, state or '
        'assignee. Returns flat list (use parent_id for hierarchy).'
    ),
    input_schema={
        'type': 'object',
        'required': ['project'],
        'properties': {
            'project': {'description': 'Project id or code',
                        'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'item_type': {'type': 'string',
                          'enum': ['task', 'milestone', 'phase', 'epic', 'bug']},
            'state': {'type': 'string',
                      'enum': ['todo', 'in_progress', 'blocked', 'done', 'cancelled']},
            'assignee': {'description': 'User login, id, or "me"',
                         'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'open_only': {'type': 'boolean', 'default': False},
            'limit': {'type': 'integer', 'default': 200, 'maximum': 1000},
        },
    },
    required_group=READ_GROUP,
)
def list_items(env, project, item_type=None, state=None, assignee=None,
               open_only=False, limit=200):
    p = _resolve_project(env, project)
    domain = [('project_id', '=', p.id)]
    if item_type:
        domain.append(('item_type', '=', item_type))
    if state:
        domain.append(('state', '=', state))
    if open_only:
        domain.append(('state', 'not in', ('done', 'cancelled')))
    if assignee:
        domain.append(('assigned_id', '=', base.resolve_user(env, assignee).id))
    items = env['myschool.project.task'].search(
        domain, limit=min(int(limit or 200), 1000), order='sequence, id')
    return [_serialize_item(i) for i in items]


@McpRegistry.tool(
    name='projects_create_item',
    description=(
        'Create a work item (task/milestone/phase/epic/bug) in a project. '
        'Optionally nest under a parent item and/or link to a milestone.'
    ),
    input_schema={
        'type': 'object',
        'required': ['project', 'name'],
        'properties': {
            'project': {'description': 'Project id or code',
                        'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'name': {'type': 'string'},
            'item_type': {'type': 'string',
                          'enum': ['task', 'milestone', 'phase', 'epic', 'bug'],
                          'default': 'task'},
            'parent': {'type': 'integer',
                       'description': 'Parent work item id (same project)'},
            'assignee': {'description': 'User login, id, or "me"',
                         'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'state': {'type': 'string',
                      'enum': ['todo', 'in_progress', 'blocked', 'done', 'cancelled'],
                      'default': 'todo'},
            'priority': {'type': 'string', 'enum': ['0', '1', '2', '3'], 'default': '1'},
            'date_start': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'date_deadline': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'planned_hours': {'type': 'number'},
            'milestone': {'description': 'Target milestone id or name (same project)',
                          'oneOf': [{'type': 'integer'}, {'type': 'string'}]},
            'description': {'type': 'string'},
        },
    },
    required_group=WRITE_GROUP,
)
def create_item(env, project, name, item_type='task', parent=None, assignee=None,
                state='todo', priority='1', date_start=None, date_deadline=None,
                planned_hours=None, milestone=None, description=None):
    p = _resolve_project(env, project)
    vals = {
        'project_id': p.id, 'name': name,
        'item_type': item_type, 'state': state, 'priority': priority,
    }
    if parent is not None:
        parent_item = _resolve_item(env, parent)
        if parent_item.project_id.id != p.id:
            raise McpToolError('Parent item moet in hetzelfde project zitten.', code=-32602)
        vals['parent_id'] = parent_item.id
    if assignee is not None:
        vals['assigned_id'] = base.resolve_user(env, assignee).id
    if date_start:
        vals['date_start'] = date_start
    if date_deadline:
        vals['date_deadline'] = date_deadline
    if planned_hours is not None:
        vals['planned_hours'] = planned_hours
    if milestone is not None:
        vals['milestone_id'] = _resolve_milestone(env, p, milestone).id
    if description:
        vals['description'] = description
    item = env['myschool.project.task'].create(vals)
    return _serialize_item(item)


@McpRegistry.tool(
    name='projects_update_item',
    description=(
        'Update fields of a work item. Pass only the fields to change. For '
        'parent/milestone pass an id (or name for milestone); pass false/0 to '
        'clear (un-nest / unlink milestone).'
    ),
    input_schema={
        'type': 'object',
        'required': ['item'],
        'properties': {
            'item': {'type': 'integer', 'description': 'Work item id'},
            'name': {'type': 'string'},
            'item_type': {'type': 'string',
                          'enum': ['task', 'milestone', 'phase', 'epic', 'bug']},
            'parent': {'description': 'New parent item id; 0/false to clear',
                       'oneOf': [{'type': 'integer'}, {'type': 'boolean'}]},
            'assignee': {'description': 'User login/id/"me"; 0/false to clear',
                         'oneOf': [{'type': 'integer'}, {'type': 'string'}, {'type': 'boolean'}]},
            'state': {'type': 'string',
                      'enum': ['todo', 'in_progress', 'blocked', 'done', 'cancelled']},
            'priority': {'type': 'string', 'enum': ['0', '1', '2', '3']},
            'date_start': {'type': 'string'},
            'date_deadline': {'type': 'string'},
            'planned_hours': {'type': 'number'},
            'milestone': {'description': 'Target milestone id/name; 0/false to clear',
                          'oneOf': [{'type': 'integer'}, {'type': 'string'}, {'type': 'boolean'}]},
        },
    },
    required_group=WRITE_GROUP,
)
def update_item(env, item, **kwargs):
    rec = _resolve_item(env, item)
    vals = {}
    for f in ('name', 'item_type', 'state', 'priority', 'planned_hours'):
        if f in kwargs:
            vals[f] = kwargs[f]
    for f in ('date_start', 'date_deadline'):
        if f in kwargs:
            vals[f] = kwargs[f] or False
    if 'assignee' in kwargs:
        a = kwargs['assignee']
        vals['assigned_id'] = base.resolve_user(env, a).id if a else False
    if 'parent' in kwargs:
        pv = kwargs['parent']
        if pv:
            par = _resolve_item(env, pv)
            if par.project_id.id != rec.project_id.id:
                raise McpToolError('Parent item moet in hetzelfde project zitten.', code=-32602)
            vals['parent_id'] = par.id
        else:
            vals['parent_id'] = False
    if 'milestone' in kwargs:
        mv = kwargs['milestone']
        vals['milestone_id'] = _resolve_milestone(env, rec.project_id, mv).id if mv else False
    if not vals:
        raise McpToolError('No updatable fields provided', code=-32602)
    rec.write(vals)
    return _serialize_item(rec)
