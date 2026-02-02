/**
 * Utility to convert SVG string to PNG and trigger download.
 */

/**
 * Parse dimension value, handling units like "pt", "px", "em", etc.
 * Graphviz often uses "pt" (points) where 1pt = 1.333px
 */
function parseDimension(value: string | null): number | null {
  if (!value) return null;
  
  const match = value.match(/^([\d.]+)(pt|px|em|%)?$/);
  if (!match) return null;
  
  const num = parseFloat(match[1]);
  const unit = match[2] || "px";
  
  // Convert to pixels
  switch (unit) {
    case "pt":
      return num * 1.333; // 1pt = 1.333px
    case "em":
      return num * 16; // Assume 16px base font
    case "%":
      return null; // Can't convert percentage without context
    default:
      return num;
  }
}

export async function downloadSvgStringAsPng(
  svgString: string,
  filename: string = "diagram.png"
): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      // Parse SVG to get and fix dimensions
      const parser = new DOMParser();
      const svgDoc = parser.parseFromString(svgString, "image/svg+xml");
      const svgElement = svgDoc.documentElement;

      // Get dimensions from width/height attributes (Graphviz uses these)
      let width = parseDimension(svgElement.getAttribute("width"));
      let height = parseDimension(svgElement.getAttribute("height"));

      // Try viewBox if width/height not available
      const viewBox = svgElement.getAttribute("viewBox");
      if (viewBox) {
        const parts = viewBox.split(/[\s,]+/).map(Number).filter(n => !isNaN(n));
        if (parts.length >= 4) {
          // viewBox format: minX minY width height
          if (!width) width = parts[2];
          if (!height) height = parts[3];
        }
      }

      // Fallback defaults
      if (!width || width <= 0) width = 800;
      if (!height || height <= 0) height = 600;

      // Add padding
      const padding = 20;
      width += padding * 2;
      height += padding * 2;

      // Modify SVG to have explicit pixel dimensions for proper rendering
      svgElement.setAttribute("width", `${width}px`);
      svgElement.setAttribute("height", `${height}px`);
      
      // Ensure viewBox covers the content
      if (!viewBox) {
        svgElement.setAttribute("viewBox", `0 0 ${width} ${height}`);
      }

      // Serialize the modified SVG
      const serializer = new XMLSerializer();
      const modifiedSvgString = serializer.serializeToString(svgElement);

      // Create a Blob from the modified SVG string
      const svgBlob = new Blob([modifiedSvgString], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(svgBlob);

      // Create an Image to load the SVG
      const img = new Image();
      
      img.onload = () => {
        // Scale for better quality (2x)
        const scale = 2;
        const canvas = document.createElement("canvas");
        canvas.width = width * scale;
        canvas.height = height * scale;

        const ctx = canvas.getContext("2d");
        if (!ctx) {
          URL.revokeObjectURL(url);
          reject(new Error("Failed to get canvas context"));
          return;
        }

        // Fill with white background
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw the image scaled up
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        // Convert to PNG and download
        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(url);

            if (!blob) {
              reject(new Error("Failed to create PNG blob"));
              return;
            }

            // Create download link
            const downloadUrl = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = downloadUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(downloadUrl);

            resolve();
          },
          "image/png",
          1.0
        );
      };

      img.onerror = (e) => {
        URL.revokeObjectURL(url);
        console.error("Image load error:", e);
        reject(new Error("Failed to load SVG image"));
      };

      img.src = url;
    } catch (error) {
      reject(error);
    }
  });
}
