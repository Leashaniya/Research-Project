"""RAG chain creation and configuration."""

import logging
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


def create_rag_chain(vectorstore: FAISS, model_name: str = "gpt-4o-mini",provider: str = "openai",base_url: str | None = None):
    """
    Create a RAG chain from a vectorstore.
    
    Args:
        vectorstore: FAISS vectorstore with embedded documents
        model_name: Name of the OpenAI model to use
        
    Returns:
        RAG chain that can be invoked with {"question": "..."}
    """
    try:
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) #5
        
        if provider == "ollama":
            llm = ChatOpenAI(model=model_name,                          # e.g. llama3:latest
            base_url=base_url or settings.OLLAMA_BASE_URL,  # http://localhost:11434/v1
            api_key="ollama",                          # dummy key required by client
            temperature=0.2,
            )
        else:
            llm = ChatOpenAI(
                model=model_name,                          # e.g. gpt-4o-mini
                api_key=settings.OPENAI_API_KEY,
                temperature=0.2,
            )



        prompt = ChatPromptTemplate.from_template("""
        Use the following context to answer the question. If images are present, mention that image(s) were found and refer to their metadata.
        Context:
        {context}

        Question: {question}
        """)

        # Use create_retrieval_chain if available, otherwise build manually with LCEL
        if USE_CREATE_RETRIEVAL_CHAIN:
            # Wrap to extract images
            def extract_images_from_docs(docs):
                """Extract image filenames from retrieved documents."""
                from pathlib import Path
                image_names = []
                for doc in docs:
                    if hasattr(doc, 'metadata') and doc.metadata:
                        image_path = doc.metadata.get('image_path')
                        if image_path:
                            # Extract just the filename
                            img_name = Path(image_path).name
                            image_names.append(img_name)
                return list(set(image_names))  # Remove duplicates
            
            base_chain = create_retrieval_chain(
                retriever=retriever,
                combine_documents_chain=prompt | llm
            )
            
            # Wrap to add image extraction
            class RAGChainWithImages:
                def __init__(self, base_chain, retriever):
                    self.base_chain = base_chain
                    self.retriever = retriever
                
                def invoke(self, input_dict):
                    question = input_dict.get("question", input_dict) if isinstance(input_dict, dict) else input_dict
                    docs = self.retriever.invoke(question)
                    images = extract_images_from_docs(docs)
                    result = self.base_chain.invoke(input_dict)
                    result["images"] = images
                    result["docs"] = docs
                    return result
            
            rag_chain = RAGChainWithImages(base_chain, retriever)
        else:
            # Build RAG chain manually using LCEL (LangChain Expression Language)
            def format_docs(docs):
                return "\n\n".join(doc.page_content for doc in docs)
            
            def extract_images_from_docs(docs):
                """Extract image filenames from retrieved documents."""
                from pathlib import Path
                image_names = []
                for doc in docs:
                    if hasattr(doc, 'metadata') and doc.metadata:
                        image_path = doc.metadata.get('image_path')
                        if image_path:
                            # Extract just the filename
                            img_name = Path(image_path).name
                            image_names.append(img_name)
                return list(set(image_names))  # Remove duplicates
            
            # Create a chain that accepts {"question": "..."} and returns {"answer": "...", "images": [...]}
            class RAGChainWrapper:
                def __init__(self, retriever, prompt, llm):
                    self.retriever = retriever
                    self.prompt = prompt
                    self.llm = llm
                
                def invoke(self, input_dict):
                    question = input_dict.get("question", input_dict) if isinstance(input_dict, dict) else input_dict
                    docs = self.retriever.invoke(question)
                    context = format_docs(docs)
                    images = extract_images_from_docs(docs)
                    messages = self.prompt.invoke({"context": context, "question": question})
                    response = self.llm.invoke(messages)
                    answer = response.content if hasattr(response, 'content') else str(response)
                    return {"answer": answer, "images": images, "docs": docs}
            
            rag_chain = RAGChainWrapper(retriever, prompt, llm)

        return rag_chain
    except Exception as e:
        logger.error(f"Failed to create RAG chain: {e}", exc_info=True)
        raise

