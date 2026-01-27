from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Cardinality = Literal["0..1", "1..1", "0..*", "1..*"]


class Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    pk: bool
    unique: bool
    nullable: bool


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    attributes: list[Attribute] = Field(default_factory=list)


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    fromEntityId: str
    toEntityId: str
    fromCardinality: Cardinality
    toCardinality: Cardinality
    attributes: list[Attribute] = Field(default_factory=list)


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

