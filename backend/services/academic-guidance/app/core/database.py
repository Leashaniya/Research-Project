"""MongoDB database connection and utilities."""

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.core.config import settings

logger = logging.getLogger(__name__)

# Global MongoDB client and database instances
_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_database() -> Database:
    """Get or create MongoDB database connection."""
    global _client, _db
    
    if _db is None:
        if not settings.MONGO_URI:
            raise ValueError("MONGO_URI environment variable is not set")
        
        try:
            _client = MongoClient(settings.MONGO_URI)
            _db = _client[settings.MONGO_DB_NAME]
            # Test connection
            _client.admin.command('ping')
            logger.info(f"Connected to MongoDB: {settings.MONGO_DB_NAME}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}", exc_info=True)
            raise
    
    return _db


def close_database():
    """Close MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")
