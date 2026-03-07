import { createId } from "./id";
import type { ERModel, ValidationMessage, Cardinality, Attribute } from "./types";

const STAR: Cardinality[] = ["0..*", "1..*"];

function isMany(card: Cardinality): boolean {
  return STAR.includes(card);
}

function countPk(attrs: Attribute[]): number {
  return attrs.reduce((acc, a) => acc + (a.pk ? 1 : 0), 0);
}

export function validateModel(model: ERModel): { messages: ValidationMessage[]; hasErrors: boolean } {
  const messages: ValidationMessage[] = [];

  const entityIdSet = new Set(model.entities.map((e) => e.id));

  // Entity validation
  for (const e of model.entities) {
    if (!e.name.trim()) {
      messages.push({
        id: createId("val"),
        severity: "error",
        title: "Entity name is required",
        detail: "One of your entities has an empty name. Give each entity a meaningful name."
      });
    }

    if (e.attributes.length === 0) {
      messages.push({
        id: createId("val"),
        severity: "warning",
        title: `Entity "${e.name || "(unnamed)"}" has no attributes`,
        detail: "Entities usually have at least one attribute (e.g., an identifier)."
      });
    }

    const pkCount = countPk(e.attributes);
    if (pkCount !== 1) {
      messages.push({
        id: createId("val"),
        severity: "warning",
        title: `Entity "${e.name || "(unnamed)"}" should have exactly 1 PK attribute`,
        detail: pkCount === 0
          ? "No PK selected. Typically one attribute is the primary key."
          : `Multiple PKs selected (${pkCount}). Typically only one attribute is the primary key.`
      });
    }
  }

  // Relationship validation
  for (const r of model.relationships) {
    if (!r.name.trim()) {
      messages.push({
        id: createId("val"),
        severity: "error",
        title: "Relationship name is required",
        detail: "Each relationship needs a name (this will be shown inside the Chen diamond)."
      });
    }

    // Aggregation relationships: validate aggregation-specific fields and skip generic from/to checks
    if (r.relationshipType === "aggregation") {
      if (!r.aggregationWholeEntityId) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `Aggregation "${r.name || "(unnamed)"}" must specify a whole entity`,
          detail: "Choose the whole entity for the aggregation (e.g., PROJECT)."
        });
      } else if (!entityIdSet.has(r.aggregationWholeEntityId)) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `Aggregation "${r.name || "(unnamed)"}" whole entity not found`,
          detail: "The chosen whole entity does not exist in the current model."
        });
      }

      const partIds = r.aggregationPartEntityIds || [];
      if (partIds.length === 0) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `Aggregation "${r.name || "(unnamed)"}" must have at least one part entity`,
          detail: "Add one or more part entities (e.g., EMPLOYEE, MACHINERY)."
        });
      } else {
        partIds.forEach((pid) => {
          if (!pid) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `Aggregation "${r.name || "(unnamed)"}" has an empty part entity`,
              detail: "Each part entity entry must select a valid entity."
            });
          } else if (!entityIdSet.has(pid)) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `Aggregation "${r.name || "(unnamed)"}" part entity not found`,
              detail: "One of the part entities does not exist in the current model."
            });
          } else if (r.aggregationWholeEntityId && pid === r.aggregationWholeEntityId) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `Aggregation "${r.name || "(unnamed)"}" part entity equals whole entity`,
              detail: "The whole entity and part entities must be different."
            });
          }
        });
      }

      const inner = r.aggregationRelationships || [];
      if (inner.length === 0) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `Aggregation "${r.name || "(unnamed)"}" must define at least one inner relationship`,
          detail: "Add relationships like WORKS_FOR or REQUIRE between the whole and part entities."
        });
      } else {
        inner.forEach((ar) => {
          if (!ar.name.trim()) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: "Inner aggregation relationship name is required",
              detail: "Give each inner aggregation relationship a meaningful name (e.g., WORKS_FOR)."
            });
          }
          if (!ar.partEntityId) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `Aggregation "${r.name || "(unnamed)"}" inner relationship is missing a part entity`,
              detail: "Select which part entity this inner relationship connects to."
            });
          } else if (!entityIdSet.has(ar.partEntityId)) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `Aggregation "${r.name || "(unnamed)"}" inner relationship part entity not found`,
              detail: "The selected part entity for an inner relationship does not exist in the model."
            });
          }
        });
      }

      // Skip generic binary checks for aggregation containers
      continue;
    }

    // ISA relationships: use parentEntityId + childEntityIds instead of from/to IDs
    if (r.relationshipType === "isa") {
      if (!r.parentEntityId) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `ISA relationship "${r.name || "(unnamed)"}" must have a parent entity`,
          detail: "Select the parent (supertype) entity for this ISA hierarchy."
        });
      } else if (!entityIdSet.has(r.parentEntityId)) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `ISA relationship "${r.name || "(unnamed)"}" parent entity not found`,
          detail: "The selected parent entity does not exist in the current model."
        });
      }

      const childIds = r.childEntityIds || [];
      if (childIds.length === 0) {
        messages.push({
          id: createId("val"),
          severity: "error",
          title: `ISA relationship "${r.name || "(unnamed)"}" must have at least one child entity`,
          detail: "Add one or more child (subtype) entities to this ISA relationship."
        });
      } else {
        childIds.forEach((cid) => {
          if (!cid) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `ISA relationship "${r.name || "(unnamed)"}" has an empty child entity`,
              detail: "Each child entry must select a valid entity."
            });
          } else if (!entityIdSet.has(cid)) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `ISA relationship "${r.name || "(unnamed)"}" child entity not found`,
              detail: "One of the child entities does not exist in the current model."
            });
          } else if (cid === r.parentEntityId) {
            messages.push({
              id: createId("val"),
              severity: "error",
              title: `ISA relationship "${r.name || "(unnamed)"}" child equals parent`,
              detail: "A child (subtype) entity cannot be the same as the parent (supertype)."
            });
          }
        });

        if (new Set(childIds).size < childIds.length) {
          messages.push({
            id: createId("val"),
            severity: "warning",
            title: `ISA relationship "${r.name || "(unnamed)"}" has duplicate children`,
            detail: "The same child entity appears more than once in this ISA relationship."
          });
        }
      }

      // Skip generic binary from/to checks for ISA; they use parent/children instead.
      continue;
    }

    // Generic binary / ternary validation
    if (!r.fromEntityId || !r.toEntityId) {
      messages.push({
        id: createId("val"),
        severity: "error",
        title: `Relationship "${r.name || "(unnamed)"}" must connect two entities`,
        detail: "Select both Entity A and Entity B."
      });
    }

    if (r.fromEntityId && r.toEntityId && r.fromEntityId === r.toEntityId) {
      messages.push({
        id: createId("val"),
        severity: "warning",
        title: `Relationship "${r.name || "(unnamed)"}" connects an entity to itself`,
        detail: "Self-relationships are allowed, but double-check this is intended."
      });
    }

    if (r.attributes.length > 0 && isMany(r.fromCardinality) && isMany(r.toCardinality)) {
      messages.push({
        id: createId("val"),
        severity: "info",
        title: `M:N relationship "${r.name || "(unnamed)"}" has attributes`,
        detail:
          "This is an M:N relationship with attributes; consider an associative entity (optional suggestion)."
      });
    }
  }

  const hasErrors = messages.some((m) => m.severity === "error");
  return { messages, hasErrors };
}

