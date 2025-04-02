from flask import Flask, request, session, jsonify
from flask_cors import CORS
from PyPDF2 import PdfReader
import openai
import faiss
import numpy as np
import os
import logging
from dotenv import load_dotenv
import uuid

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])

openai.api_key = os.getenv("OPENAI_API_KEY") or "your-openai-api-key-here"

# FAISS index setup
dimension = 1536
index = faiss.IndexFlatL2(dimension)
chunks = []
pdf_texts = []
chat_histories = {}

@app.route("/upload_pdfs", methods=["POST"])
def upload_pdfs():
    files = request.files.getlist("files")
    logger.debug(f"Received {len(files)} files for upload")
    session_id = session.get("session_id", str(uuid.uuid4()))
    session["session_id"] = session_id

    pdf_sessions = session.get("pdf_sessions", {})
    pdf_sessions[session_id] = pdf_sessions.get(session_id, []) + [file.filename for file in files]
    session["pdf_sessions"] = pdf_sessions

    try:
        for file in files:
            logger.debug(f"Processing file: {file.filename}")
            pdf_reader = PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                extracted_text = page.extract_text()
                text += extracted_text if extracted_text else ""
            logger.debug(f"Extracted {len(text)} characters from {file.filename}")
            pdf_texts.append((file.filename, text, session_id))
        logger.info(f"Successfully uploaded {len(files)} PDFs")
        return jsonify({"message": f"Uploaded {len(files)} PDFs successfully", "session_id": session_id})
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        return jsonify({"detail": f"Upload failed: {str(e)}"}), 500

@app.route("/process_pdfs", methods=["POST"])
def process_pdfs():
    logger.debug("Processing PDFs to create embeddings")
    session_id = session.get("session_id") or request.json.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id

    pdf_sessions = session.get("pdf_sessions", {})
    session_pdfs = pdf_sessions.get(session_id, [])
    
    global chunks, index
    chunks.clear()
    index = faiss.IndexFlatL2(dimension)

    try:
        if not pdf_texts:
            return jsonify({"detail": "No PDFs to process"}), 400

        for filename, text, sid in pdf_texts:
            if sid != session_id or filename not in session_pdfs:
                continue
            chunk_size = 1000
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                response = openai.Embedding.create(input=chunk, model="text-embedding-ada-002")
                embedding = response["data"][0]["embedding"]
                index.add(np.array([embedding], dtype="float32"))
                chunks.append({"text": chunk, "filename": filename, "session_id": sid})
        
        logger.info("Successfully created vector embeddings")
        return jsonify({"message": "Vector embeddings created", "session_id": session_id})
    except Exception as e:
        logger.error(f"Embedding creation failed: {str(e)}", exc_info=True)
        return jsonify({"detail": f"Embedding creation failed: {str(e)}"}), 500

@app.route("/query", methods=["POST"])
def query():
    data = request.json
    logger.debug(f"Received query: {data}")
    session_id = session.get("session_id")
    if not session_id:
        return jsonify({"detail": "No session found"}), 400

    try:
        query = data.get("query", "").strip().lower()
        use_vector_db = data.get("useVectorDB", False)
        use_llm = data.get("useLLM", False)

        if not query:
            return jsonify({"detail": "Query is required"}), 400

        # List of common greetings
        greetings = {"hello", "hi", "hey", "how are you", "good morning", "good evening", "good night", "thank you", "thanks"}
    
        # If the query is a greeting, trigger LLM API to generate a friendly response
        if any(greeting in query for greeting in greetings):
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": query}],
                max_tokens=50
            )
            return jsonify({"answer": response.choices[0].message.content.strip()})

        # If LLM is not enabled, return a response
        if not use_llm:
            return jsonify({"answer": "LLM is not connected"})

        # If vector DB is not enabled or empty, return a default response
        if not use_vector_db or index.ntotal == 0:
            return jsonify({"answer": f"Ooops, Can't find anything related to '{query}' in the given PDFs. Wanna try something else?"})

        # Process query with FAISS
        response = openai.Embedding.create(input=query, model="text-embedding-ada-002")
        query_embedding = np.array([response["data"][0]["embedding"]], dtype="float32")
        distances, indices = index.search(query_embedding, 3)
        relevant_chunks = [chunks[i] for i in indices[0] if i < len(chunks)]

        # Prioritize chunks from the most recent PDFs
        pdf_sessions = session.get("pdf_sessions", {})
        session_pdfs = pdf_sessions.get(session_id, [])
        prioritized_chunks = sorted(
            relevant_chunks,
            key=lambda x: session_pdfs.index(x["filename"]) if x["filename"] in session_pdfs else -1,
            reverse=True
        )
        context = "\n".join(chunk["text"] for chunk in prioritized_chunks[:3])

        # If no relevant information is found, handle it gracefully
        if not context.strip():
            return jsonify({"answer": f"Ooops, Can't find anything related to '{query}' in the given PDFs. Wanna try something else?"})

        # Include chat history and context for LLM
        chat_history = chat_histories.get(session_id, [])
        history_text = "\n".join([f"Q: {h['query']}\nA: {h['answer']}" for h in chat_history[-3:]])
        prompt = (
            "You are an assistant that answers questions strictly based on the provided document context. "
            "If the context doesn’t contain relevant information, do not generate an answer from general knowledge. "
            f"Chat History:\n{history_text}\n\nDocument Context:\n{context}\n\nQuery: {query}"
     )   

        # Call OpenAI LLM
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Answer only based on the provided document context. If the context is insufficient, say 'No relevant information found in the PDFs.'"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        answer = response.choices[0].message.content.strip()

        # If LLM still doesn’t find anything relevant, override with custom message
        if "no relevant information found" in answer.lower():
            answer = f"Oops, Can't find anything related to '{query}' in the given PDFs. Wanna try something else?"

        chat_histories[session_id] = chat_histories.get(session_id, []) + [{"query": query, "answer": answer}]
    
        return jsonify({"answer": answer})

    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        return jsonify({"detail": f"Query failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
