from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient


# Embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Qdrant connection
qdrant_client = QdrantClient(host="localhost", port=6333)


def retrieve_context_from_qdrant(query_text, collection_name, limit=5):
    """
    Step 1:
    Convert user question into embedding.
    Search Qdrant.
    Return relevant chunks.
    """

    query_vector = model.encode(query_text).tolist()

    results = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit
    )

    context_parts = []

    for point in results.points:
        payload = point.payload

        context_parts.append(f"""
        Source: {payload.get("source")}
        Product/Movie: {payload.get("product_name") or payload.get("title")}
        Rating: {payload.get("rating") or payload.get("average_rating")}
        Text: {payload.get("text")}
        """)

    return "\n---\n".join(context_parts)


def build_rag_prompt(user_question, context):
    """
    Step 2:
    Create final prompt for LLM.
    """

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


if __name__ == "__main__":

    question = "Recommend headphones with good battery life and clear sound"

    context = retrieve_context_from_qdrant(
        query_text=question,
        collection_name="reviewverse_amazon_review_vectors",
        limit=5
    )

    prompt = build_rag_prompt(question, context)

    print(prompt)