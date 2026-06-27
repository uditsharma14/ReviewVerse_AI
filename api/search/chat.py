from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
import requests
import warnings

# Ignore FutureWarning messages from libraries
warnings.filterwarnings("ignore", category=FutureWarning)


# This function sends the final RAG prompt to the local LLM using Ollama
def ask_llm(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2",   # Local LLM model name
            "prompt": prompt,      # Final prompt with context + user question
            "stream": False        # Return complete response at once
        }
    )

    # Extract only the generated answer from Ollama response
    return response.json()["response"]


# Load embedding model
# This model converts text into vector embeddings
model = SentenceTransformer("all-MiniLM-L6-v2")


# Create Qdrant client connection
# Qdrant is your vector database running locally
qdrant_client = QdrantClient(host="localhost", port=6333)


def retrieve_context_from_qdrant(query_text, collection_name, limit=5):
    """
    Step 1:
    Convert user question into embedding.
    Search similar vectors in Qdrant.
    Return relevant review/movie chunks as context.
    """

    # Convert user question into vector format
    query_vector = model.encode(query_text).tolist()

    # Search Qdrant collection for similar vectors
    results = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit
    )

    # Store retrieved text chunks here
    context_parts = []

    # Loop through Qdrant search results
    for point in results.points:
        payload = point.payload

        # Build readable context from metadata stored in Qdrant
        context_parts.append(f"""
        Source: {payload.get("source")}
        Product/Movie: {payload.get("product_name") or payload.get("title")}
        Rating: {payload.get("rating") or payload.get("average_rating")}
        Text: {payload.get("text")}
        """)

    # Join all chunks with separator
    return "\n---\n".join(context_parts)


def build_rag_prompt(user_question, context):
    """
    Step 2:
    Create final prompt for LLM using retrieved context.
    """

    # This prompt tells the LLM how to answer
    # It forces the model to use only retrieved context
    prompt = f"""
    You are ReviewVerse AI, a recommendation assistant.

    Use only the provided context to answer the user's question.
    Do not make up information.
    If context is not enough, say that the available review data is not sufficient.

    Context:
    {context}

    User Question:
    {user_question}

    Answer:
    """

    return prompt


# Main execution starts here
if __name__ == "__main__":

    # User question
    question = "Can you recommend some good movies similar to Interstellar with space and science fiction themes?"

    # Retrieve relevant context from Qdrant
    context = retrieve_context_from_qdrant(
        query_text=question,
        collection_name="reviewverse_movie_review_vectors",
        limit=5
    )

    # Print original question
    print("Question:", question)

    # Build final RAG prompt
    prompt = build_rag_prompt(question, context)

    # Send prompt to LLM and get answer
    answer = ask_llm(prompt)

    # Print final LLM response
    print(answer)
