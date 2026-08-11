import { useMemo } from "react";
import type { AttributeNode, ERModel, RenderEdge, RenderNode, RenderPlan } from "../types";

interface AttributeAnchorInfo {
  ownerAnchorX: number;
  ownerAnchorY: number;
  attrEdgeX: number;
  attrEdgeY: number;
}

interface Props {
  plan: RenderPlan | null;
  model: ERModel | null;
}

/**
 * SVG renderer for Chen ER diagram notation.
 * 
 * Chen notation:
 * - Entity = rectangle
 * - Relationship = diamond (polygon with 4 points)
 * - Attribute = oval (ellipse)
 * - Connection = solid straight line
 */
export function ERDiagramSvg({ plan, model }: Props) {
  const { viewBox, svgWidth, svgHeight } = useMemo(() => {
    if (!plan || plan.nodes.length === 0) {
      return { viewBox: "0 0 800 600", svgWidth: 800, svgHeight: 600 };
    }

    // Calculate bounding box from all nodes and attribute nodes
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    // Check nodes (entities and relationships)
    for (const node of plan.nodes) {
      minX = Math.min(minX, node.x);
      minY = Math.min(minY, node.y);
      maxX = Math.max(maxX, node.x + node.w);
      maxY = Math.max(maxY, node.y + node.h);
    }

    // Check attribute nodes (they're positioned as centers, so add radius)
    const attrRadiusX = 50;
    const attrRadiusY = 20;
    for (const attr of plan.attributeNodes) {
      minX = Math.min(minX, attr.x - attrRadiusX);
      minY = Math.min(minY, attr.y - attrRadiusY);
      maxX = Math.max(maxX, attr.x + attrRadiusX);
      maxY = Math.max(maxY, attr.y + attrRadiusY);
    }

    // Add generous padding to prevent clipping (especially important for attributes above owners)
    const padding = 100;  // Increased padding for attributes above owners
    const width = Math.max(800, maxX - minX + padding * 2);
    const height = Math.max(600, maxY - minY + padding * 2);
    const offsetX = Math.min(0, minX - padding);
    const offsetY = Math.min(0, minY - padding);

    return {
      viewBox: `${offsetX} ${offsetY} ${width} ${height}`,
      svgWidth: width,
      svgHeight: height,
    };
  }, [plan]);

  // Scale factor for entity rectangles (make them smaller)
  const entityScale = 0.7; // Reduce entity size by 30%

  // Compute anchor info map for all attributes (moved to top level for React hooks)
  const anchorInfoMap = useMemo(() => {
    if (!plan || plan.nodes.length === 0) {
      return new Map<string, AttributeAnchorInfo>();
    }

    // Helper functions (defined inline since they depend on plan)
    const getNodeCenter = (node: RenderNode): [number, number] => {
      if (node.type === "entity") {
        const scaledW = node.w * entityScale;
        const scaledH = node.h * entityScale;
        return [node.x + scaledW / 2, node.y + scaledH / 2];
      }
      return [node.x + node.w / 2, node.y + node.h / 2];
    };

    const getAttributeOwner = (ownerId: string): RenderNode | undefined => {
      return plan.nodes.find((n) => n.id === ownerId);
    };

    // Group attributes by owner and edge side to assign anchor offsets
    const attrGroups: Map<string, AttributeNode[]> = new Map();
    
    plan.attributeNodes.forEach((attrNode) => {
      const owner = getAttributeOwner(attrNode.ownerId);
      if (!owner) return;
      
      const [ownerCenterX, ownerCenterY] = getNodeCenter(owner);
      const attrToOwnerDx = attrNode.x - ownerCenterX;
      const attrToOwnerDy = attrNode.y - ownerCenterY;
      const absDx = Math.abs(attrToOwnerDx);
      const absDy = Math.abs(attrToOwnerDy);
      
      let side: string;
      if (owner.type === "entity") {
        if (absDx > absDy) {
          side = attrToOwnerDx > 0 ? "right" : "left";
        } else {
          side = "top";
        }
      } else {
        side = "bottom";
      }
      
      const key = `${attrNode.ownerId}:${side}`;
      if (!attrGroups.has(key)) {
        attrGroups.set(key, []);
      }
      attrGroups.get(key)!.push(attrNode);
    });
    
    // Compute anchor info for each attribute
    const infoMap = new Map<string, AttributeAnchorInfo>();
    
    plan.attributeNodes.forEach((attrNode) => {
      const owner = getAttributeOwner(attrNode.ownerId);
      if (!owner) return;

      const attrRadiusX = 50;
      const attrRadiusY = 20;
      const anchorSeparation = 12;
      
      const [ownerCenterX, ownerCenterY] = getNodeCenter(owner);
      const attrToOwnerDx = attrNode.x - ownerCenterX;
      const attrToOwnerDy = attrNode.y - ownerCenterY;
      const absDx = Math.abs(attrToOwnerDx);
      const absDy = Math.abs(attrToOwnerDy);
      
      let side: string;
      if (owner.type === "entity") {
        if (absDx > absDy) {
          side = attrToOwnerDx > 0 ? "right" : "left";
        } else {
          side = "top";
        }
      } else {
        side = "bottom";
      }
      
      const key = `${attrNode.ownerId}:${side}`;
      const group = attrGroups.get(key) || [];
      const attrIndexInGroup = group.findIndex(a => a.id === attrNode.id);
      
      let ownerAnchorX: number;
      let ownerAnchorY: number;
      let attrEdgeX: number;
      let attrEdgeY: number;
      
      if (owner.type === "entity") {
        const scaledW = owner.w * entityScale;
        const scaledH = owner.h * entityScale;
        
        if (absDx > absDy) {
          // Horizontal placement (left or right) - vertical offset
          const offsetSign = attrIndexInGroup % 2 === 0 ? 1 : -1;
          const offsetCount = Math.floor(attrIndexInGroup / 2);
          const verticalOffset = (offsetCount * anchorSeparation + (attrIndexInGroup > 0 ? anchorSeparation / 2 : 0)) * offsetSign;
          
          if (attrToOwnerDx > 0) {
            ownerAnchorX = owner.x + scaledW;
            ownerAnchorY = owner.y + scaledH / 2.0 + verticalOffset;
            attrEdgeX = attrNode.x - attrRadiusX;
            attrEdgeY = attrNode.y;
          } else {
            ownerAnchorX = owner.x;
            ownerAnchorY = owner.y + scaledH / 2.0 + verticalOffset;
            attrEdgeX = attrNode.x + attrRadiusX;
            attrEdgeY = attrNode.y;
          }
        } else {
          // Vertical placement (above) - horizontal offset
          const offsetSign = attrIndexInGroup % 2 === 0 ? 1 : -1;
          const offsetCount = Math.floor(attrIndexInGroup / 2);
          const horizontalOffset = (offsetCount * anchorSeparation + (attrIndexInGroup > 0 ? anchorSeparation / 2 : 0)) * offsetSign;
          
          ownerAnchorX = owner.x + scaledW / 2.0 + horizontalOffset;
          ownerAnchorY = owner.y;
          attrEdgeX = attrNode.x;
          attrEdgeY = attrNode.y + attrRadiusY;
        }
      } else {
        // Relationship: attributes BELOW - horizontal offset
        const offsetSign = attrIndexInGroup % 2 === 0 ? 1 : -1;
        const offsetCount = Math.floor(attrIndexInGroup / 2);
        const horizontalOffset = (offsetCount * anchorSeparation + (attrIndexInGroup > 0 ? anchorSeparation / 2 : 0)) * offsetSign;
        
        ownerAnchorX = owner.x + owner.w / 2.0 + horizontalOffset;
        ownerAnchorY = owner.y + owner.h;
        attrEdgeX = attrNode.x;
        attrEdgeY = attrNode.y - attrRadiusY;
      }
      
      infoMap.set(attrNode.id, {
        ownerAnchorX,
        ownerAnchorY,
        attrEdgeX,
        attrEdgeY,
      });
    });
    
    return infoMap;
  }, [plan, entityScale]);

  if (!plan || plan.nodes.length === 0) {
    return (
      <div className="er-panel">
        <h3 className="er-section-title">Diagram Preview</h3>
        <div className="er-muted" style={{ padding: "40px", textAlign: "center" }}>
          No diagram data available. Generate a diagram to see the preview.
        </div>
      </div>
    );
  }

  // Helper to get node center coordinates
  const getNodeCenter = (node: RenderNode): [number, number] => {
    if (node.type === "entity") {
      // Scale entity centers
      const scaledW = node.w * entityScale;
      const scaledH = node.h * entityScale;
      return [node.x + scaledW / 2, node.y + scaledH / 2];
    }
    return [node.x + node.w / 2, node.y + node.h / 2];
  };

  // Helper to get edge anchor point on a node based on target direction
  const getEdgeAnchor = (node: RenderNode, targetX: number, targetY: number): [number, number] => {
    const [centerX, centerY] = getNodeCenter(node);
    const dx = targetX - centerX;
    const dy = targetY - centerY;
    
    if (node.type === "entity") {
      const scaledW = node.w * entityScale;
      const scaledH = node.h * entityScale;
      
      // Determine which edge to use based on direction
      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);
      
      if (absDx > absDy) {
        // Horizontal direction
        if (dx > 0) {
          // Target is to the right
          return [node.x + scaledW, node.y + scaledH / 2];
        } else {
          // Target is to the left
          return [node.x, node.y + scaledH / 2];
        }
      } else {
        // Vertical direction
        if (dy > 0) {
          // Target is below
          return [node.x + scaledW / 2, node.y + scaledH];
        } else {
          // Target is above
          return [node.x + scaledW / 2, node.y];
        }
      }
    } else {
      // Relationship diamond
      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);
      
      if (absDx > absDy) {
        // Horizontal direction
        if (dx > 0) {
          // Target is to the right
          return [node.x + node.w, node.y + node.h / 2];
        } else {
          // Target is to the left
          return [node.x, node.y + node.h / 2];
        }
      } else {
        // Vertical direction
        if (dy > 0) {
          // Target is below
          return [node.x + node.w / 2, node.y + node.h];
        } else {
          // Target is above
          return [node.x + node.w / 2, node.y];
        }
      }
    }
  };

  // Helper to get node by ID
  const getNodeById = (id: string): RenderNode | undefined => {
    return plan.nodes.find((n) => n.id === id);
  };

  // Helper to get attribute owner (entity or relationship node)
  const getAttributeOwner = (ownerId: string): RenderNode | undefined => {
    return plan.nodes.find((n) => n.id === ownerId);
  };

  // Helper to check if an attribute is a PK by matching its ID with the model
  const isAttributePK = (attrId: string): boolean => {
    if (!model) return false;
    
    // Extract attribute ID from render plan ID (format: "A:<attrId>")
    const actualAttrId = attrId.startsWith("A:") ? attrId.slice(2) : attrId;
    
    // Check in entity attributes
    for (const entity of model.entities) {
      const attr = entity.attributes.find((a) => a.id === actualAttrId);
      if (attr) return attr.pk;
    }
    
    // Check in relationship attributes
    for (const rel of model.relationships) {
      const attr = rel.attributes.find((a) => a.id === actualAttrId);
      if (attr) return attr.pk;
    }
    
    return false;
  };

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Diagram Preview</h3>
      <div style={{ overflow: "auto", border: "1px solid #dee2e6", borderRadius: 8, backgroundColor: "#fff" }}>
        <svg
          width="100%"
          height="100%"
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          style={{ display: "block", minHeight: "400px" }}
        >
          {/* Render edges first (so they appear behind nodes) */}
          {plan.edges.map((edge) => {
            const fromNode = getNodeById(edge.from);
            const toNode = getNodeById(edge.to);

            if (!fromNode || !toNode) return null;

            // Use edge anchors instead of centers
            const [toCenterX, toCenterY] = getNodeCenter(toNode);
            const [fromX, fromY] = getEdgeAnchor(fromNode, toCenterX, toCenterY);
            
            const [fromCenterX, fromCenterY] = getNodeCenter(fromNode);
            const [toX, toY] = getEdgeAnchor(toNode, fromCenterX, fromCenterY);

            // Calculate unit vector along the edge
            const dx = toX - fromX;
            const dy = toY - fromY;
            const len = Math.sqrt(dx * dx + dy * dy);
            
            if (len === 0) return null; // Avoid division by zero
            
            const unitX = dx / len;
            const unitY = dy / len;

            // Position cardinality label near entity end (20px from anchor)
            const labelOffset = 20;
            const labelX = fromX + unitX * labelOffset;
            const labelY = fromY + unitY * labelOffset;

            // Add perpendicular offset based on edge direction to avoid overlap
            // If edge is mostly horizontal, move label UP; if vertical, move LEFT
            const absDx = Math.abs(dx);
            const absDy = Math.abs(dy);
            const perpOffset = 14; // Offset distance
            
            let perpX: number;
            let perpY: number;
            
            if (absDx > absDy) {
              // Mostly horizontal edge → move label UP
              perpX = 0;
              perpY = -perpOffset;
            } else {
              // Mostly vertical edge → move label LEFT
              perpX = -perpOffset;
              perpY = 0;
            }

            return (
              <g key={edge.id}>
                {/* Edge line - SOLID (no dash) */}
                <line
                  x1={fromX}
                  y1={fromY}
                  x2={toX}
                  y2={toY}
                  stroke="#495057"
                  strokeWidth={2}
                />
                {/* Cardinality label near entity (from) end */}
                {edge.labelNearFrom && (
                  <text
                    x={labelX + perpX}
                    y={labelY + perpY}
                    fontSize={13}
                    fill="#212529"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontWeight: 700 }}
                  >
                    {edge.labelNearFrom}
                  </text>
                )}
                {/* Cardinality label near relationship (to) end if present */}
                {edge.labelNearTo && (
                  <text
                    x={toX - unitX * labelOffset + perpX}
                    y={toY - unitY * labelOffset + perpY}
                    fontSize={13}
                    fill="#212529"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontWeight: 700 }}
                  >
                    {edge.labelNearTo}
                  </text>
                )}
              </g>
            );
          })}

          {/* Render nodes (entities and relationships) */}
          {plan.nodes.map((node) => {
            if (node.type === "entity") {
              // Entity = rectangle (scaled down)
              const scaledW = node.w * entityScale;
              const scaledH = node.h * entityScale;
              
              return (
                <g key={node.id}>
                  <rect
                    x={node.x}
                    y={node.y}
                    width={scaledW}
                    height={scaledH}
                    fill="#fff"
                    stroke="#495057"
                    strokeWidth={2}
                    rx={4}
                  />
                  {/* Entity label (centered near top) */}
                  <text
                    x={node.x + scaledW / 2}
                    y={node.y + 20}
                    fontSize={14}
                    fill="#212529"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontWeight: 700 }}
                  >
                    {node.label}
                  </text>
                </g>
              );
            } else {
              // Relationship = diamond (polygon with 4 points)
              const centerX = node.x + node.w / 2;
              const centerY = node.y + node.h / 2;
              const halfW = node.w / 2;
              const halfH = node.h / 2;

              // Diamond points: top, right, bottom, left
              const points = [
                [centerX, node.y], // top
                [node.x + node.w, centerY], // right
                [centerX, node.y + node.h], // bottom
                [node.x, centerY], // left
              ]
                .map(([x, y]) => `${x},${y}`)
                .join(" ");

              return (
                <g key={node.id}>
                  <polygon
                    points={points}
                    fill="#fff"
                    stroke="#495057"
                    strokeWidth={2}
                  />
                  {/* Relationship label (centered inside diamond) */}
                  <text
                    x={centerX}
                    y={centerY}
                    fontSize={12}
                    fill="#212529"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontWeight: 600 }}
                  >
                    {node.label}
                  </text>
                </g>
              );
            }
          })}

          {/* Render attribute nodes (ovals) and their connection lines */}
          {plan.attributeNodes.map((attrNode) => {
            const owner = getAttributeOwner(attrNode.ownerId);
            if (!owner) return null;

            const anchorInfo = anchorInfoMap.get(attrNode.id);
            if (!anchorInfo) return null;
            
            const attrRadiusX = 50;
            const attrRadiusY = 20;
            const isPK = isAttributePK(attrNode.id);

            return (
              <g key={attrNode.id}>
                {/* Connection line from attribute to owner anchor - SOLID */}
                <line
                  x1={anchorInfo.attrEdgeX}
                  y1={anchorInfo.attrEdgeY}
                  x2={anchorInfo.ownerAnchorX}
                  y2={anchorInfo.ownerAnchorY}
                  stroke="#495057"
                  strokeWidth={1.5}
                />
                {/* Attribute oval */}
                <ellipse
                  cx={attrNode.x}
                  cy={attrNode.y}
                  rx={attrRadiusX}
                  ry={attrRadiusY}
                  fill="#fff"
                  stroke="#495057"
                  strokeWidth={1.5}
                />
                {/* Attribute label */}
                <text
                  x={attrNode.x}
                  y={attrNode.y}
                  fontSize={11}
                  fill="#212529"
                  textAnchor="middle"
                  dominantBaseline="middle"
                  style={{ fontWeight: isPK ? 700 : 400 }}
                >
                  {attrNode.label}
                </text>
                {/* Underline for PK attributes */}
                {isPK && (
                  <line
                    x1={attrNode.x - attrRadiusX + 5}
                    y1={attrNode.y + 8}
                    x2={attrNode.x + attrRadiusX - 5}
                    y2={attrNode.y + 8}
                    stroke="#212529"
                    strokeWidth={1.5}
                  />
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
