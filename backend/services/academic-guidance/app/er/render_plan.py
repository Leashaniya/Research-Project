from __future__ import annotations
import math
from collections import defaultdict

from app.er.schemas import AttributeNode, ERModel, RenderEdge, RenderNode, RenderPlan


def build_render_plan(model: ERModel) -> RenderPlan:
    """
    Build a simple Chen-diagram render plan (no image generation).

    Layout:
    - Entities laid out in a grid of 3 columns (row-major)
    - Relationship diamonds placed with vector-based positioning and lane offsets
    - Entity attributes placed LEFT/ABOVE/RIGHT based on column
    - Relationship attributes always BELOW
    - Edge anchors used instead of center-to-center connections
    - All coordinates shifted to prevent negative values
    """
    x_step = 600.0  # Increased spacing to accommodate attributes
    y_step = 450.0  # Increased vertical spacing
    entity_w = 180.0
    entity_h = 120.0
    rel_w = 120.0
    rel_h = 80.0
    
    # Attribute placement constants (treat x/y as OVAL CENTER)
    attr_ry = 20.0  # Vertical radius of attribute oval
    attr_rx = 50.0  # Horizontal radius of attribute oval
    attr_oval_height = 40.0  # Height of attribute oval (2 * attr_ry)
    attr_gap = 12.0  # Gap between attribute ovals
    attr_step = attr_oval_height + attr_gap  # Step between attribute centers
    attr_offset_side = 50.0  # Offset for left/right placement
    attr_offset_above = 30.0  # Offset above entity top
    attr_offset_below = 30.0  # Offset below relationship bottom
    min_rel_gap = 40.0  # Minimum gap between relationship diamond and entity
    lane_offset = 60.0  # Vertical offset per lane for relationship diamonds
    padding = 50.0  # Padding to prevent clipping

    plan = RenderPlan()

    # First pass: calculate entity positions
    entity_pos: dict[str, tuple[float, float, int]] = {}  # (x, y, col)
    entity_col_map: dict[str, int] = {}
    
    for i, e in enumerate(model.entities):
        col = i % 3
        row = i // 3
        x = col * x_step
        y = row * y_step
        entity_pos[e.id] = (x, y, col)
        entity_col_map[e.id] = col
        plan.nodes.append(
            RenderNode(
                id=f"E:{e.id}",
                type="entity",
                label=e.name,
                x=x,
                y=y,
                w=entity_w,
                h=entity_h,
            )
        )

    # Track relationship lanes per entity (for multiple relationships from same entity)
    entity_lane_counters: dict[str, int] = defaultdict(int)

    # Relationships: place diamonds with vector-based positioning and lane offsets
    edge_counter = 1

    def _place_relationship_node(rel_id: str, label: str, from_entity_id: str, to_entity_id: str, from_card: str, to_card: str) -> None:
        nonlocal edge_counter

        from_xy = entity_pos.get(from_entity_id)
        to_xy = entity_pos.get(to_entity_id)

        # Calculate entity centers
        if from_xy is None:
            from_cx, from_cy = (0.0 + entity_w / 2.0), (0.0 + entity_h / 2.0)
        else:
            from_cx, from_cy = (from_xy[0] + entity_w / 2.0), (from_xy[1] + entity_h / 2.0)

        if to_xy is None:
            to_cx, to_cy = (0.0 + entity_w / 2.0), (0.0 + entity_h / 2.0)
        else:
            to_cx, to_cy = (to_xy[0] + entity_w / 2.0), (to_xy[1] + entity_h / 2.0)

        # Get lane index for this relationship (use from-entity's lane counter)
        lane_index = entity_lane_counters[from_entity_id]
        entity_lane_counters[from_entity_id] += 1

        # Vector-based positioning: compute unit vector from from-entity to to-entity
        dx = to_cx - from_cx
        dy = to_cy - from_cy
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            unit_x = dx / distance
            unit_y = dy / distance
        else:
            # Fallback if entities are at same position
            unit_x = 1.0
            unit_y = 0.0

        # Place diamond center along the direction with margin
        margin = (entity_w / 2.0) + (rel_w / 2.0) + min_rel_gap
        rel_center_x = from_cx + unit_x * margin
        rel_center_y = from_cy + unit_y * margin

        # Add lane offset (perpendicular to the connection direction)
        perp_x = -unit_y
        perp_y = unit_x
        rel_center_x += perp_x * (lane_index * lane_offset)
        rel_center_y += perp_y * (lane_index * lane_offset)

        # If diamond would be too close to to-entity, adjust
        to_dist = math.sqrt((to_cx - rel_center_x) ** 2 + (to_cy - rel_center_y) ** 2)
        if to_dist < margin:
            # Place diamond closer to midpoint but maintain margin
            mid_cx = (from_cx + to_cx) / 2.0
            mid_cy = (from_cy + to_cy) / 2.0
            # Use perpendicular direction if entities are too close
            if distance < margin * 2:
                rel_center_x = mid_cx + perp_x * (margin + lane_index * lane_offset)
                rel_center_y = mid_cy + perp_y * (margin + lane_index * lane_offset)
            else:
                rel_center_x = mid_cx + perp_x * (lane_index * lane_offset)
                rel_center_y = mid_cy + perp_y * (lane_index * lane_offset)

        rx = rel_center_x - rel_w / 2.0
        ry = rel_center_y - rel_h / 2.0

        plan.nodes.append(
            RenderNode(
                id=rel_id,
                type="relationship",
                label=label,
                x=rx,
                y=ry,
                w=rel_w,
                h=rel_h,
            )
        )

        # Two edges per relationship, cardinality label near entity end
        plan.edges.append(
            RenderEdge(
                id=f"edge-{edge_counter}",
                **{
                    "from": f"E:{from_entity_id}",
                    "to": rel_id,
                },
                labelNearFrom=from_card,
                labelNearTo="",
            )
        )
        edge_counter += 1

        plan.edges.append(
            RenderEdge(
                id=f"edge-{edge_counter}",
                **{
                    "from": f"E:{to_entity_id}",
                    "to": rel_id,
                },
                labelNearFrom=to_card,
                labelNearTo="",
            )
        )
        edge_counter += 1

    for r in model.relationships:
        # Aggregation relationships: create one diamond per inner aggregation relationship (whole ↔ part)
        if r.relationshipType == "aggregation":
            whole_id = r.aggregationWholeEntityId
            inner_rels = r.aggregationRelationships or []
            if not whole_id or not inner_rels:
                continue

            for inner in inner_rels:
                if not inner.partEntityId:
                    continue

                # Determine cardinalities based on direction
                # Whole side gets the specified cardinality when direction is part_to_whole, and vice versa.
                default_one = "1..1"
                if inner.direction == "part_to_whole":
                    from_card = inner.cardinality
                    to_card = default_one
                    from_entity_id = inner.partEntityId
                    to_entity_id = whole_id
                else:
                    from_card = default_one
                    to_card = inner.cardinality
                    from_entity_id = whole_id
                    to_entity_id = inner.partEntityId

                rel_node_id = f"R:{r.id}:{inner.id}"
                _place_relationship_node(
                    rel_id=rel_node_id,
                    label=inner.name or "",
                    from_entity_id=from_entity_id,
                    to_entity_id=to_entity_id,
                    from_card=from_card,
                    to_card=to_card,
                )
            continue

        # Regular (binary / ternary / ISA treated as binary here) relationship node
        _place_relationship_node(
            rel_id=f"R:{r.id}",
            label=r.name,
            from_entity_id=r.fromEntityId,
            to_entity_id=r.toEntityId,
            from_card=r.fromCardinality,
            to_card=r.toCardinality,
        )

    # Second pass: place attributes (treat x/y as OVAL CENTER)
    # Entity attributes: placement based on column
    for e in model.entities:
        entity_node = next((n for n in plan.nodes if n.id == f"E:{e.id}"), None)
        if not entity_node:
            continue
        
        col = entity_col_map.get(e.id, 1)  # Default to middle column
        owner_center_x = entity_node.x + entity_node.w / 2.0
        owner_center_y = entity_node.y + entity_node.h / 2.0
        owner_top_y = entity_node.y
        owner_bottom_y = entity_node.y + entity_node.h
        owner_left_x = entity_node.x
        owner_right_x = entity_node.x + entity_node.w
        
        # Place attributes based on column
        for ai, a in enumerate(e.attributes):
            if col == 0:
                # Column 0: attributes to the LEFT (vertical stack)
                attr_x = owner_left_x - attr_offset_side
                attr_y = owner_top_y + attr_ry + (ai * attr_step)
            elif col == 2:
                # Column 2: attributes to the RIGHT (vertical stack)
                attr_x = owner_right_x + attr_offset_side
                attr_y = owner_top_y + attr_ry + (ai * attr_step)
            else:
                # Column 1: attributes ABOVE (vertical stack)
                attr_x = owner_center_x
                attr_y = owner_top_y - attr_offset_above - attr_ry - (ai * attr_step)
            
            plan.attributeNodes.append(
                AttributeNode(
                    id=f"A:{a.id}",
                    ownerId=f"E:{e.id}",
                    label=a.name,
                    x=attr_x,  # Oval center X
                    y=attr_y,  # Oval center Y
                )
            )

    # Relationship attributes: always BELOW relationship diamond
    for r in model.relationships:
        rel_node = next((n for n in plan.nodes if n.id == f"R:{r.id}"), None)
        if not rel_node:
            continue
        
        owner_center_x = rel_node.x + rel_node.w / 2.0
        owner_bottom_y = rel_node.y + rel_node.h
        
        # Place attributes below, stacked vertically, center-aligned
        for ai, a in enumerate(r.attributes):
            attr_y = owner_bottom_y + attr_offset_below + attr_ry + (ai * attr_step)
            plan.attributeNodes.append(
                AttributeNode(
                    id=f"A:{a.id}",
                    ownerId=f"R:{r.id}",
                    label=a.name,
                    x=owner_center_x,  # Center-aligned to owner
                    y=attr_y,  # Oval center Y
                )
            )

    # Third pass: shift all coordinates to prevent negative values
    # Compute minimum coordinates considering radii
    min_x = float('inf')
    min_y = float('inf')
    
    # Check nodes
    for node in plan.nodes:
        min_x = min(min_x, node.x)
        min_y = min(min_y, node.y)
    
    # Check attribute nodes (account for oval radius)
    for attr in plan.attributeNodes:
        min_x = min(min_x, attr.x - attr_rx)
        min_y = min(min_y, attr.y - attr_ry)
    
    # Calculate shift needed
    dx = 0.0
    dy = 0.0
    
    if min_x < padding:
        dx = padding - min_x
    if min_y < padding:
        dy = padding - min_y
    
    # Apply shift to all nodes
    if dx != 0.0 or dy != 0.0:
        for node in plan.nodes:
            node.x += dx
            node.y += dy
        
        for attr in plan.attributeNodes:
            attr.x += dx
            attr.y += dy

    return plan
