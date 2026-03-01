import { FaExclamationTriangle, FaCheck, FaTimes } from "react-icons/fa";

interface Props {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  type?: "danger" | "warning" | "info";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmationDialog({
  isOpen,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  type = "danger",
  onConfirm,
  onCancel
}: Props) {
  if (!isOpen) return null;

  const getIcon = () => {
    switch (type) {
      case "danger":
        return <FaExclamationTriangle className="er-dialog-icon danger" />;
      case "warning":
        return <FaExclamationTriangle className="er-dialog-icon warning" />;
      case "info":
        return <FaExclamationTriangle className="er-dialog-icon info" />;
      default:
        return null;
    }
  };

  return (
    <div className="er-dialog-overlay" onClick={onCancel}>
      <div className="er-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="er-dialog-header">
          <div className="er-dialog-header-content">
            {getIcon()}
            <h3>{title}</h3>
          </div>
        </div>
        <div className="er-dialog-body">
          <p>{message}</p>
        </div>
        <div className="er-dialog-actions">
          <button 
            className="er-btn er-btn-icon" 
            onClick={onCancel}
          >
            <FaTimes />
            <span>{cancelText}</span>
          </button>
          <button 
            className={`er-btn er-btn-icon ${type === "danger" ? "danger" : "primary"}`}
            onClick={onConfirm}
          >
            <FaCheck />
            <span>{confirmText}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
