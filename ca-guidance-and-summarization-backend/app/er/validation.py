from __future__ import annotations

from app.er.schemas import ERModel, Issue, ValidationOutput


def _canon_name(value: str) -> str:
    return (value or "").strip().lower()


def _add_issue(target: list[Issue], code: str, message: str, path: str) -> None:
    target.append(Issue(code=code, message=message, path=path))


def validate_er_model(model: ERModel) -> ValidationOutput:
    """
    Validate an ERModel and return structured feedback.

    Notes:
    - This function does not mutate the model.
    - Name uniqueness is case-insensitive and trim-insensitive (canonical: lower(trim(name))).
    """
    out = ValidationOutput()

    entity_id_set = {e.id for e in model.entities}

    # ---- Entities ----
    entity_name_first_index: dict[str, int] = {}
    for ei, entity in enumerate(model.entities):
        entity_name_path = f"entities[{ei}].name"
        canon_entity_name = _canon_name(entity.name)
        if not canon_entity_name:
            _add_issue(
                out.errors,
                code="ENTITY_NAME_EMPTY",
                message="Entity name must be non-empty.",
                path=entity_name_path,
            )
        else:
            prev = entity_name_first_index.get(canon_entity_name)
            if prev is None:
                entity_name_first_index[canon_entity_name] = ei
            else:
                _add_issue(
                    out.errors,
                    code="ENTITY_NAME_DUPLICATE",
                    message=f"Entity name '{entity.name.strip()}' duplicates entity at entities[{prev}].name (case-insensitive).",
                    path=entity_name_path,
                )

        if len(entity.attributes) == 0:
            _add_issue(
                out.warnings,
                code="ENTITY_NO_ATTRIBUTES",
                message="Entity has 0 attributes.",
                path=f"entities[{ei}].attributes",
            )

        pk_count = sum(1 for a in entity.attributes if a.pk)
        if pk_count == 0:
            _add_issue(
                out.warnings,
                code="ENTITY_NO_PK",
                message="Entity has 0 primary key attributes.",
                path=f"entities[{ei}].attributes",
            )
        elif pk_count > 1:
            _add_issue(
                out.warnings,
                code="ENTITY_MULTIPLE_PK",
                message=f"Entity has {pk_count} primary key attributes (expected 1).",
                path=f"entities[{ei}].attributes",
            )

        # Attribute names: non-empty + unique within entity (case-insensitive)
        attr_name_first_index: dict[str, int] = {}
        for ai, attr in enumerate(entity.attributes):
            attr_name_path = f"entities[{ei}].attributes[{ai}].name"
            canon_attr_name = _canon_name(attr.name)
            if not canon_attr_name:
                _add_issue(
                    out.errors,
                    code="ATTRIBUTE_NAME_EMPTY",
                    message="Attribute name must be non-empty.",
                    path=attr_name_path,
                )
                continue

            prev = attr_name_first_index.get(canon_attr_name)
            if prev is None:
                attr_name_first_index[canon_attr_name] = ai
            else:
                _add_issue(
                    out.errors,
                    code="ATTRIBUTE_NAME_DUPLICATE",
                    message=f"Attribute name '{attr.name.strip()}' duplicates attribute at entities[{ei}].attributes[{prev}].name (case-insensitive).",
                    path=attr_name_path,
                )

    # ---- Relationships ----
    many_values = {"0..*", "1..*"}
    for ri, rel in enumerate(model.relationships):
        rel_name_path = f"relationships[{ri}].name"
        canon_rel_name = _canon_name(rel.name)
        if not canon_rel_name:
            _add_issue(
                out.errors,
                code="RELATIONSHIP_NAME_EMPTY",
                message="Relationship name must be non-empty.",
                path=rel_name_path,
            )

        if rel.fromEntityId not in entity_id_set:
            _add_issue(
                out.errors,
                code="RELATIONSHIP_FROM_ENTITY_NOT_FOUND",
                message=f"fromEntityId '{rel.fromEntityId}' does not refer to an existing entity.",
                path=f"relationships[{ri}].fromEntityId",
            )

        if rel.toEntityId not in entity_id_set:
            _add_issue(
                out.errors,
                code="RELATIONSHIP_TO_ENTITY_NOT_FOUND",
                message=f"toEntityId '{rel.toEntityId}' does not refer to an existing entity.",
                path=f"relationships[{ri}].toEntityId",
            )

        if rel.fromEntityId == rel.toEntityId and rel.fromEntityId:
            _add_issue(
                out.warnings,
                code="RELATIONSHIP_SELF",
                message="Relationship connects an entity to itself (self-relationship).",
                path=f"relationships[{ri}]",
            )

        # Relationship attribute names: non-empty + unique within relationship (case-insensitive)
        rel_attr_name_first_index: dict[str, int] = {}
        for ai, attr in enumerate(rel.attributes):
            attr_name_path = f"relationships[{ri}].attributes[{ai}].name"
            canon_attr_name = _canon_name(attr.name)
            if not canon_attr_name:
                _add_issue(
                    out.errors,
                    code="RELATIONSHIP_ATTRIBUTE_NAME_EMPTY",
                    message="Relationship attribute name must be non-empty.",
                    path=attr_name_path,
                )
                continue

            prev = rel_attr_name_first_index.get(canon_attr_name)
            if prev is None:
                rel_attr_name_first_index[canon_attr_name] = ai
            else:
                _add_issue(
                    out.errors,
                    code="RELATIONSHIP_ATTRIBUTE_NAME_DUPLICATE",
                    message=f"Relationship attribute name '{attr.name.strip()}' duplicates attribute at relationships[{ri}].attributes[{prev}].name (case-insensitive).",
                    path=attr_name_path,
                )

        is_many_to_many = rel.fromCardinality in many_values and rel.toCardinality in many_values
        if is_many_to_many and len(rel.attributes) > 0:
            _add_issue(
                out.info,
                code="RELATIONSHIP_MN_WITH_ATTRIBUTES",
                message="M:N relationship has attributes; consider modeling it as an associative entity.",
                path=f"relationships[{ri}].attributes",
            )

    return out

