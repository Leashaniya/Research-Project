import os
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class Database:
    client: AsyncIOMotorClient = None

    def connect(self):
        """Establish connection to MongoDB."""
        if not self.client:
            print(f"Connecting to MongoDB at {settings.MONGO_URI}...")
            self.client = AsyncIOMotorClient(settings.MONGO_URI)
            print("MongoDB Connected.")

    def close(self):
        """Close connection."""
        if self.client:
            self.client.close()
            print("🛑 MongoDB Connection Closed.")

    def get_db(self):
        """Get the database instance."""
        if not self.client:
            self.connect()
        return self.client[settings.MONGO_DB_NAME]

db = Database()
