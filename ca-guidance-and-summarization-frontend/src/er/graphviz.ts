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
  // For weak entities, PK uses dashed underline; for regular entities, PK uses solid underline
  // Note: Graphviz HTML labels don't support CSS dashed underlines, so we use double underline as visual distinction
  // The double underline visually represents the dashed underline concept for weak entity PKs
  const getAttributeLabel = (attr: Attribute, isWeakEntity: boolean = false): string => {
    const escapedName = attr.name.replace(/"/g, '\\"').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    if (attr.pk) {
      if (isWeakEntity) {
        // Weak entity PK: double underline (represents dashed underline concept)
        // Graphviz limitation: cannot render true dashed underline, so double underline is used as visual distinction
        return `<<U><U>${escapedName}</U></U>>`;
      } else {
        // Regular entity PK: solid underline
        return `<<U>${escapedName}</U>>`;
      }
    } else {
      // Use normal label
      return `"${escapedName}"`;
    }
  };

  // Helper to get shape and peripheries for attribute type
  const getAttributeShape = (attr: Attribute): { shape: string; peripheries?: number } => {
    if (attr.type === "multivalued") {
      // Multi-valued: double oval (peripheries=2)
      return { shape: "ellipse", peripheries: 2 };
    }
    // Regular and composite: single oval
    return { shape: "ellipse" };
  };
  
  // Create entity nodes
  for (const entity of model.entities) {
    const nodeId = `E_${entity.id}`;
    const label = escapeLabel(entity.name);
    // Weak entities: double rectangle (peripheries=2)
    if (entity.isWeak) {
      lines.push(`  ${escapeId(nodeId)} [shape=box, peripheries=2, label=${label}];`);
    } else {
      lines.push(`  ${escapeId(nodeId)} [shape=box, label=${label}];`);
    }
  }
  
  lines.push("");
  
  // Create relationship nodes (diamonds for binary/ternary, triangle for ISA)
  for (const rel of model.relationships) {
    const nodeId = `R_${rel.id}`;
    const label = escapeLabel(rel.name);
    
    if (rel.relationshipType === "isa") {
      // ISA relationship: inverted triangle (parent at top, children at bottom)
      // Graphviz uses invtriangle for this
      lines.push(`  ${escapeId(nodeId)} [shape=invtriangle, label=${label}];`);
    } else {
      // Binary or Ternary relationship: diamond shape
      // Weak relationships: always double-line diamond (peripheries=2) - mandatory
      if (rel.isWeak) {
        lines.push(`  ${escapeId(nodeId)} [shape=diamond, peripheries=2, label=${label}];`);
      } else {
        lines.push(`  ${escapeId(nodeId)} [shape=diamond, label=${label}];`);
      }
    }
  }
  
  lines.push("");
  
  // Create attribute nodes (ellipses)
  // Entity attributes
  for (const entity of model.entities) {
    for (const attr of entity.attributes) {
      const nodeId = `A_${attr.id}`;
      const label = getAttributeLabel(attr, entity.isWeak);
      const shapeInfo = getAttributeShape(attr);
      const shapeStr = shapeInfo.peripheries 
        ? `shape=${shapeInfo.shape}, peripheries=${shapeInfo.peripheries}`
        : `shape=${shapeInfo.shape}`;
      lines.push(`  ${escapeId(nodeId)} [${shapeStr}, label=${label}];`);
      
      // Connect attribute to entity
      const ownerId = `E_${entity.id}`;
      lines.push(`  ${escapeId(ownerId)} -> ${escapeId(nodeId)} [style=solid, arrowhead=none];`);
      
      // Handle composite attributes: create sub-attributes and connect them
      if (attr.type === "composite" && attr.subAttributes && attr.subAttributes.length > 0) {
        for (const subAttr of attr.subAttributes) {
          const subNodeId = `A_${subAttr.id}`;
          const subLabel = getAttributeLabel(subAttr, entity.isWeak);
          const subShapeInfo = getAttributeShape(subAttr);
          const subShapeStr = subShapeInfo.peripheries 
            ? `shape=${subShapeInfo.shape}, peripheries=${subShapeInfo.peripheries}`
            : `shape=${subShapeInfo.shape}`;
          lines.push(`  ${escapeId(subNodeId)} [${subShapeStr}, label=${subLabel}];`);
          
          // Connect sub-attribute to composite attribute
          lines.push(`  ${escapeId(nodeId)} -> ${escapeId(subNodeId)} [style=solid, arrowhead=none];`);
        }
      }
    }
  }
  
  // Relationship attributes
  for (const rel of model.relationships) {
    for (const attr of rel.attributes) {
      const nodeId = `A_${attr.id}`;
      const label = getAttributeLabel(attr);
      const shapeInfo = getAttributeShape(attr);
      const shapeStr = shapeInfo.peripheries 
        ? `shape=${shapeInfo.shape}, peripheries=${shapeInfo.peripheries}`
        : `shape=${shapeInfo.shape}`;
      lines.push(`  ${escapeId(nodeId)} [${shapeStr}, label=${label}];`);
      
      // Connect attribute to relationship
      const ownerId = `R_${rel.id}`;
      lines.push(`  ${escapeId(ownerId)} -> ${escapeId(nodeId)} [style=solid, arrowhead=none];`);
      
      // Handle composite attributes: create sub-attributes and connect them
      if (attr.type === "composite" && attr.subAttributes && attr.subAttributes.length > 0) {
        for (const subAttr of attr.subAttributes) {
          const subNodeId = `A_${subAttr.id}`;
          const subLabel = getAttributeLabel(subAttr);
          const subShapeInfo = getAttributeShape(subAttr);
          const subShapeStr = subShapeInfo.peripheries 
            ? `shape=${subShapeInfo.shape}, peripheries=${subShapeInfo.peripheries}`
            : `shape=${subShapeInfo.shape}`;
          lines.push(`  ${escapeId(subNodeId)} [${subShapeStr}, label=${subLabel}];`);
          
          // Connect sub-attribute to composite attribute
          lines.push(`  ${escapeId(nodeId)} -> ${escapeId(subNodeId)} [style=solid, arrowhead=none];`);
        }
      }
    }
  }
  
  lines.push("");
  
  // Create entity->relationship edges with cardinality labels and participation constraints
  for (const rel of model.relationships) {
    const relId = `R_${rel.id}`;
    
    // Determine edge style based on participation and weak relationship
    // Weak relationships always use double lines on both sides (mandatory)
    const getEdgeStyle = (participation: string, isWeakRel: boolean): string => {
      const styles: string[] = [];
      
      if (isWeakRel) {
        // Weak relationship: always double line on both sides (mandatory)
        styles.push("style=solid");
        styles.push("penwidth=2");
      } else {
        // Regular relationship: handle participation constraints
        styles.push("style=solid");
        if (participation === "total") {
          styles.push("penwidth=2");
        }
      }
      
      return styles.join(", ");
    };
    
    if (rel.relationshipType === "isa") {
      // ISA relationship: parent at top, children at bottom (no cardinality labels)
      if (rel.parentEntityId) {
        const parentId = `E_${rel.parentEntityId}`;
        // Connect parent to triangle (at top)
        lines.push(`  ${escapeId(parentId)} -> ${escapeId(relId)} [style=solid, arrowhead=none];`);
        
        // Connect triangle to each child (at bottom)
        if (rel.childEntityIds && rel.childEntityIds.length > 0) {
          for (const childId of rel.childEntityIds) {
            if (childId) {
              const childEntityId = `E_${childId}`;
              lines.push(`  ${escapeId(relId)} -> ${escapeId(childEntityId)} [style=solid, arrowhead=none];`);
            }
          }
        }
      }
    } else if (rel.relationshipType === "ternary") {
      // Ternary relationship: connect 3 entities
      const fromEntityId = `E_${rel.fromEntityId}`;
      const toEntityId = `E_${rel.toEntityId}`;
      const thirdEntityId = rel.thirdEntityId ? `E_${rel.thirdEntityId}` : null;
      
      // Edge from entity A to relationship
      const fromStyle = getEdgeStyle(rel.fromParticipation, rel.isWeak);
      lines.push(`  ${escapeId(fromEntityId)} -> ${escapeId(relId)} [label=${escapeLabel(rel.fromCardinality)}, ${fromStyle}, arrowhead=none];`);
      
      // Edge from relationship to entity B
      const toStyle = getEdgeStyle(rel.toParticipation, rel.isWeak);
      lines.push(`  ${escapeId(relId)} -> ${escapeId(toEntityId)} [label=${escapeLabel(rel.toCardinality)}, ${toStyle}, arrowhead=none];`);
      
      // Edge from relationship to entity C (if specified)
      if (thirdEntityId) {
        const thirdStyle = getEdgeStyle(rel.thirdParticipation || "none", rel.isWeak);
        const thirdCardinality = rel.thirdCardinality || "0..*";
        lines.push(`  ${escapeId(relId)} -> ${escapeId(thirdEntityId)} [label=${escapeLabel(thirdCardinality)}, ${thirdStyle}, arrowhead=none];`);
      }
    } else {
      // Binary relationship: connect 2 entities
      const fromEntityId = `E_${rel.fromEntityId}`;
      const toEntityId = `E_${rel.toEntityId}`;
      
      // Edge from entity to relationship (with cardinality label and participation)
      const fromStyle = getEdgeStyle(rel.fromParticipation, rel.isWeak);
      lines.push(`  ${escapeId(fromEntityId)} -> ${escapeId(relId)} [label=${escapeLabel(rel.fromCardinality)}, ${fromStyle}, arrowhead=none];`);
      
      // Edge from relationship to entity (with cardinality label and participation)
      const toStyle = getEdgeStyle(rel.toParticipation, rel.isWeak);
      lines.push(`  ${escapeId(relId)} -> ${escapeId(toEntityId)} [label=${escapeLabel(rel.toCardinality)}, ${toStyle}, arrowhead=none];`);
    }
  }
  
  lines.push("}");
  
  return lines.join("\n");
}
