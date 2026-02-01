import type { ERModel, RenderPlan, RenderNode, RenderEdge, AttributeNode } from "./types";

/**
 * FigmaImport payload structure for ER diagram export.
 * This format will be consumed by a Figma plugin to render the diagram.
 */
export interface FigmaImportPayload {
  version: string;
  diagramType: "chen-er";
  model: ERModel;
  renderPlan: {
    nodes: Array<{
      id: string;
      type: "entity" | "relationship";
      label: string;
      x: number;
      y: number;
      w: number;
      h: number;
    }>;
    edges: Array<{
      id: string;
      from: string;
      to: string;
      labelNearFrom: string;
      labelNearTo: string;
    }>;
    attributeNodes: Array<{
      id: string;
      ownerId: string;
      label: string;
      x: number;
      y: number;
    }>;
  };
}

/**
 * Converts a RenderPlan and ERModel to FigmaImport JSON payload.
 */
export function generateFigmaImportPayload(
  model: ERModel,
  renderPlan: RenderPlan
): FigmaImportPayload {
  return {
    version: "1.0",
    diagramType: "chen-er",
    model: model,
    renderPlan: {
      nodes: renderPlan.nodes.map((node) => ({
        id: node.id,
        type: node.type,
        label: node.label,
        x: node.x,
        y: node.y,
        w: node.w,
        h: node.h,
      })),
      edges: renderPlan.edges.map((edge) => ({
        id: edge.id,
        from: edge.from,
        to: edge.to,
        labelNearFrom: edge.labelNearFrom,
        labelNearTo: edge.labelNearTo,
      })),
      attributeNodes: renderPlan.attributeNodes.map((attr) => ({
        id: attr.id,
        ownerId: attr.ownerId,
        label: attr.label,
        x: attr.x,
        y: attr.y,
      })),
    },
  };
}

/**
 * Copies text to clipboard.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    console.error("Failed to copy to clipboard:", err);
    // Fallback for older browsers
    try {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      return true;
    } catch (fallbackErr) {
      console.error("Fallback copy failed:", fallbackErr);
      return false;
    }
  }
}

/**
 * Downloads a JSON file.
 */
export function downloadJsonFile(json: object, filename: string): void {
  const jsonString = JSON.stringify(json, null, 2);
  const blob = new Blob([jsonString], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
