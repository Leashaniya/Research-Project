import { useState } from "react";

interface Props {
  dotText: string | null;
}

/**
 * DotPreview component displays the DOT source code in a collapsible section.
 */
export function DotPreview({ dotText }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!dotText) {
    return null;
  }

  return (
    <div className="er-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h3 className="er-section-title" style={{ margin: 0 }}>DOT Source</h3>
        <button
          className="er-btn"
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          style={{ fontSize: "0.875rem", padding: "4px 12px" }}
        >
          {isExpanded ? "Hide" : "Show"}
        </button>
      </div>
      
      {isExpanded && (
        <pre
          style={{
            backgroundColor: "#f8f9fa",
            border: "1px solid #dee2e6",
            borderRadius: 4,
            padding: "12px",
            overflow: "auto",
            fontSize: "0.875rem",
            fontFamily: "monospace",
            margin: 0,
            maxHeight: "400px",
          }}
        >
          {dotText}
        </pre>
      )}
    </div>
  );
}
