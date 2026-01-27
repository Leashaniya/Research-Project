import type { ERModel, RenderPlan, ValidationOutput } from "./types";

const API_BASE_URL = "http://localhost:8000";

/**
 * Call POST /validate endpoint to validate the ER model.
 */
export async function validateModelAPI(model: ERModel): Promise<ValidationOutput> {
  const response = await fetch(`${API_BASE_URL}/validate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(model),
  });

  if (!response.ok) {
    throw new Error(`Validation API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * Call POST /render-plan endpoint to get the render plan.
 * Returns the render plan if valid, or throws with validation output if 400.
 */
export async function getRenderPlanAPI(model: ERModel): Promise<RenderPlan> {
  const response = await fetch(`${API_BASE_URL}/render-plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(model),
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
