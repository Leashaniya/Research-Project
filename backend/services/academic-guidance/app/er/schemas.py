from __future__ import annotations

from typing import Literal, Optional, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from typing import Self

Cardinality = Literal["0..1", "1..1", "0..*", "1..*"]
AttributeType = Literal["regular", "composite", "multivalued"]
ParticipationType = Literal["partial", "total", "none"]
RelationshipType = Literal["binary", "ternary", "isa", "aggregation"]
AggregationDirection = Literal["whole_to_part", "part_to_whole"]


class Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    pk: bool
    unique: bool
    nullable: bool
    type: AttributeType = "regular"  # Default to regular for backward compatibility
    subAttributes: Optional[list["Attribute"]] = None  # For composite attributes only

    @model_validator(mode="after")
    def validate_subattributes(self) -> "Attribute":
        """Clear subAttributes if type is not composite."""
        if self.type != "composite" and self.subAttributes is not None:
            self.subAttributes = None
        return self


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    attributes: list[Attribute] = Field(default_factory=list)
    isWeak: bool = False  # True if this is a weak entity
    strongEntityId: Optional[str] = None  # ID of the strong entity (required if isWeak is True)


class AggregationRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    partEntityId: str
    cardinality: Cardinality
    direction: AggregationDirection
    inAggregationBox: bool = True
    # Optional attributes that belong specifically to this inner aggregation
    # relationship (e.g., WORKS_FOR has its own attributes separate from the
    # aggregation container).
    attributes: list[Attribute] = Field(default_factory=list)


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    relationshipType: RelationshipType = "binary"  # binary, ternary, or isa
    
    # Binary relationship fields (always present)
    fromEntityId: str
    toEntityId: str
    fromCardinality: Cardinality
    toCardinality: Cardinality
    fromParticipation: ParticipationType = "none"  # Participation constraint for entity A
    toParticipation: ParticipationType = "none"  # Participation constraint for entity B
    
    # Ternary relationship fields (only when relationshipType === "ternary")
    thirdEntityId: Optional[str] = None
    thirdCardinality: Optional[Cardinality] = None
    thirdParticipation: Optional[ParticipationType] = None
    
    # ISA relationship fields (only when relationshipType === "isa")
    parentEntityId: Optional[str] = None
    childEntityIds: Optional[list[str]] = None
    isDisjoint: Optional[bool] = None
    isTotal: Optional[bool] = None

    # Aggregation relationship fields (only when relationshipType === "aggregation")
    # These fields describe an aggregation group where a whole entity connects to multiple part entities
    # through one or more inner relationships.
    aggregationWholeEntityId: Optional[str] = None
    aggregationPartEntityIds: Optional[list[str]] = None
    aggregationRelationships: Optional[list[AggregationRelationship]] = None
    
    attributes: list[Attribute] = Field(default_factory=list)
    isWeak: bool = False  # True if this is a weak relationship (connecting weak entity to strong entity) - always mandatory


class ERModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: str


class ValidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    errors: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    info: list[Issue] = Field(default_factory=list)


class RenderNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["entity", "relationship"]
    label: str
    x: float
    y: float
    w: float
    h: float


class RenderEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    from_: str = Field(validation_alias="from", serialization_alias="from")
    to: str
    labelNearFrom: str
    labelNearTo: str


class AttributeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ownerId: str
    label: str
    x: float
    y: float


class RenderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[RenderNode] = Field(default_factory=list)
    edges: list[RenderEdge] = Field(default_factory=list)
    attributeNodes: list[AttributeNode] = Field(default_factory=list)


# Rebuild models to resolve forward references (needed for recursive Attribute type)
Attribute.model_rebuild()

