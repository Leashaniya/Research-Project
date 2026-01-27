import { useState } from "react";
import type { ERModel } from "../types";

interface Props {
  model: ERModel;
}

export function JsonPreview({ model }: Props) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  return (
    <div className="er-panel">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <h3 className="er-section-title" style={{ margin: 0 }}>Model JSON</h3>
        <button
          className="er-btn"
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          style={{ padding: "4px 10px", fontSize: "0.85rem" }}
        >
          {isCollapsed ? "Show" : "Hide"}
        </button>
      </div>
      {!isCollapsed && <pre className="er-pre">{JSON.stringify(model, null, 2)}</pre>}
    </div>
  );
}

