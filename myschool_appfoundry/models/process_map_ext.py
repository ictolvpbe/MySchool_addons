import re

from odoo import models, fields, api


class ProcessMapStepAppfoundry(models.Model):
    _inherit = 'process.map.step'

    appfoundry_item_id = fields.Many2one(
        'appfoundry.item', string='User Story',
        domain=[('item_type', '=', 'story')],
        ondelete='set null',
    )


class ProcessMapAppfoundry(models.Model):
    _inherit = 'process.map'

    def _build_prompt(self, module_name):
        """Override to enrich the prompt with user story context."""
        prompt = super()._build_prompt(module_name)

        # Collect stories linked to steps
        linked_stories = self.step_ids.mapped('appfoundry_item_id').filtered(
            lambda s: s.item_type == 'story')

        # Find the parent project (if any) and collect unlinked stories
        project = self.env['appfoundry.project'].search(
            [('process_map_ids', 'in', self.ids)], limit=1)
        unlinked_stories = self.env['appfoundry.item']
        if project:
            all_project_stories = project.story_ids
            unlinked_stories = all_project_stories - linked_stories

        if not linked_stories and not unlinked_stories:
            return prompt

        # Build the user stories section
        lines = []
        lines.append("")
        lines.append("## User Stories / Requirements")
        if project:
            lines.append(f"Project: {project.name} ({project.code})")
        lines.append("")

        priority_map = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Critical'}

        # Stories linked to process steps
        if linked_stories:
            lines.append("### Stories linked to process steps")
            for story in linked_stories.sorted('sequence'):
                prio = priority_map.get(story.priority, story.priority)
                steps = self.step_ids.filtered(
                    lambda s: s.appfoundry_item_id.id == story.id)
                step_names = ', '.join(steps.mapped('name'))
                lines.append(f"- **{story.display_name}** [Priority: {prio}]")
                lines.append(f"  Linked steps: {step_names}")
                if story.description:
                    desc = re.sub(r'<[^>]+>', '', str(story.description)).strip()
                    if desc:
                        lines.append(f"  Description: {desc}")
                if story.story_points:
                    lines.append(f"  Story points: {story.story_points}")
                if story.tag_ids:
                    lines.append(f"  Tags: {', '.join(story.tag_ids.mapped('name'))}")
            lines.append("")

        # Stories not linked to any step (additional requirements)
        if unlinked_stories:
            lines.append("### Additional stories (not linked to process steps)")
            for story in unlinked_stories.sorted('sequence'):
                prio = priority_map.get(story.priority, story.priority)
                lines.append(f"- **{story.display_name}** [Priority: {prio}]")
                if story.description:
                    desc = re.sub(r'<[^>]+>', '', str(story.description)).strip()
                    if desc:
                        lines.append(f"  Description: {desc}")
                if story.story_points:
                    lines.append(f"  Story points: {story.story_points}")
            lines.append("")

        # Inject story references into the Process Steps section
        step_story_map = {}
        for step in self.step_ids:
            if step.appfoundry_item_id:
                step_story_map[step.name] = step.appfoundry_item_id.display_name

        if step_story_map:
            # Append story references after each step in the existing prompt
            for step_name, story_name in step_story_map.items():
                marker = f"- **{step_name}**"
                if marker in prompt:
                    prompt = prompt.replace(
                        marker,
                        f"{marker}\n  User story: {story_name}",
                        1,
                    )

        # Insert the user stories section before "## Generation Instructions"
        insert_marker = "## Generation Instructions"
        if insert_marker in prompt:
            prompt = prompt.replace(
                insert_marker,
                '\n'.join(lines) + '\n' + insert_marker,
            )
        else:
            prompt += '\n'.join(lines)

        return prompt

    def get_diagram_data(self):
        data = super().get_diagram_data()
        step_map = {s.id: s for s in self.step_ids}
        for step_data in data['steps']:
            step = step_map.get(step_data['id'])
            if step:
                step_data['appfoundry_item_id'] = step.appfoundry_item_id.id if step.appfoundry_item_id else False
                step_data['appfoundry_item_name'] = step.appfoundry_item_id.display_name if step.appfoundry_item_id else ''
        return data

    def save_diagram_data(self, data):
        # Collect appfoundry_item_id mapping before super processes steps
        appfoundry_by_id = {}
        appfoundry_by_attrs = {}
        for step_data in data.get('steps', []):
            if 'appfoundry_item_id' not in step_data:
                continue
            sid = step_data.get('id')
            item_id = step_data.get('appfoundry_item_id') or False
            if isinstance(sid, int) and sid > 0:
                appfoundry_by_id[sid] = item_id
            else:
                # For new steps (temp IDs), index by name+position for matching
                key = (
                    step_data.get('name', ''),
                    round(step_data.get('x_position', 0)),
                    round(step_data.get('y_position', 0)),
                )
                appfoundry_by_attrs[key] = item_id

        result = super().save_diagram_data(data)

        # Apply appfoundry_item_id to existing steps (matched by ID)
        Step = self.env['process.map.step']
        for sid, item_id in appfoundry_by_id.items():
            step = Step.browse(sid).exists()
            if step:
                step.appfoundry_item_id = item_id

        # Apply appfoundry_item_id to newly created steps (matched by attributes)
        if appfoundry_by_attrs:
            for step in self.step_ids:
                if step.appfoundry_item_id:
                    continue
                key = (step.name, round(step.x_position), round(step.y_position))
                item_id = appfoundry_by_attrs.get(key)
                if item_id:
                    step.appfoundry_item_id = item_id

        return result

    @api.model
    def search_user_stories(self, query='', project_id=False):
        """Search user stories for the canvas properties panel."""
        domain = [('item_type', '=', 'story')]
        if query:
            domain.append(('display_name', 'ilike', query))
        if project_id:
            domain.append(('project_id', '=', project_id))
        stories = self.env['appfoundry.item'].search(domain, limit=20, order='sequence')
        return [{'id': s.id, 'name': s.display_name} for s in stories]

    @api.model
    def create_user_story(self, name, project_id):
        """Create a new user story and return its data."""
        project = self.env['appfoundry.project'].browse(project_id)
        story = self.env['appfoundry.item'].create({
            'name': name,
            'item_type': 'story',
            'project_id': project_id,
            'release_id': project.current_release_id.id,
        })
        return {'id': story.id, 'name': story.display_name}
