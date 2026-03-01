import type { Attribute, Cardinality, Entity, Relationship, AttributeType, ParticipationType, RelationshipType } from "../types";
import { createId } from "../id";
import { useMemo } from "react";
import { FaTrash, FaPlus } from "react-icons/fa";

const CARDINALITIES: Cardinality[] = ["0..1", "1..1", "0..*", "1..*"];
const PARTICIPATION_TYPES: ParticipationType[] = ["none", "partial", "total"];
const RELATIONSHIP_TYPES: RelationshipType[] = ["binary", "ternary", "isa"];
const DEFAULT_CARD: Cardinality = "0..*";

interface Props {
  relationship: Relationship;
  entities: Entity[];
  onChange: (next: Relationship) => void;
}

export function RelationshipEditor({ relationship, entities, onChange }: Props) {
  // Ensure relationshipType is always set (for backward compatibility)
  // Use useMemo to recalculate when relationship prop changes
  const normalizedRelationship: Relationship = useMemo(() => ({
    ...relationship,
    relationshipType: relationship.relationshipType || "binary"
  }), [relationship]);

  const updateAttr = (attrId: string, patch: Partial<Attribute>) => {
    onChange({
      ...normalizedRelationship,
      attributes: normalizedRelationship.attributes.map((a) => {
        if (a.id === attrId) {
          const updated = { ...a, ...patch };
          if (patch.type && patch.type !== "composite" && updated.subAttributes) {
            delete updated.subAttributes;
          }
          if (patch.type === "composite" && !updated.subAttributes) {
            updated.subAttributes = [];
          }
          return updated;
        }
        return a;
      })
    });
  };

  const updateSubAttr = (attrId: string, subAttrId: string, patch: Partial<Attribute>) => {
    onChange({
      ...relationship,
      attributes: relationship.attributes.map((a) => {
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
    });
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
    onChange({
      ...relationship,
      attributes: relationship.attributes.map((a) => {
        if (a.id === attrId) {
          return {
            ...a,
            subAttributes: [...(a.subAttributes || []), nextSubAttr]
          };
        }
        return a;
      })
    });
  };

  const deleteSubAttr = (attrId: string, subAttrId: string) => {
    onChange({
      ...relationship,
      attributes: relationship.attributes.map((a) => {
        if (a.id === attrId && a.subAttributes) {
          return {
            ...a,
            subAttributes: a.subAttributes.filter((sa) => sa.id !== subAttrId)
          };
        }
        return a;
      })
    });
  };

  const deleteAttr = (attrId: string) => {
    onChange({ ...normalizedRelationship, attributes: normalizedRelationship.attributes.filter((a) => a.id !== attrId) });
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
    onChange({ ...normalizedRelationship, attributes: [...normalizedRelationship.attributes, nextAttr] });
  };

  const addChildEntity = () => {
    onChange({
      ...normalizedRelationship,
      childEntityIds: [...(normalizedRelationship.childEntityIds || []), ""]
    });
  };

  const removeChildEntity = (index: number) => {
    const newChildIds = [...(normalizedRelationship.childEntityIds || [])];
    newChildIds.splice(index, 1);
    onChange({
      ...normalizedRelationship,
      childEntityIds: newChildIds.length > 0 ? newChildIds : undefined
    });
  };

  const updateChildEntity = (index: number, entityId: string) => {
    const newChildIds = [...(normalizedRelationship.childEntityIds || [])];
    newChildIds[index] = entityId;
    onChange({
      ...normalizedRelationship,
      childEntityIds: newChildIds
    });
  };

  const handleRelationshipTypeChange = (newType: RelationshipType) => {
    console.log("Changing relationship type to:", newType);
    // Reset relationship-specific fields when changing type
    // Include all required fields from the current relationship
    const base: Relationship = {
      id: normalizedRelationship.id,
      name: normalizedRelationship.name,
      relationshipType: newType,
      fromEntityId: normalizedRelationship.fromEntityId,
      toEntityId: normalizedRelationship.toEntityId,
      fromCardinality: normalizedRelationship.fromCardinality,
      toCardinality: normalizedRelationship.toCardinality,
      fromParticipation: normalizedRelationship.fromParticipation,
      toParticipation: normalizedRelationship.toParticipation,
      attributes: normalizedRelationship.attributes,
      isWeak: normalizedRelationship.isWeak,
      // Clear optional fields first
      thirdEntityId: undefined,
      thirdCardinality: undefined,
      thirdParticipation: undefined,
      parentEntityId: undefined,
      childEntityIds: undefined,
      isDisjoint: undefined,
      isTotal: undefined
    };

    if (newType === "ternary") {
      onChange({
        ...base,
        thirdEntityId: normalizedRelationship.thirdEntityId || "",
        thirdCardinality: normalizedRelationship.thirdCardinality || DEFAULT_CARD,
        thirdParticipation: normalizedRelationship.thirdParticipation || "none"
      });
    } else if (newType === "isa") {
      onChange({
        ...base,
        parentEntityId: normalizedRelationship.parentEntityId || "",
        childEntityIds: normalizedRelationship.childEntityIds || [],
        isDisjoint: normalizedRelationship.isDisjoint || false,
        isTotal: normalizedRelationship.isTotal || false
      });
    } else {
      // Binary - keep base as is (fields already cleared)
      onChange(base);
    }
  };

  return (
    <div className="er-panel">
      <h3 className="er-section-title">Relationship Editor</h3>

      <div style={{ marginBottom: 12 }}>
        <label className="er-muted" htmlFor="rel-name">
          Relationship name
        </label>
        <input
          id="rel-name"
          className="er-input"
          value={normalizedRelationship.name}
          onChange={(e) => onChange({ ...normalizedRelationship, name: e.target.value })}
          placeholder={normalizedRelationship.relationshipType === "isa" ? "ISA (inheritance)" : normalizedRelationship.relationshipType === "ternary" ? "e.g., WorksIn" : "e.g., EnrollsIn"}
        />
      </div>

      {/* Relationship Type Selector */}
      <div style={{ marginBottom: 12 }}>
        <label className="er-muted" htmlFor="rel-type">
          Relationship Type
        </label>
        <select
          id="rel-type"
          className="er-select"
          value={normalizedRelationship.relationshipType}
          onChange={(e) => handleRelationshipTypeChange(e.target.value as RelationshipType)}
        >
          {RELATIONSHIP_TYPES.map((type) => (
            <option key={type} value={type}>
              {type === "binary" ? "Binary (2 entities)" : type === "ternary" ? "Ternary (3 entities)" : "ISA (Inheritance)"}
            </option>
          ))}
        </select>
      </div>

      {/* Binary Relationship UI */}
      {normalizedRelationship.relationshipType === "binary" && (
        <>
          <div className="er-row-equal-3">
        <div>
          <label className="er-muted" htmlFor="entity-a">
            Entity A
          </label>
          <select
            id="entity-a"
            className="er-select"
            value={normalizedRelationship.fromEntityId}
            onChange={(e) => onChange({ ...normalizedRelationship, fromEntityId: e.target.value })}
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
            value={normalizedRelationship.fromCardinality}
            onChange={(e) => onChange({ ...normalizedRelationship, fromCardinality: e.target.value as Cardinality })}
          >
            {CARDINALITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="er-muted" htmlFor="participation-a" title="Participation (Entity A)">
            Participation A
          </label>
          <select
            id="participation-a"
            className="er-select"
            value={normalizedRelationship.fromParticipation}
            onChange={(e) => onChange({ ...normalizedRelationship, fromParticipation: e.target.value as ParticipationType })}
          >
            {PARTICIPATION_TYPES.map((p) => (
              <option key={p} value={p}>
                {p === "none" ? "None" : p === "total" ? "Total (double line)" : "Partial (single line)"}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="er-row-equal-3">
        <div>
          <label className="er-muted" htmlFor="entity-b">
            Entity B
          </label>
          <select
            id="entity-b"
            className="er-select"
            value={normalizedRelationship.toEntityId}
            onChange={(e) => onChange({ ...normalizedRelationship, toEntityId: e.target.value })}
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
            value={normalizedRelationship.toCardinality}
            onChange={(e) => onChange({ ...normalizedRelationship, toCardinality: e.target.value as Cardinality })}
          >
            {CARDINALITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="er-muted" htmlFor="participation-b" title="Participation (Entity B)">
            Participation B
          </label>
          <select
            id="participation-b"
            className="er-select"
            value={normalizedRelationship.toParticipation}
            onChange={(e) => onChange({ ...normalizedRelationship, toParticipation: e.target.value as ParticipationType })}
          >
            {PARTICIPATION_TYPES.map((p) => (
              <option key={p} value={p}>
                {p === "none" ? "None" : p === "total" ? "Total (double line)" : "Partial (single line)"}
              </option>
            ))}
          </select>
        </div>
      </div>

          {/* Weak Relationship (only for binary) */}
          {normalizedRelationship.relationshipType === "binary" && (
            <div style={{ marginTop: 12, marginBottom: 12, padding: "12px", backgroundColor: "#f8f9fa", borderRadius: "6px", border: "1px solid #dee2e6" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <input
                  type="checkbox"
                  id="is-weak-rel"
                  checked={normalizedRelationship.isWeak}
                  onChange={(e) => onChange({ ...normalizedRelationship, isWeak: e.target.checked })}
                />
                <label htmlFor="is-weak-rel" className="er-muted" style={{ fontWeight: 600, cursor: "pointer" }}>
                  Weak Relationship (mandatory)
                </label>
              </div>
              {normalizedRelationship.isWeak && (
                <div className="er-muted" style={{ fontSize: "0.85rem", marginTop: "4px", marginLeft: "24px" }}>
                  Use this when connecting a weak entity to its strong entity. Represented with double-line diamond and double lines on both sides.
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Ternary Relationship UI */}
      {normalizedRelationship.relationshipType === "ternary" && (
        <>
          <div className="er-row-equal-3">
            <div>
              <label className="er-muted" htmlFor="entity-a-ternary">
                Entity A
              </label>
              <select
                id="entity-a-ternary"
                className="er-select"
                value={normalizedRelationship.fromEntityId}
                onChange={(e) => onChange({ ...normalizedRelationship, fromEntityId: e.target.value })}
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
              <label className="er-muted" htmlFor="card-a-ternary">
                Cardinality A
              </label>
              <select
                id="card-a-ternary"
                className="er-select"
                value={normalizedRelationship.fromCardinality}
                onChange={(e) => onChange({ ...normalizedRelationship, fromCardinality: e.target.value as Cardinality })}
              >
                {CARDINALITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="er-muted" htmlFor="participation-a-ternary">
                Participation A
              </label>
              <select
                id="participation-a-ternary"
                className="er-select"
                value={normalizedRelationship.fromParticipation}
                onChange={(e) => onChange({ ...normalizedRelationship, fromParticipation: e.target.value as ParticipationType })}
              >
                {PARTICIPATION_TYPES.map((p) => (
                  <option key={p} value={p}>
                    {p === "none" ? "None" : p === "total" ? "Total" : "Partial"}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="er-row-equal-3">
            <div>
              <label className="er-muted" htmlFor="entity-b-ternary">
                Entity B
              </label>
              <select
                id="entity-b-ternary"
                className="er-select"
                value={normalizedRelationship.toEntityId}
                onChange={(e) => onChange({ ...normalizedRelationship, toEntityId: e.target.value })}
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
              <label className="er-muted" htmlFor="card-b-ternary">
                Cardinality B
              </label>
              <select
                id="card-b-ternary"
                className="er-select"
                value={normalizedRelationship.toCardinality}
                onChange={(e) => onChange({ ...normalizedRelationship, toCardinality: e.target.value as Cardinality })}
              >
                {CARDINALITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="er-muted" htmlFor="participation-b-ternary">
                Participation B
              </label>
              <select
                id="participation-b-ternary"
                className="er-select"
                value={normalizedRelationship.toParticipation}
                onChange={(e) => onChange({ ...normalizedRelationship, toParticipation: e.target.value as ParticipationType })}
              >
                {PARTICIPATION_TYPES.map((p) => (
                  <option key={p} value={p}>
                    {p === "none" ? "None" : p === "total" ? "Total" : "Partial"}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="er-row-equal-3">
            <div>
              <label className="er-muted" htmlFor="entity-c-ternary">
                Entity C
              </label>
              <select
                id="entity-c-ternary"
                className="er-select"
                value={normalizedRelationship.thirdEntityId || ""}
                onChange={(e) => onChange({ ...relationship, thirdEntityId: e.target.value || undefined })}
              >
                <option value="">Select Entity C</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name || "(unnamed entity)"}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="er-muted" htmlFor="card-c-ternary">
                Cardinality C
              </label>
              <select
                id="card-c-ternary"
                className="er-select"
                value={normalizedRelationship.thirdCardinality || DEFAULT_CARD}
                onChange={(e) => onChange({ ...normalizedRelationship, thirdCardinality: e.target.value as Cardinality })}
              >
                {CARDINALITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="er-muted" htmlFor="participation-c-ternary">
                Participation C
              </label>
              <select
                id="participation-c-ternary"
                className="er-select"
                value={normalizedRelationship.thirdParticipation || "none"}
                onChange={(e) => onChange({ ...normalizedRelationship, thirdParticipation: e.target.value as ParticipationType })}
              >
                {PARTICIPATION_TYPES.map((p) => (
                  <option key={p} value={p}>
                    {p === "none" ? "None" : p === "total" ? "Total" : "Partial"}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </>
      )}

      {/* ISA Relationship UI */}
      {normalizedRelationship.relationshipType === "isa" && (
        <>
          <div style={{ marginBottom: 12 }}>
            <label className="er-muted" htmlFor="parent-entity">
              Parent Entity (Supertype)
            </label>
            <select
              id="parent-entity"
              className="er-select"
              value={normalizedRelationship.parentEntityId || ""}
              onChange={(e) => onChange({ ...normalizedRelationship, parentEntityId: e.target.value || undefined })}
            >
              <option value="">Select Parent Entity</option>
              {entities.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name || "(unnamed entity)"}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
              <label className="er-muted" style={{ fontWeight: 700 }}>
                Child Entities (Subtypes)
              </label>
              <button className="er-btn er-btn-icon primary" type="button" onClick={addChildEntity} style={{ fontSize: "0.9rem", padding: "6px 12px" }}>
                <FaPlus />
                <span>Add Child</span>
              </button>
            </div>
            {normalizedRelationship.childEntityIds && normalizedRelationship.childEntityIds.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {normalizedRelationship.childEntityIds.map((childId, index) => (
                  <div key={index} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <select
                      className="er-select"
                      value={childId}
                      onChange={(e) => updateChildEntity(index, e.target.value)}
                      style={{ flex: 1 }}
                    >
                      <option value="">Select Child Entity</option>
                      {entities
                        .filter((e) => e.id !== normalizedRelationship.parentEntityId)
                        .map((e) => (
                          <option key={e.id} value={e.id}>
                            {e.name || "(unnamed entity)"}
                          </option>
                        ))}
                    </select>
                    <button
                      className="er-btn er-btn-icon-only danger"
                      type="button"
                      onClick={() => removeChildEntity(index)}
                      title="Remove child entity"
                      style={{ fontSize: "0.85rem", padding: "4px 8px" }}
                    >
                      <FaTrash />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="er-muted" style={{ fontSize: "0.9rem", fontStyle: "italic", padding: "8px" }}>
                No child entities yet. Add at least one child entity.
              </div>
            )}
          </div>

          {/* ISA Constraints */}
          <div style={{ marginTop: 12, padding: "12px", backgroundColor: "#f8f9fa", borderRadius: "6px", border: "1px solid #dee2e6" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
              <input
                type="checkbox"
                id="is-disjoint"
                checked={normalizedRelationship.isDisjoint || false}
                onChange={(e) => onChange({ ...normalizedRelationship, isDisjoint: e.target.checked })}
              />
              <label htmlFor="is-disjoint" className="er-muted" style={{ fontWeight: 600, cursor: "pointer" }}>
                Disjoint (mutually exclusive subtypes)
              </label>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="checkbox"
                id="is-total"
                checked={normalizedRelationship.isTotal || false}
                onChange={(e) => onChange({ ...normalizedRelationship, isTotal: e.target.checked })}
              />
              <label htmlFor="is-total" className="er-muted" style={{ fontWeight: 600, cursor: "pointer" }}>
                Total (all instances must belong to a subtype)
              </label>
            </div>
          </div>
        </>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 6 }}>
        <div className="er-muted" style={{ fontWeight: 700 }}>
          Relationship Attributes
        </div>
        <button className="er-btn er-btn-icon primary" type="button" onClick={addAttr}>
          <FaPlus />
          <span>Add Attribute</span>
        </button>
      </div>

      <div className="er-muted" style={{ marginTop: 6 }}>
        PK on relationship attributes is allowed (we will warn later if needed).
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
          {normalizedRelationship.attributes.length === 0 ? (
            <tr>
              <td colSpan={6} className="er-muted">
                No relationship attributes.
              </td>
            </tr>
          ) : (
            normalizedRelationship.attributes.map((a) => (
              <>
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
                    <button 
                      className="er-btn er-btn-icon-only danger" 
                      type="button" 
                      onClick={() => deleteAttr(a.id)}
                      title="Delete attribute"
                    >
                      <FaTrash />
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
                          className="er-btn er-btn-icon primary"
                          type="button"
                          onClick={() => addSubAttr(a.id)}
                          style={{ fontSize: "0.85rem", padding: "4px 10px" }}
                        >
                          <FaPlus />
                          <span>Add Sub-attribute</span>
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
                                className="er-btn er-btn-icon-only danger"
                                type="button"
                                onClick={() => deleteSubAttr(a.id, subAttr.id)}
                                title="Remove sub-attribute"
                                style={{ fontSize: "0.85rem", padding: "4px 8px" }}
                              >
                                <FaTrash />
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

