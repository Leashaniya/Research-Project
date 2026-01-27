import type { Attribute, Entity } from "../types";
import { createId } from "../id";

interface Props {
  entity: Entity;
  onChange: (next: Entity) => void;
}

export function EntityEditor({ entity, onChange }: Props) {
  const updateAttr = (attrId: string, patch: Partial<Attribute>) => {
    const next = {
      ...entity,
      attributes: entity.attributes.map((a) => (a.id === attrId ? { ...a, ...patch } : a))
    };
    onChange(next);
  };

  const deleteAttr = (attrId: string) => {
    onChange({ ...entity, attributes: entity.attributes.filter((a) => a.id !== attrId) });
  };

  const addAttr = () => {
    const nextAttr: Attribute = {
      id: createId("attr"),
      name: "",
      pk: false,
      unique: false,
      nullable: true
    };
    onChange({ ...entity, attributes: [...entity.attributes, nextAttr] });
  };

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Entity Editor</h3>

      <div style={{ marginBottom: 12 }}>
        <label className="er-muted" htmlFor="entity-name">
          Entity name
        </label>
        <input
          id="entity-name"
          className="er-input"
          value={entity.name}
          onChange={(e) => onChange({ ...entity, name: e.target.value })}
          placeholder="e.g., Student"
        />
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div className="er-muted" style={{ fontWeight: 700 }}>
          Attributes
        </div>
        <button className="er-btn primary" type="button" onClick={addAttr}>
          + Add Attribute
        </button>
      </div>

      <table className="er-attrs-table" style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th style={{ width: "45%" }}>Name</th>
            <th>PK</th>
            <th>Unique</th>
            <th>Nullable</th>
            <th style={{ width: 90 }} />
          </tr>
        </thead>
        <tbody>
          {entity.attributes.length === 0 ? (
            <tr>
              <td colSpan={5} className="er-muted">
                No attributes yet. Add at least one (e.g., an identifier).
              </td>
            </tr>
          ) : (
            entity.attributes.map((a) => (
              <tr key={a.id}>
                <td>
                  <input
                    className="er-input"
                    value={a.name}
                    onChange={(e) => updateAttr(a.id, { name: e.target.value })}
                    placeholder="e.g., student_id"
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={a.pk}
                    onChange={(e) => updateAttr(a.id, { pk: e.target.checked })}
                    aria-label="Primary key"
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={a.unique}
                    onChange={(e) => updateAttr(a.id, { unique: e.target.checked })}
                    aria-label="Unique"
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={a.nullable}
                    onChange={(e) => updateAttr(a.id, { nullable: e.target.checked })}
                    aria-label="Nullable"
                  />
                </td>
                <td>
                  <button className="er-btn danger" type="button" onClick={() => deleteAttr(a.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

