import type { Attribute, Cardinality, Entity, Relationship } from "../types";
import { createId } from "../id";

const CARDINALITIES: Cardinality[] = ["0..1", "1..1", "0..*", "1..*"];

interface Props {
  relationship: Relationship;
  entities: Entity[];
  onChange: (next: Relationship) => void;
}

export function RelationshipEditor({ relationship, entities, onChange }: Props) {
  const updateAttr = (attrId: string, patch: Partial<Attribute>) => {
    onChange({
      ...relationship,
      attributes: relationship.attributes.map((a) => (a.id === attrId ? { ...a, ...patch } : a))
    });
  };

  const deleteAttr = (attrId: string) => {
    onChange({ ...relationship, attributes: relationship.attributes.filter((a) => a.id !== attrId) });
  };

  const addAttr = () => {
    const nextAttr: Attribute = {
      id: createId("attr"),
      name: "",
      pk: false, // allowed, but validation can warn later if desired
      unique: false,
      nullable: true
    };
    onChange({ ...relationship, attributes: [...relationship.attributes, nextAttr] });
  };

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Relationship Editor</h3>

      <div style={{ marginBottom: 12 }}>
        <label className="er-muted" htmlFor="rel-name">
          Relationship name (Chen diamond text)
        </label>
        <input
          id="rel-name"
          className="er-input"
          value={relationship.name}
          onChange={(e) => onChange({ ...relationship, name: e.target.value })}
          placeholder="e.g., EnrollsIn"
        />
      </div>

      <div className="er-row">
        <div>
          <label className="er-muted" htmlFor="entity-a">
            Entity A
          </label>
          <select
            id="entity-a"
            className="er-select"
            value={relationship.fromEntityId}
            onChange={(e) => onChange({ ...relationship, fromEntityId: e.target.value })}
          >
            <option value="">Select Entity A</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name || "(unnamed entity)"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="er-muted" htmlFor="card-a">
            Cardinality near A
          </label>
          <select
            id="card-a"
            className="er-select"
            value={relationship.fromCardinality}
            onChange={(e) => onChange({ ...relationship, fromCardinality: e.target.value as Cardinality })}
          >
            {CARDINALITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="er-row">
        <div>
          <label className="er-muted" htmlFor="entity-b">
            Entity B
          </label>
          <select
            id="entity-b"
            className="er-select"
            value={relationship.toEntityId}
            onChange={(e) => onChange({ ...relationship, toEntityId: e.target.value })}
          >
            <option value="">Select Entity B</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name || "(unnamed entity)"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="er-muted" htmlFor="card-b">
            Cardinality near B
          </label>
          <select
            id="card-b"
            className="er-select"
            value={relationship.toCardinality}
            onChange={(e) => onChange({ ...relationship, toCardinality: e.target.value as Cardinality })}
          >
            {CARDINALITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 6 }}>
        <div className="er-muted" style={{ fontWeight: 700 }}>
          Relationship Attributes
        </div>
        <button className="er-btn primary" type="button" onClick={addAttr}>
          + Add Attribute
        </button>
      </div>

      <div className="er-muted" style={{ marginTop: 6 }}>
        PK on relationship attributes is allowed (we will warn later if needed).
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
          {relationship.attributes.length === 0 ? (
            <tr>
              <td colSpan={5} className="er-muted">
                No relationship attributes.
              </td>
            </tr>
          ) : (
            relationship.attributes.map((a) => (
              <tr key={a.id}>
                <td>
                  <input
                    className="er-input"
                    value={a.name}
                    onChange={(e) => updateAttr(a.id, { name: e.target.value })}
                    placeholder="e.g., grade"
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

