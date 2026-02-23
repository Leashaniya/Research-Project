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

