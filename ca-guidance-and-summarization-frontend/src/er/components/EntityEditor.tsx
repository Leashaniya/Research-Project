import type { Attribute, Entity, AttributeType } from "../types";
import { createId } from "../id";

interface Props {
  entity: Entity;
  entities: Entity[]; // All entities (needed for strong entity selection)
  onChange: (next: Entity) => void;
}

export function EntityEditor({ entity, entities, onChange }: Props) {
  const updateAttr = (attrId: string, patch: Partial<Attribute>) => {
    const next = {
      ...entity,
      attributes: entity.attributes.map((a) => {
        if (a.id === attrId) {
          const updated = { ...a, ...patch };
          // If changing from composite to non-composite, remove subAttributes
          if (patch.type && patch.type !== "composite" && updated.subAttributes) {
            delete updated.subAttributes;
          }
          // If changing to composite and no subAttributes exist, initialize empty array
          if (patch.type === "composite" && !updated.subAttributes) {
            updated.subAttributes = [];
          }
          return updated;
        }
        return a;
      })
    };
    onChange(next);
  };

  const updateSubAttr = (attrId: string, subAttrId: string, patch: Partial<Attribute>) => {
    const next = {
      ...entity,
      attributes: entity.attributes.map((a) => {
        if (a.id === attrId && a.subAttributes) {
          return {
            ...a,
            subAttributes: a.subAttributes.map((sa) => 
              sa.id === subAttrId ? { ...sa, ...patch } : sa
            )
          };
        }
        return a;
      })
    };
    onChange(next);
  };

  const addSubAttr = (attrId: string) => {
    const nextSubAttr: Attribute = {
      id: createId("subattr"),
      name: "",
      pk: false,
      unique: false,
      nullable: true,
      type: "regular"
    };
    const next = {
      ...entity,
      attributes: entity.attributes.map((a) => {
        if (a.id === attrId) {
          return {
            ...a,
            subAttributes: [...(a.subAttributes || []), nextSubAttr]
          };
        }
        return a;
      })
    };
    onChange(next);
  };

  const deleteSubAttr = (attrId: string, subAttrId: string) => {
    const next = {
      ...entity,
      attributes: entity.attributes.map((a) => {
        if (a.id === attrId && a.subAttributes) {
          return {
            ...a,
            subAttributes: a.subAttributes.filter((sa) => sa.id !== subAttrId)
          };
        }
        return a;
      })
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
      nullable: true,
      type: "regular"
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

      {/* Weak Entity Settings */}
      <div style={{ marginBottom: 12, padding: "12px", backgroundColor: "#f8f9fa", borderRadius: "6px", border: "1px solid #dee2e6" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: entity.isWeak ? "8px" : "0" }}>
          <input
            type="checkbox"
            id="is-weak"
            checked={entity.isWeak}
            onChange={(e) => {
              onChange({
                ...entity,
                isWeak: e.target.checked,
                strongEntityId: e.target.checked ? entity.strongEntityId : undefined
              });
            }}
          />
          <label htmlFor="is-weak" className="er-muted" style={{ fontWeight: 600, cursor: "pointer" }}>
            Weak Entity (double rectangle)
          </label>
        </div>
        {entity.isWeak && (
          <div style={{ marginLeft: "24px", marginTop: "8px" }}>
            <label className="er-muted" htmlFor="strong-entity" style={{ display: "block", marginBottom: "4px", fontSize: "0.9rem" }}>
              Strong Entity (provides primary key):
            </label>
            <select
              id="strong-entity"
              className="er-select"
              value={entity.strongEntityId || ""}
              onChange={(e) => onChange({ ...entity, strongEntityId: e.target.value || undefined })}
              style={{ width: "100%" }}
            >
              <option value="">Select Strong Entity</option>
              {entities
                .filter((e) => e.id !== entity.id && !e.isWeak)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name || "(unnamed entity)"}
                  </option>
                ))}
            </select>
            {entity.isWeak && !entity.strongEntityId && (
              <div className="er-muted" style={{ fontSize: "0.85rem", marginTop: "4px", fontStyle: "italic", color: "#dc3545" }}>
                Please select a strong entity for this weak entity.
              </div>
            )}
          </div>
        )}
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
            <th style={{ width: "30%" }}>Name</th>
            <th style={{ width: "15%" }}>Type</th>
            <th>PK</th>
            <th>Unique</th>
            <th>Nullable</th>
            <th style={{ width: 90 }} />
          </tr>
        </thead>
        <tbody>
          {entity.attributes.length === 0 ? (
            <tr>
              <td colSpan={6} className="er-muted">
                No attributes yet. Add at least one (e.g., an identifier).
              </td>
            </tr>
          ) : (
            entity.attributes.map((a) => (
              <>
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
                    <select
                      className="er-input"
                      value={a.type}
                      onChange={(e) => updateAttr(a.id, { type: e.target.value as AttributeType })}
                      style={{ fontSize: "0.9rem", padding: "4px 8px" }}
                    >
                      <option value="regular">Regular</option>
                      <option value="composite">Composite</option>
                      <option value="multivalued">Multi-valued</option>
                    </select>
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
                {/* Sub-attributes for composite attributes */}
                {a.type === "composite" && (
                  <tr key={`${a.id}-subattrs`}>
                    <td colSpan={6} style={{ padding: "8px 0 8px 20px", backgroundColor: "#f8f9fa" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                        <span className="er-muted" style={{ fontSize: "0.85rem", fontWeight: 600 }}>
                          Sub-attributes:
                        </span>
                        <button
                          className="er-btn primary"
                          type="button"
                          onClick={() => addSubAttr(a.id)}
                          style={{ fontSize: "0.85rem", padding: "2px 8px" }}
                        >
                          + Add Sub-attribute
                        </button>
                      </div>
                      {a.subAttributes && a.subAttributes.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          {a.subAttributes.map((subAttr) => (
                            <div key={subAttr.id} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              <input
                                className="er-input"
                                value={subAttr.name}
                                onChange={(e) => updateSubAttr(a.id, subAttr.id, { name: e.target.value })}
                                placeholder="e.g., street, city"
                                style={{ flex: 1, fontSize: "0.9rem" }}
                              />
                              <button
                                className="er-btn danger"
                                type="button"
                                onClick={() => deleteSubAttr(a.id, subAttr.id)}
                                style={{ fontSize: "0.85rem", padding: "2px 8px" }}
                              >
                                Remove
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="er-muted" style={{ fontSize: "0.85rem", fontStyle: "italic" }}>
                          No sub-attributes yet. Add at least one (e.g., street, city for address).
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

