from __future__ import annotations

from app.er.schemas import AttributeNode, ERModel, RenderEdge, RenderNode, RenderPlan


def build_render_plan(model: ERModel) -> RenderPlan:
    """
    Build a simple Chen-diagram render plan (no image generation).

    Layout (MVP):
    - Entities laid out in a grid of 3 columns (row-major)
    - Relationship diamonds placed at midpoint between their two entities (by center)
    - Two edges per relationship: E(from)->R and E(to)->R with cardinality near entity
    """
    x_step = 360.0
    y_step = 260.0
    entity_w = 240.0
    entity_h = 160.0
    rel_w = 140.0
    rel_h = 100.0

    plan = RenderPlan()

    # Entity positions (top-left)
    entity_pos: dict[str, tuple[float, float]] = {}
    for i, e in enumerate(model.entities):
        col = i % 3
        row = i // 3
        x = col * x_step
        y = row * y_step
        entity_pos[e.id] = (x, y)
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

        # Entity attribute nodes: stacked to the right
        base_ax = x + entity_w + 40.0
        base_ay = y + 20.0
        for ai, a in enumerate(e.attributes):
            plan.attributeNodes.append(
                AttributeNode(
                    id=f"A:{a.id}",
                    ownerId=f"E:{e.id}",
                    label=a.name,
                    x=base_ax,
                    y=base_ay + ai * 22.0,
                )
            )

    # Relationships
    edge_counter = 1
    for r in model.relationships:
        from_xy = entity_pos.get(r.fromEntityId)
        to_xy = entity_pos.get(r.toEntityId)

        # Midpoint between entity centers (fallback to origin if missing)
        if from_xy is None:
            from_cx, from_cy = (0.0 + entity_w / 2.0), (0.0 + entity_h / 2.0)
        else:
            from_cx, from_cy = (from_xy[0] + entity_w / 2.0), (from_xy[1] + entity_h / 2.0)

        if to_xy is None:
            to_cx, to_cy = (0.0 + entity_w / 2.0), (0.0 + entity_h / 2.0)
        else:
            to_cx, to_cy = (to_xy[0] + entity_w / 2.0), (to_xy[1] + entity_h / 2.0)

        mid_cx = (from_cx + to_cx) / 2.0
        mid_cy = (from_cy + to_cy) / 2.0
        rx = mid_cx - rel_w / 2.0
        ry = mid_cy - rel_h / 2.0

        plan.nodes.append(
            RenderNode(
                id=f"R:{r.id}",
                type="relationship",
                label=r.name,
                x=rx,
                y=ry,
                w=rel_w,
                h=rel_h,
            )
        )

        # Relationship attribute nodes: stacked to the right of the diamond
        base_ax = rx + rel_w + 40.0
        base_ay = ry + 10.0
        for ai, a in enumerate(r.attributes):
            plan.attributeNodes.append(
                AttributeNode(
                    id=f"A:{a.id}",
                    ownerId=f"R:{r.id}",
                    label=a.name,
                    x=base_ax,
                    y=base_ay + ai * 22.0,
                )
            )

        # Two edges per relationship, cardinality label near entity end
        plan.edges.append(
            RenderEdge(
                id=f"edge-{edge_counter}",
                **{
                    "from": f"E:{r.fromEntityId}",
                    "to": f"R:{r.id}",
                },
                labelNearFrom=r.fromCardinality,
                labelNearTo="",
            )
        )
        edge_counter += 1

        plan.edges.append(
            RenderEdge(
                id=f"edge-{edge_counter}",
                **{
                    "from": f"E:{r.toEntityId}",
                    "to": f"R:{r.id}",
                },
                labelNearFrom=r.toCardinality,
                labelNearTo="",
            )
        )
        edge_counter += 1

    return plan

