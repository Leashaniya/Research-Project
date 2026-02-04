import { createId } from "../id";
import type { ValidationMessage, ValidationOutput } from "../types";
import { FaCheckCircle, FaExclamationTriangle, FaInfoCircle, FaExclamationCircle } from "react-icons/fa";

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

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "error":
        return <FaExclamationCircle className="er-validation-icon error" />;
      case "warning":
        return <FaExclamationTriangle className="er-validation-icon warning" />;
      case "info":
        return <FaInfoCircle className="er-validation-icon info" />;
      default:
        return null;
    }
  };

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Validation Results</h3>

      {!hasRun ? (
        <div className="er-muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <FaInfoCircle style={{ color: "#6c757d" }} />
          <span>Click "Validate" to see warnings and errors.</span>
        </div>
      ) : displayMessages.length === 0 ? (
        <div className="er-validation-success">
          <FaCheckCircle />
          <span>No issues found. Your model is valid!</span>
        </div>
      ) : (
        <div className="er-validation-messages">
          {hasErrors && (
            <div className="er-validation-summary error">
              <FaExclamationCircle />
              <span>Model has errors. Fix them before generating a diagram.</span>
            </div>
          )}
          <div className="er-validation-scroll">
            {displayMessages.map((m) => (
              <div key={m.id} className={`er-validation-item ${m.severity}`}>
                <div className="er-validation-item-header">
                  {getSeverityIcon(m.severity)}
                  <span className={`er-pill ${m.severity}`}>{m.severity.toUpperCase()}</span>
                  <div className="er-validation-title">{m.title}</div>
                </div>
                {m.detail && (
                  <div className="er-validation-detail" title={m.detail}>
                    {m.detail}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
