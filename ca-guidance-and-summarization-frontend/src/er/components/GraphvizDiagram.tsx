import { useEffect, useMemo, useState } from "react";
import { Graphviz } from "@hpcc-js/wasm";
import type { ERModel } from "../types";
import { erModelToDot } from "../graphviz";

interface Props {
  model: ERModel | null;
  dotText?: string; // Optional: if provided, use this instead of generating from model
}

/**
 * GraphvizDiagram component renders an ER diagram using Graphviz DOT.
 * 
 * Uses @hpcc-js/wasm to render DOT -> SVG in the browser.
 */
export function GraphvizDiagram({ model, dotText }: Props) {
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRendering, setIsRendering] = useState(false);

  // Generate DOT text from model or use provided dotText
  const dot = useMemo(() => {
    if (dotText) return dotText;
    if (!model || model.entities.length === 0) return null;
    try {
      return erModelToDot(model);
    } catch (err) {
      console.error("Error generating DOT:", err);
      return null;
    }
  }, [model, dotText]);

  // Set error if DOT generation failed
  useEffect(() => {
    if (!dot && model && model.entities.length > 0 && !dotText) {
      setError("Failed to generate DOT from model");
    } else if (dot) {
      setError(null);
    }
  }, [dot, model, dotText]);

  // Render DOT to SVG
  useEffect(() => {
    if (!dot) {
      setSvgContent(null);
      setError(null);
      return;
    }

    setIsRendering(true);
    setError(null);

    // Render DOT to SVG using Graphviz WASM
    Graphviz.load()
      .then((graphviz) => {
        const svg = graphviz.dot(dot);
        setSvgContent(svg);
        setError(null);
      })
      .catch((err: unknown) => {
        console.error("Graphviz rendering error:", err);
        setError(`Failed to render diagram: ${err instanceof Error ? err.message : String(err)}`);
        setSvgContent(null);
      })
      .finally(() => {
        setIsRendering(false);
      });
  }, [dot]);

  if (!model || model.entities.length === 0) {
    return (
      <div className="er-panel">
        <h3 className="er-section-title">Graphviz Preview</h3>
        <div className="er-muted" style={{ padding: "40px", textAlign: "center" }}>
          No model data available. Add entities and relationships to generate a diagram.
        </div>
      </div>
    );
  }

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Graphviz Preview</h3>
      
      {isRendering && (
        <div style={{ padding: "20px", textAlign: "center", color: "#6c757d" }}>
          Rendering diagram...
        </div>
      )}

      {error && (
        <div style={{ padding: "16px", backgroundColor: "#f8d7da", color: "#842029", borderRadius: 4, marginBottom: 16 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {svgContent && !isRendering && (
        <div
          style={{
            overflow: "auto",
            border: "1px solid #dee2e6",
            borderRadius: 8,
            backgroundColor: "#fff",
            padding: "16px",
            minHeight: "400px",
          }}
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      )}

      {!svgContent && !isRendering && !error && dot && (
        <div className="er-muted" style={{ padding: "20px", textAlign: "center" }}>
          Generating diagram...
        </div>
      )}
    </div>
  );
}
