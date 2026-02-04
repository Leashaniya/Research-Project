import type { Entity } from "../types";
import { FaTrash, FaPlus } from "react-icons/fa";

interface Props {
  entities: Entity[];
  selectedEntityId: string | null;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
}

export function EntityList({ entities, selectedEntityId, onSelect, onAdd, onDelete }: Props) {
  return (
    <div className="er-panel">
      <h3 className="er-section-title">Entities</h3>

      <div className="er-list">
        {entities.length === 0 ? (
          <div className="er-muted">No entities yet. Add one to start.</div>
        ) : (
          entities.map((e) => (
            <div
              key={e.id}
              className={`er-list-item ${selectedEntityId === e.id ? "active" : ""}`}
              onClick={() => onSelect(e.id)}
              role="button"
              tabIndex={0}
            >
              <div style={{ minWidth: 0 }}>
                <div className="er-list-item-title">{e.name || "(unnamed entity)"}</div>
                <div className="er-muted">{e.attributes.length} attribute(s)</div>
              </div>
              <button
                className="er-btn er-btn-icon-only danger"
                onClick={(ev) => {
                  ev.stopPropagation();
                  onDelete(e.id);
                }}
                title="Delete entity"
                type="button"
              >
                <FaTrash />
              </button>
            </div>
          ))
        )}
      </div>

      <button className="er-btn er-btn-icon primary" onClick={onAdd} type="button">
        <FaPlus />
        <span>Add Entity</span>
      </button>
    </div>
  );
}

