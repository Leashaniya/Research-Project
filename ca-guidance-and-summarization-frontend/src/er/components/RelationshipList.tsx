import type { Entity, Relationship } from "../types";

interface Props {
  relationships: Relationship[];
  entities: Entity[];
  selectedRelationshipId: string | null;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
}

function nameForEntity(entities: Entity[], id: string): string {
  const e = entities.find((x) => x.id === id);
  return e?.name || "(unselected)";
}

export function RelationshipList({
  relationships,
  entities,
  selectedRelationshipId,
  onSelect,
  onAdd,
  onDelete
}: Props) {
  return (
    <div className="er-panel">
      <h3 className="er-section-title">Relationships</h3>

      <div className="er-list">
        {relationships.length === 0 ? (
          <div className="er-muted">No relationships yet. Add one after creating entities.</div>
        ) : (
          relationships.map((r) => (
            <div
              key={r.id}
              className={`er-list-item ${selectedRelationshipId === r.id ? "active" : ""}`}
              onClick={() => onSelect(r.id)}
              role="button"
              tabIndex={0}
            >
              <div style={{ minWidth: 0 }}>
                <div className="er-list-item-title">{r.name || "(unnamed relationship)"}</div>
                <div className="er-muted">
                  {nameForEntity(entities, r.fromEntityId)} {r.fromCardinality} ↔ {r.toCardinality}{" "}
                  {nameForEntity(entities, r.toEntityId)}
                </div>
              </div>
              <button
                className="er-btn danger"
                onClick={(ev) => {
                  ev.stopPropagation();
                  onDelete(r.id);
                }}
                title="Delete relationship"
                type="button"
              >
                Delete
              </button>
            </div>
          ))
        )}
      </div>

      <button className="er-btn primary" onClick={onAdd} type="button">
        + Add Relationship
      </button>
    </div>
  );
}

