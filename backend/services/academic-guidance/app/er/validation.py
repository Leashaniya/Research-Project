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

        # Validate weak entity
        if entity.isWeak:
            if not entity.strongEntityId:
                _add_issue(
                    out.errors,
                    code="WEAK_ENTITY_NO_STRONG_ENTITY",
                    message=f"Weak entity '{entity.name.strip()}' must have a strongEntityId specified.",
                    path=f"entities[{ei}].strongEntityId",
                )
            elif entity.strongEntityId not in entity_id_set:
                _add_issue(
                    out.errors,
                    code="WEAK_ENTITY_INVALID_STRONG_ENTITY",
                    message=f"Weak entity '{entity.name.strip()}' references non-existent strong entity ID '{entity.strongEntityId}'.",
                    path=f"entities[{ei}].strongEntityId",
                )
            elif entity.strongEntityId == entity.id:
                _add_issue(
                    out.errors,
                    code="WEAK_ENTITY_SELF_REFERENCE",
                    message=f"Weak entity '{entity.name.strip()}' cannot reference itself as the strong entity.",
                    path=f"entities[{ei}].strongEntityId",
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
            
            # Validate composite attributes
            if attr.type == "composite":
                if not attr.subAttributes or len(attr.subAttributes) == 0:
                    _add_issue(
                        out.warnings,
                        code="COMPOSITE_NO_SUBATTRIBUTES",
                        message=f"Composite attribute '{attr.name.strip()}' has no sub-attributes.",
                        path=attr_name_path,
                    )
                else:
                    # Validate sub-attributes
                    sub_attr_name_first_index: dict[str, int] = {}
                    for sai, sub_attr in enumerate(attr.subAttributes):
                        sub_attr_name_path = f"{attr_name_path}.subAttributes[{sai}].name"
                        canon_sub_attr_name = _canon_name(sub_attr.name)
                        if not canon_sub_attr_name:
                            _add_issue(
                                out.errors,
                                code="SUBATTRIBUTE_NAME_EMPTY",
                                message="Sub-attribute name must be non-empty.",
                                path=sub_attr_name_path,
                            )
                            continue
                        
                        prev_sub = sub_attr_name_first_index.get(canon_sub_attr_name)
                        if prev_sub is None:
                            sub_attr_name_first_index[canon_sub_attr_name] = sai
                        else:
                            _add_issue(
                                out.errors,
                                code="SUBATTRIBUTE_NAME_DUPLICATE",
                                message=f"Sub-attribute name '{sub_attr.name.strip()}' duplicates sub-attribute at {attr_name_path}.subAttributes[{prev_sub}].name (case-insensitive).",
                                path=sub_attr_name_path,
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

        # Special handling for aggregation relationships – validate whole/parts and inner relationships,
        # then skip generic from/to validations.
        if rel.relationshipType == "aggregation":
            # Whole entity must exist
            if not rel.aggregationWholeEntityId:
                _add_issue(
                    out.errors,
                    code="AGGREGATION_MISSING_WHOLE_ENTITY",
                    message="Aggregation relationship must specify a whole entity.",
                    path=f"relationships[{ri}].aggregationWholeEntityId",
                )
            elif rel.aggregationWholeEntityId not in entity_id_set:
                _add_issue(
                    out.errors,
                    code="AGGREGATION_WHOLE_ENTITY_NOT_FOUND",
                    message=f"aggregationWholeEntityId '{rel.aggregationWholeEntityId}' does not refer to an existing entity.",
                    path=f"relationships[{ri}].aggregationWholeEntityId",
                )

            # Part entities – must exist and be different from whole
            part_ids = rel.aggregationPartEntityIds or []
            if len(part_ids) == 0:
                _add_issue(
                    out.errors,
                    code="AGGREGATION_NO_PART_ENTITIES",
                    message="Aggregation relationship must have at least one part entity.",
                    path=f"relationships[{ri}].aggregationPartEntityIds",
                )
            else:
                for pi, part_id in enumerate(part_ids):
                    if not part_id:
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_PART_ENTITY_EMPTY",
                            message=f"Part entity at index {pi} is empty.",
                            path=f"relationships[{ri}].aggregationPartEntityIds[{pi}]",
                        )
                    elif part_id not in entity_id_set:
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_PART_ENTITY_NOT_FOUND",
                            message=f"Part entity ID '{part_id}' does not refer to an existing entity.",
                            path=f"relationships[{ri}].aggregationPartEntityIds[{pi}]",
                        )
                    elif rel.aggregationWholeEntityId and part_id == rel.aggregationWholeEntityId:
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_PART_SAME_AS_WHOLE",
                            message="Part entity cannot be the same as the whole entity.",
                            path=f"relationships[{ri}].aggregationPartEntityIds[{pi}]",
                        )

                # Warn on duplicate part entities
                if len(set(part_ids)) < len(part_ids):
                    _add_issue(
                        out.warnings,
                        code="AGGREGATION_DUPLICATE_PART_ENTITIES",
                        message="Aggregation relationship has duplicate part entities.",
                        path=f"relationships[{ri}].aggregationPartEntityIds",
                    )

            # Inner aggregation relationships
            inner_rels = rel.aggregationRelationships or []
            if len(inner_rels) == 0:
                _add_issue(
                    out.errors,
                    code="AGGREGATION_NO_RELATIONSHIPS",
                    message="Aggregation relationship must define at least one inner relationship.",
                    path=f"relationships[{ri}].aggregationRelationships",
                )
            else:
                for ai, agg_rel in enumerate(inner_rels):
                    inner_path = f"relationships[{ri}].aggregationRelationships[{ai}]"
                    if not _canon_name(agg_rel.name):
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_RELATIONSHIP_NAME_EMPTY",
                            message="Inner aggregation relationship name must be non-empty.",
                            path=f"{inner_path}.name",
                        )
                    if not agg_rel.partEntityId:
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_RELATIONSHIP_PART_EMPTY",
                            message="Inner aggregation relationship must specify a part entity.",
                            path=f"{inner_path}.partEntityId",
                        )
                    elif agg_rel.partEntityId not in entity_id_set:
                        _add_issue(
                            out.errors,
                            code="AGGREGATION_RELATIONSHIP_PART_NOT_FOUND",
                            message=f"Inner aggregation relationship partEntityId '{agg_rel.partEntityId}' does not refer to an existing entity.",
                            path=f"{inner_path}.partEntityId",
                        )
                    elif part_ids and agg_rel.partEntityId not in part_ids:
                        _add_issue(
                            out.warnings,
                            code="AGGREGATION_RELATIONSHIP_PART_NOT_IN_LIST",
                            message="Inner aggregation relationship refers to a part entity that is not in aggregationPartEntityIds.",
                            path=f"{inner_path}.partEntityId",
                        )

            # Skip the rest of the generic relationship validation for aggregation containers.
            continue

        # For ISA relationships we don't require from/to entity IDs; they use
        # parentEntityId/childEntityIds instead. Skip generic from/to checks
        # in that case to avoid false "entity not found" errors.
        if rel.relationshipType != "isa" and rel.fromEntityId not in entity_id_set:
            _add_issue(
                out.errors,
                code="RELATIONSHIP_FROM_ENTITY_NOT_FOUND",
                message=f"fromEntityId '{rel.fromEntityId}' does not refer to an existing entity.",
                path=f"relationships[{ri}].fromEntityId",
            )

        if rel.relationshipType != "isa" and rel.toEntityId not in entity_id_set:
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

        # Validate ternary relationships
        if rel.relationshipType == "ternary":
            if not rel.thirdEntityId:
                _add_issue(
                    out.errors,
                    code="TERNARY_MISSING_THIRD_ENTITY",
                    message="Ternary relationship must have a third entity specified.",
                    path=f"relationships[{ri}].thirdEntityId",
                )
            elif rel.thirdEntityId not in entity_id_set:
                _add_issue(
                    out.errors,
                    code="TERNARY_THIRD_ENTITY_NOT_FOUND",
                    message=f"thirdEntityId '{rel.thirdEntityId}' does not refer to an existing entity.",
                    path=f"relationships[{ri}].thirdEntityId",
                )
            # Check for duplicate entities in ternary
            entity_ids = [rel.fromEntityId, rel.toEntityId, rel.thirdEntityId]
            if len(set(entity_ids)) < 3:
                _add_issue(
                    out.errors,
                    code="TERNARY_DUPLICATE_ENTITIES",
                    message="Ternary relationship must connect three different entities.",
                    path=f"relationships[{ri}]",
                )

        # Validate ISA relationships
        if rel.relationshipType == "isa":
            if not rel.parentEntityId:
                _add_issue(
                    out.errors,
                    code="ISA_MISSING_PARENT",
                    message="ISA relationship must have a parent entity specified.",
                    path=f"relationships[{ri}].parentEntityId",
                )
            elif rel.parentEntityId not in entity_id_set:
                _add_issue(
                    out.errors,
                    code="ISA_PARENT_NOT_FOUND",
                    message=f"parentEntityId '{rel.parentEntityId}' does not refer to an existing entity.",
                    path=f"relationships[{ri}].parentEntityId",
                )
            
            if not rel.childEntityIds or len(rel.childEntityIds) == 0:
                _add_issue(
                    out.errors,
                    code="ISA_NO_CHILDREN",
                    message="ISA relationship must have at least one child entity.",
                    path=f"relationships[{ri}].childEntityIds",
                )
            else:
                # Validate child entities
                for ci, childId in enumerate(rel.childEntityIds):
                    if not childId:
                        _add_issue(
                            out.errors,
                            code="ISA_CHILD_EMPTY",
                            message=f"Child entity at index {ci} is empty.",
                            path=f"relationships[{ri}].childEntityIds[{ci}]",
                        )
                    elif childId not in entity_id_set:
                        _add_issue(
                            out.errors,
                            code="ISA_CHILD_NOT_FOUND",
                            message=f"Child entity ID '{childId}' does not refer to an existing entity.",
                            path=f"relationships[{ri}].childEntityIds[{ci}]",
                        )
                    elif childId == rel.parentEntityId:
                        _add_issue(
                            out.errors,
                            code="ISA_CHILD_SAME_AS_PARENT",
                            message="Child entity cannot be the same as parent entity.",
                            path=f"relationships[{ri}].childEntityIds[{ci}]",
                        )
                
                # Check for duplicate child entities
                if len(set(rel.childEntityIds)) < len(rel.childEntityIds):
                    _add_issue(
                        out.warnings,
                        code="ISA_DUPLICATE_CHILDREN",
                        message="ISA relationship has duplicate child entities.",
                        path=f"relationships[{ri}].childEntityIds",
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
            
            # Validate composite attributes for relationships
            if attr.type == "composite":
                if not attr.subAttributes or len(attr.subAttributes) == 0:
                    _add_issue(
                        out.warnings,
                        code="COMPOSITE_NO_SUBATTRIBUTES",
                        message=f"Composite attribute '{attr.name.strip()}' has no sub-attributes.",
                        path=attr_name_path,
                    )
                else:
                    # Validate sub-attributes
                    sub_attr_name_first_index: dict[str, int] = {}
                    for sai, sub_attr in enumerate(attr.subAttributes):
                        sub_attr_name_path = f"{attr_name_path}.subAttributes[{sai}].name"
                        canon_sub_attr_name = _canon_name(sub_attr.name)
                        if not canon_sub_attr_name:
                            _add_issue(
                                out.errors,
                                code="SUBATTRIBUTE_NAME_EMPTY",
                                message="Sub-attribute name must be non-empty.",
                                path=sub_attr_name_path,
                            )
                            continue
                        
                        prev_sub = sub_attr_name_first_index.get(canon_sub_attr_name)
                        if prev_sub is None:
                            sub_attr_name_first_index[canon_sub_attr_name] = sai
                        else:
                            _add_issue(
                                out.errors,
                                code="SUBATTRIBUTE_NAME_DUPLICATE",
                                message=f"Sub-attribute name '{sub_attr.name.strip()}' duplicates sub-attribute at {attr_name_path}.subAttributes[{prev_sub}].name (case-insensitive).",
                                path=sub_attr_name_path,
                            )

        # Validate weak relationship (only for binary relationships)
        if rel.isWeak and rel.relationshipType == "binary":
            from_entity = next((e for e in model.entities if e.id == rel.fromEntityId), None)
            to_entity = next((e for e in model.entities if e.id == rel.toEntityId), None)
            
            # Check if weak relationship connects a weak entity to its strong entity
            if from_entity and to_entity:
                from_is_weak = from_entity.isWeak and from_entity.strongEntityId == to_entity.id
                to_is_weak = to_entity.isWeak and to_entity.strongEntityId == from_entity.id
                
                if not (from_is_weak or to_is_weak):
                    _add_issue(
                        out.warnings,
                        code="WEAK_RELATIONSHIP_NOT_CONNECTING_WEAK_TO_STRONG",
                        message=f"Weak relationship '{rel.name.strip()}' should connect a weak entity to its strong entity.",
                        path=f"relationships[{ri}].isWeak",
                    )
        
        # Warn if isWeak is set for non-binary relationships
        if rel.isWeak and rel.relationshipType != "binary":
            _add_issue(
                out.warnings,
                code="WEAK_RELATIONSHIP_NON_BINARY",
                message="Weak relationships are only supported for binary relationships.",
                path=f"relationships[{ri}].isWeak",
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

