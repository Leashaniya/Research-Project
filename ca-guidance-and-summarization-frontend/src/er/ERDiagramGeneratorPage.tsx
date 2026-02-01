import { useMemo, useState } from "react";
import "./er.css";

import type { Attribute, Cardinality, ERModel, Entity, Relationship, Selection, ValidationMessage, ValidationOutput } from "./types";
import { createId } from "./id";
import { validateModel } from "./validation";
import { validateModelAPI } from "./api";

import { EntityList } from "./components/EntityList";
import { RelationshipList } from "./components/RelationshipList";
import { EntityEditor } from "./components/EntityEditor";
import { RelationshipEditor } from "./components/RelationshipEditor";
import { ValidationPanel } from "./components/ValidationPanel";
import { GraphvizDiagram } from "./components/GraphvizDiagram";
import { erModelToDot } from "./graphviz";
import { downloadSvgStringAsPng } from "./pngExport";

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

  // Diagram generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  // Graphviz state
  const [dotText, setDotText] = useState<string | null>(null);
  const [currentSvg, setCurrentSvg] = useState<string | null>(null);

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

  const generateDiagram = async (): Promise<string> => {
    setIsGenerating(true);
    setGenerationError(null);
    setDotText(null);
    setCurrentSvg(null);

    try {
      // First validate
      const validationResult = await validateModelAPI(model);
      setBackendValidation(validationResult);
      setHasValidated(true);

      // Check if there are errors
      if (validationResult.errors.length > 0) {
        const errorMsg = "Model has validation errors. Fix them before generating a diagram.";
        setGenerationError(errorMsg);
        setIsGenerating(false);
        throw new Error(errorMsg);
      }

      // Generate DOT for Graphviz
      let dot: string;
      try {
        dot = erModelToDot(model);
        setDotText(dot);
        setGenerationError(null);
      } catch (err) {
        const errorMsg = `Failed to generate DOT: ${err instanceof Error ? err.message : String(err)}`;
        setGenerationError(errorMsg);
        setIsGenerating(false);
        throw new Error(errorMsg);
      }

      // Render DOT to SVG using Graphviz
      const { Graphviz } = await import("@hpcc-js/wasm");
      const graphviz = await Graphviz.load();
      const svg = graphviz.dot(dot);
      
      // Update state for preview
      setCurrentSvg(svg);
      setIsGenerating(false);
      
      return svg;
    } catch (error: any) {
      console.error("Validation error:", error);
      
      // If 400, backend returned validation output
      if (error.status === 400 && error.validation) {
        setBackendValidation(error.validation);
        const errorMsg = "Model has validation errors. Fix them before generating a diagram.";
        setGenerationError(errorMsg);
        setIsGenerating(false);
        throw new Error(errorMsg);
      } else if (error.message) {
        // Already handled error with message
        throw error;
      } else {
        const errorMsg = `Failed to generate diagram: ${error instanceof Error ? error.message : String(error)}`;
        setGenerationError(errorMsg);
        setDotText(null);
        setCurrentSvg(null);
        setIsGenerating(false);
        throw new Error(errorMsg);
      }
    }
  };

  // Check if backend validation has errors
  const backendHasErrors = backendValidation ? backendValidation.errors.length > 0 : false;

  // Download PNG handler
  const handleDownloadPng = async () => {
    // Check validation errors
    if (hasErrors || backendHasErrors) {
      alert("Please fix validation errors before downloading the diagram.");
      return;
    }

    try {
      // Use current SVG if available, otherwise generate diagram
      const svg = currentSvg ?? await generateDiagram();
      await downloadSvgStringAsPng(svg, "er-diagram.png");
    } catch (error) {
      console.error("PNG download error:", error);
      alert(`Failed to download PNG: ${error instanceof Error ? error.message : String(error)}`);
    }
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
            <button
              className="er-btn"
              type="button"
              onClick={handleDownloadPng}
              disabled={hasErrors || backendHasErrors || isGenerating}
              style={{ marginLeft: 8 }}
            >
              Download PNG
            </button>
          </div>
          
          <div className="er-muted" style={{ marginTop: 8 }}>
            {hasErrors || backendHasErrors
              ? "Fix validation errors before generating or downloading a diagram."
              : "Generate Diagram creates a visual ER diagram using Graphviz automatic layout. Download PNG exports the current diagram as an image."}
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
        <GraphvizDiagram model={model} dotText={dotText ?? undefined} onSvgReady={setCurrentSvg} />
      </div>
    </div>
  );
}
