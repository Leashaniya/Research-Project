"""
Semantic to Graphviz Diagram Generation Service

Parses semantic descriptions of ER/EER diagrams and generates Graphviz visualizations.
Used for automatically generating diagrams from textual descriptions in questions.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.core.llm_factory import get_llm_client
import subprocess
import tempfile
import os


class SemanticDiagramService:
    """Service to convert semantic descriptions to Graphviz ER/EER diagrams"""
    
    def __init__(self):
        self.client = get_llm_client()
        self.model = "gpt-4"
    
    def _find_graphviz_dot(self) -> Optional[str]:
        """Find Graphviz dot executable"""
        import shutil
        import glob
        
        # First try standard PATH
        dot_path = shutil.which("dot")
        if dot_path:
            return dot_path
        
        # Check common Windows installation locations
        common_paths = [
            r"C:\Program Files\Graphviz\bin\dot.exe",
            r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
            r"C:\Program Files\Graphviz 14.1.2\bin\dot.exe",
            r"C:\Program Files\Graphviz*\bin\dot.exe",
        ]
        
        # Also check user's AppData for WinGet installations
        user_appdata = os.path.expanduser("~")
        winget_paths = [
            os.path.join(user_appdata, r"AppData\Local\Microsoft\WinGet\Packages\Graphviz.Graphviz*\bin\dot.exe"),
            os.path.join(user_appdata, r"AppData\Local\Microsoft\WinGet\Packages\Graphviz*\bin\dot.exe"),
        ]
        common_paths.extend(winget_paths)
        
        for path in common_paths:
            if "*" in path:
                # Handle glob patterns
                matches = glob.glob(path)
                if matches:
                    return matches[0]
            elif os.path.exists(path):
                return path
        
        # Last resort: search in Program Files
        try:
            for root, dirs, files in os.walk(r"C:\Program Files"):
                if "dot.exe" in files and "graphviz" in root.lower():
                    return os.path.join(root, "dot.exe")
        except:
            pass
        
        return None
    
    def parse_semantic_description(self, description: str, requires_isa: bool = False) -> Dict[str, Any]:
        """
        Parse a semantic description to extract ER/EER diagram components.
        
        Args:
            description: Textual description of entities, relationships, attributes, etc.
        
        Returns:
            Dictionary with parsed components:
            {
                "entities": [{"name": str, "attributes": [str], "primary_key": str}],
                "relationships": [{"name": str, "entity1": str, "entity2": str, "cardinality": str}],
                "isa_hierarchies": [{"supertype": str, "subtypes": [str]}],
                "weak_entities": [{"name": str, "owner": str}]
            }
        """
        # Build prompt with ISA requirement emphasis
        isa_requirement_note = ""
        if requires_isa:
            isa_requirement_note = """
⚠️ MANDATORY ISA REQUIREMENT: This description MUST include ISA hierarchies (subtype/supertype relationships).
⚠️ CRITICAL: ISA hierarchies are ONLY for subtype/supertype relationships - subtypes are specializations of the supertype.
⚠️ ISA means "is a" - the subtype IS A type of the supertype (e.g., GraduateStudent IS A Student).
⚠️ DO NOT create ISA between unrelated entities (e.g., Student → Course is WRONG - use a relationship instead).

If the description mentions entities like Student, Course, Employee, Member, etc., you MUST create appropriate subtypes.
Examples:
- Student → GraduateStudent, UndergraduateStudent (CORRECT - subtypes of Student)
- Course → CoreCourse, ElectiveCourse (CORRECT - subtypes of Course)
- Employee → FullTimeEmployee, PartTimeEmployee (CORRECT - subtypes of Employee)
- Member → RegularMember, PremiumMember (CORRECT - subtypes of Member)
- Student → Course (WRONG - this is a relationship, NOT an ISA hierarchy)

Each subtype MUST have at least 2-3 specific attributes that are NOT in the parent entity.
"""
        
        # Escape curly braces in JSON example to avoid format string errors
        json_example = """{
    "entities": [
        {
            "name": "EntityName", 
            "attributes": ["attr1", "attr2", "Address", "PhoneNumbers"], 
            "primary_key": "attr1",
            "composite_attributes": [
                {
                    "name": "Address",
                    "sub_attributes": ["Street", "City", "ZipCode"]
                },
                {
                    "name": "Name",
                    "sub_attributes": ["FirstName", "LastName"]
                }
            ],
            "multivalued_attributes": ["PhoneNumbers", "EmailAddresses"]
        }
    ],
    "relationships": [
        {
            "name": "RelationshipName", 
            "entity1": "Entity1", 
            "entity2": "Entity2", 
            "cardinality": "many-to-many",
            "min1": 0,
            "max1": "N",
            "min2": 0,
            "max2": "N",
            "descriptive_attributes": ["EnrollmentDate", "Grade"]
        }
    ],
    "isa_hierarchies": [
        {
            "supertype": "SuperType",
            "subtypes": [
                {
                    "name": "SubType1",
                    "specific_attributes": ["AttrSpecificToSubType1", "AnotherAttr"]
                },
                {
                    "name": "SubType2",
                    "specific_attributes": ["AttrSpecificToSubType2"]
                }
            ]
        }
    ],
    "weak_entities": []
}"""
        
        prompt = f"""
Parse the following database description and extract ER/EER diagram components.

Description:
{description}

{isa_requirement_note}

Extract:
1. Entities with their attributes and primary keys (MINIMUM 4 entities required)
2. Relationships between entities with cardinalities AND participation constraints (min/max)
3. ISA hierarchies (subtype/supertype relationships) with subtype-specific attributes
   ⚠️ CRITICAL: ISA hierarchies are ONLY for subtype/supertype relationships (e.g., Student → GraduateStudent, UndergraduateStudent)
   ⚠️ ISA is NOT for regular relationships (e.g., Student → Course is a RELATIONSHIP, NOT an ISA hierarchy)
   ⚠️ ISA means "is a" - subtypes are specializations of the supertype (e.g., GraduateStudent IS A Student)
   ⚠️ DO NOT create ISA between unrelated entities (e.g., Student → Course is WRONG - use a relationship instead)
4. Weak entities (if any)
5. Composite attributes (attributes composed of multiple sub-attributes, e.g., Address with Street, City, ZipCode)
   - For composite attributes, you MUST extract the sub-attributes explicitly
   - Example: If description says "Address, consisting of Street, City, and ZipCode", extract:
     composite_attributes: [{{"name": "Address", "sub_attributes": ["Street", "City", "ZipCode"]}}]
6. Multivalued attributes (attributes that can have multiple values, e.g., PhoneNumbers, EmailAddresses)
   - These should be listed in the attributes array AND in multivalued_attributes array
7. Descriptive attributes attached to relationships (attributes that belong to the relationship itself, e.g., EnrollmentDate on Enrolls relationship)

CRITICAL REQUIREMENTS:
- MINIMUM 4 distinct entities must be included (at least 4 entities)
- ⚠️ ALL entities MUST be connected through relationships - NO standalone entities
- ⚠️ If an entity like "Instructor" or "Department" exists, it MUST be connected to at least one other entity via a relationship
- ⚠️ ISA hierarchies MUST be subtype/supertype only (e.g., Student → GraduateStudent, NOT Student → Course)
- At least ONE composite attribute must be included (e.g., Address, Name with FirstName/LastName, Date with Day/Month/Year)
- At least ONE multivalued attribute must be included (e.g., PhoneNumbers, EmailAddresses, Skills, Hobbies)
- At least ONE descriptive attribute attached to a relationship must be included (e.g., EnrollmentDate, Grade, Salary, StartDate)
- For ISA hierarchies: Subtypes MUST have additional attributes specific to them (not just inherited)
  Example: GraduateStudent should have attributes like ThesisTitle, AdvisorName (specific to graduates)
  Example: UndergraduateStudent should have attributes like YearOfStudy, Major, GPA (specific to undergraduates)
- For relationships: Include participation constraints (min, max) - is participation mandatory (1) or optional (0)?
- Subtypes inherit all attributes from parent entity PLUS have their own specific attributes
- {"⚠️ ISA hierarchies are REQUIRED for this diagram. If not explicitly mentioned, infer appropriate subtypes based on the main entities." if requires_isa else ""}

⚠️ CRITICAL CONSTRAINT: AVOID REDUNDANT/STANDALONE ENTITIES ⚠️
- If a process/transaction (e.g., "Enrollment", "Enrollments") is described as a link between two other entities (e.g., "Students" and "Courses"), represent it EITHER as:
  * A Relationship Diamond with descriptive attributes (e.g., "Enrolls" relationship with attributes like EnrollmentDate, Grade), OR
  * An Associative Entity connected to both entities (e.g., "Enrollment" entity connected to both Student and Course)
- DO NOT create BOTH a standalone entity box AND a relationship diamond for the same data - this creates a logical conflict
- DO NOT create a standalone transaction entity (like "Enrollments", "Registrations", "Reservations") that is not connected to any relationship - this is wrong
- Example of CORRECT approach: If "Enrollments" links Students and Courses, create a relationship "Enrolls" with descriptive attributes (EnrollmentDate, Grade) - DO NOT also create a standalone "Enrollments" entity
- Example of INCORRECT approach: Creating both an "Enrollments" entity box AND an "Enrolls" relationship - this is redundant and wrong
- Example of INCORRECT approach: Creating a standalone "Enrollments" entity that is not connected to any relationship - this is wrong
- Rule: If an entity name (singular or plural) matches or is similar to a relationship name, and both connect the same two entities, remove the standalone entity and use the relationship with descriptive attributes instead
- Rule: If an entity has transaction-like attributes (dates, IDs, statuses, grades) and is not connected to any relationship, it should be removed or converted to a relationship with descriptive attributes

Return strict JSON format:
{json_example}

Cardinality options: "one-to-one", "one-to-many", "many-to-one", "many-to-many"

⚠️ MANDATORY: Participation constraints MUST be included for EVERY relationship:
- min1: Minimum participation for entity1 (0 = optional, 1 = mandatory)
- max1: Maximum participation for entity1 (1 = single, "N" = many)
- min2: Minimum participation for entity2 (0 = optional, 1 = mandatory)
- max2: Maximum participation for entity2 (1 = single, "N" = many)

Examples:
- Many-to-many (Student ↔ Course): min1=0, max1="N", min2=0, max2="N" → (0,N) on both ends
- One-to-many (Instructor ↔ Course): min1=0, max1="N", min2=1, max2="N" → (0,N) on Instructor, (1,N) on Course
- One-to-one (Person ↔ Passport): min1=0, max1=1, min2=1, max2=1 → (0,1) on Person, (1,1) on Passport

DO NOT omit participation constraints. They are REQUIRED for every relationship.
"""
        
        try:
            # Try with response_format first (for GPT-4, GPT-3.5-turbo)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an expert database designer. Extract ER/EER diagram components from textual descriptions. Return only valid JSON, no markdown formatting."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
            except Exception as format_error:
                # Fallback: try without response_format (for models that don't support it)
                if "response_format" in str(format_error).lower():
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are an expert database designer. Extract ER/EER diagram components from textual descriptions. Return ONLY valid JSON, no markdown, no code blocks, no explanations."},
                            {"role": "user", "content": prompt + "\n\nReturn ONLY the JSON object, nothing else."}
                        ],
                        temperature=0.1
                    )
                else:
                    raise
            
            content = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                # Extract JSON from markdown code block
                lines = content.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(json_lines)
            
            # Handle encoding issues
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            
            result = json.loads(content)
            return result
        except json.JSONDecodeError as e:
            print(f"[WARN] JSON parsing error: {e}")
            print(f"[WARN] Response content: {response.choices[0].message.content[:200]}")
            # Fallback: try to extract basic entities
            return self._fallback_parse(description)
        except Exception as e:
            print(f"[WARN] Error parsing semantic description: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: try to extract basic entities
            return self._fallback_parse(description)
    
    def _remove_redundant_entities(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove redundant standalone entities that are already represented as relationships.
        
        Rule: If an entity (e.g., "Enrollments") represents a transaction/link between two other entities
        and there's already a relationship (e.g., "Enrolls") connecting those same entities,
        remove the standalone entity and move its attributes to the relationship's descriptive_attributes.
        
        Also removes standalone transaction entities that are not connected to any relationship.
        
        Example:
        - Entity: "Enrollments" with attributes [EnrollmentID, EnrollmentDate, Grade]
        - Relationship: "Enrolls" between "Student" and "Course"
        - Action: Remove "Enrollments" entity, add [EnrollmentDate, Grade] to "Enrolls" relationship's descriptive_attributes
        """
        entities = parsed_data.get("entities", [])
        relationships = parsed_data.get("relationships", [])
        
        if not entities:
            return parsed_data
        
        # Track which entities to remove
        entities_to_remove = []
        entities_to_keep = []
        
        # Get all entity names that are connected via relationships
        connected_entity_names = set()
        for rel in relationships:
            entity1 = rel.get("entity1", "").lower()
            entity2 = rel.get("entity2", "").lower()
            connected_entity_names.add(entity1)
            connected_entity_names.add(entity2)
        
        for entity in entities:
            entity_name = entity["name"]
            entity_name_lower = entity_name.lower()
            
            # Check if this entity name is similar to any relationship name
            # and if it connects the same entities as that relationship
            is_redundant = False
            matching_relationship = None
            
            # First, check if entity matches a relationship name pattern
            for rel in relationships:
                rel_name = rel.get("name", "").lower()
                
                # Enhanced name matching: check for common transaction entity patterns
                # "Enrollments" vs "Enrolls", "Enrollment" vs "Enrolls", "Registrations" vs "Registers"
                name_matches = (
                    entity_name_lower == rel_name or
                    entity_name_lower == rel_name + "s" or
                    entity_name_lower == rel_name + "ment" or
                    entity_name_lower == rel_name + "ments" or
                    (rel_name.endswith("s") and entity_name_lower == rel_name[:-1]) or
                    (rel_name.endswith("s") and entity_name_lower == rel_name[:-1] + "ment") or
                    (rel_name.endswith("s") and entity_name_lower == rel_name[:-1] + "ments") or
                    rel_name == entity_name_lower + "s" or
                    (entity_name_lower.endswith("s") and rel_name == entity_name_lower[:-1]) or
                    (entity_name_lower.endswith("ment") and rel_name == entity_name_lower[:-4]) or
                    (entity_name_lower.endswith("ments") and rel_name == entity_name_lower[:-5]) or
                    (entity_name_lower.endswith("ments") and rel_name == entity_name_lower[:-5] + "s")
                )
                
                # Also check if entity name contains relationship name or vice versa
                if not name_matches:
                    # Check for common patterns: "Enrollments" vs "Enrolls", "Registrations" vs "Registers"
                    # Extract root words (remove common suffixes)
                    entity_root = entity_name_lower.rstrip("s").rstrip("ment").rstrip("ments").replace("medical ", "").replace("medical", "")
                    rel_root = rel_name.rstrip("s")
                    if entity_root == rel_root or rel_root == entity_root:
                        name_matches = True
                    elif (entity_name_lower.startswith(rel_root) or rel_name.startswith(entity_root)) and len(rel_root) > 3:
                        name_matches = True
                    # Special handling for medical domain: "Treatment" matches "Treats", "Medical Record" matches "Records"
                    elif entity_name_lower in ["treatment", "medical record", "medicalrecord"] and rel_name in ["treats", "provides", "receives", "records", "has record", "maintains"]:
                        name_matches = True
                
                if name_matches:
                    # Check if this entity's attributes suggest it's a transaction/link entity
                    # Transaction entities typically have attributes like dates, IDs, statuses
                    entity_attrs = entity.get("attributes", [])
                    transaction_keywords = ["date", "time", "id", "status", "grade", "amount", "quantity", "type", "enrollment", "registration", "transaction", "treatment", "record", "diagnosis", "prescription", "appointment", "visit"]
                    has_transaction_attrs = any(
                        any(keyword in attr.lower() for keyword in transaction_keywords)
                        for attr in entity_attrs
                    )
                    
                    # If entity has transaction-like attributes and matches relationship name, it's likely redundant
                    if has_transaction_attrs:
                        is_redundant = True
                        matching_relationship = rel
                        break
            
            # If not matched to a relationship, check if it's a standalone transaction entity
            if not is_redundant:
                # Check if entity is not connected to any relationship (standalone)
                is_standalone = entity_name_lower not in connected_entity_names
                
                # Check if it's a transaction-like entity (has transaction keywords in name or attributes)
                entity_attrs = entity.get("attributes", [])
                transaction_keywords = ["date", "time", "id", "status", "grade", "amount", "quantity", "type", "treatment", "record", "diagnosis", "prescription", "appointment", "visit"]
                has_transaction_attrs = any(
                    any(keyword in attr.lower() for keyword in transaction_keywords)
                    for attr in entity_attrs
                )
                
                # Transaction entity name patterns (plural forms, -ment/-ments suffixes, medical domain)
                transaction_name_patterns = ["enrollment", "registration", "transaction", "reservation", "subscription", "membership", "treatment", "medical record", "medicalrecord", "record", "appointment", "visit", "diagnosis", "prescription"]
                is_transaction_name = any(pattern in entity_name_lower for pattern in transaction_name_patterns)
                
                # If it's standalone AND has transaction characteristics, it's likely redundant
                if is_standalone and (has_transaction_attrs or is_transaction_name):
                    # Try to find a related relationship that might represent this
                    # Look for relationships that might connect entities related to this transaction
                    for rel in relationships:
                        rel_name = rel.get("name", "").lower()
                        # Check if relationship name is related to entity name
                        entity_root = entity_name_lower.rstrip("s").rstrip("ment").rstrip("ments").replace("medical ", "").replace("medical", "")
                        rel_root = rel_name.rstrip("s")
                        if entity_root == rel_root or (len(entity_root) > 4 and entity_root in rel_root) or (len(rel_root) > 4 and rel_root in entity_root):
                            is_redundant = True
                            matching_relationship = rel
                            break
                        # Special handling for medical domain: "Treatment" matches "Treats", "Medical Record" matches "Records"
                        elif entity_name_lower in ["treatment", "medical record", "medicalrecord"] and rel_name in ["treats", "provides", "receives", "records", "has record", "maintains"]:
                            is_redundant = True
                            matching_relationship = rel
                            break
            
            if is_redundant and matching_relationship:
                # Move entity's attributes to relationship's descriptive_attributes
                entity_attrs = entity.get("attributes", [])
                # Filter out primary key attributes (they're not descriptive)
                pk = entity.get("primary_key", "")
                descriptive_attrs = [attr for attr in entity_attrs if attr.lower() != pk.lower() and attr.lower() != (pk + "id").lower()]
                
                # Add to relationship's descriptive_attributes
                if "descriptive_attributes" not in matching_relationship:
                    matching_relationship["descriptive_attributes"] = []
                # Avoid duplicates
                for attr in descriptive_attrs:
                    if attr not in matching_relationship["descriptive_attributes"]:
                        matching_relationship["descriptive_attributes"].append(attr)
                
                # Mark entity for removal
                entities_to_remove.append(entity_name)
                print(f"   [INFO] Removed redundant entity '{entity_name}' - data already represented by relationship '{matching_relationship.get('name')}'")
            else:
                entities_to_keep.append(entity)
        
        # Update entities list
        parsed_data["entities"] = entities_to_keep
        parsed_data["relationships"] = relationships
        
        # Store removed entity names for description update
        if entities_to_remove:
            parsed_data["_removed_entities"] = entities_to_remove
            print(f"   [INFO] Removed {len(entities_to_remove)} redundant entities: {', '.join(entities_to_remove)}")
        
        # Validate that all entities are connected (no standalone entities)
        parsed_data = self._validate_all_entities_connected(parsed_data)
        
        return parsed_data
    
    def _validate_all_entities_connected(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that all entities are connected via relationships or ISA hierarchies.
        If an entity is standalone, log a warning.
        """
        entities = parsed_data.get("entities", [])
        relationships = parsed_data.get("relationships", [])
        
        if not entities:
            return parsed_data
        
        # Get all entity names that are connected via relationships
        connected_entity_names = set()
        for rel in relationships:
            entity1 = rel.get("entity1", "").lower()
            entity2 = rel.get("entity2", "").lower()
            connected_entity_names.add(entity1)
            connected_entity_names.add(entity2)
        
        # Also check ISA hierarchies - entities in ISA are considered connected
        isa_hierarchies = parsed_data.get("isa_hierarchies", [])
        for isa in isa_hierarchies:
            supertype = isa.get("supertype", "").lower()
            connected_entity_names.add(supertype)
            subtypes = isa.get("subtypes", [])
            for subtype_data in subtypes:
                if isinstance(subtype_data, dict):
                    subtype = subtype_data.get("name", "").lower()
                else:
                    subtype = str(subtype_data).lower()
                connected_entity_names.add(subtype)
        
        # Check for standalone entities
        standalone_entities = []
        for entity in entities:
            entity_name = entity["name"]
            entity_name_lower = entity_name.lower()
            if entity_name_lower not in connected_entity_names:
                standalone_entities.append(entity_name)
        
        # If there are standalone entities, log a warning
        if standalone_entities:
            print(f"   [WARN] Found {len(standalone_entities)} standalone entities (not connected via relationships or ISA): {', '.join(standalone_entities)}")
            print(f"   [WARN] These entities should be connected via relationships. Consider adding relationships or removing unnecessary entities.")
            # Store standalone entities for potential future removal or connection
            parsed_data["_standalone_entities"] = standalone_entities
        
        return parsed_data
    
    def _fallback_parse(self, description: str) -> Dict[str, Any]:
        """Fallback parser using regex if GPT parsing fails"""
        entities = []
        relationships = []
        
        # Simple entity extraction
        entity_patterns = [
            r"(\w+)\s+have\s+attributes?\s+such\s+as\s+([^.]+)",
            r"(\w+)\s+has\s+attributes?\s+like\s+([^.]+)",
            r"(\w+)\s+includes\s+attributes?\s+([^.]+)",
        ]
        
        for pattern in entity_patterns:
            matches = re.finditer(pattern, description, re.IGNORECASE)
            for match in matches:
                entity_name = match.group(1).capitalize()
                attrs_text = match.group(2)
                # Extract attributes
                attrs = re.findall(r"(\w+)\s*\([^)]*\)", attrs_text)
                pk = None
                if "primary key" in attrs_text.lower():
                    pk_match = re.search(r"(\w+)\s*\([^)]*primary\s+key", attrs_text, re.IGNORECASE)
                    if pk_match:
                        pk = pk_match.group(1)
                
                entities.append({
                    "name": entity_name,
                    "attributes": attrs if attrs else [a.strip() for a in attrs_text.split(",")],
                    "primary_key": pk or attrs[0] if attrs else None
                })
        
        # Extract relationships
        rel_patterns = [
            r"(\w+)\s+connects?\s+(\w+)\s+to\s+(\w+)",
            r"(\w+)\s+relationship\s+between\s+(\w+)\s+and\s+(\w+)",
            r"(\w+)\s+for\s+each\s+(\w+)",
        ]
        
        for pattern in rel_patterns:
            matches = re.finditer(pattern, description, re.IGNORECASE)
            for match in matches:
                rel_name = match.group(1) if len(match.groups()) > 3 else "Relates"
                entity1 = match.group(-2).capitalize()
                entity2 = match.group(-1).capitalize()
                
                # Determine cardinality
                cardinality = "many-to-many"
                if "many" in description.lower() and "each" in description.lower():
                    cardinality = "many-to-many"
                elif "one" in description.lower():
                    cardinality = "one-to-many"
                
                relationships.append({
                    "name": rel_name,
                    "entity1": entity1,
                    "entity2": entity2,
                    "cardinality": cardinality
                })
        
        return {
            "entities": entities,
            "relationships": relationships,
            "isa_hierarchies": [],
            "weak_entities": []
        }
    
    def _update_description_after_removal(self, description: str, removed_entities: List[str], parsed_data: Dict[str, Any]) -> str:
        """
        Update the description text to remove references to redundant entities that were removed.
        
        Args:
            description: Original description text
            removed_entities: List of entity names that were removed
            parsed_data: Updated parsed data with relationships that now contain the attributes
        
        Returns:
            Updated description text with references to removed entities cleaned up
        """
        if not removed_entities:
            return description
        
        updated_description = description
        import re
        
        for entity_name in removed_entities:
            # Find the matching relationship that now contains this entity's data
            matching_rel = None
            for rel in parsed_data.get("relationships", []):
                rel_name = rel.get("name", "").lower()
                entity_lower = entity_name.lower()
                # Check if relationship name matches entity name pattern
                if (entity_lower in rel_name or rel_name in entity_lower or
                    entity_lower.rstrip("s").rstrip("ment") == rel_name.rstrip("s")):
                    matching_rel = rel
                    break
            
            # Remove standalone entity references from description
            # Pattern 1: "The 'EntityName' entity has attributes..." -> Remove this sentence/paragraph
            patterns_to_remove = [
                rf"The\s+['\"]?{re.escape(entity_name)}['\"]?\s+entity\s+[^.]*\.",  # "The 'Treatment' entity has..."
                rf"The\s+{re.escape(entity_name)}\s+entity\s+[^.]*\.",  # "The Treatment entity has..."
                rf"['\"]?{re.escape(entity_name)}['\"]?\s+entity\s+[^.]*\.",  # "'Treatment' entity has..."
                rf"Entity\s+['\"]?{re.escape(entity_name)}['\"]?\s+[^.]*\.",  # "Entity 'Treatment' has..."
                rf"Each\s+['\"]?{re.escape(entity_name)}['\"]?\s+[^.]*\.",  # "Each 'Treatment' has..."
            ]
            
            for pattern in patterns_to_remove:
                updated_description = re.sub(pattern, '', updated_description, flags=re.IGNORECASE)
            
            # If we found a matching relationship, update the description to mention the relationship instead
            if matching_rel:
                rel_name = matching_rel.get("name", "")
                # Replace entity references with relationship references where appropriate
                entity_patterns = [
                    rf"\b{re.escape(entity_name)}\s+entity\b",
                    rf"entity\s+['\"]?{re.escape(entity_name)}['\"]?\b",
                ]
                for pattern in entity_patterns:
                    # Check if relationship is already mentioned nearby
                    if rel_name.lower() in updated_description.lower():
                        # Just remove the entity reference
                        updated_description = re.sub(pattern, '', updated_description, flags=re.IGNORECASE)
                    else:
                        # Replace with relationship reference
                        updated_description = re.sub(pattern, f"{rel_name} relationship", updated_description, flags=re.IGNORECASE)
        
        # Clean up multiple spaces and empty sentences
        updated_description = re.sub(r'\s+', ' ', updated_description)  # Multiple spaces to single
        updated_description = re.sub(r'\.\s*\.', '.', updated_description)  # Double periods
        updated_description = re.sub(r'\s+\.', '.', updated_description)  # Space before period
        updated_description = updated_description.strip()
        
        return updated_description
    
    def generate_graphviz_code(self, parsed_data: Dict[str, Any], diagram_type: str = "EER") -> str:
        """
        Generate Graphviz DOT code from parsed ER/EER components.
        Uses proper ER notation: Entities as boxes, Attributes as ovals connected to entities.
        
        Args:
            parsed_data: Parsed components from parse_semantic_description
            diagram_type: "ER" or "EER"
        
        Returns:
            Graphviz DOT code as string
        """
        entities = parsed_data.get("entities", [])
        relationships = parsed_data.get("relationships", [])
        isa_hierarchies = parsed_data.get("isa_hierarchies", [])
        weak_entities = parsed_data.get("weak_entities", [])
        
        lines = []
        lines.append("digraph ER_Diagram {")
        lines.append("    rankdir=LR;")
        lines.append("    node [fontname=\"Arial\", fontsize=10];")
        lines.append("")
        
        # Track weak entity names
        weak_entity_names = {w["name"] for w in weak_entities}
        
        # Draw entities as boxes
        for entity in entities:
            entity_name = entity["name"]
            # Sanitize node ID to ensure it's valid Graphviz identifier
            node_id = entity_name.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
            node_id = "".join(c if c.isalnum() or c == "_" else "_" for c in node_id)
            
            # Escape special characters in label for Graphviz
            entity_label = entity_name.replace('"', '\\"').replace('\\', '\\\\')
            
            # Check if this is a weak entity (use double box)
            if entity_name in weak_entity_names:
                lines.append(f'    {node_id} [label="{entity_label}", shape=box, style="rounded, filled", fillcolor=lightgray, peripheries=2];')
            else:
                lines.append(f'    {node_id} [label="{entity_label}", shape=box, style="rounded, filled", fillcolor=lightblue];')
        
        lines.append("")
        
        # Draw attributes as ovals connected to entities
        for entity in entities:
            entity_name = entity["name"]
            entity_id = entity_name.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
            attrs = entity.get("attributes", [])
            pk = entity.get("primary_key", "")
            composite_attrs = entity.get("composite_attributes", [])
            multivalued_attrs = entity.get("multivalued_attributes", [])
            
            # First, draw composite attributes with their sub-attributes
            for comp_attr_data in composite_attrs:
                # Handle both formats: string or object with sub_attributes
                if isinstance(comp_attr_data, dict):
                    comp_attr_name = comp_attr_data.get("name", "")
                    sub_attrs = comp_attr_data.get("sub_attributes", [])
                else:
                    # Backward compatibility: string format
                    comp_attr_name = str(comp_attr_data) if not isinstance(comp_attr_data, str) else comp_attr_data
                    # Try to infer sub-attributes from common patterns
                    if isinstance(comp_attr_name, str):
                        if "address" in comp_attr_name.lower():
                            sub_attrs = ["Street", "City", "ZipCode"]
                        elif "name" in comp_attr_name.lower():
                            sub_attrs = ["FirstName", "LastName"]
                        elif "date" in comp_attr_name.lower():
                            sub_attrs = ["Day", "Month", "Year"]
                        else:
                            sub_attrs = []
                    else:
                        sub_attrs = []
                
                # Ensure comp_attr_name is a string
                if not isinstance(comp_attr_name, str):
                    comp_attr_name = str(comp_attr_name)
                
                # Find the composite attribute in the attributes list
                comp_attr = None
                for attr in attrs:
                    # CRITICAL: Ensure attr is a string before calling .lower()
                    attr_str = str(attr) if not isinstance(attr, str) else attr
                    if isinstance(comp_attr_name, str) and isinstance(attr_str, str):
                        if comp_attr_name.lower() in attr_str.lower() or attr_str.lower() in comp_attr_name.lower():
                            comp_attr = attr_str
                            break
                
                # If not found in attributes list, use the name directly
                if not comp_attr:
                    comp_attr = comp_attr_name
                
                # Draw the composite attribute (e.g., "Address")
                comp_attr_clean = comp_attr.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "_")
                comp_attr_clean = comp_attr_clean.replace("_PK", "").replace("_pk", "")
                comp_attr_id = f"{entity_id}_{comp_attr_clean}"
                comp_attr_id = "".join(c if c.isalnum() or c == "_" else "_" for c in comp_attr_id)
                comp_attr_label = comp_attr.replace('"', '\\"').replace('\\', '\\\\')
                
                # Composite attribute: ellipse shape with special styling
                lines.append(f'    {comp_attr_id} [label="{comp_attr_label}", shape=ellipse, style="filled,bold", fillcolor=lightgreen, penwidth=2];')
                lines.append(f'    {entity_id} -> {comp_attr_id} [style=solid, arrowhead=none];')
                
                # Draw sub-attributes (Street, City, ZipCode) connected to the composite attribute
                for sub_attr in sub_attrs:
                    sub_attr_clean = sub_attr.replace(" ", "_").replace("-", "_")
                    sub_attr_id = f"{comp_attr_id}_{sub_attr_clean}"
                    sub_attr_id = "".join(c if c.isalnum() or c == "_" else "_" for c in sub_attr_id)
                    lines.append(f'    {sub_attr_id} [label="{sub_attr}", shape=ellipse, style="filled", fillcolor=lightblue];')
                    lines.append(f'    {comp_attr_id} -> {sub_attr_id} [style=solid, arrowhead=none];')
            
            # Draw regular and multivalued attributes
            for attr in attrs:
                # CRITICAL: Ensure attr is a string (handle cases where LLM returns list/dict)
                if not isinstance(attr, str):
                    if isinstance(attr, dict):
                        attr = attr.get("name", str(attr))
                    else:
                        attr = str(attr)
                
                # Skip if this attribute is a composite (already drawn above)
                is_composite_attr = False
                for comp_attr_data in composite_attrs:
                    if isinstance(comp_attr_data, dict):
                        comp_name = comp_attr_data.get("name", "")
                    else:
                        comp_name = str(comp_attr_data) if not isinstance(comp_attr_data, str) else comp_attr_data
                    if comp_name.lower() in attr.lower() or attr.lower() in comp_name.lower():
                        is_composite_attr = True
                        break
                if is_composite_attr:
                    continue
                
                # Clean attribute name for node ID (remove spaces, hyphens, parentheses, etc.)
                attr_clean = attr.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "_")
                # Remove (PK) suffix if present for node ID
                attr_clean = attr_clean.replace("_PK", "").replace("_pk", "")
                attr_id = f"{entity_id}_{attr_clean}"
                
                # Sanitize node ID to ensure it's valid Graphviz identifier
                attr_id = "".join(c if c.isalnum() or c == "_" else "_" for c in attr_id)
                
                # Determine if this is the primary key (underline in label)
                is_pk = pk and isinstance(pk, str) and (pk.lower() in attr.lower() or attr.lower().endswith("(pk)"))
                
                # Check if this is a multivalued attribute
                # CRITICAL: Ensure mv is a string before calling .lower()
                is_multivalued = False
                for mv in multivalued_attrs:
                    if isinstance(mv, str):
                        if mv.lower() in attr.lower():
                            is_multivalued = True
                            break
                    elif isinstance(mv, dict):
                        mv_name = mv.get("name", "")
                        if isinstance(mv_name, str) and mv_name.lower() in attr.lower():
                            is_multivalued = True
                            break
                    else:
                        # Convert to string and check
                        mv_str = str(mv)
                        if mv_str.lower() in attr.lower():
                            is_multivalued = True
                            break
                
                # Escape special characters in label for Graphviz
                attr_label = attr.replace('"', '\\"').replace('\\', '\\\\')
                
                if is_pk:
                    # Primary key: underline in label using HTML-like formatting, ellipse shape
                    attr_label_underlined = f"<u>{attr_label}</u>"
                    lines.append(f'    {attr_id} [label=<{attr_label_underlined}>, shape=ellipse, style="filled", fillcolor=lightyellow];')
                    # Connect attribute to entity with solid line
                    lines.append(f'    {entity_id} -> {attr_id} [style=solid, arrowhead=none];')
                elif is_multivalued:
                    # Multivalued attribute: double oval (use double border/peripheries)
                    # In EER diagrams, multivalued attributes are shown with double ovals (concentric circles)
                    # Use peripheries=2 to create double border effect
                    lines.append(f'    {attr_id} [label="{attr_label}", shape=ellipse, style="filled", fillcolor=lightcoral, penwidth=2, peripheries=2];')
                    lines.append(f'    {entity_id} -> {attr_id} [style=solid, arrowhead=none];')
                else:
                    # Regular attribute: ellipse shape
                    lines.append(f'    {attr_id} [label="{attr_label}", shape=ellipse, style="filled", fillcolor=white];')
                    # Connect attribute to entity with solid line
                    lines.append(f'    {entity_id} -> {attr_id} [style=solid, arrowhead=none];')
        
        lines.append("")
        
        # Draw relationships as diamonds
        for rel in relationships:
            entity1 = rel["entity1"].replace(" ", "_").replace("-", "_")
            entity1 = "".join(c if c.isalnum() or c == "_" else "_" for c in entity1)
            entity2 = rel["entity2"].replace(" ", "_").replace("-", "_")
            entity2 = "".join(c if c.isalnum() or c == "_" else "_" for c in entity2)
            rel_name = rel.get("name", "Relates")
            cardinality = rel.get("cardinality", "many-to-many")
            
            # Create relationship node (diamond) - sanitize ID
            rel_node_id = rel_name.replace(" ", "_").replace("-", "_")
            rel_node_id = "".join(c if c.isalnum() or c == "_" else "_" for c in rel_node_id)
            rel_node_id = f"R_{rel_node_id}"
            
            # Escape special characters in label and ensure relationship is clearly labeled
            rel_label = rel_name.replace('"', '\\"').replace('\\', '\\\\')
            # Make relationship label prominent and clear
            if not rel_label or rel_label.strip() == "":
                rel_label = "Relates"
            lines.append(f'    {rel_node_id} [label="{rel_label}", shape=diamond, style="filled", fillcolor=lightgray, fontsize=10];')
            
            # Get participation constraints (default to optional if not specified)
            min1 = rel.get("min1", 0)
            max1 = rel.get("max1", "N")
            min2 = rel.get("min2", 0)
            max2 = rel.get("max2", "N")
            
            # Format participation labels: (min, max) format
            # Ensure max is displayed correctly (1 for single, N for many)
            max1_str = str(max1) if max1 != "N" else "N"
            max2_str = str(max2) if max2 != "N" else "N"
            label1 = f"({min1},{max1_str})"
            label2 = f"({min2},{max2_str})"
            
            # Connect entities to relationship with cardinality and participation labels
            if cardinality == "many-to-many":
                lines.append(f'    {entity1} -> {rel_node_id} [label="{label1}", arrowhead=none];')
                lines.append(f'    {rel_node_id} -> {entity2} [label="{label2}", arrowhead=none];')
            elif cardinality == "one-to-many":
                lines.append(f'    {entity1} -> {rel_node_id} [label="{label1}", arrowhead=none];')
                lines.append(f'    {rel_node_id} -> {entity2} [label="{label2}", arrowhead=none];')
            elif cardinality == "many-to-one":
                lines.append(f'    {entity1} -> {rel_node_id} [label="{label1}", arrowhead=none];')
                lines.append(f'    {rel_node_id} -> {entity2} [label="{label2}", arrowhead=none];')
            else:  # one-to-one
                lines.append(f'    {entity1} -> {rel_node_id} [label="{label1}", arrowhead=none];')
                lines.append(f'    {rel_node_id} -> {entity2} [label="{label2}", arrowhead=none];')
            
            # Draw descriptive attributes attached to relationships
            descriptive_attrs = rel.get("descriptive_attributes", [])
            for desc_attr in descriptive_attrs:
                if desc_attr:
                    desc_attr_clean = desc_attr.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "_")
                    desc_attr_id = f"{rel_node_id}_{desc_attr_clean}"
                    desc_attr_id = "".join(c if c.isalnum() or c == "_" else "_" for c in desc_attr_id)
                    desc_attr_label = desc_attr.replace('"', '\\"').replace('\\', '\\\\')
                    # Descriptive attributes are shown as ovals connected to the relationship diamond
                    lines.append(f'    {desc_attr_id} [label="{desc_attr_label}", shape=ellipse, style="filled", fillcolor=lightblue];')
                    lines.append(f'    {rel_node_id} -> {desc_attr_id} [style=solid, arrowhead=none];')
        
        lines.append("")
        
        # Draw ISA hierarchies (EER) - single ISA node per hierarchy, no inherited attributes on subtypes
        if diagram_type == "EER" and isa_hierarchies:
            for isa in isa_hierarchies:
                supertype_raw = isa["supertype"]
                supertype = supertype_raw.replace(" ", "_").replace("-", "_")
                supertype = "".join(c if c.isalnum() or c == "_" else "_" for c in supertype)
                
                subtypes = isa.get("subtypes", [])
                
                if not subtypes:
                    continue
                
                # Create ONE ISA relationship node (triangle) for the entire hierarchy
                isa_node = f"ISA_{supertype}"
                lines.append(f'    {isa_node} [label="ISA\\n(Inheritance)", shape=triangle, style="filled", fillcolor=lightgreen, orientation=0, fontsize=9];')
                
                # Connect supertype to ISA node (only once) - USE SOLID LINES for ISA hierarchies
                lines.append(f'    {supertype} -> {isa_node} [style=solid, arrowhead=none];')
                
                # Process all subtypes and connect them to the same ISA node
                for subtype_data in subtypes:
                    # Handle both dict format (with specific_attributes) and string format
                    if isinstance(subtype_data, dict):
                        subtype_raw = subtype_data.get("name", "")
                        specific_attrs = subtype_data.get("specific_attributes", [])
                        if not subtype_raw:
                            continue
                    elif isinstance(subtype_data, str):
                        subtype_raw = subtype_data
                        specific_attrs = []
                    else:
                        subtype_raw = str(subtype_data)
                        specific_attrs = []
                    
                    subtype_id = subtype_raw.replace(" ", "_").replace("-", "_")
                    subtype_id = "".join(c if c.isalnum() or c == "_" else "_" for c in subtype_id)
                    
                    # CRITICAL: Ensure subtype is drawn as an entity box (rectangle), not an oval
                    # Subtypes must be entity rectangles, same as the supertype
                    # Check if subtype entity box was already drawn in the entities section
                    subtype_label = subtype_raw.replace('"', '\\"').replace('\\', '\\\\')
                    
                    # Check if this subtype node was already defined as a box in the entities section
                    # We need to check the actual lines that were already added
                    subtype_entity_exists = False
                    for existing_line in lines:
                        # Check if this subtype_id is already defined as a node
                        if f'{subtype_id} [' in existing_line and 'shape=box' in existing_line:
                            subtype_entity_exists = True
                            break
                    
                    # If subtype wasn't drawn as a box in entities section, explicitly draw it here
                    # This ensures subtypes are ALWAYS drawn as entity boxes (rectangles), not ovals
                    if not subtype_entity_exists:
                        # Explicitly draw subtype as an entity box (rectangle) BEFORE connecting to ISA
                        # Insert it right before the ISA connection to ensure proper rendering
                        lines.append(f'    {subtype_id} [label="{subtype_label}", shape=box, style="rounded, filled", fillcolor=lightblue];')
                    
                    # Connect subtype to the same ISA node (only one ISA relationship) - USE SOLID LINES for ISA hierarchies
                    lines.append(f'    {isa_node} -> {subtype_id} [style=solid, arrowhead=none];')
                    
                    # Draw ONLY subtype-specific attributes (inherited attributes are NOT repeated)
                    for attr in specific_attrs:
                        attr_clean = attr.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "_")
                        attr_id = f"{subtype_id}_specific_{attr_clean}"
                        attr_id = "".join(c if c.isalnum() or c == "_" else "_" for c in attr_id)
                        
                        attr_label = attr.replace('"', '\\"').replace('\\', '\\\\')
                        # Check if this is a primary key (subtype-specific PK)
                        # Note: Subtype PKs typically inherit from supertype, but check anyway
                        is_pk_subtype = "(PK)" in attr_label.upper() or "(pk)" in attr_label
                        if is_pk_subtype:
                            attr_label_underlined = f"<u>{attr_label}</u>"
                            lines.append(f'    {attr_id} [label=<{attr_label_underlined}>, shape=ellipse, style="filled", fillcolor=lightcyan];')
                        else:
                            lines.append(f'    {attr_id} [label="{attr_label}", shape=ellipse, style="filled", fillcolor=lightcyan];')
                        lines.append(f'    {subtype_id} -> {attr_id} [style=solid, arrowhead=none];')
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def render_graphviz_to_image(
        self, 
        dot_code: str, 
        output_path: Path, 
        format: str = "png",
        dpi: int = 300
    ) -> bool:
        """
        Render Graphviz DOT code to an image file.
        
        Args:
            dot_code: Graphviz DOT code
            output_path: Path to save the image
            format: Output format ("png", "svg", "pdf")
            dpi: Resolution for PNG (default 300)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Find Graphviz dot executable
            dot_exe = self._find_graphviz_dot()
            if not dot_exe:
                raise FileNotFoundError("Graphviz 'dot' command not found")
            
            # Create temporary DOT file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False, encoding='utf-8') as tmp_file:
                tmp_file.write(dot_code)
                tmp_dot_path = tmp_file.name
            
            try:
                # Determine output format flag
                if format == "png":
                    output_format = "png"
                    dpi_flag = f"-Gdpi={dpi}"
                elif format == "svg":
                    output_format = "svg"
                    dpi_flag = ""
                elif format == "pdf":
                    output_format = "pdf"
                    dpi_flag = ""
                else:
                    output_format = "png"
                    dpi_flag = f"-Gdpi={dpi}"
                
                # Run Graphviz
                cmd = [dot_exe, "-T" + output_format, "-o", str(output_path)]
                if dpi_flag:
                    cmd.insert(-2, dpi_flag)
                cmd.append(tmp_dot_path)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    print(f"[OK] Graphviz diagram generated: {output_path}")
                    return True
                else:
                    print(f"[ERROR] Graphviz error: {result.stderr}")
                    return False
                    
            finally:
                # Clean up temp file
                if os.path.exists(tmp_dot_path):
                    os.unlink(tmp_dot_path)
                    
        except FileNotFoundError as e:
            print(f"[ERROR] Graphviz 'dot' command not found: {e}")
            print("   Graphviz was installed but may need a shell restart for PATH to update.")
            print("   Or manually add Graphviz bin directory to PATH.")
            return False
        except Exception as e:
            print(f"[ERROR] Error rendering Graphviz diagram: {e}")
            return False
    
    def generate_diagram_from_semantic_description(
        self,
        description: str,
        output_path: Path,
        diagram_type: str = "EER",
        format: str = "png",
        requires_isa: bool = False
    ) -> Dict[str, Any]:
        """
        Complete pipeline: Parse semantic description and generate diagram image.
        
        Args:
            description: Textual description of the ER/EER diagram
            output_path: Path to save the generated image
            diagram_type: "ER" or "EER"
            format: Output format ("png", "svg", "pdf")
        
        Returns:
            Dictionary with result:
            {
                "success": bool,
                "image_path": str,
                "dot_code": str,
                "parsed_data": dict,
                "error": str (if failed)
            }
        """
        try:
            print(f"   [INFO] Parsing semantic description for {diagram_type} diagram...")
            
            # Step 1: Parse semantic description (pass requires_isa flag)
            parsed_data = self.parse_semantic_description(description, requires_isa=requires_isa)
            
            if not parsed_data.get("entities"):
                return {
                    "success": False,
                    "error": "No entities found in description",
                    "parsed_data": parsed_data
                }
            
            # If this is an EER diagram and description mentions ISA/subtypes but none were parsed,
            # try to infer ISA hierarchies from entity names
            if diagram_type == "EER":
                isa_hierarchies = parsed_data.get("isa_hierarchies", [])
                description_lower = description.lower()
                
                # Check if description mentions ISA-related terms but no hierarchies were parsed
                mentions_isa = any(term in description_lower for term in [
                    "isa", "subtype", "supertype", "graduate", "undergraduate",
                    "generalization", "specialization", "inheritance", "subclass"
                ])
                
                # If ISA hierarchies are required (from subquestion) but not parsed, force them
                if (mentions_isa or requires_isa) and not isa_hierarchies:
                    print(f"   [WARN] ISA hierarchies required but none were parsed. Forcing creation of ISA hierarchies...")
                    # Try to infer ISA hierarchies from entity names
                    entities = parsed_data.get("entities", [])
                    entity_names = [e["name"].lower() for e in entities]
                    
                    # Find main entity candidates for ISA hierarchies
                    main_entity = None
                    if "student" in " ".join(entity_names):
                        main_entity = next((e for e in entities if "student" in e["name"].lower() and "graduate" not in e["name"].lower() and "undergraduate" not in e["name"].lower()), None)
                        if main_entity:
                            # Create subtypes if they don't exist
                            grad_student = next((e for e in entities if "graduate" in e["name"].lower()), None)
                            undergrad_student = next((e for e in entities if "undergraduate" in e["name"].lower()), None)
                            
                            subtypes = []
                            if grad_student:
                                subtypes.append({
                                    "name": grad_student["name"],
                                    "specific_attributes": grad_student.get("attributes", [])[:3] if grad_student.get("attributes") else ["ThesisTitle", "AdvisorName"]
                                })
                            else:
                                # Create GraduateStudent subtype
                                subtypes.append({
                                    "name": "GraduateStudent",
                                    "specific_attributes": ["ThesisTitle", "AdvisorName", "ResearchArea"]
                                })
                            
                            if undergrad_student:
                                subtypes.append({
                                    "name": undergrad_student["name"],
                                    "specific_attributes": undergrad_student.get("attributes", [])[:3] if undergrad_student.get("attributes") else ["YearOfStudy", "Major"]
                                })
                            else:
                                # Create UndergraduateStudent subtype
                                subtypes.append({
                                    "name": "UndergraduateStudent",
                                    "specific_attributes": ["YearOfStudy", "Major", "GPA"]
                                })
                            
                            parsed_data["isa_hierarchies"] = [{
                                "supertype": main_entity["name"],
                                "subtypes": subtypes
                            }]
                            # IMPORTANT: Add subtypes as entities so they can be rendered
                            entities = parsed_data.get("entities", [])
                            for subtype in subtypes:
                                subtype_name = subtype["name"]
                                # Check if subtype already exists as entity
                                if not any(e["name"] == subtype_name for e in entities):
                                    entities.append({
                                        "name": subtype_name,
                                        "attributes": subtype.get("specific_attributes", []),
                                        "primary_key": main_entity.get("primary_key", "")
                                    })
                            parsed_data["entities"] = entities
                            print(f"   [INFO] Created ISA hierarchy: {main_entity['name']} -> {[s['name'] for s in subtypes]}")
                            print(f"   [INFO] Added {len(subtypes)} subtypes as entities")
                    
                    elif "course" in " ".join(entity_names):
                        main_entity = next((e for e in entities if "course" in e["name"].lower() and "core" not in e["name"].lower() and "elective" not in e["name"].lower()), None)
                        if main_entity:
                            subtypes = [
                                {
                                    "name": "CoreCourse",
                                    "specific_attributes": ["PrerequisiteCourseID", "RequiredCredits", "Department"]
                                },
                                {
                                    "name": "ElectiveCourse",
                                    "specific_attributes": ["MaxEnrollment", "DepartmentRestriction", "ElectiveType"]
                                }
                            ]
                            parsed_data["isa_hierarchies"] = [{
                                "supertype": main_entity["name"],
                                "subtypes": subtypes
                            }]
                            # IMPORTANT: Add subtypes as entities so they can be rendered
                            entities = parsed_data.get("entities", [])
                            for subtype in subtypes:
                                subtype_name = subtype["name"]
                                # Check if subtype already exists as entity
                                if not any(e["name"] == subtype_name for e in entities):
                                    entities.append({
                                        "name": subtype_name,
                                        "attributes": subtype.get("specific_attributes", []),
                                        "primary_key": main_entity.get("primary_key", "")
                                    })
                            parsed_data["entities"] = entities
                            print(f"   [INFO] Created ISA hierarchy: {main_entity['name']} -> {[s['name'] for s in subtypes]}")
                            print(f"   [INFO] Added {len(subtypes)} subtypes as entities")
                    
                    elif "employee" in " ".join(entity_names) or "staff" in " ".join(entity_names):
                        main_entity = next((e for e in entities if ("employee" in e["name"].lower() or "staff" in e["name"].lower()) and "full" not in e["name"].lower() and "part" not in e["name"].lower()), None)
                        if main_entity:
                            subtypes = [
                                {
                                    "name": "FullTimeEmployee",
                                    "specific_attributes": ["Salary", "Benefits", "AnnualLeave"]
                                },
                                {
                                    "name": "PartTimeEmployee",
                                    "specific_attributes": ["HourlyRate", "MaxHours", "ContractEndDate"]
                                }
                            ]
                            parsed_data["isa_hierarchies"] = [{
                                "supertype": main_entity["name"],
                                "subtypes": subtypes
                            }]
                            # IMPORTANT: Add subtypes as entities so they can be rendered
                            entities = parsed_data.get("entities", [])
                            for subtype in subtypes:
                                subtype_name = subtype["name"]
                                # Check if subtype already exists as entity
                                if not any(e["name"] == subtype_name for e in entities):
                                    entities.append({
                                        "name": subtype_name,
                                        "attributes": subtype.get("specific_attributes", []),
                                        "primary_key": main_entity.get("primary_key", "")
                                    })
                            parsed_data["entities"] = entities
                            print(f"   [INFO] Created ISA hierarchy: {main_entity['name']} -> {[s['name'] for s in subtypes]}")
                            print(f"   [INFO] Added {len(subtypes)} subtypes as entities")
                    
                    else:
                        # Generic fallback: use first entity as supertype
                        if entities:
                            main_entity = entities[0]
                            subtypes = [
                                {
                                    "name": f"{main_entity['name']}TypeA",
                                    "specific_attributes": ["AttributeA1", "AttributeA2"]
                                },
                                {
                                    "name": f"{main_entity['name']}TypeB",
                                    "specific_attributes": ["AttributeB1", "AttributeB2"]
                                }
                            ]
                            parsed_data["isa_hierarchies"] = [{
                                "supertype": main_entity["name"],
                                "subtypes": subtypes
                            }]
                            # IMPORTANT: Add subtypes as entities so they can be rendered
                            for subtype in subtypes:
                                subtype_name = subtype["name"]
                                # Check if subtype already exists as entity
                                if not any(e["name"] == subtype_name for e in entities):
                                    entities.append({
                                        "name": subtype_name,
                                        "attributes": subtype.get("specific_attributes", []),
                                        "primary_key": main_entity.get("primary_key", "")
                                    })
                            parsed_data["entities"] = entities
                            print(f"   [INFO] Created generic ISA hierarchy: {main_entity['name']} -> {[s['name'] for s in subtypes]}")
                            print(f"   [INFO] Added {len(subtypes)} subtypes as entities")
            
            print(f"   [OK] Parsed {len(parsed_data.get('entities', []))} entities, {len(parsed_data.get('relationships', []))} relationships, {len(parsed_data.get('isa_hierarchies', []))} ISA hierarchies")
            
            # Step 1.5: Post-process to remove redundant standalone entities
            parsed_data = self._remove_redundant_entities(parsed_data)
            print(f"   [OK] After removing redundant entities: {len(parsed_data.get('entities', []))} entities, {len(parsed_data.get('relationships', []))} relationships")
            
            # Step 1.6: Update description to reflect removed entities
            removed_entities = parsed_data.get("_removed_entities", [])
            if removed_entities:
                description = self._update_description_after_removal(description, removed_entities, parsed_data)
                # Store updated description in parsed_data for later use
                parsed_data["updated_description"] = description
                print(f"   [INFO] Updated description after removing {len(removed_entities)} redundant entities")
            
            # Step 2: Generate Graphviz code
            print(f"   [INFO] Generating Graphviz DOT code...")
            dot_code = self.generate_graphviz_code(parsed_data, diagram_type)
            
            # Step 3: Render to image
            print(f"   [INFO] Rendering diagram to {format}...")
            success = self.render_graphviz_to_image(dot_code, output_path, format=format)
            
            if success:
                result = {
                    "success": True,
                    "image_path": str(output_path),
                    "dot_code": dot_code,
                    "parsed_data": parsed_data
                }
                # Include updated description if entities were removed
                if "updated_description" in parsed_data:
                    result["updated_description"] = parsed_data["updated_description"]
                return result
            else:
                return {
                    "success": False,
                    "error": "Graphviz rendering failed",
                    "dot_code": dot_code,
                    "parsed_data": parsed_data
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "parsed_data": {}
            }


# Convenience function
def generate_er_diagram_from_description(
    description: str,
    output_path: Path,
    diagram_type: str = "EER",
    format: str = "png"
) -> Dict[str, Any]:
    """
    Convenience function to generate ER/EER diagram from semantic description.
    
    Args:
        description: Textual description
        output_path: Path to save image
        diagram_type: "ER" or "EER"
        format: "png", "svg", or "pdf"
    
    Returns:
        Result dictionary
    """
    service = SemanticDiagramService()
    return service.generate_diagram_from_semantic_description(
        description, output_path, diagram_type, format
    )
