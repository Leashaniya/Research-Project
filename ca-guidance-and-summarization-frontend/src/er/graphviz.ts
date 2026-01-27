import type { ERModel, Entity, Relationship, Attribute } from "./types";

/**
 * Converts an ERModel to Graphviz DOT format.
 * 
 * Uses Chen notation:
 * - Entities: box shape
 * - Relationships: diamond shape
 * - Attributes: ellipse shape
 * - Edges connect entities to relationships and owners to attributes
 * - Cardinality labels on entity->relationship edges
 */
export function erModelToDot(model: ERModel): string {
  const lines: string[] = [];
  
  // Graph header
  lines.push("digraph ERDiagram {");
  lines.push("  rankdir=LR;");
  lines.push("  nodesep=1.0;");
  lines.push("  ranksep=1.5;");
  lines.push("  node [fontname=\"Arial\", fontsize=10];");
  lines.push("  edge [fontname=\"Arial\", fontsize=9];");
  lines.push("");
  
  // Helper to escape node IDs and labels for DOT
  const escapeId = (id: string): string => {
    // Replace special characters that might break DOT syntax
    return `"${id.replace(/"/g, '\\"')}"`;
  };
  
  const escapeLabel = (label: string): string => {
    // Escape quotes and newlines for labels
    return `"${label.replace(/"/g, '\\"').replace(/\n/g, '\\n')}"`;
  };
  
  // Helper to generate attribute label (with underline for PK)
  const getAttributeLabel = (attr: Attribute): string => {
    const escapedName = attr.name.replace(/"/g, '\\"').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    if (attr.pk) {
      // Use Graphviz HTML-like label with underline
      return `<<U>${escapedName}</U>>`;
    } else {
      // Use normal label
      return `"${escapedName}"`;
    }
  };
  
  // Create entity nodes
  for (const entity of model.entities) {
    const nodeId = `E_${entity.id}`;
    const label = escapeLabel(entity.name);
    lines.push(`  ${escapeId(nodeId)} [shape=box, label=${label}];`);
  }
  
  lines.push("");
  
  // Create relationship nodes (diamonds)
  for (const rel of model.relationships) {
    const nodeId = `R_${rel.id}`;
    const label = escapeLabel(rel.name);
    lines.push(`  ${escapeId(nodeId)} [shape=diamond, label=${label}];`);
  }
  
  lines.push("");
  
  // Create attribute nodes (ellipses)
  // Entity attributes
  for (const entity of model.entities) {
    for (const attr of entity.attributes) {
      const nodeId = `A_${attr.id}`;
      const label = getAttributeLabel(attr);
      lines.push(`  ${escapeId(nodeId)} [shape=ellipse, label=${label}];`);
      
      // Connect attribute to entity
      const ownerId = `E_${entity.id}`;
      lines.push(`  ${escapeId(ownerId)} -> ${escapeId(nodeId)} [style=solid, arrowhead=none];`);
    }
  }
  
  // Relationship attributes
  for (const rel of model.relationships) {
    for (const attr of rel.attributes) {
      const nodeId = `A_${attr.id}`;
      const label = getAttributeLabel(attr);
      lines.push(`  ${escapeId(nodeId)} [shape=ellipse, label=${label}];`);
      
      // Connect attribute to relationship
      const ownerId = `R_${rel.id}`;
      lines.push(`  ${escapeId(ownerId)} -> ${escapeId(nodeId)} [style=solid, arrowhead=none];`);
    }
  }
  
  lines.push("");
  
  // Create entity->relationship edges with cardinality labels
  for (const rel of model.relationships) {
    const relId = `R_${rel.id}`;
    const fromEntityId = `E_${rel.fromEntityId}`;
    const toEntityId = `E_${rel.toEntityId}`;
    
    // Edge from entity to relationship (with cardinality label)
    lines.push(`  ${escapeId(fromEntityId)} -> ${escapeId(relId)} [label=${escapeLabel(rel.fromCardinality)}, arrowhead=none];`);
    
    // Edge from relationship to entity (with cardinality label)
    lines.push(`  ${escapeId(relId)} -> ${escapeId(toEntityId)} [label=${escapeLabel(rel.toCardinality)}, arrowhead=none];`);
  }
  
  lines.push("}");
  
  return lines.join("\n");
}
