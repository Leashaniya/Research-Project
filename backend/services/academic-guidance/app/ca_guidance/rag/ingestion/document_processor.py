"""Document processing utilities for converting extracted items to LangChain Documents."""

from pathlib import Path
from typing import List, Dict, Any

from langchain_core.documents import Document


def create_documents_from_items(items: List[Dict[str, Any]]) -> List[Document]:
    """
    Convert extracted items to LangChain Document objects.
    
    Args:
        items: List of extracted items with type, content/path, and metadata
        
    Returns:
        List of LangChain Document objects
    """
    docs: List[Document] = []
    for it in items:
        if it["type"] == "text":
            # chunk long page text
            content = it["content"]
            metadata = it["metadata"]
            docs.append(Document(page_content=content, metadata=metadata))
        elif it["type"] == "table":
            content = "[TABLE]\n" + it["content"]
            metadata = it["metadata"]
            docs.append(Document(page_content=content, metadata=metadata))
        elif it["type"] == "image":
            # for images, we store a short textual placeholder and set metadata to include path
            metadata = it["metadata"].copy()
            metadata["image_path"] = it["path"]
            # Represent the image as a short caption placeholder for retrieval; actual image embeddings will be added separately.
            docs.append(Document(page_content=f"[IMAGE: {Path(it['path']).name}]", metadata=metadata))
    return docs

