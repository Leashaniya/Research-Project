export type Cardinality = "0..1" | "1..1" | "0..*" | "1..*";

export interface Attribute {
  id: string;
  name: string;
  pk: boolean;
  unique: boolean;
  nullable: boolean;
}

export interface Entity {
  id: string;
  name: string;
  attributes: Attribute[];
}

export interface Relationship {
  id: string;
  name: string;
  fromEntityId: string; // entity A
  toEntityId: string; // entity B
  fromCardinality: Cardinality;
  toCardinality: Cardinality;
  attributes: Attribute[];
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

