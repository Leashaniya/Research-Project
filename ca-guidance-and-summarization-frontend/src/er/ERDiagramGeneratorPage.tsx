import { useMemo, useState } from "react";
import "./er.css";

import type { Attribute, Cardinality, ERModel, Entity, Relationship, Selection, ValidationMessage } from "./types";
import { createId } from "./id";
import { validateModel } from "./validation";

import { EntityList } from "./components/EntityList";
import { RelationshipList } from "./components/RelationshipList";
import { EntityEditor } from "./components/EntityEditor";
import { RelationshipEditor } from "./components/RelationshipEditor";
import { JsonPreview } from "./components/JsonPreview";
import { ValidationPanel } from "./components/ValidationPanel";

const DEFAULT_CARD: Cardinality = "0..*";

function newAttribute(): Attribute {
  return { id: createId("attr"), name: "", pk: false, unique: false, nullable: true };
}

function newEntity(nextIndex: number): Entity {
  return { id: createId("ent"), name: `Entity ${nextIndex}`, attributes: [newAttribute()] };
}

function newRelationship(nextIndex: number): Relationship {
  return {
    id: createId("rel"),
    name: `Relationship ${nextIndex}`,
    fromEntityId: "",
    toEntityId: "",
    fromCardinality: DEFAULT_CARD,
    toCardinality: DEFAULT_CARD,
    attributes: []
  };
}

export default function ERDiagramGeneratorPage() {
  // Canonical model state (must match the required interface exactly)
  const [model, setModel] = useState<ERModel>({ entities: [], relationships: [] });
  const [selection, setSelection] = useState<Selection>(null);

  // Validation state (only populated after user clicks Validate Model)
  const [hasValidated, setHasValidated] = useState(false);
  const [validationMessages, setValidationMessages] = useState<ValidationMessage[]>([]);

  const selectedEntity = useMemo(() => {
    if (selection?.type !== "entity") return null;
    return model.entities.find((e) => e.id === selection.id) || null;
  }, [model.entities, selection]);

  const selectedRelationship = useMemo(() => {
    if (selection?.type !== "relationship") return null;
    return model.relationships.find((r) => r.id === selection.id) || null;
  }, [model.relationships, selection]);

  const { hasErrors } = useMemo(() => {
    const res = validateModel(model);
    return { hasErrors: res.hasErrors };
  }, [model]);

  const addEntity = () => {
    const nextIndex = model.entities.length + 1;
    const e = newEntity(nextIndex);
    setModel({ ...model, entities: [...model.entities, e] });
    setSelection({ type: "entity", id: e.id });
  };

  const deleteEntity = (id: string) => {
    const e = model.entities.find((x) => x.id === id);
    const name = e?.name || "(unnamed entity)";
    if (!window.confirm(`Delete entity "${name}"? This will not delete relationships, but they may become invalid.`)) {
      return;
    }

    const nextEntities = model.entities.filter((x) => x.id !== id);
    const nextModel: ERModel = { ...model, entities: nextEntities };
    setModel(nextModel);

    if (selection?.type === "entity" && selection.id === id) setSelection(null);
  };

  const addRelationship = () => {
    const nextIndex = model.relationships.length + 1;
    const r = newRelationship(nextIndex);
    setModel({ ...model, relationships: [...model.relationships, r] });
    setSelection({ type: "relationship", id: r.id });
  };

  const deleteRelationship = (id: string) => {
    const r = model.relationships.find((x) => x.id === id);
    const name = r?.name || "(unnamed relationship)";
    if (!window.confirm(`Delete relationship "${name}"?`)) return;

    const nextRels = model.relationships.filter((x) => x.id !== id);
    setModel({ ...model, relationships: nextRels });
    if (selection?.type === "relationship" && selection.id === id) setSelection(null);
  };

  const updateEntity = (next: Entity) => {
    setModel({
      ...model,
      entities: model.entities.map((e) => (e.id === next.id ? next : e))
    });
  };

  const updateRelationship = (next: Relationship) => {
    setModel({
      ...model,
      relationships: model.relationships.map((r) => (r.id === next.id ? next : r))
    });
  };

  const runValidation = () => {
    const res = validateModel(model);
    setHasValidated(true);
    setValidationMessages(res.messages);
  };

  const generateDiagram = () => {
    // Placeholder only (no backend, no rendering yet)
    alert("Diagram generation will be added next (Figma MCP)");
  };

  return (
    <div className="er-page">
      {/* LEFT PANEL */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <EntityList
          entities={model.entities}
          selectedEntityId={selection?.type === "entity" ? selection.id : null}
          onSelect={(id) => setSelection({ type: "entity", id })}
          onAdd={addEntity}
          onDelete={deleteEntity}
        />

        <RelationshipList
          relationships={model.relationships}
          entities={model.entities}
          selectedRelationshipId={selection?.type === "relationship" ? selection.id : null}
          onSelect={(id) => setSelection({ type: "relationship", id })}
          onAdd={addRelationship}
          onDelete={deleteRelationship}
        />
      </div>

      {/* MIDDLE PANEL (Editor) */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {selectedEntity ? (
          <EntityEditor entity={selectedEntity} onChange={updateEntity} />
        ) : selectedRelationship ? (
          <RelationshipEditor relationship={selectedRelationship} entities={model.entities} onChange={updateRelationship} />
        ) : (
          <div className="er-panel">
            <h3 className="er-section-title">Editor</h3>
            <div className="er-muted">Select an entity or relationship to edit.</div>
          </div>
        )}
      </div>

      {/* RIGHT PANEL */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="er-panel">
          <h3 className="er-section-title">Actions</h3>
          <div className="er-actions">
            <button className="er-btn primary" type="button" onClick={runValidation}>
              Validate Model
            </button>
            <button className="er-btn" type="button" onClick={generateDiagram} disabled={hasErrors}>
              Generate Diagram
            </button>
          </div>
          <div className="er-muted" style={{ marginTop: 8 }}>
            Generate Diagram is disabled until there are no errors (warnings are allowed).
          </div>
        </div>

        <JsonPreview model={model} />
        <ValidationPanel messages={validationMessages} hasRun={hasValidated} />
      </div>
    </div>
  );
}

