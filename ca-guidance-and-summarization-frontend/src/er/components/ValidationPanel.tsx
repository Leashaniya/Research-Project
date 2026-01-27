import { createId } from "../id";
import type { ValidationMessage, ValidationOutput } from "../types";

interface Props {
  messages?: ValidationMessage[];
  backendValidation?: ValidationOutput;
  hasRun: boolean;
}

/**
 * Convert backend ValidationOutput to frontend ValidationMessage format.
 */
function convertBackendValidation(backend: ValidationOutput): ValidationMessage[] {
  const messages: ValidationMessage[] = [];

  backend.errors.forEach((issue) => {
    messages.push({
      id: createId("val"),
      severity: "error",
      title: issue.code,
      detail: `${issue.message} (${issue.path})`,
    });
  });

  backend.warnings.forEach((issue) => {
    messages.push({
      id: createId("val"),
      severity: "warning",
      title: issue.code,
      detail: `${issue.message} (${issue.path})`,
    });
  });

  backend.info.forEach((issue) => {
    messages.push({
      id: createId("val"),
      severity: "info",
      title: issue.code,
      detail: `${issue.message} (${issue.path})`,
    });
  });

  return messages;
}

export function ValidationPanel({ messages, backendValidation, hasRun }: Props) {
  // Use backend validation if available, otherwise use frontend messages
  const displayMessages = backendValidation
    ? convertBackendValidation(backendValidation)
    : messages || [];

  const hasErrors = displayMessages.some((m) => m.severity === "error");

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Validation Results</h3>

      {!hasRun ? (
        <div className="er-muted">Click "Validate Model" to see warnings and errors.</div>
      ) : displayMessages.length === 0 ? (
        <div style={{ color: "#155724", fontWeight: 700 }}>No issues found.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {hasErrors && (
            <div style={{ color: "#842029", fontWeight: 700, marginBottom: 8 }}>
              ⚠️ Model has errors. Fix them before generating a diagram.
            </div>
          )}
          {displayMessages.map((m) => (
            <div key={m.id} style={{ border: "1px solid #dee2e6", borderRadius: 8, padding: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <span className={`er-pill ${m.severity}`}>{m.severity.toUpperCase()}</span>
                <div style={{ fontWeight: 700, color: "#495057" }}>{m.title}</div>
              </div>
              {m.detail && <div className="er-muted">{m.detail}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
