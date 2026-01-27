import { useMemo, useState } from "react";
import "./er.css";

import type { Attribute, Cardinality, ERModel, Entity, Relationship, Selection, ValidationMessage, RenderPlan, ValidationOutput } from "./types";
import { createId } from "./id";
import { validateModel } from "./validation";
import { validateModelAPI, getRenderPlanAPI } from "./api";

import { EntityList } from "./components/EntityList";
import { RelationshipList } from "./components/RelationshipList";
import { EntityEditor } from "./components/EntityEditor";
import { RelationshipEditor } from "./components/RelationshipEditor";
import { JsonPreview } from "./components/JsonPreview";
import { ValidationPanel } from "./components/ValidationPanel";
import { ERDiagramSvg } from "./components/ERDiagramSvg";
import { GraphvizDiagram } from "./components/GraphvizDiagram";
import { DotPreview } from "./components/DotPreview";
import { erModelToDot } from "./graphviz";

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

  // Validation state
  const [hasValidated, setHasValidated] = useState(false);
  const [validationMessages, setValidationMessages] = useState<ValidationMessage[]>([]);
  const [backendValidation, setBackendValidation] = useState<ValidationOutput | null>(null);

  // Render plan state
  const [renderPlan, setRenderPlan] = useState<RenderPlan | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  // Graphviz state
  const [diagramMode, setDiagramMode] = useState<"chen" | "graphviz">("graphviz");
  const [dotText, setDotText] = useState<string | null>(null);

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

  const runValidation = async () => {
    try {
      setHasValidated(true);
      // Call backend validation API
      const backendResult = await validateModelAPI(model);
      setBackendValidation(backendResult);
      
      // Also run frontend validation for immediate feedback
      const frontendResult = validateModel(model);
      setValidationMessages(frontendResult.messages);
    } catch (error) {
      console.error("Validation API error:", error);
      // Fallback to frontend validation
      const frontendResult = validateModel(model);
      setValidationMessages(frontendResult.messages);
      setBackendValidation(null);
      alert(`Validation API error: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const generateDiagram = async () => {
    setIsGenerating(true);
    setGenerationError(null);
    setRenderPlan(null);
    setDotText(null);

    try {
      // First validate
      const validationResult = await validateModelAPI(model);
      setBackendValidation(validationResult);
      setHasValidated(true);

      // Check if there are errors
      if (validationResult.errors.length > 0) {
        setGenerationError("Model has validation errors. Fix them before generating a diagram.");
        setIsGenerating(false);
        return;
      }

      if (diagramMode === "chen") {
        // Get render plan for Chen SVG
        const plan = await getRenderPlanAPI(model);
        setRenderPlan(plan);
        setGenerationError(null);
      } else {
        // Generate DOT for Graphviz
        try {
          const dot = erModelToDot(model);
          setDotText(dot);
          setGenerationError(null);
        } catch (err) {
          setGenerationError(`Failed to generate DOT: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    } catch (error: any) {
      console.error("Render plan API error:", error);
      
      // If 400, backend returned validation output
      if (error.status === 400 && error.validation) {
        setBackendValidation(error.validation);
        setGenerationError("Model has validation errors. Fix them before generating a diagram.");
      } else {
        setGenerationError(`Failed to generate diagram: ${error instanceof Error ? error.message : String(error)}`);
      }
      setRenderPlan(null);
      setDotText(null);
    } finally {
      setIsGenerating(false);
    }
  };

  // Check if backend validation has errors
  const backendHasErrors = backendValidation ? backendValidation.errors.length > 0 : false;

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
            <button className="er-btn primary" type="button" onClick={runValidation} disabled={isGenerating}>
              Validate Model
            </button>
            <button
              className="er-btn"
              type="button"
              onClick={generateDiagram}
              disabled={hasErrors || backendHasErrors || isGenerating}
            >
              {isGenerating ? "Generating..." : "Generate Diagram"}
            </button>
          </div>
          
          {/* Diagram mode toggle */}
          <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: "0.875rem", color: "#6c757d" }}>Layout:</label>
            <button
              className={`er-btn ${diagramMode === "chen" ? "primary" : ""}`}
              type="button"
              onClick={() => setDiagramMode("chen")}
              style={{ fontSize: "0.875rem", padding: "4px 12px" }}
            >
              Chen (SVG)
            </button>
            <button
              className={`er-btn ${diagramMode === "graphviz" ? "primary" : ""}`}
              type="button"
              onClick={() => setDiagramMode("graphviz")}
              style={{ fontSize: "0.875rem", padding: "4px 12px" }}
            >
              Graphviz (Auto)
            </button>
          </div>
          
          <div className="er-muted" style={{ marginTop: 8 }}>
            {hasErrors || backendHasErrors
              ? "Fix validation errors before generating a diagram."
              : diagramMode === "chen"
              ? "Generate Diagram creates a visual Chen ER diagram with manual layout."
              : "Generate Diagram creates a visual ER diagram using Graphviz automatic layout."}
          </div>
          {generationError && (
            <div style={{ marginTop: 8, color: "#842029", fontSize: "0.9rem" }}>
              {generationError}
            </div>
          )}
        </div>

        {/* Validation Results */}
        <ValidationPanel
          messages={validationMessages}
          backendValidation={backendValidation || undefined}
          hasRun={hasValidated}
        />

        {/* Diagram Preview */}
        {diagramMode === "chen" ? (
          <ERDiagramSvg plan={renderPlan} model={model} />
        ) : (
          <>
            <GraphvizDiagram model={model} dotText={dotText} />
            {dotText && <DotPreview dotText={dotText} />}
          </>
        )}

        {/* JSON Preview (collapsible) */}
        <JsonPreview model={model} />
      </div>
    </div>
  );
}
