"""Ingestion module for processing documents and building vectorstores."""

from .document_processor import create_documents_from_items
from .vectorstore_builder import ingest_lectures_folder

__all__ = ["create_documents_from_items", "ingest_lectures_folder"]

