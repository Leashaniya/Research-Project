"""Vectorstore building logic for creating FAISS indexes from documents."""

from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import faiss

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore

from app.ca_guidance.rag.config.settings import LECTURES_DIR, VECTORSTORE_DIR, TEXT_EMBED_MODEL_NAME, IMAGE_MODEL_NAME, DEVICE, TARGET_DIM
from app.ca_guidance.rag.extractors.pdf_extractor import extract_from_pdf
from app.ca_guidance.rag.embeddings.combined_embeddings import CombinedEmbeddings
from app.ca_guidance.rag.ingestion.document_processor import create_documents_from_items


def ingest_lectures_folder(lectures_dir: Path = LECTURES_DIR, vectorstore_dir: Path = VECTORSTORE_DIR, force_rebuild: bool = False):
    """
    Ingest all PDFs from a folder and create a FAISS vectorstore.
    If a saved vectorstore exists, it will be loaded instead of rebuilding.
    
    Args:
        lectures_dir: Path to directory containing PDF files
        vectorstore_dir: Path to directory where vectorstore will be saved/loaded
        force_rebuild: If True, rebuild the vectorstore even if a saved one exists
        
    Returns:
        FAISS vectorstore with embedded documents
    """
    # Check if vectorstore already exists
    vectorstore_path = vectorstore_dir / "index.faiss"
    if not force_rebuild and vectorstore_path.exists():
        print(f"Loading existing vectorstore from {vectorstore_dir}...")
        try:
            combined_embeddings = CombinedEmbeddings(TEXT_EMBED_MODEL_NAME, IMAGE_MODEL_NAME, device=DEVICE)
            
            class SimpleEmbFunc:
                def __init__(self, adapter):
                    self.adapter = adapter
                def embed_query(self, q):
                    return np.array(self.adapter.embed_query(q), dtype=np.float32)
            
            emb_func = SimpleEmbFunc(combined_embeddings)
            
            # FAISS.load_local expects an Embeddings object or callable
            # We need to pass the embed_query method as a callable
            def embedding_func(text: str):
                return emb_func.embed_query(text)
            
            vectorstore = FAISS.load_local(
                folder_path=str(vectorstore_dir),
                embeddings=embedding_func,
                index_name="index",
                allow_dangerous_deserialization=True
            )
            print(f"Loaded vectorstore with {vectorstore.index.ntotal} vectors.")
            return vectorstore
        except Exception as e:
            print(f"Failed to load existing vectorstore: {e}")
            print("Rebuilding vectorstore...")
    all_items = []
    for pdf_path in lectures_dir.glob("**/*.pdf"):
        print("Processing", pdf_path)
        items = extract_from_pdf(pdf_path)
        all_items.extend(items)
    
    # Convert items to Documents
    documents = create_documents_from_items(all_items)

    # split long text docs into chunks for retrieval
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = splitter.split_documents(documents)

    # Build combined embeddings object
    combined_embeddings = CombinedEmbeddings(TEXT_EMBED_MODEL_NAME, IMAGE_MODEL_NAME, device=DEVICE)

    # For FAISS.from_documents we need an embedding object that handles text-only documents.
    # We'll first create embeddings for textual docs (text + tables + image placeholders)
    text_docs = []
    for d in splits:
        # For image placeholders we still keep the placeholder text so they can be retrieved by text queries (but we will also add image embeddings to the vectorstore separately).
        text_docs.append(d)

    # create a list of strings for embed_documents
    text_strings = [d.page_content for d in text_docs]
    text_embeddings = combined_embeddings.embed_documents(text_strings)

    # Build FAISS index manually from embeddings and metadata
    # We'll map our text_embeddings (shape N x TARGET_DIM) into a float32 numpy array
    text_emb_arr = np.array(text_embeddings, dtype=np.float32)
    # If embedding dims differ from TARGET_DIM ensure shape ok; here they are TARGET_DIM
    dim = text_emb_arr.shape[1]
    index = faiss.IndexFlatIP(dim)  # use inner-product on normalized vectors -> equivalent to cosine
    # normalize vectors
    norms = np.linalg.norm(text_emb_arr, axis=1, keepdims=True)
    text_emb_arr = text_emb_arr / (norms + 1e-12)
    index.add(text_emb_arr)

    # Create the FAISS vectorstore object directly
    # FAISS constructor for langchain-community requires index and embedding function
    # We'll create a minimal embedding function wrapper with embed_query
    class SimpleEmbFunc:
        def __init__(self, adapter):
            self.adapter = adapter
        def embed_query(self, q):
            return np.array(self.adapter.embed_query(q), dtype=np.float32)

    emb_func = SimpleEmbFunc(combined_embeddings)

    # Build an id->doc mapping for docstore
    ids = [str(i) for i in range(len(text_docs))]  # simple string ids
    docstore = InMemoryDocstore()
    index_to_docstore_id = {i: ids[i] for i in range(len(text_docs))}
    
    # Manually populate the docstore's internal dictionary
    # InMemoryDocstore uses an internal _dict to store documents
    for i, doc in enumerate(text_docs):
        docstore._dict[ids[i]] = doc

    # create langchain FAISS instance with required parameters
    # Create a callable wrapper for the embedding function
    def embedding_func(text: str):
        return emb_func.embed_query(text)
    
    vectorstore = FAISS(
        index=index,
        embedding_function=embedding_func,
        docstore=docstore,
        index_to_docstore_id=index_to_docstore_id
    )

    # If you want to add image embeddings too: find image items and embed and add to index
    image_items = [it for it in all_items if it["type"] == "image"]
    if image_items:
        image_paths = [it["path"] for it in image_items]
        img_embs = combined_embeddings.embed_images(image_paths)  # shape M x TARGET_DIM
        img_emb_arr = np.array(img_embs, dtype=np.float32)
        img_emb_arr = img_emb_arr / (np.linalg.norm(img_emb_arr, axis=1, keepdims=True) + 1e-12)
        # add to index
        start_idx = len(text_docs)
        index.add(img_emb_arr)
        # and add corresponding documents to docstore
        for i, it in enumerate(image_items):
            doc_meta = it["metadata"].copy()
            doc_meta["image_path"] = it["path"]
            doc = Document(page_content=f"[IMAGE: {Path(it['path']).name}]", metadata=doc_meta)
            doc_id = str(start_idx + i)
            vectorstore.docstore._dict[doc_id] = doc
            vectorstore.index_to_docstore_id[start_idx + i] = doc_id

    print("Ingestion complete. FAISS size:", index.ntotal)
    
    # Save vectorstore to disk
    print(f"Saving vectorstore to {vectorstore_dir}...")
    vectorstore.save_local(folder_path=str(vectorstore_dir), index_name="index")
    print("Vectorstore saved successfully.")
    
    return vectorstore


def load_vectorstore(vectorstore_dir: Path = VECTORSTORE_DIR):
    """
    Load an existing vectorstore from disk.
    
    Args:
        vectorstore_dir: Path to directory where vectorstore is saved
        
    Returns:
        FAISS vectorstore or None if not found
    """
    import logging
    logger = logging.getLogger(__name__)
    
    vectorstore_path = vectorstore_dir / "index.faiss"
    if not vectorstore_path.exists():
        return None
    
    try:
        from app.ca_guidance.rag.embeddings.text_embeddings import TextEmbeddings
        from app.ca_guidance.rag.config.settings import TEXT_EMBED_MODEL_NAME, DEVICE
        
        text_embeddings = TextEmbeddings(TEXT_EMBED_MODEL_NAME, device=DEVICE)
        
        class SimpleEmbFunc:
            def __init__(self, adapter):
                self.adapter = adapter
            def embed_query(self, q):
                return np.array(self.adapter.embed_query(q), dtype=np.float32)
        
        emb_func = SimpleEmbFunc(text_embeddings)
        
        def embedding_func(text: str):
            return emb_func.embed_query(text)
        
        vectorstore = FAISS.load_local(
            folder_path=str(vectorstore_dir),
            embeddings=embedding_func,
            index_name="index",
            allow_dangerous_deserialization=True
        )
        logger.info(f"Loaded vectorstore with {vectorstore.index.ntotal} vectors")
        return vectorstore
    except Exception as e:
        logger.error(f"Failed to load vectorstore: {e}", exc_info=True)
        return None

