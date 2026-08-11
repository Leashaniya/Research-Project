import { useEffect, useMemo, useState, useRef } from "react";
import { Graphviz } from "@hpcc-js/wasm";
import type { ERModel } from "../types";
import { erModelToDot } from "../graphviz";
import { FaSpinner } from "react-icons/fa";

interface Props {
  model: ERModel | null;
  dotText?: string | null; // Optional: if provided, use this instead of generating from model
  onSvgReady?: (svg: string | null) => void; // Callback when SVG is ready
  autoGenerate?: boolean; // If true, automatically generate diagram when model changes
  hasValidationErrors?: boolean; // If true, don't generate diagram
}

/**
 * GraphvizDiagram component renders an ER diagram using Graphviz DOT.
 * 
 * Uses @hpcc-js/wasm to render DOT -> SVG in the browser.
 */
export function GraphvizDiagram({ model, dotText, onSvgReady, autoGenerate = false, hasValidationErrors = false }: Props) {
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Generate DOT text from model or use provided dotText
  const dot = useMemo(() => {
    if (dotText) return dotText;
    if (!model || model.entities.length === 0) return null;
    if (hasValidationErrors && autoGenerate) return null; // Don't generate if there are validation errors
    try {
      return erModelToDot(model);
    } catch (err) {
      console.error("Error generating DOT:", err);
      return null;
    }
  }, [model, dotText, hasValidationErrors, autoGenerate]);

  // Set error if DOT generation failed
  useEffect(() => {
    if (!dot && model && model.entities.length > 0 && !dotText) {
      setError("Failed to generate DOT from model");
    } else if (dot) {
      setError(null);
    }
  }, [dot, model, dotText]);

  // Render DOT to SVG - with debouncing for auto-generate
  useEffect(() => {
    // Clear any pending debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // If auto-generate is disabled and no dotText provided, don't render
    if (!autoGenerate && !dotText) {
      setSvgContent(null);
      setError(null);
      return;
    }
    
    if (!dot) {
      setSvgContent(null);
      setError(null);
      return;
    }

    // Debounce rendering to avoid excessive re-renders (500ms delay for auto-generate)
    const renderDelay = autoGenerate ? 500 : 0;
    
    debounceTimerRef.current = setTimeout(() => {
      setIsRendering(true);
      setError(null);

      // Render DOT to SVG using Graphviz WASM
      Graphviz.load()
        .then((graphviz) => {
          const svg = graphviz.dot(dot);
          
          // Process SVG to make it responsive
          let processedSvg = svg;
          try {
            // Use DOMParser for more reliable processing
            const parser = new DOMParser();
            const svgDoc = parser.parseFromString(svg, 'image/svg+xml');
            const svgElement = svgDoc.documentElement;
            
            if (svgElement && svgElement.tagName === 'svg') {
              // Get viewBox or create from dimensions
              let viewBox = svgElement.getAttribute('viewBox');
              const width = svgElement.getAttribute('width');
              const height = svgElement.getAttribute('height');
              
              // Create viewBox if missing
              if (!viewBox && width && height) {
                const w = parseFloat(width.replace(/pt|px|in/, '')) || 0;
                const h = parseFloat(height.replace(/pt|px|in/, '')) || 0;
                if (w > 0 && h > 0) {
                  viewBox = `0 0 ${w} ${h}`;
                  svgElement.setAttribute('viewBox', viewBox);
                }
              }
              
              // Remove fixed dimensions
              svgElement.removeAttribute('width');
              svgElement.removeAttribute('height');
              
              // Add responsive styling
              svgElement.setAttribute('style', 'max-width: 100%; height: auto; display: block; width: 100%;');
              
              // Serialize back to string
              const serializer = new XMLSerializer();
              processedSvg = serializer.serializeToString(svgElement);
            } else {
              // Fallback: simple regex replacement
              processedSvg = svg
                .replace(/\s+width="[^"]*"/gi, '')
                .replace(/\s+height="[^"]*"/gi, '')
                .replace(/<svg([^>]*)>/i, '<svg$1 style="max-width: 100%; height: auto; display: block; width: 100%;">');
            }
          } catch (e) {
            console.warn("Error processing SVG:", e);
            // Use original SVG if processing fails
            processedSvg = svg;
          }
          
          setSvgContent(processedSvg);
          setError(null);
          onSvgReady?.(processedSvg);
        })
        .catch((err: unknown) => {
          console.error("Graphviz rendering error:", err);
          setError(`Failed to render diagram: ${err instanceof Error ? err.message : String(err)}`);
          setSvgContent(null);
          onSvgReady?.(null);
        })
        .finally(() => {
          setIsRendering(false);
        });
    }, renderDelay);

    // Cleanup function
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [dot, onSvgReady, autoGenerate]);

  if (!model || model.entities.length === 0) {
    return (
      <div className="er-panel">
        <h3 className="er-section-title">Graphviz Preview</h3>
        <div className="er-muted" style={{ padding: "40px", textAlign: "center" }}>
          No model data available. Add entities and relationships to see the diagram.
        </div>
      </div>
    );
  }
  
  // Show message if there are validation errors and auto-generate is enabled
  if (hasValidationErrors && autoGenerate && !dotText) {
    return (
      <div className="er-panel">
        <h3 className="er-section-title">Graphviz Preview</h3>
        <div className="er-muted" style={{ padding: "40px", textAlign: "center" }}>
          Fix validation errors to see the diagram preview.
        </div>
      </div>
    );
  }

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Graphviz Preview</h3>
      
      {isRendering && (
        <div className="er-graphviz-loading">
          <FaSpinner className="er-spin" />
          <span>Rendering diagram...</span>
        </div>
      )}

      {error && (
        <div style={{ padding: "16px", backgroundColor: "#f8d7da", color: "#842029", borderRadius: 4, marginBottom: 16 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {svgContent && !isRendering && (
        <div className="er-graphviz-container">
          <div
            className="er-graphviz-wrapper"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        </div>
      )}

      {!svgContent && !isRendering && !error && dot && (
        <div className="er-graphviz-loading">
          <FaSpinner className="er-spin" />
          <span>Generating diagram...</span>
        </div>
      )}
    </div>
  );
}
