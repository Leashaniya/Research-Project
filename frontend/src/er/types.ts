export type Cardinality = "0..1" | "1..1" | "0..*" | "1..*";

export type AttributeType = "regular" | "composite" | "multivalued";

export type ParticipationType = "partial" | "total" | "none"; // none = no special constraint

export type RelationshipType = "binary" | "ternary" | "isa" | "aggregation";

export type AggregationDirection = "whole_to_part" | "part_to_whole";

export interface AggregationRelationship {
  id: string;
  name: string;
  partEntityId: string;
  cardinality: Cardinality;
  direction: AggregationDirection;
  inAggregationBox: boolean;
}

export interface Attribute {
  id: string;
  name: string;
  pk: boolean;
  unique: boolean;
  nullable: boolean;
  type: AttributeType; // regular, composite, or multivalued
  subAttributes?: Attribute[]; // For composite attributes only
}

export interface Entity {
  id: string;
  name: string;
  attributes: Attribute[];
  isWeak: boolean; // true if this is a weak entity
  strongEntityId?: string; // ID of the strong entity (required if isWeak is true)
}

export interface Relationship {
  id: string;
  name: string;
  relationshipType: RelationshipType; // binary, ternary, isa, or aggregation
  
  // Binary relationship fields (always present)
  fromEntityId: string; // entity A
  toEntityId: string; // entity B
  fromCardinality: Cardinality;
  toCardinality: Cardinality;
  fromParticipation: ParticipationType; // participation constraint for entity A
  toParticipation: ParticipationType; // participation constraint for entity B
  
  // Ternary relationship fields (only when relationshipType === "ternary")
  thirdEntityId?: string; // entity C
  thirdCardinality?: Cardinality;
  thirdParticipation?: ParticipationType;
  
  // ISA relationship fields (only when relationshipType === "isa")
  parentEntityId?: string; // parent entity (supertype)
  childEntityIds?: string[]; // child entities (subtypes)
  isDisjoint?: boolean; // true if ISA is disjoint (mutually exclusive subtypes)
  isTotal?: boolean; // true if ISA is total (all instances must belong to a subtype)
  
  // Aggregation relationship fields (only when relationshipType === "aggregation")
  // These are front-end only and are not sent to the backend validation/render APIs.
  aggregationWholeEntityId?: string; // whole entity (e.g., PROJECT)
  aggregationPartEntityIds?: string[]; // part entities (e.g., EMPLOYEE, MACHINERY)
  aggregationRelationships?: AggregationRelationship[]; // grouped relationships with cardinality, direction, and grouping flag 
  
  attributes: Attribute[];
  isWeak: boolean; // true if this is a weak relationship (connecting weak entity to strong entity) - always mandatory
}

export interface ERModel {
  entities: Entity[];
  relationships: Relationship[];
}

export type Selection =
  | { type: "entity"; id: string }
  | { type: "relationship"; id: string }
  | null;

export type ValidationSeverity = "error" | "warning" | "info";

export interface ValidationMessage {
  id: string;
  severity: ValidationSeverity;
  title: string;
  detail?: string;
}

// Render plan types (matching backend response)
export interface RenderNode {
  id: string;
  type: "entity" | "relationship";
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface RenderEdge {
  id: string;
  from: string;
  to: string;
  labelNearFrom: string;
  labelNearTo: string;
}

export interface AttributeNode {
  id: string;
  ownerId: string;
  label: string;
  x: number;
  y: number;
}

export interface RenderPlan {
  nodes: RenderNode[];
  edges: RenderEdge[];
  attributeNodes: AttributeNode[];
}

// Backend validation response
export interface ValidationIssue {
  code: string;
  message: string;
  path: string;
}

export interface ValidationOutput {
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  info: ValidationIssue[];
}

