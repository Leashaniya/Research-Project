"""Image filtering utilities to identify and keep only diagrams."""

from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import numpy as np


def is_diagram(image_path: str, min_width: int = 150, min_height: int = 150, 
               max_aspect_ratio: float = 15.0, min_aspect_ratio: float = 0.1) -> Tuple[bool, dict]:
    """
    Determine if an image is likely a diagram based on various heuristics.
    
    Args:
        image_path: Path to the image file
        min_width: Minimum width in pixels (diagrams are usually larger)
        min_height: Minimum height in pixels
        max_aspect_ratio: Maximum width/height ratio (exclude very wide/tall images)
        min_aspect_ratio: Minimum width/height ratio
        
    Returns:
        Tuple of (is_diagram: bool, metadata: dict) with filtering information
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            file_size = Path(image_path).stat().st_size
            
            metadata = {
                "width": width,
                "height": height,
                "file_size": file_size,
                "aspect_ratio": width / height if height > 0 else 0,
            }
            
            # Filter 1: Size check - diagrams are usually larger than logos/icons
            if width < min_width or height < min_height:
                metadata["filter_reason"] = "too_small"
                return False, metadata
            
            # Filter 2: Aspect ratio check - exclude very wide or very tall images
            aspect_ratio = width / height if height > 0 else 0
            if aspect_ratio > max_aspect_ratio or aspect_ratio < min_aspect_ratio:
                metadata["filter_reason"] = "extreme_aspect_ratio"
                return False, metadata
            
            # Filter 3: File size check - very small files are likely icons/logos
            if file_size < 1500:  # Less than 1.5KB
                metadata["filter_reason"] = "file_too_small"
                return False, metadata
            
            # Filter 4: Color analysis - diagrams often have fewer colors than photos
            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            img_array = np.array(img)
            
            # Count unique colors (diagrams have fewer colors than photos)
            # Resize for faster processing if image is very large
            if width * height > 1000000:  # > 1M pixels
                small_img = img.resize((width // 4, height // 4), Image.Resampling.LANCZOS)
                small_array = np.array(small_img)
            else:
                small_array = img_array
            
            # Count unique colors
            unique_colors = len(np.unique(small_array.reshape(-1, 3), axis=0))
            metadata["unique_colors"] = unique_colors
            
            # Diagrams typically have fewer colors (but not too few - that might be a logo)
            # Typical range: 10-1000 colors for diagrams, 1000+ for photos
            if unique_colors < 10:
                metadata["filter_reason"] = "too_few_colors"
                return False, metadata
            
            # Filter 5: Edge density - diagrams often have more defined edges
            # Convert to grayscale for edge detection
            gray = img.convert("L")
            gray_array = np.array(gray)
            
            # Simple edge detection using gradient
            # Calculate horizontal and vertical gradients
            h_gradient = np.abs(np.diff(gray_array, axis=1))
            v_gradient = np.abs(np.diff(gray_array, axis=0))
            
            # Edge density (percentage of pixels with significant gradients)
            edge_threshold = 30  # Adjust based on testing
            h_edges = np.sum(h_gradient > edge_threshold) / h_gradient.size
            v_edges = np.sum(v_gradient > edge_threshold) / v_gradient.size
            edge_density = (h_edges + v_edges) / 2
            
            metadata["edge_density"] = edge_density
            
            # Diagrams typically have moderate to high edge density
            # Very low edge density might indicate a photo or gradient background
            if edge_density < 0.01:  # Less than 1% edge pixels
                metadata["filter_reason"] = "low_edge_density"
                return False, metadata
            
            # Filter 6: Check if image is mostly white/light (common in diagrams)
            # Calculate average brightness
            brightness = np.mean(gray_array)
            metadata["brightness"] = brightness
            
            # All checks passed - likely a diagram
            metadata["filter_reason"] = "passed"
            return True, metadata
            
    except Exception as e:
        # If we can't analyze the image, exclude it to be safe
        return False, {"error": str(e), "filter_reason": "analysis_failed"}


def filter_diagrams(image_paths: list[str], **filter_kwargs) -> Tuple[list[str], list[dict]]:
    """
    Filter a list of image paths to keep only diagrams.
    
    Args:
        image_paths: List of image file paths
        **filter_kwargs: Additional arguments to pass to is_diagram()
        
    Returns:
        Tuple of (filtered_image_paths, metadata_list)
    """
    filtered_paths = []
    metadata_list = []
    
    for img_path in image_paths:
        is_diag, metadata = is_diagram(img_path, **filter_kwargs)
        metadata["path"] = img_path
        metadata_list.append(metadata)
        
        if is_diag:
            filtered_paths.append(img_path)
        else:
            # Optionally delete filtered images to save space
            # Uncomment if you want to delete non-diagram images
            # try:
            #     Path(img_path).unlink()
            # except Exception:
            #     pass
            pass
    
    return filtered_paths, metadata_list

