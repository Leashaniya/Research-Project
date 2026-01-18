"""RAG chain creation and configuration."""

import logging
import re
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from app.core.config import settings


logger = logging.getLogger(__name__)

# Try different import paths for create_retrieval_chain based on LangChain version
try:
    from langchain.chains.retrieval import create_retrieval_chain
    USE_CREATE_RETRIEVAL_CHAIN = True
except ImportError:
    try:
        from langchain_classic.chains.retrieval_qa.base import create_retrieval_chain
        USE_CREATE_RETRIEVAL_CHAIN = True
    except ImportError:
        USE_CREATE_RETRIEVAL_CHAIN = False


def create_rag_chain(
    vectorstore: FAISS,
    model_name: str = "gpt-4o-mini",
):
    """
    Create a RAG chain from a vectorstore with robust image retrieval.
    """

    try:
        # 🔹 Retriever for answer context (small k)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

        # 🔹 Retriever for images only (large k)
        image_retriever = vectorstore.as_retriever(search_kwargs={"k": 80})

        # ---------------- LLM ----------------
        llm = ChatOpenAI(
            model=model_name,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.2,
        )

        # ---------------- Prompt ----------------
        prompt = ChatPromptTemplate.from_template(
            """
Use the following context to answer the question.
If images are present, mention that related image(s) were found.

Context:
{context}

Question: {question}
"""
        )

        # ---------------- Image extraction ----------------
        def extract_images_from_docs(docs):
            image_names = []

            for doc in docs:
                # 1) From metadata
                if doc.metadata:
                    image_path = doc.metadata.get("image_path")
                    if image_path:
                        image_names.append(Path(image_path).name)

                # 2) From placeholder text
                matches = re.findall(r"\[IMAGE:\s*([^\]]+)\]", doc.page_content or "")
                for m in matches:
                    image_names.append(m.strip())

            # dedupe while preserving order
            return list(dict.fromkeys(image_names))

        # ---------------- Chain creation ----------------
        if USE_CREATE_RETRIEVAL_CHAIN:
            base_chain = create_retrieval_chain(
                retriever=retriever,
                combine_documents_chain=prompt | llm,
            )

            class RAGChainWithImages:
                def __init__(self, base_chain, retriever, image_retriever):
                    self.base_chain = base_chain
                    self.retriever = retriever
                    self.image_retriever = image_retriever

                def invoke(self, input_dict):
                    question = (
                        input_dict.get("question", input_dict)
                        if isinstance(input_dict, dict)
                        else input_dict
                    )

                    # 🔹 Answer docs (small k)
                    docs = self.retriever.invoke(question)

                    # 🔹 Image sweep (large k)
                    image_docs = self.image_retriever.invoke(question)
                    images = extract_images_from_docs(image_docs)

                    result = self.base_chain.invoke(input_dict)
                    result["images"] = images
                    result["docs"] = docs
                    return result

            rag_chain = RAGChainWithImages(base_chain, retriever, image_retriever)

        else:
            # ---------------- Manual LCEL fallback ----------------
            def format_docs(docs):
                return "\n\n".join(doc.page_content for doc in docs)

            class RAGChainWrapper:
                def __init__(self, retriever, image_retriever, prompt, llm):
                    self.retriever = retriever
                    self.image_retriever = image_retriever
                    self.prompt = prompt
                    self.llm = llm

                def invoke(self, input_dict):
                    question = (
                        input_dict.get("question", input_dict)
                        if isinstance(input_dict, dict)
                        else input_dict
                    )

                    docs = self.retriever.invoke(question)
                    image_docs = self.image_retriever.invoke(question)

                    images = extract_images_from_docs(image_docs)
                    context = format_docs(docs)

                    messages = self.prompt.invoke(
                        {"context": context, "question": question}
                    )
                    response = self.llm.invoke(messages)
                    answer = (
                        response.content
                        if hasattr(response, "content")
                        else str(response)
                    )

                    return {
                        "answer": answer,
                        "images": images,
                        "docs": docs,
                    }

            rag_chain = RAGChainWrapper(
                retriever, image_retriever, prompt, llm
            )

        return rag_chain

    except Exception as e:
        logger.error(f"Failed to create RAG chain: {e}", exc_info=True)
        raise
