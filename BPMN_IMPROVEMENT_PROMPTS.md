# Process Mapper - BPMN 2.0 Improvement Prompts

Based on the BPMN 2.0 specification (sources: [Camunda Reference](https://camunda.com/bpmn/reference/),
[Visual Paradigm Guide](https://www.visual-paradigm.com/guide/bpmn/what-is-bpmn/),
[Creately Symbols](https://creately.com/guides/bpmn-symbols/)).

## Current State vs BPMN 2.0

**Currently implemented:** start, end, task, subprocess, condition, gateway_exclusive, gateway_parallel
**Missing from BPMN 2.0:** event subtypes (timer, message, error, signal, etc.), inclusive gateway,
event-based gateway, task subtypes (user, service, manual, script, send, receive), intermediate events,
boundary events, data objects, groups, text annotations, pools

---

## Phase 1: Event Subtypes (High Priority)

### 1.1 Add intermediate events (timer, message, error, signal)
```
Add intermediate event types to the process_mapper. These are BPMN events that occur between
start and end, shown as double-lined circles.

Backend changes in process_map_step.py:
- Add to STEP_TYPES: ('intermediate_timer', 'Timer Event'), ('intermediate_message', 'Message Event'),
  ('intermediate_error', 'Error Event'), ('intermediate_signal', 'Signal Event')

Frontend changes in process_mapper_canvas.js:
- In shapeCenter/shapeEdgePoint/shapePortPoint: treat these like start/end (circles)
  but with default size 50x50
- In process_mapper_canvas.xml: render as double-lined circles (two concentric circles,
  outer r=25, inner r=21) with inner icon:
  - Timer: clock icon (fa-clock-o) or SVG clock symbol
  - Message: envelope icon (fa-envelope-o) or SVG envelope outline
  - Error: lightning bolt icon (fa-bolt) or SVG zigzag
  - Signal: triangle icon (fa-caret-up) or SVG triangle
- The outer circle uses stroke-width="2", the inner circle uses stroke-width="1"
- Default fill: white, stroke: #555

In process_mapper_canvas.xml toolbar section, add palette buttons:
- Timer (fa-clock-o), Message (fa-envelope), Error (fa-bolt), Signal (fa-exclamation-triangle)
Group them in a "Events" subsection after the Start/End buttons.

In PropertiesPanel: add these types to the type dropdown.

In process_map.py _derive_workflow_states: handle intermediate events as wait states
(e.g., timer -> "wait_for_timer", message -> "wait_for_message").
```

### 1.2 Add start/end event subtypes via event_trigger field
```
Instead of creating separate step_types for every start/end variant, add an event_trigger
field to process.map.step:

Backend (process_map_step.py):
- Add field: event_trigger = fields.Selection([
    ('none', 'None'),
    ('message', 'Message'),
    ('timer', 'Timer'),
    ('conditional', 'Conditional'),
    ('signal', 'Signal'),
    ('error', 'Error'),
    ('escalation', 'Escalation'),
    ('compensation', 'Compensation'),
    ('cancel', 'Cancel'),
    ('terminate', 'Terminate'),
    ('multiple', 'Multiple'),
  ], string='Event Trigger', default='none')

Frontend rendering (process_mapper_canvas.xml):
- For start events: thin circle (stroke-width=2) with trigger icon inside
- For end events: thick circle (stroke-width=4) with filled/solid trigger icon inside
- For intermediate events: double circle with trigger icon inside
- Icon mapping:
  - none: empty
  - message: envelope outline (start/intermediate catching) or filled envelope (end/throwing)
  - timer: clock symbol (circle with hands)
  - error: lightning zigzag
  - signal: triangle
  - escalation: upward arrow
  - compensation: double rewind arrows
  - cancel: X mark
  - terminate: filled black circle inside
  - multiple: pentagon
  - conditional: document/list lines

Properties panel: Show event_trigger dropdown only when step_type is start, end,
or intermediate_*. Update get_diagram_data/save_diagram_data to include event_trigger.
```

---

## Phase 2: Gateway & Activity Subtypes (High Priority)

### 2.1 Add inclusive and event-based gateways
```
Add two missing BPMN gateway types to process_mapper:

Backend (process_map_step.py):
- Add to STEP_TYPES: ('gateway_inclusive', 'Inclusive Gateway (OR)'),
  ('gateway_event', 'Event-Based Gateway')

Frontend rendering (process_mapper_canvas.xml):
- gateway_inclusive: Diamond with a circle inside (O symbol). The circle should be
  centered in the diamond, radius ~12px, stroke-width 2, no fill.
- gateway_event: Diamond with a pentagon inside. Draw a regular pentagon centered
  in the diamond, radius ~10px, stroke-width 2, no fill.

In process_mapper_canvas.js:
- Add these types to the diamond-type checks in shapeCenter, shapeEdgePoint,
  shapePortPoint (same geometry as gateway_exclusive/gateway_parallel, default 60x60)

Toolbar: Add "OR" and "Event" gateway buttons next to existing XOR and AND buttons.

Properties panel: Add to type dropdown.

Prompt generation: gateway_inclusive generates OR-split states, gateway_event generates
event-wait states.
```

### 2.2 Add task subtypes (user, service, manual, script, send, receive)
```
Add BPMN task type markers to process_mapper. Instead of separate step_types, add a
task_subtype field:

Backend (process_map_step.py):
- Add field: task_subtype = fields.Selection([
    ('none', 'None'),
    ('user', 'User Task'),
    ('service', 'Service Task'),
    ('manual', 'Manual Task'),
    ('script', 'Script Task'),
    ('send', 'Send Task'),
    ('receive', 'Receive Task'),
    ('business_rule', 'Business Rule Task'),
  ], string='Task Subtype', default='none')

Frontend rendering (process_mapper_canvas.xml):
- Only visible when step_type is 'task'
- Render a small marker icon in the top-left corner of the task rectangle (inside,
  positioned at x+6, y+6, size 16x16):
  - user: person/bust icon (fa-user)
  - service: gear icon (fa-cog)
  - manual: hand icon (fa-hand-paper-o)
  - script: scroll/code icon (fa-file-code-o)
  - send: filled envelope icon (fa-envelope)
  - receive: open envelope icon (fa-envelope-o)
  - business_rule: table/grid icon (fa-table)
- Use foreignObject to render the FontAwesome icon, small and subtle (color: rgba(0,0,0,0.4))

Properties panel: Show task_subtype dropdown only when step_type is 'task'.
Update get_diagram_data/save_diagram_data to include task_subtype.

Prompt generation: Include task subtype info in step descriptions (e.g., "[User Task]
Review Application" vs "[Service Task] Send Notification Email").
```

---

## Phase 3: Artifacts & Data (Medium Priority)

### 3.1 Add text annotations as a step type
```
Add BPMN text annotations to process_mapper. Annotations are free-form notes connected
to flow objects via dotted association lines.

Backend (process_map_step.py):
- Add to STEP_TYPES: ('annotation', 'Text Annotation')

Frontend rendering:
- Shape: Open bracket on the left side + text. SVG: a vertical line on the left edge
  with a horizontal bracket at top and bottom (like "[" rotated), followed by wrapped text.
  Implementation: rect with no fill, left border only (use path: M x,y V y+h),
  with text inside.
- Default size: 120x60, resizable
- No connector dots (annotations connect via association lines only)
- Text wrapping applies

Connection behavior:
- When creating a connection FROM an annotation or TO an annotation, automatically set
  connection_type to 'association'
- Render association connections as dotted lines (stroke-dasharray="4 2") without arrowheads

Properties panel: Show only name (text content) and size for annotations.
```

### 3.2 Add data object as a step type
```
Add BPMN data objects to process_mapper. Data objects represent documents or data used/produced.

Backend (process_map_step.py):
- Add to STEP_TYPES: ('data_object', 'Data Object'), ('data_store', 'Data Store')

Frontend rendering:
- data_object: Document shape - rectangle with folded corner (top-right). SVG path:
  M x,y  L x+w-15,y  L x+w,y+15  L x+w,y+h  L x,y+h Z  M x+w-15,y L x+w-15,y+15 L x+w,y+15
  Default size: 40x50. Fill: white, stroke: #555.
- data_store: Cylinder shape (database icon). SVG: ellipse top + rect body + ellipse bottom.
  Default size: 50x60. Fill: white, stroke: #555.
- Both render name text below the shape.

Connection behavior: connections to/from data objects use 'association' type (dotted line).
Data objects are not part of the sequence flow.

Toolbar: Add a "Data" subsection with Document and Database icons.
```

### 3.3 Add group (visual grouping box)
```
Add BPMN groups to process_mapper. Groups are visual boxes that categorize related elements
without affecting flow.

This could be a new model or a step type. Simplest approach: new step type.

Backend (process_map_step.py):
- Add to STEP_TYPES: ('group', 'Group')

Frontend rendering:
- Rounded rectangle with dashed border (stroke-dasharray="8 4"), no fill (transparent),
  large default size (300x200)
- Name rendered at top-left inside the group
- Groups render BEHIND other steps (render them first in the steps loop or use a
  separate rendering pass)
- No connector dots
- Resizable via corner handles

Interaction: groups don't participate in connections. They are purely visual containers.
Steps inside a group's bounds are visually "in" the group but not structurally linked.
```

---

## Phase 4: Connection Enhancements (Medium Priority)

### 4.1 Differentiate connection rendering by type
```
Currently all connection types render as solid arrows. Implement BPMN-correct rendering:

In process_mapper_canvas.xml and process_mapper_canvas.js:

1. Sequence Flow (existing): Solid line with filled arrowhead. No changes needed.

2. Message Flow: Dashed line (stroke-dasharray="6 3") with open circle at source
   and open arrowhead at target.
   - Add new SVG marker: id="pm-arrowhead-open" with unfilled triangle
   - Add new SVG marker: id="pm-message-start" with small unfilled circle (r=4)
   - Apply: marker-start="url(#pm-message-start)" marker-end="url(#pm-arrowhead-open)"

3. Association: Dotted line (stroke-dasharray="2 2") with NO arrowheads.
   - Remove marker-end for association connections
   - Use lighter stroke color (#999)

Update getConnectionClass() to return different CSS classes per type.
Update the CSS with distinct styles for each connection type.
```

### 4.2 Add conditional and default sequence flow markers
```
Add BPMN conditional and default flow markers to sequence connections:

Backend (process_map_connection.py):
- Add field: flow_condition = fields.Selection([
    ('normal', 'Normal'),
    ('conditional', 'Conditional'),
    ('default', 'Default'),
  ], string='Flow Condition', default='normal')

Frontend rendering:
- conditional: Small diamond at the source end of the line (not to be confused with
  gateway shapes). Add SVG marker: id="pm-conditional-start" with a small diamond (8x8px).
- default: Small slash/tick mark near the source end. Render as a short diagonal line
  crossing the connection path near the source.

Properties panel: Show flow_condition dropdown when a connection is selected.
Update get_diagram_data/save_diagram_data.
```

---

## Phase 5: Pools (Nice-to-have)

### 5.1 Add pool support (participant containers)
```
Add BPMN pools to process_mapper. Pools represent process participants (organizations,
systems) and contain lanes.

Backend - new model process_map_pool.py:
- name: Char (required)
- x_position: Float (default 0)
- y_position: Float (default 0)
- width: Float (default 800)
- height: Float (computed from contained lanes)
- is_collapsed: Boolean (default False, for blackbox pools)
- map_id: Many2one('process.map', required, cascade)

Update process_map_lane.py:
- Add: pool_id = fields.Many2one('process.map.pool', string='Pool', ondelete='set null')

Frontend rendering:
- Pool: Large rectangle with name label rotated 90 degrees on the left side
  (vertical text in a narrow left band, like a tab)
- Lanes inside a pool stack vertically within the pool bounds
- Pool header (left band): width 30px, dark background matching pool theme
- Collapsed pool (blackbox): Just the header band with name, no internal lanes visible

Message flows should cross pool boundaries. Sequence flows should stay within a pool.
Add validation: warn when a sequence flow crosses pools.

Toolbar: Add "Pool" button. When dropped, creates a pool with one default lane inside.
```

---

## Phase 6: Advanced Features (Nice-to-have)

### 6.1 Add boundary events on tasks
```
Add BPMN boundary events - events attached to the border of an activity (task/subprocess).

Backend (process_map_step.py):
- Add field: boundary_of_id = fields.Many2one('process.map.step', string='Boundary Of',
    ondelete='cascade', help='If set, this event is attached to the border of another step')
- Add field: is_interrupting = fields.Boolean(string='Interrupting', default=True)

Frontend rendering:
- When a step has boundary_of_id set, render it as a small circle (r=15) on the border
  of the parent step
- Position: bottom-right corner of the parent step by default
- Interrupting: solid double circle border
- Non-interrupting: dashed double circle border
- Inner icon based on event_trigger (timer, message, error, etc.)
- Boundary events should "snap" to the parent shape border when dragged

Connection behavior:
- Boundary events can only be sources of connections (outgoing), not targets
- The outgoing flow represents the exception/alternate path

Properties panel: Show "Attached to" field (dropdown of tasks in same map) and
"Interrupting" checkbox when step is a boundary event type.
```

### 6.2 Add loop and multi-instance markers on tasks
```
Add BPMN task markers for loop types:

Backend (process_map_step.py):
- Add field: loop_type = fields.Selection([
    ('none', 'None'),
    ('standard', 'Standard Loop'),
    ('multi_instance_parallel', 'Parallel Multi-Instance'),
    ('multi_instance_sequential', 'Sequential Multi-Instance'),
  ], string='Loop Type', default='none')

Frontend rendering (process_mapper_canvas.xml):
- Render marker at the bottom center of the task rectangle, inside the shape:
  - standard: Small curved arrow icon (circular arrow, like a refresh symbol)
  - multi_instance_parallel: Three vertical bars (|||)
  - multi_instance_sequential: Three horizontal bars (===)
- Use SVG path or text symbols, positioned at (center_x, y + height - 12)
- Size: about 14px wide

Properties panel: Show loop_type dropdown when step_type is 'task' or 'subprocess'.
```

### 6.3 Add BPMN validation rules
```
Implement BPMN structural validation for process_mapper:

Backend (process_map.py) - add method validate_bpmn():
Rules to check:
1. Exactly one "none" start event per process (warning if multiple or zero)
2. At least one end event (error if none)
3. All steps reachable from start (warning for orphan nodes)
4. No dead-end steps: every non-end step must have outgoing connections (warning)
5. Exclusive gateways: each outgoing connection should have a label (warning)
6. Exclusive gateways: should have a "default" flow (warning)
7. Parallel gateways: must have matching join (warning if unbalanced split/join)
8. Sequence flows cannot cross pool boundaries (error)
9. Message flows must cross pool boundaries (error)
10. Boundary events must have exactly one outgoing connection (error)
11. Start events cannot have incoming connections (error)
12. End events cannot have outgoing connections (error)

Return: list of {level: 'error'|'warning'|'info', step_id: int|False, message: str}

Frontend:
- Add "Validate" button to toolbar (fa-check-circle icon)
- Show validation results in a slide-out panel
- Each result is clickable: selects and centers the problematic step
- Color-code: red for errors, yellow for warnings, blue for info
- Show count badge on the validate button when issues exist
```
