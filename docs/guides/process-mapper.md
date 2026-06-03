# Process Mapper - User Manual

## Overview

Process Mapper is a visual BPMN-inspired process mapping tool built into Odoo 19. It allows you to design, document, and manage business process workflows using a drag-and-drop SVG canvas editor. Completed process maps can generate Odoo module specifications for LLM-based code generation.

---

## Getting Started

### Accessing Process Mapper

1. Navigate to **Process Mapper** in the main Odoo menu
2. Click **Process Maps** to see the list of existing maps
3. Click **Create** to start a new process map

### Creating a Process Map

1. Fill in the **Name** (required) and optional **Description**
2. Optionally assign an **Organization** to scope the map
3. Click **Save** to create the record
4. Click **Open Canvas Editor** to launch the visual editor

---

## The Canvas Editor

The canvas editor is the main workspace where you design your process maps. It consists of four areas:

```
+--------------------------------------------------+
|                    Toolbar                        |
+----------+------------------------+--------------+
|          |                        |              |
|          |       SVG Canvas       |  Properties  |
|          |                        |    Panel     |
|          |                        |              |
+----------+------------------------+--------------+
```

### Toolbar

The toolbar at the top provides all tools and actions:

| Section | Items | Description |
|---------|-------|-------------|
| **Title** | Map name + state badge | Shows current map name and workflow state |
| **Palette** | Start, End, Task, Sub, If/Else, XOR, AND, Lane | Drag these onto the canvas to create elements |
| **Actions** | Undo, Redo, Auto Layout | History navigation and automatic positioning |
| **Save** | Save button with dirty indicator | Saves current diagram (orange dot = unsaved changes) |
| **Zoom** | +, -, Fit, Grid | Zoom controls and grid toggle |
| **Tools** | Minimap, Versions, PNG, SVG, Print | Auxiliary tools and export options |

### Canvas Navigation

| Action | How |
|--------|-----|
| **Pan** | Click and drag on empty canvas area |
| **Zoom in/out** | Scroll wheel, or use toolbar +/- buttons |
| **Fit to view** | Click the compress icon in toolbar |
| **Toggle grid** | Click the grid icon (highlighted when active) |

---

## Elements

### Shape Types

#### Start Event
- **Shape:** Green circle (thin border)
- **Purpose:** Marks where the process begins
- **Rules:** A process should have exactly one start event. Start events have no incoming connections.
- **Default size:** 50x50

#### End Event
- **Shape:** Red circle (thick border)
- **Purpose:** Marks where the process terminates
- **Rules:** A process should have at least one end event. End events have no outgoing connections.
- **Default size:** 50x50

#### Task
- **Shape:** Blue rounded rectangle
- **Purpose:** Represents a unit of work to be performed
- **Features:** Supports description, responsible person, system action, data fields, annotation, icon, and color customization
- **Default size:** 140x60

#### Sub-Process
- **Shape:** Purple rounded rectangle with inner border and "+" indicator
- **Purpose:** Represents a task that can be expanded into a separate process map
- **Features:** Can link to another Process Map record via the "Linked Process Map" property. Double-click on the canvas to navigate to the linked map.
- **Default size:** 140x60

#### Condition (If/Else)
- **Shape:** Light blue diamond with "Yes / No" label
- **Purpose:** Represents a decision point where the flow splits based on a condition
- **Rules:** Should have at least two outgoing connections, typically labeled "Yes" and "No"
- **Default size:** 100x100

#### Exclusive Gateway (XOR)
- **Shape:** Yellow diamond with "X" symbol
- **Purpose:** Routes the flow to exactly one of the outgoing paths based on evaluated conditions
- **Rules:** Only one outgoing path is taken. Each outgoing connection should have a label describing the condition.
- **Default size:** 60x60

#### Parallel Gateway (AND)
- **Shape:** Yellow diamond with "+" symbol
- **Purpose:** Splits the flow into multiple parallel paths (all paths execute simultaneously) or synchronizes multiple incoming paths
- **Rules:** When splitting, all outgoing paths are taken. When joining, the flow waits for all incoming paths to complete.
- **Default size:** 60x60

### Swimlanes

- **Shape:** Horizontal band spanning the full canvas width, with dashed border
- **Purpose:** Represents a department, role, or organizational unit responsible for the steps within
- **Properties:** Name, color, height, linked Organization, linked Role
- **Behavior:** Steps automatically associate with a lane when dragged into its vertical bounds

### Connections

Connections link elements together to define the flow of the process.

| Type | Appearance | Purpose |
|------|-----------|---------|
| **Sequence Flow** | Solid line with arrow | Normal flow between steps within the same process |
| **Message Flow** | Dashed line with arrow | Communication between different participants/pools |
| **Association** | Dotted line | Links annotations or data objects to flow elements |

---

## Working with Elements

### Adding Elements

**Method 1: Drag from toolbar**
1. Click and hold a palette button in the toolbar (Start, End, Task, etc.)
2. Drag onto the canvas
3. Release to place the element at that position

**Method 2: Through the form view**
1. In the Process Map form view, use the Lanes/Steps/Connections tabs
2. Click "Add a line" to create elements directly in the list

### Selecting Elements

| Action | Result |
|--------|--------|
| Click on a step | Selects it (shows in Properties panel) |
| Click on a connection | Selects it |
| Click on a lane | Selects it |
| Shift+click | Adds to selection (multi-select) |
| Click on empty canvas | Deselects all |
| Drag on empty canvas | Rubber-band selection rectangle |

### Moving Elements

- **Single step:** Click and drag the step to a new position
- **Multiple steps:** Shift+click to select multiple, then drag any selected step to move all
- **Lane assignment:** When a step is dropped within a lane's vertical bounds, it automatically associates with that lane

### Resizing Elements

- Select a step to see resize handles (small squares) around it
- Drag a handle to resize:
  - **Corner handles:** Resize both width and height
  - **Edge handles:** Resize in one dimension
- Circles (start/end events) resize uniformly (maintaining circular shape)
- Minimum size constraints prevent elements from becoming too small

### Renaming Elements

- **Double-click** on any step to enter inline editing mode
- Type the new name (supports multi-line text)
- Press **Ctrl+Enter** or click outside to confirm
- Press **Escape** to cancel

### Creating Connections

1. Hover over a step to see the four **connector dots** (top, right, bottom, left)
2. Click and drag from a connector dot
3. A rubber-band line appears while dragging
4. Release over another step to create the connection
5. For conditions and exclusive gateways, the first two connections are automatically labeled "Yes" and "No"

### Editing Connection Routing

Connections use orthogonal (right-angle) routing by default:

1. Select a connection by clicking on it
2. Small **segment handles** (circles) appear at the midpoint of each segment
3. Drag a segment handle to adjust the routing
4. The waypoints are saved with the connection

### Deleting Elements

- Select one or more elements
- Press the **Delete** key, or click the "Delete" button in the Properties panel
- Deleting a step also removes all its connections

---

## Properties Panel

The right-side panel shows and edits properties for the selected element.

### Step Properties

| Property | Description |
|----------|-------------|
| **Name** | Display name shown on the shape |
| **Type** | Shape type (Start, End, Task, etc.) |
| **Description** | Detailed description of the step |
| **Color** | Custom fill color (hex). Click the X button to reset to default. |
| **Icon** | FontAwesome icon displayed inside the shape. Choose from the icon picker. |
| **Annotation** | Business rules or additional notes. Shows as an "i" indicator on the shape. |
| **Linked Process Map** | (Sub-Process only) Links to another process map for drill-down |
| **Lane** | Which swimlane this step belongs to |
| **Role** | MySchool role associated with this step |
| **Responsible** | Person or position responsible for this step |
| **System Action** | Automated action performed (e.g., "Send email", "Create record") |
| **Data Fields** | Fields/data needed for this step (use the Field Builder) |

### Connection Properties

| Property | Description |
|----------|-------------|
| **Label** | Text displayed on the connection line |
| **Type** | Sequence Flow, Message Flow, or Association |

### Lane Properties

| Property | Description |
|----------|-------------|
| **Name** | Lane display name |
| **Color** | Background color of the lane band |
| **Height** | Vertical height in pixels (minimum 80) |
| **Organization** | Linked MySchool organization |
| **Role** | Linked MySchool role |

---

## Field Builder

The Field Builder is a tool for defining data fields associated with a task step. It helps specify what data model fields are needed for the step, which feeds into the prompt generation.

### Opening the Field Builder

1. Select a task step
2. In the Properties panel, find the "Data Fields" section
3. Click **Field Builder**

### Using the Field Builder

The Field Builder has two tabs:

**Types Tab:**
- Shows all available Odoo field types (Char, Text, Integer, Boolean, Date, Many2one, etc.)
- Drag a field type from the palette to the field list on the right
- Each field entry has: name input, type dropdown, required toggle
- For relational fields (Many2one, One2many, Many2many), a relation input appears to specify the related model (e.g., `res.partner`)

**From Model Tab:**
- Search for existing Odoo models by name or technical name
- Select a model to browse its fields
- Drag fields from the model into your field list (imports name, type, and relation)

### Managing Fields

| Action | How |
|--------|-----|
| **Add field** | Drag from palette or model to a drop zone |
| **Reorder** | Use up/down arrows, or drag by the grip handle |
| **Edit name** | Type in the name input field |
| **Change type** | Use the type dropdown |
| **Toggle required** | Click the "req" button (highlighted when required) |
| **Set relation** | Type model name in the relation input (for Many2one/One2many/Many2many) |
| **Remove** | Click the trash icon |

### Field Notation Format

Fields are saved in a text notation: `field_name: Type (relation, required)`

Examples:
```
name: Char (required)
description: Text
amount: Float
partner_id: Many2one (res.partner, required)
line_ids: One2many (sale.order.line)
start_date: Date
is_active: Boolean
```

Click **Apply Fields** to save and close.

---

## Version History

Process Mapper automatically creates a version snapshot each time you save.

### Viewing Versions

1. Click the **history icon** in the toolbar
2. The Version Panel slides out on the right
3. Each version shows: version number, timestamp, and author

### Restoring a Version

1. Open the Version Panel
2. Click **Restore** next to the desired version
3. The diagram reverts to that version's state
4. A new version snapshot is created before restoring (so you can undo the restore)

---

## Minimap

The minimap provides a bird's-eye overview of your entire diagram.

### Using the Minimap

1. Click the **map icon** in the toolbar to toggle the minimap
2. The minimap appears as a small overlay in the bottom-right corner
3. A dashed rectangle shows your current viewport
4. Click anywhere on the minimap to navigate to that area

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+S** | Save diagram |
| **Ctrl+Z** | Undo |
| **Ctrl+Shift+Z** | Redo |
| **Ctrl+C** | Copy selected elements |
| **Ctrl+V** | Paste copied elements (offset by 20px) |
| **Delete** | Delete selected elements |
| **Shift+Click** | Add to selection (multi-select) |
| **Double-click** | Inline rename a step / Open linked sub-process |
| **Escape** | Cancel inline editing |
| **Ctrl+Enter** | Confirm inline editing |
| **Scroll wheel** | Zoom in/out |

---

## Export Options

### Export as PNG

1. Click the **image icon** in the toolbar
2. A PNG file is generated from the current SVG canvas
3. The file downloads automatically
4. The export captures the full diagram, not just the visible viewport

### Export as SVG

1. Click the **download icon** in the toolbar
2. An SVG file is downloaded
3. SVG files are vector-based and can be edited in tools like Inkscape or imported into documents

### Print

1. Click the **print icon** in the toolbar
2. The browser print dialog opens
3. A print legend table is included showing all steps with their type, description, and responsible person

---

## Auto Layout

The Auto Layout feature automatically positions all elements in a structured arrangement:

1. Click the **magic wand icon** in the toolbar
2. The algorithm:
   - Finds start nodes (steps with no incoming connections)
   - Traverses the flow using BFS (breadth-first search)
   - Assigns depth levels based on distance from start
   - Positions steps: 200px horizontal spacing, 100px vertical spacing
   - Clears all manual waypoints for clean routing
3. Steps are arranged left-to-right by flow order

**Note:** Auto Layout resets all manual positioning. Use Undo (Ctrl+Z) if the result is not satisfactory.

---

## Workflow States

Process maps follow a three-state workflow:

| State | Description | Actions Available |
|-------|-------------|-------------------|
| **Draft** | Initial state. Map can be freely edited. | Submit for Review |
| **Review** | Map is being reviewed. Requires at least one step. | Approve, Reset to Draft |
| **Approved** | Map is finalized. Prompt generation becomes available. | Reset to Draft, Generate Prompt |

State transitions are available via buttons in the form view header.

---

## Prompt Generation

When a process map is in the **Approved** state, you can generate an Odoo module specification:

1. Open the process map form view
2. Click **Generate Prompt**
3. The generated prompt appears in the "Generated Prompt" tab

### What the Prompt Contains

The generated specification includes:

- **Module name and purpose** derived from the map name
- **Actors/departments** derived from swimlanes (with roles and organizations)
- **Process steps** grouped by lane, including descriptions, annotations, responsible parties, and system actions
- **Process flow** listing all connections with labels
- **Suggested workflow states** derived by tracing the flow from start to end
- **Suggested data models** with field definitions parsed from the Field Builder notation
- **Business rules** extracted from step annotations
- **Security groups** derived from lanes
- **View and menu requirements** for each model
- **Odoo 19 generation instructions** with coding conventions

### Using the Prompt

Copy the generated prompt and provide it to an LLM (like Claude) to generate a complete Odoo 19 module with:
- Python model files
- XML view files (form, list, search)
- Security configuration
- Menu items
- Workflow logic

---

## Tips and Best Practices

### Process Design

1. **Start with one Start event** and at least one End event
2. **Use lanes** to clarify responsibilities - assign roles or organizations to each lane
3. **Name tasks clearly** - use verb-noun format (e.g., "Review Application", "Send Notification")
4. **Add descriptions** to complex tasks explaining what needs to happen
5. **Use annotations** for business rules and edge cases
6. **Label gateway outputs** - especially for exclusive gateways, label each outgoing connection with the condition

### Canvas Organization

1. **Enable the grid** for alignment when manually positioning elements
2. **Use Auto Layout** as a starting point, then fine-tune manually
3. **Use the minimap** for large diagrams to keep orientation
4. **Save frequently** - the dirty indicator (orange dot) reminds you of unsaved changes
5. **Use version history** before making major changes - you can always restore

### Data Modeling

1. **Use the Field Builder** to define data fields on task steps
2. **Import fields from existing models** when extending or integrating with existing Odoo modules
3. **Mark required fields** to ensure they appear in the generated specification
4. **Use proper relational types** (Many2one for lookups, One2many for detail lines)

### Collaboration

1. **Use the Review state** to signal that a map is ready for feedback
2. **Only Approve** when the process is fully validated and agreed upon
3. **Use descriptions and annotations** to document decisions and rationale
4. **Export PNG/SVG** for sharing with stakeholders who don't have Odoo access

---

## Security

Process Mapper has two security groups:

| Group | Permissions |
|-------|------------|
| **Process Mapper User** | Can view, create, and edit process maps. Cannot delete. |
| **Process Mapper Manager** | Full access including delete. Can manage versions. |

Both groups inherit from the base Odoo user group.

---

## Glossary

| Term | Definition |
|------|-----------|
| **BPMN** | Business Process Model and Notation - an international standard for process modeling |
| **Step** | A single element on the canvas (event, task, gateway, etc.) |
| **Connection** | A line linking two steps, representing flow or communication |
| **Lane** | A horizontal band representing a role, department, or system |
| **Gateway** | A diamond-shaped decision point that splits or merges the flow |
| **Waypoint** | A coordinate point along a connection path used for orthogonal routing |
| **Orthogonal routing** | Connection lines that use only horizontal and vertical segments (right angles) |
| **Field Builder** | A tool for defining Odoo data model fields visually |
| **Prompt** | A generated text specification used to instruct an LLM to create an Odoo module |
