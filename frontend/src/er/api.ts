import type { ERModel, RenderPlan, ValidationOutput } from "./types";

// ER validate/render-plan are on the guidance backend; use same base as GuidancePage
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || "/guidance";

/**
 * Normalize the ER model to ensure all relationships have relationshipType set.
 * This ensures backward compatibility and prevents validation errors.
 * Also removes undefined optional fields to avoid Pydantic validation issues.
 */
function normalizeModelForAPI(model: ERModel): ERModel {
  return {
    ...model,
    relationships: model.relationships.map(rel => {
      // Ensure relationshipType is set
      const relationshipType = rel.relationshipType || "binary";
      
      // Build normalized relationship - ensure all required fields are present
      const normalized: any = {
        id: rel.id || "",
        name: rel.name || "",
        relationshipType: relationshipType,
        fromEntityId: rel.fromEntityId || "",
        toEntityId: rel.toEntityId || "",
        fromCardinality: rel.fromCardinality || "0..*",
        toCardinality: rel.toCardinality || "0..*",
        fromParticipation: rel.fromParticipation || "none",
        toParticipation: rel.toParticipation || "none",
        attributes: rel.attributes || [],
        isWeak: rel.isWeak || false
      };
      
      // Only include optional fields if they are defined and not null
      if (relationshipType === "ternary") {
        if (rel.thirdEntityId !== undefined && rel.thirdEntityId !== null) {
          normalized.thirdEntityId = rel.thirdEntityId;
        }
        if (rel.thirdCardinality !== undefined && rel.thirdCardinality !== null) {
          normalized.thirdCardinality = rel.thirdCardinality;
        }
        if (rel.thirdParticipation !== undefined && rel.thirdParticipation !== null) {
          normalized.thirdParticipation = rel.thirdParticipation;
        }
      } else if (relationshipType === "isa") {
        if (rel.parentEntityId !== undefined && rel.parentEntityId !== null) {
          normalized.parentEntityId = rel.parentEntityId;
        }
        if (rel.childEntityIds !== undefined && rel.childEntityIds !== null) {
          normalized.childEntityIds = rel.childEntityIds;
        }
        if (rel.isDisjoint !== undefined && rel.isDisjoint !== null) {
          normalized.isDisjoint = rel.isDisjoint;
        }
        if (rel.isTotal !== undefined && rel.isTotal !== null) {
          normalized.isTotal = rel.isTotal;
        }
      } else if (relationshipType === "aggregation") {
        if (rel.aggregationWholeEntityId !== undefined && rel.aggregationWholeEntityId !== null) {
          normalized.aggregationWholeEntityId = rel.aggregationWholeEntityId;
        }
        if (rel.aggregationPartEntityIds !== undefined && rel.aggregationPartEntityIds !== null) {
          normalized.aggregationPartEntityIds = rel.aggregationPartEntityIds;
        }
        if (rel.aggregationRelationships !== undefined && rel.aggregationRelationships !== null) {
          normalized.aggregationRelationships = rel.aggregationRelationships;
        }
      }
      
      // Remove any undefined values (JSON.stringify will omit them, but be explicit)
      Object.keys(normalized).forEach(key => {
        if (normalized[key] === undefined) {
          delete normalized[key];
        }
      });
      
      return normalized;
    })
  };
}

/**
 * Call POST /validate endpoint to validate the ER model.
 */
export async function validateModelAPI(model: ERModel): Promise<ValidationOutput> {
  // Normalize the model before sending to ensure all relationships have relationshipType
  const normalizedModel = normalizeModelForAPI(model);
  
  // Log the normalized model for debugging
  console.log("Sending normalized model to backend:", JSON.stringify(normalizedModel, null, 2));
  
  const response = await fetch(`${API_BASE_URL}/validate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(normalizedModel),
  });

  if (!response.ok) {
    // Try to get detailed error message from response
    let errorMessage = `Validation API error: ${response.status} ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        // Pydantic validation errors have a 'detail' field
        errorMessage = `Validation failed: ${JSON.stringify(errorData.detail, null, 2)}`;
      }
    } catch (e) {
      // If response is not JSON, use default message
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Call POST /render-plan endpoint to get the render plan.
 * Returns the render plan if valid, or throws with validation output if 400.
 */
export async function getRenderPlanAPI(model: ERModel): Promise<RenderPlan> {
  // Normalize the model before sending to ensure all relationships have relationshipType
  const normalizedModel = normalizeModelForAPI(model);
  
  const response = await fetch(`${API_BASE_URL}/render-plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(normalizedModel),
  });

  if (response.status === 400) {
    // Backend returns validation output on 400
    const validationOutput: ValidationOutput = await response.json();
    throw { status: 400, validation: validationOutput };
  }

  if (!response.ok) {
    throw new Error(`Render plan API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}
