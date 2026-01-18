# # import requests

# # url = "http://localhost:11434/api/generate"

# # payload = {
# #     "model": "llama3:latest",  # or "llama3:latest"
# #     "prompt": "Summarize the following lecture content in bullet points:\n\n"
# #               "Normalization is a database design technique that reduces data redundancy "
# #               "and improves data integrity. It organizes data using normal forms such as "
# #               "1NF, 2NF, and 3NF.",
# #     "stream": False
# # }

# # response = requests.post(url, json=payload)

# # print(response.status_code)
# # print(response.json())   # 👈 PRINT EVERYTHING

# # from app.ca_guidance.tools.rag_tool import summarize_lecture_materials

# # result = summarize_lecture_materials.run("isa relationship")
# # print(result)

# # from app.ca_guidance.rag.ingestion.vectorstore_builder import load_vectorstore
# # from app.ca_guidance.rag.config.settings import VECTORSTORE_DIR

# # def inspect_vectorstore(n=5):
# #     vs = load_vectorstore(VECTORSTORE_DIR)
# #     if vs is None:
# #         print("❌ Vectorstore not found")
# #         return

# #     print("✅ Vectorstore type:", type(vs))
# #     print("✅ Total vectors (index size):", vs.index.ntotal)

# #     # langchain FAISS store internals:
# #     # - vs.docstore._dict holds the Documents
# #     # - vs.index_to_docstore_id maps FAISS positions to doc IDs
# #     doc_ids = list(vs.docstore._dict.keys())
# #     print("✅ Total documents in docstore:", len(doc_ids))

# #     print("\n--- Sample documents ---")
# #     for i, doc_id in enumerate(doc_ids[:n], start=1):
# #         doc = vs.docstore._dict[doc_id]
# #         print(f"\n[{i}] doc_id={doc_id}")
# #         print("metadata keys:", list(doc.metadata.keys()))
# #         print("metadata:", doc.metadata)
# #         print("content preview:", doc.page_content[:250].replace("\n", " "), "...")
        
# #         # specifically check images
# #         imgs = doc.metadata.get("images") or doc.metadata.get("image") or doc.metadata.get("image_paths")
# #         if imgs:
# #             print("📸 images field:", imgs)

# # if __name__ == "__main__":
# #     inspect_vectorstore(n=20)


# from app.ca_guidance.rag.ingestion.vectorstore_builder import load_vectorstore
# from app.ca_guidance.rag.config.settings import VECTORSTORE_DIR

# vs = load_vectorstore(VECTORSTORE_DIR)

# count_with_images = 0
# sample = None

# for doc in vs.docstore._dict.values():
#     if "images" in doc.metadata and doc.metadata["images"]:
#         count_with_images += 1
#         if sample is None:
#             sample = doc.metadata["images"]

# print("Total docs:", len(vs.docstore._dict))
# print("Docs with images metadata:", count_with_images)
# print("Sample images:", sample)


# from app.ca_guidance.rag.ingestion.vectorstore_builder import load_vectorstore
# from app.ca_guidance.rag.config.settings import VECTORSTORE_DIR

# vs = load_vectorstore(VECTORSTORE_DIR)
# docs = vs.similarity_search("Fan trap", k=5)

# print("Total retrieved:", len(docs))
# print("Image docs in topK:", sum(1 for d in docs if "image_path" in (d.metadata or {})))

# for d in docs:
#     if "image_path" in (d.metadata or {}):
#         print("IMAGE HIT:", d.metadata["image_path"])


# from app.ca_guidance.tools.rag_tool import (
#     _get_rag_chain,
#     _extract_context_text,
#     _verify_summary_accuracy
# )

# def test_summary_accuracy_checker():
#     print("TEST STARTED", flush=True)

#     rag_chain = _get_rag_chain()
#     assert rag_chain is not None, "RAG chain not initialized"
#     print("RAG CHAIN READY", flush=True)

#     # Normal topic
#     result = rag_chain.invoke({"question": "Summarize Fan Trap"})
#     summary = result.get("answer", "")
#     context = _extract_context_text(result)

#     check = _verify_summary_accuracy(
#         summary=summary,
#         context_text=context,
#         topic="Fan Trap"
#     )

#     print("\n=== ACCURACY CHECK (VALID TOPIC) ===", flush=True)
#     print(check, flush=True)

#     # Hallucination test
#     bad_result = rag_chain.invoke(
#         {"question": "Summarize Fan Trap in quantum computing"}
#     )
#     bad_summary = bad_result.get("answer", "")
#     bad_context = _extract_context_text(bad_result)

#     bad_check = _verify_summary_accuracy(
#         summary=bad_summary,
#         context_text=bad_context,
#         topic="Fan Trap (Quantum Computing)"
#     )

#     print("\n=== ACCURACY CHECK (HALLUCINATION TEST) ===", flush=True)
#     print(bad_check, flush=True)

#     assert "report" in check
#     assert "report" in bad_check
#     assert "rouge_1" in check
#     assert "rouge_2" in check
#     assert "rouge_l" in check


# # ✅ THIS is what you asked to add
# if __name__ == "__main__":
#     test_summary_accuracy_checker()

from pymongo import MongoClient
import os
from dotenv import load_dotenv
load_dotenv()


client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME")]

db.test.insert_one({"status": "connected"})
print("MongoDB connection successful")
