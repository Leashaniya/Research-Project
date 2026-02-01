import { useEffect, useRef } from "react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Modal component showing instructions for exporting to Figma.
 */
export function FigmaExportModal({ isOpen, onClose }: Props) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Close modal on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  // Close modal on outside click
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        style={{
          backgroundColor: "#fff",
          borderRadius: 8,
          padding: "24px",
          maxWidth: "500px",
          width: "90%",
          boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}>Export to Figma</h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: "1.5rem",
              cursor: "pointer",
              color: "#6c757d",
              padding: 0,
              width: "24px",
              height: "24px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ×
          </button>
        </div>

        <div style={{ marginBottom: 16 }}>
          <p style={{ margin: "0 0 12px 0", color: "#495057" }}>
            The ER diagram JSON payload has been copied to your clipboard and downloaded as <code style={{ backgroundColor: "#f8f9fa", padding: "2px 6px", borderRadius: 3 }}>er-diagram-figma.json</code>.
          </p>
          
          <div style={{ backgroundColor: "#f8f9fa", padding: "16px", borderRadius: 4, marginTop: 16 }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1rem", fontWeight: 600 }}>Next Steps:</h3>
            <ol style={{ margin: 0, paddingLeft: "20px", color: "#495057" }}>
              <li style={{ marginBottom: 8 }}>Open Figma</li>
              <li style={{ marginBottom: 8 }}>Go to <strong>Plugins</strong> → <strong>Import ER Diagram</strong></li>
              <li style={{ marginBottom: 8 }}>Paste the JSON payload (or use the downloaded file)</li>
              <li style={{ marginBottom: 8 }}>Click <strong>Render</strong> to create editable diagram objects</li>
            </ol>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button
            className="er-btn"
            type="button"
            onClick={onClose}
            style={{ padding: "8px 16px" }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
