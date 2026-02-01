/**
 * Converts SVG string to PNG and triggers download.
 */
export async function downloadSvgStringAsPng(svgString: string, filename: string = "er-diagram.png"): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      // Create blob from SVG
      const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(svgBlob);

      // Create image element
      const img = new Image();
      
      img.onload = () => {
        try {
          // Create canvas
          const canvas = document.createElement("canvas");
          
          // Extract dimensions from SVG viewBox or use image dimensions
          const parser = new DOMParser();
          const svgDoc = parser.parseFromString(svgString, "image/svg+xml");
          const svgElement = svgDoc.documentElement;
          
          let width = img.width || 800;
          let height = img.height || 600;
          
          // Try to get viewBox dimensions (more accurate)
          const viewBox = svgElement.getAttribute("viewBox");
          if (viewBox) {
            const parts = viewBox.split(/\s+/);
            if (parts.length >= 4) {
              const vw = parseFloat(parts[2]);
              const vh = parseFloat(parts[3]);
              if (!isNaN(vw) && !isNaN(vh) && vw > 0 && vh > 0) {
                width = vw;
                height = vh;
              }
            }
          } else {
            // Fallback to width/height attributes
            const svgWidth = svgElement.getAttribute("width");
            const svgHeight = svgElement.getAttribute("height");
            if (svgWidth && svgHeight) {
              const parsedWidth = parseFloat(svgWidth.replace(/[^\d.]/g, ""));
              const parsedHeight = parseFloat(svgHeight.replace(/[^\d.]/g, ""));
              if (!isNaN(parsedWidth) && parsedWidth > 0) width = parsedWidth;
              if (!isNaN(parsedHeight) && parsedHeight > 0) height = parsedHeight;
            }
          }
          
          // Set canvas dimensions (use 2x for better quality)
          const scale = 2;
          canvas.width = width * scale;
          canvas.height = height * scale;
          
          // Draw image on canvas
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            throw new Error("Failed to get canvas context");
          }
          
          // Scale context for high DPI
          ctx.scale(scale, scale);
          ctx.drawImage(img, 0, 0, width, height);
          
          // Convert to blob and download
          canvas.toBlob(
            (blob) => {
              if (!blob) {
                reject(new Error("Failed to create PNG blob"));
                return;
              }
              
              const pngUrl = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = pngUrl;
              link.download = filename;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              
              // Cleanup
              URL.revokeObjectURL(url);
              URL.revokeObjectURL(pngUrl);
              
              resolve();
            },
            "image/png",
            1.0
          );
        } catch (err) {
          URL.revokeObjectURL(url);
          reject(err);
        }
      };
      
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Failed to load SVG image"));
      };
      
      img.src = url;
    } catch (err) {
      reject(err);
    }
  });
}
