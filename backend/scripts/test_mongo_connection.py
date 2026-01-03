import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add parent directory to path to import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import settings

async def test_connection():
    uri = settings.MONGO_URI
    db_name = settings.MONGO_DB_NAME
    
    print(f"🔌 Attempting to connect to: {uri}")
    print(f"📂 Database: {db_name}")
    
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        # The ismaster command is cheap and does not require auth.
        await client.admin.command('ismaster')
        print("✅ MongoDB connection successful!")
        
        db = client[db_name]
        collections = await db.list_collection_names()
        print(f"📊 Collections found: {collections}")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Tip: Check your MongoDB Atlas 'Network Access' settings. Your current IP might not be whitelisted.")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_connection())
