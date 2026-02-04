# Automatic Diagram Generation Implementation

## Overview
This implementation automatically generates ER/EER diagrams from semantic descriptions in questions that need to SHOW diagrams (not ask students to draw them).

## Key Changes

### 1. New Service: `semantic_diagram_service.py`
- **Location**: `backend/app/services/semantic_diagram_service.py`
- **Purpose**: Converts semantic text descriptions to Graphviz ER/EER diagrams
- **Features**:
  - Parses semantic descriptions using GPT-4 to extract entities, relationships, attributes, ISA hierarchies
  - Generates Graphviz DOT code from parsed components
  - Renders diagrams to PNG/SVG/PDF using Graphviz

### 2. Updated Orchestrator Logic
- **File**: `backend/app/agents/orchestrator.py`
- **Changes**:
  - Added detection for questions that need to SHOW diagrams (vs. asking students to draw)
  - Automatically generates diagrams using Graphviz when needed
  - Only generates for questions referencing existing diagrams (e.g., "Convert the following EER model")

## How It Works

### Detection Logic
The system detects when a diagram needs to be shown by checking for phrases like:
- "Convert the following EER model"
- "Based on the diagram"
- "The following diagram"
- "Referring to the diagram"

### Generation Process
1. **Parse Semantic Description**: Uses GPT-4 to extract:
   - Entities with attributes and primary keys
   - Relationships with cardinalities
   - ISA hierarchies (for EER)
   - Weak entities

2. **Generate Graphviz Code**: Converts parsed data to DOT format

3. **Render Image**: Uses Graphviz `dot` command to generate PNG image

4. **Embed in Paper**: Adds image path to question JSON

## Requirements

### Python Dependencies
- `graphviz` Python package (for subprocess calls)
- OpenAI API access (for GPT-4 parsing)

### System Dependencies
- **Graphviz** must be installed on the system:
  - Windows: `choco install graphviz` or download from https://graphviz.org/
  - Linux: `sudo apt-get install graphviz`
  - Mac: `brew install graphviz`

## Usage

### Automatic (During Paper Generation)
The system automatically detects and generates diagrams during paper generation when:
- Question references an existing diagram that should be shown
- Question type is ER/EER/FD

### Manual Testing
```python
from backend.app.services.semantic_diagram_service import SemanticDiagramService
from pathlib import Path

service = SemanticDiagramService()
result = service.generate_diagram_from_semantic_description(
    description="A university has students and courses...",
    output_path=Path("output.png"),
    diagram_type="EER",
    format="png"
)
```

## Example: Q1

**Input (Semantic Description)**:
```
A university has a database that contains information about students, courses, and enrollments. 
The students have attributes such as StudentID (primary key), Name, and Age. 
The courses have attributes like CourseID (primary key), CourseName, and Credits. 
An enrollment connects students to courses and includes attributes EnrollmentID (primary key), Grade, and Semester. 
There are many students for each course (many-to-many relationship), and a student can be enrolled in multiple courses.
```

**Output**: 
- PNG image showing ER diagram with:
  - Student entity (StudentID PK, Name, Age)
  - Course entity (CourseID PK, CourseName, Credits)
  - Enrollment entity (EnrollmentID PK, Grade, Semester)
  - Many-to-many relationship between Student and Course via Enrollment

## Current Status

✅ **Implemented**:
- Semantic parsing using GPT-4
- Graphviz code generation
- Image rendering
- Automatic detection in orchestrator

⚠️ **Requirements**:
- Graphviz must be installed on system
- OpenAI API key must be configured

## Testing

Run test script:
```bash
python test_semantic_diagram.py
```

This will test Q1's semantic description and generate a sample diagram.
