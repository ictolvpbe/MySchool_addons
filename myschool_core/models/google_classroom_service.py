# -*- coding: utf-8 -*-
"""
Google Classroom Service
========================

Course + roster operations on the Classroom v1 API.

Course lifecycle:
    PROVISIONED  →  ACTIVE  →  ARCHIVED  →  (DELETED)

The API only allows admin-level operations when the impersonated
subject is a Workspace super-admin AND the OU has Classroom enabled
for the relevant role (teacher/student). Symptoms of misconfiguration
surface as 403 / 404 — they're returned as ``UserError`` by
``_drive_for(...)`` callers.
"""

import json
import logging

from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


class GoogleClassroomService(models.AbstractModel):
    _name = 'myschool.google.classroom.service'
    _description = 'Google Classroom Service'

    def _check_google_available(self):
        if not GOOGLE_AVAILABLE:
            raise UserError(_(
                'google-api-python-client / google-auth not installed.'
            ))

    @api.model
    def _get_classroom_service(self, config):
        self._check_google_available()
        if not config.scope_classroom:
            raise UserError(_(
                'Workspace config "%s" does not have the Classroom scope enabled.'
            ) % config.name)
        if config.key_file_path:
            with open(config.key_file_path, 'r') as f:
                key = json.load(f)
        elif config.key_json:
            key = json.loads(config.key_json)
        else:
            raise UserError(_('No service-account key configured.'))
        scopes = [
            'https://www.googleapis.com/auth/classroom.courses',
            'https://www.googleapis.com/auth/classroom.rosters',
        ]
        creds = service_account.Credentials.from_service_account_info(
            key, scopes=scopes).with_subject(config.subject_email)
        return build('classroom', 'v1', credentials=creds,
                     cache_discovery=False)

    # =========================================================================
    # Course operations
    # =========================================================================

    @api.model
    def create_course(self, config, name, owner_email, section=None,
                      description=None, room=None, course_state='ACTIVE',
                      dry_run=False):
        body = {
            'name': name,
            'ownerId': owner_email,
            'courseState': course_state,
        }
        if section:
            body['section'] = section
        if description:
            body['description'] = description
        if room:
            body['room'] = room
        if dry_run:
            return {
                'success': True, 'id': '',
                'attributes': body,
                'message': f'Dry run — would create course "{name}"',
            }
        svc = self._get_classroom_service(config)
        try:
            res = svc.courses().create(body=body).execute()
        except HttpError as e:
            raise UserError(_('courses.create failed: %s') % e)
        return {
            'success': True, 'id': res.get('id'),
            'message': f'Course created: {name} ({res.get("id")})',
        }

    @api.model
    def update_course(self, config, course_id, name=None, section=None,
                      description=None, room=None, course_state=None,
                      dry_run=False):
        """PATCH a course. Only the keys you supply are touched.

        ``course_state`` accepted values: ``ACTIVE``, ``ARCHIVED``,
        ``PROVISIONED``, ``DECLINED``, ``SUSPENDED``. Use this to flip
        ARCHIVED for end-of-year cleanup.
        """
        body = {}
        update_mask = []
        if name is not None:
            body['name'] = name
            update_mask.append('name')
        if section is not None:
            body['section'] = section
            update_mask.append('section')
        if description is not None:
            body['description'] = description
            update_mask.append('description')
        if room is not None:
            body['room'] = room
            update_mask.append('room')
        if course_state is not None:
            body['courseState'] = course_state
            update_mask.append('courseState')
        if not update_mask:
            return {'success': True, 'id': course_id, 'message': 'No changes'}
        if dry_run:
            return {
                'success': True, 'id': course_id,
                'attributes': body,
                'message': f'Dry run — would patch course {course_id}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().patch(
                id=course_id,
                updateMask=','.join(update_mask),
                body=body).execute()
        except HttpError as e:
            raise UserError(_('courses.patch failed: %s') % e)
        return {
            'success': True, 'id': course_id,
            'message': f'Course patched: {course_id}',
        }

    @api.model
    def archive_course(self, config, course_id, dry_run=False):
        """Convenience wrapper — flip courseState to ARCHIVED."""
        return self.update_course(
            config, course_id, course_state='ARCHIVED', dry_run=dry_run)

    @api.model
    def delete_course(self, config, course_id, dry_run=False):
        """Hard-delete a course. Classroom requires the course to be
        ARCHIVED first — caller should call ``archive_course`` before
        delete (the API returns FAILED_PRECONDITION otherwise)."""
        if dry_run:
            return {
                'success': True, 'id': course_id,
                'message': f'Dry run — would delete course {course_id}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().delete(id=course_id).execute()
        except HttpError as e:
            raise UserError(_('courses.delete failed: %s') % e)
        return {
            'success': True, 'id': course_id,
            'message': f'Course deleted: {course_id}',
        }

    # =========================================================================
    # Rosters
    # =========================================================================

    @api.model
    def add_teacher(self, config, course_id, email, dry_run=False):
        if dry_run:
            return {
                'success': True, 'id': course_id, 'member_id': email,
                'message': f'Dry run — would add teacher {email}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().teachers().create(
                courseId=course_id,
                body={'userId': email}).execute()
        except HttpError as e:
            # 409 → already a teacher.
            if getattr(getattr(e, 'resp', None), 'status', None) == 409:
                return {
                    'success': True, 'id': course_id, 'member_id': email,
                    'message': f'Already a teacher: {email}',
                }
            raise UserError(_('teachers.create failed: %s') % e)
        return {
            'success': True, 'id': course_id, 'member_id': email,
            'message': f'Teacher added: {email}',
        }

    @api.model
    def remove_teacher(self, config, course_id, email, dry_run=False):
        if dry_run:
            return {
                'success': True, 'id': course_id, 'member_id': email,
                'message': f'Dry run — would remove teacher {email}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().teachers().delete(
                courseId=course_id, userId=email).execute()
        except HttpError as e:
            if getattr(getattr(e, 'resp', None), 'status', None) == 404:
                return {
                    'success': True, 'id': course_id, 'member_id': email,
                    'message': f'Was not a teacher: {email}',
                }
            raise UserError(_('teachers.delete failed: %s') % e)
        return {
            'success': True, 'id': course_id, 'member_id': email,
            'message': f'Teacher removed: {email}',
        }

    @api.model
    def add_student(self, config, course_id, email, dry_run=False):
        if dry_run:
            return {
                'success': True, 'id': course_id, 'member_id': email,
                'message': f'Dry run — would add student {email}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().students().create(
                courseId=course_id,
                body={'userId': email}).execute()
        except HttpError as e:
            if getattr(getattr(e, 'resp', None), 'status', None) == 409:
                return {
                    'success': True, 'id': course_id, 'member_id': email,
                    'message': f'Already a student: {email}',
                }
            raise UserError(_('students.create failed: %s') % e)
        return {
            'success': True, 'id': course_id, 'member_id': email,
            'message': f'Student added: {email}',
        }

    @api.model
    def remove_student(self, config, course_id, email, dry_run=False):
        if dry_run:
            return {
                'success': True, 'id': course_id, 'member_id': email,
                'message': f'Dry run — would remove student {email}',
            }
        svc = self._get_classroom_service(config)
        try:
            svc.courses().students().delete(
                courseId=course_id, userId=email).execute()
        except HttpError as e:
            if getattr(getattr(e, 'resp', None), 'status', None) == 404:
                return {
                    'success': True, 'id': course_id, 'member_id': email,
                    'message': f'Was not a student: {email}',
                }
            raise UserError(_('students.delete failed: %s') % e)
        return {
            'success': True, 'id': course_id, 'member_id': email,
            'message': f'Student removed: {email}',
        }
