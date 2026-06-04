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
                'date': m.date.isoformat() if m.date else None,
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
    description='Add a milestone (dated checkpoint) to a project.',
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
                'enum': ['pending', 'reached', 'missed'],
                'default': 'pending',
            },
            'description': {'type': 'string'},
        },
    },
    required_group=WRITE_GROUP,
)
def add_milestone(env, project, name, date=None, state='pending', description=None):
    p = _resolve_project(env, project)
    vals = {'project_id': p.id, 'name': name, 'state': state}
    if date:
        vals['date'] = date
    if description:
        vals['description'] = description
    milestone = env['myschool.project.milestone'].create(vals)
    return {
        'id': milestone.id,
        'project_id': p.id,
        'project_name': p.name,
        'name': milestone.name,
        'date': milestone.date.isoformat() if milestone.date else None,
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
