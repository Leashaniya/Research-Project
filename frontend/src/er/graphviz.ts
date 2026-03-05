import type {
  ERModel,
  Entity,
  Relationship,
  Attribute,
  AggregationRelationship,
} from "./types";

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
  // Needed for lhead/ltail to attach edges to clusters
  lines.push("  compound=true;");
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

  const collectAttributeNodeIds = (attrs: Attribute[]): string[] => {
    const ids: string[] = [];
    const stack: Attribute[] = [...attrs];
    while (stack.length > 0) {
      const a = stack.pop();
      if (!a) continue;
      ids.push(`A_${a.id}`);
      if (a.type === "composite" && a.subAttributes && a.subAttributes.length > 0) {
        for (const sub of a.subAttributes) stack.push(sub);
      }
    }
    return ids;
  };

  // Precompute aggregation clusters keyed by their whole entity id. We only keep
  // clusters that actually have at least one inner relationship inside the
  // dashed box (inAggregationBox === true), since those are the ones that
  // render an aggregation container visually.
  const aggregationClustersByWhole = new Map<string, string>();
  const aggregationClusterByEntity = new Map<string, string>();
  for (const rel of model.relationships) {
    if (rel.relationshipType !== "aggregation") continue;
    const wholeEntityId = rel.aggregationWholeEntityId;
    const aggregationRels: AggregationRelationship[] = rel.aggregationRelationships || [];
    if (!wholeEntityId || aggregationRels.length === 0) continue;

    const hasInBox = aggregationRels.some((aggr) => aggr.inAggregationBox && aggr.partEntityId);
    if (!hasInBox) continue;

    const clusterIdRaw = `cluster_agg_${String(rel.id)}`;
    const safeClusterId = clusterIdRaw.replace(/[^a-zA-Z0-9_]/g, "_");

    if (!aggregationClustersByWhole.has(wholeEntityId)) {
      aggregationClustersByWhole.set(wholeEntityId, safeClusterId);
    }

    // Any entity that is visually inside the dashed box should connect to the
    // cluster boundary when it participates in an outside relationship.
    if (!aggregationClusterByEntity.has(wholeEntityId)) {
      aggregationClusterByEntity.set(wholeEntityId, safeClusterId);
    }
    for (const aggr of aggregationRels) {
      if (!aggr.inAggregationBox) continue;
      if (!aggr.partEntityId) continue;
      if (!aggregationClusterByEntity.has(aggr.partEntityId)) {
        aggregationClusterByEntity.set(aggr.partEntityId, safeClusterId);
      }
    }
  }
  
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
    // Aggregation relationships are rendered via their inner aggregationRelationships below
    if (rel.relationshipType === "aggregation") {
      continue;
    }
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
    // Skip aggregation container itself here; its inner relationships are
    // rendered separately below (and can have their own attributes).
    if (rel.relationshipType === "aggregation") {
      continue;
    }
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
    // Aggregation relationships handled separately below
    if (rel.relationshipType === "aggregation") {
      continue;
    }
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
        const parentCluster = aggregationClusterByEntity.get(rel.parentEntityId);
        const parentClusterAttr = parentCluster ? `, ltail=${parentCluster}` : "";
        // Connect parent to triangle (at top)
        lines.push(`  ${escapeId(parentId)} -> ${escapeId(relId)} [style=solid, arrowhead=none${parentClusterAttr}];`);
        
        // Connect triangle to each child (at bottom)
        if (rel.childEntityIds && rel.childEntityIds.length > 0) {
          for (const childId of rel.childEntityIds) {
            if (childId) {
              const childEntityId = `E_${childId}`;
              const childCluster = aggregationClusterByEntity.get(childId);
              const childClusterAttr = childCluster ? `, lhead=${childCluster}` : "";
              lines.push(`  ${escapeId(relId)} -> ${escapeId(childEntityId)} [style=solid, arrowhead=none${childClusterAttr}];`);
            }
          }
        }
      }
    } else if (rel.relationshipType === "ternary") {
      // Ternary relationship: connect 3 entities
      const fromEntityId = `E_${rel.fromEntityId}`;
      const toEntityId = `E_${rel.toEntityId}`;
      const thirdEntityId = rel.thirdEntityId ? `E_${rel.thirdEntityId}` : null;
      const fromCluster = aggregationClusterByEntity.get(rel.fromEntityId);
      const toCluster = aggregationClusterByEntity.get(rel.toEntityId);
      const thirdCluster = rel.thirdEntityId ? aggregationClusterByEntity.get(rel.thirdEntityId) : undefined;
      
      // Edge from entity A to relationship
      const fromStyle = getEdgeStyle(rel.fromParticipation, rel.isWeak);
      const fromClusterAttr = fromCluster ? `, ltail=${fromCluster}` : "";
      lines.push(`  ${escapeId(fromEntityId)} -> ${escapeId(relId)} [label=${escapeLabel(rel.fromCardinality)}, ${fromStyle}, arrowhead=none${fromClusterAttr}];`);
      
      // Edge from relationship to entity B
      const toStyle = getEdgeStyle(rel.toParticipation, rel.isWeak);
      const toClusterAttr = toCluster ? `, lhead=${toCluster}` : "";
      lines.push(`  ${escapeId(relId)} -> ${escapeId(toEntityId)} [label=${escapeLabel(rel.toCardinality)}, ${toStyle}, arrowhead=none${toClusterAttr}];`);
      
      // Edge from relationship to entity C (if specified)
      if (thirdEntityId) {
        const thirdStyle = getEdgeStyle(rel.thirdParticipation || "none", rel.isWeak);
        const thirdCardinality = rel.thirdCardinality || "0..*";
        const thirdClusterAttr = thirdCluster ? `, lhead=${thirdCluster}` : "";
        lines.push(`  ${escapeId(relId)} -> ${escapeId(thirdEntityId)} [label=${escapeLabel(thirdCardinality)}, ${thirdStyle}, arrowhead=none${thirdClusterAttr}];`);
      }
    } else {
      // Binary relationship: connect 2 entities
      const fromEntityId = `E_${rel.fromEntityId}`;
      const toEntityId = `E_${rel.toEntityId}`;
      const fromCluster = aggregationClusterByEntity.get(rel.fromEntityId);
      const toCluster = aggregationClusterByEntity.get(rel.toEntityId);
      
      // Edge from entity to relationship (with cardinality label and participation)
      const fromStyle = getEdgeStyle(rel.fromParticipation, rel.isWeak);
      const fromClusterAttr = fromCluster ? `, ltail=${fromCluster}` : "";
      lines.push(`  ${escapeId(fromEntityId)} -> ${escapeId(relId)} [label=${escapeLabel(rel.fromCardinality)}, ${fromStyle}, arrowhead=none${fromClusterAttr}];`);
      
      // Edge from relationship to entity (with cardinality label and participation)
      const toStyle = getEdgeStyle(rel.toParticipation, rel.isWeak);
      const toClusterAttr = toCluster ? `, lhead=${toCluster}` : "";
      lines.push(`  ${escapeId(relId)} -> ${escapeId(toEntityId)} [label=${escapeLabel(rel.toCardinality)}, ${toStyle}, arrowhead=none${toClusterAttr}];`);
    }
  }

  // Aggregation relationships: render inner relationships and dashed aggregation boxes
  for (const rel of model.relationships) {
    if (rel.relationshipType !== "aggregation") continue;

    const wholeEntityId = rel.aggregationWholeEntityId;
    const aggregationRels: AggregationRelationship[] = rel.aggregationRelationships || [];

    if (!wholeEntityId || aggregationRels.length === 0) {
      continue;
    }

    const wholeNodeId = `E_${wholeEntityId}`;
    // Cluster IDs must not contain characters that break DOT syntax (like "-")
    const clusterIdRaw = `cluster_agg_${String(rel.id)}`;
    const safeClusterId = clusterIdRaw.replace(/[^a-zA-Z0-9_]/g, "_");

    // Create inner relationship nodes and edges
    for (const aggr of aggregationRels) {
      if (!aggr.partEntityId) continue;

      const partNodeId = `E_${aggr.partEntityId}`;
      const innerNodeId = `R_${rel.id}_${aggr.id}`;
      const innerLabel = escapeLabel(aggr.name || "");

      // Diamond node for inner aggregation relationship
      lines.push(`  ${escapeId(innerNodeId)} [shape=diamond, label=${innerLabel}];`);

      // Determine which side gets the specified cardinality based on direction
      const defaultOne = "1..1" as const;
      const wholeCard =
        aggr.direction === "part_to_whole" ? aggr.cardinality : defaultOne;
      const partCard =
        aggr.direction === "whole_to_part" ? aggr.cardinality : defaultOne;

      // Edges within an aggregation:
      // - If the inner relationship is inside the dashed box, draw edges normally.
      // - If the inner relationship is outside, the whole entity is still inside the box
      //   (cluster always includes the whole), so attach the edge to the cluster border.
      const wholeToInnerClusterAttr = aggr.inAggregationBox ? "" : `, ltail=${safeClusterId}`;
      lines.push(
        `  ${escapeId(wholeNodeId)} -> ${escapeId(innerNodeId)} [label=${escapeLabel(
          wholeCard
        )}, style=solid, arrowhead=none${wholeToInnerClusterAttr}];`
      );

      // Edge from inner relationship to part entity
      lines.push(
        `  ${escapeId(innerNodeId)} -> ${escapeId(partNodeId)} [label=${escapeLabel(
          partCard
        )}, style=solid, arrowhead=none];`
      );

      // --- Attributes on inner aggregation relationships ---
      if (aggr.attributes && aggr.attributes.length > 0) {
        for (const attr of aggr.attributes) {
          const aNodeId = `A_${attr.id}`;
          const aLabel = getAttributeLabel(attr);
          const aShapeInfo = getAttributeShape(attr);
          const aShapeStr = aShapeInfo.peripheries
            ? `shape=${aShapeInfo.shape}, peripheries=${aShapeInfo.peripheries}`
            : `shape=${aShapeInfo.shape}`;
          lines.push(`  ${escapeId(aNodeId)} [${aShapeStr}, label=${aLabel}];`);

          // Connect attribute to the inner relationship diamond
          lines.push(`  ${escapeId(innerNodeId)} -> ${escapeId(aNodeId)} [style=solid, arrowhead=none];`);

          // Composite attributes on inner aggregation relationships
          if (attr.type === "composite" && attr.subAttributes && attr.subAttributes.length > 0) {
            for (const subAttr of attr.subAttributes) {
              const subNodeId = `A_${subAttr.id}`;
              const subLabel = getAttributeLabel(subAttr);
              const subShapeInfo = getAttributeShape(subAttr);
              const subShapeStr = subShapeInfo.peripheries
                ? `shape=${subShapeInfo.shape}, peripheries=${subShapeInfo.peripheries}`
                : `shape=${subShapeInfo.shape}`;
              lines.push(`  ${escapeId(subNodeId)} [${subShapeStr}, label=${subLabel}];`);
              lines.push(`  ${escapeId(aNodeId)} -> ${escapeId(subNodeId)} [style=solid, arrowhead=none];`);
            }
          }
        }
      }
    }

    // Build dashed aggregation box (cluster) around selected entities and relationships
    const clusterNodeIds = new Set<string>();

    // Always include the whole entity
    clusterNodeIds.add(wholeNodeId);

    for (const aggr of aggregationRels) {
      if (!aggr.inAggregationBox) continue;
      if (aggr.partEntityId) {
        clusterNodeIds.add(`E_${aggr.partEntityId}`);
      }
      clusterNodeIds.add(`R_${rel.id}_${aggr.id}`);
    }

    // If an entity is inside the dashed aggregation box, include its attributes too
    for (const nodeId of Array.from(clusterNodeIds)) {
      if (!nodeId.startsWith("E_")) continue;
      const entityId = nodeId.slice("E_".length);
      const entity = model.entities.find((e) => e.id === entityId);
      if (!entity) continue;
      for (const attrNodeId of collectAttributeNodeIds(entity.attributes)) {
        clusterNodeIds.add(attrNodeId);
      }
    }

    if (clusterNodeIds.size > 1) {
      lines.push("");
      lines.push(`  subgraph ${safeClusterId} {`);
      // No label at top of the aggregation box (remove "Relationship 1" heading)
      lines.push(`    style="dashed";`);
      lines.push(`    color="#6c757d";`);
      lines.push(`    penwidth=1.5;`);
      for (const nodeId of clusterNodeIds) {
        lines.push(`    ${escapeId(nodeId)};`);
      }
      lines.push("  }");
    }
  }

  lines.push("}");
  
  return lines.join("\n");
}
