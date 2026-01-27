import type { ERModel } from "../types";

interface Props {
  model: ERModel;
}

export function JsonPreview({ model }: Props) {
  return (
    <div className="er-panel">
      <h3 className="er-section-title">Model JSON</h3>
      <pre className="er-pre">{JSON.stringify(model, null, 2)}</pre>
    </div>
  );
}

