import { useMemo, useState } from "react";
import "./er.css";
import { FaCheckCircle, FaExclamationTriangle, FaInfoCircle, FaDownload, FaSpinner } from "react-icons/fa";
import { HiSparkles } from "react-icons/hi";

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
import { ConfirmationDialog } from "./components/ConfirmationDialog";
import { erModelToDot } from "./graphviz";
import { downloadSvgStringAsPng } from "./pngExport";

const DEFAULT_CARD: Cardinality = "0..*";

function newAttribute(): Attribute {
  return { 
    id: createId("attr"), 
    name: "", 
    pk: false, 
    unique: false, 
    nullable: true,
    type: "regular"
  };
}

function newEntity(nextIndex: number): Entity {
  return { 
    id: createId("ent"), 
    name: `Entity ${nextIndex}`, 
    attributes: [newAttribute()],
    isWeak: false,
    strongEntityId: undefined
  };
}

function newRelationship(nextIndex: number): Relationship {
  return {
    id: createId("rel"),
    name: `Relationship ${nextIndex}`,
    relationshipType: "binary",
    fromEntityId: "",
    toEntityId: "",
    fromCardinality: DEFAULT_CARD,
    toCardinality: DEFAULT_CARD,
    fromParticipation: "none",
    toParticipation: "none",
    attributes: [],
    isWeak: false
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
  
  // Confirmation dialog state
  const [showDownloadConfirm, setShowDownloadConfirm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{
    type: "entity" | "relationship";
    id: string;
    name: string;
  } | null>(null);

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
    setDeleteConfirm({ type: "entity", id, name });
  };

  const confirmDeleteEntity = () => {
    if (!deleteConfirm || deleteConfirm.type !== "entity") return;
    
    const nextEntities = model.entities.filter((x) => x.id !== deleteConfirm.id);
    const nextModel: ERModel = { ...model, entities: nextEntities };
    setModel(nextModel);

    if (selection?.type === "entity" && selection.id === deleteConfirm.id) setSelection(null);
    setDeleteConfirm(null);
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
    setDeleteConfirm({ type: "relationship", id, name });
  };

  const confirmDeleteRelationship = () => {
    if (!deleteConfirm || deleteConfirm.type !== "relationship") return;
    
    const nextRels = model.relationships.filter((x) => x.id !== deleteConfirm.id);
    setModel({ ...model, relationships: nextRels });
    if (selection?.type === "relationship" && selection.id === deleteConfirm.id) setSelection(null);
    setDeleteConfirm(null);
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
      
      // Show detailed error message
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error("Full validation error:", errorMessage);
      // Don't show alert for 422 errors - they're handled by validation messages
      if (!errorMessage.includes("422")) {
        alert(`Validation API error: ${errorMessage}`);
      }
    }
  };

  // Keep generateDiagram for manual generation if needed (e.g., for download)
  const generateDiagram = async (): Promise<string> => {
    setIsGenerating(true);
    setGenerationError(null);

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

    // Show confirmation dialog
    setShowDownloadConfirm(true);
  };

  const confirmDownloadPng = async () => {
    setShowDownloadConfirm(false);
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
    <>
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
            <EntityEditor entity={selectedEntity} entities={model.entities} onChange={updateEntity} />
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
              <button 
                className="er-btn er-btn-icon primary" 
                type="button" 
                onClick={runValidation} 
                title="Validate Model"
              >
                <FaCheckCircle />
                <span>Validate</span>
              </button>
              <button
                className="er-btn er-btn-icon"
                type="button"
                onClick={handleDownloadPng}
                disabled={hasErrors || backendHasErrors || !currentSvg}
                title="Download PNG"
              >
                <FaDownload />
                <span>Download</span>
              </button>
            </div>
            
            <div className="er-muted" style={{ marginTop: 12 }}>
              {hasErrors || backendHasErrors
                ? "Fix validation errors to see the diagram preview and download."
                : "The diagram preview updates automatically as you edit. Download PNG exports the current diagram as an image."}
            </div>
            {generationError && (
              <div className="er-error-message" style={{ marginTop: 12 }}>
                <FaExclamationTriangle style={{ marginRight: 6 }} />
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
        </div>
      </div>

      {/* Download Confirmation Dialog */}
      <ConfirmationDialog
        isOpen={showDownloadConfirm}
        title="Confirm Download"
        message="Download the current ER diagram as a PNG image?"
        confirmText="Download"
        cancelText="Cancel"
        type="info"
        onConfirm={confirmDownloadPng}
        onCancel={() => setShowDownloadConfirm(false)}
      />

      {/* Delete Confirmation Dialog */}
      {deleteConfirm && (
        <ConfirmationDialog
          isOpen={true}
          title={deleteConfirm.type === "entity" ? "Delete Entity" : "Delete Relationship"}
          message={
            deleteConfirm.type === "entity"
              ? `Are you sure you want to delete the entity "${deleteConfirm.name}"? This will not delete relationships, but they may become invalid.`
              : `Are you sure you want to delete the relationship "${deleteConfirm.name}"? This action cannot be undone.`
          }
          confirmText="Delete"
          cancelText="Cancel"
          type="danger"
          onConfirm={deleteConfirm.type === "entity" ? confirmDeleteEntity : confirmDeleteRelationship}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}

      {/* Diagram Preview - Full width below main content */}
      <div className="er-preview-fullwidth">
        <GraphvizDiagram 
          model={model} 
          dotText={dotText ?? undefined} 
          onSvgReady={setCurrentSvg}
          autoGenerate={true}
          hasValidationErrors={hasErrors || backendHasErrors}
        />
      </div>
    </>
  );
}
