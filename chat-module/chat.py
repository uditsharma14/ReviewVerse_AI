from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import requests
import warnings

# Ignore FutureWarning messages from libraries
warnings.filterwarnings("ignore", category=FutureWarning)


# ==========================================================
# 1. Common Qdrant Collection
# ==========================================================
# This collection stores both movie vectors and product review vectors.
COLLECTION_NAME = "reviewverse_common_review_vectors"


# ==========================================================
# 2. Embedding Model and Qdrant Client
# ==========================================================
# This model converts user questions into 384-dimensional vectors.
model = SentenceTransformer("all-MiniLM-L6-v2")

# Connect to local Qdrant vector database.
qdrant_client = QdrantClient(host="localhost", port=6333)


# ==========================================================
# 3. Ask Local LLM
# ==========================================================
def ask_llm(prompt):
    """
    Sends the final RAG prompt to the local Gemma 3 (12B) model using Ollama.
    """

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "gemma3:12b",   # Gemma 3 12B model
            "prompt": prompt,
            "stream": False
        },
        timeout=180  # Increase timeout for larger models
    )

    # Raise an exception if the request fails
    response.raise_for_status()

    # Return only the generated response
    return response.json().get("response", "")

# ==========================================================
# 4. Detect Domain from User Query
# ==========================================================
def detect_domain_from_query(query_text):
    """
    Detect whether the user query is about movies or products.

    Returns:
    - "movie"   -> search only movie vectors
    - "product" -> search only product vectors
    - None      -> search across all domains
    """

    query = query_text.lower()

    # Keywords that usually indicate movie-related intent
    movie_keywords = [
        "movie", "movies", "film", "films", "cinema",
        "actor", "actress", "director",
        "sci-fi", "science fiction", "space movie",
        "thriller", "comedy", "horror", "romance", "drama",
        "interstellar", "inception", "avatar"
    ]

    # Keywords that usually indicate product-related intent
    product_keywords = [
        "product", "products", "amazon", "review", "reviews",
        "headphones", "phone", "laptop", "battery",
        "brand", "price", "speaker", "camera",
        "keyboard", "mouse", "quality", "buy"
    ]

    # Count how many movie/product keywords appear in the query
    movie_score = sum(1 for keyword in movie_keywords if keyword in query)
    product_score = sum(1 for keyword in product_keywords if keyword in query)

    # If movie keywords dominate, search movie domain only
    if movie_score > product_score:
        return "movie"

    # If product keywords dominate, search product domain only
    if product_score > movie_score:
        return "product"

    # If unclear or mixed, search the full common collection
    return None


# ==========================================================
# 5. Retrieve Context from Qdrant
# ==========================================================
def retrieve_context_from_qdrant(query_text, limit=5, domain=None):
    """
    Converts user query into an embedding vector.
    Searches the common Qdrant collection.
    Optionally applies domain filter:
    - domain="movie"
    - domain="product"
    - domain=None searches everything
    """

    # Convert user query into vector embedding
    query_vector = model.encode(query_text).tolist()

    # By default, no filter is applied
    query_filter = None

    # If domain is detected, apply Qdrant metadata filter
    if domain:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="domain",
                    match=MatchValue(value=domain)
                )
            ]
        )

    # Search Qdrant for semantically similar vectors
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit
    )

    # Store retrieved chunks as context for LLM
    context_parts = []

    # Convert Qdrant results into readable context
    for point in results.points:
        payload = point.payload or {}

        domain_value = payload.get("domain")

        # Format movie-specific metadata
        if domain_value == "movie":
            item_name = payload.get("title")

            item_details = f"""
            Movie Title: {payload.get("title")}
            Year: {payload.get("year")}
            Genres: {payload.get("genres")}
            Average Rating: {payload.get("average_rating")}
            Rating Count: {payload.get("rating_count")}
            Tags: {payload.get("tags")}
            """

        # Format product-specific metadata
        elif domain_value == "product":
            item_name = payload.get("product_name")

            item_details = f"""
            Product Name: {payload.get("product_name")}
            Brand: {payload.get("brand")}
            Categories: {payload.get("categories")}
            Rating: {payload.get("rating")}
            Average Rating: {payload.get("average_rating")}
            Total Reviews: {payload.get("total_reviews")}
            """

        # Fallback for unknown domain
        else:
            item_name = payload.get("product_name") or payload.get("title")
            item_details = ""

        # Add one retrieved chunk to the final context
        context_parts.append(f"""
        Score: {point.score}
        Domain: {domain_value}
        Source: {payload.get("source")}
        Type: {payload.get("type")}
        Item: {item_name}

        Details:
        {item_details}

        Text:
        {payload.get("text")}
        """)

    # Join all retrieved chunks using separator
    return "\n---\n".join(context_parts)


# ==========================================================
# 6. Build RAG Prompt
# ==========================================================
def build_rag_prompt(user_question, context):
    """
    Builds the final prompt for the LLM.

    This prompt forces the LLM to answer only using retrieved context.
    """

    prompt = f"""
    You are ReviewVerse AI, a recommendation assistant.

    Use only the provided context to answer the user's question.
    Do not make up information.

    If the context contains movie data, recommend movies.
    If the context contains product review data, recommend products.
    If the context contains both, clearly separate movie and product recommendations.

    If context is not enough, say:
    "The available review data is not sufficient to answer this question."

    Context:
    {context}

    User Question:
    {user_question}

    Answer:
    """

    return prompt


# ==========================================================
# 7. Main Execution
# ==========================================================
if __name__ == "__main__":

    # Example user question
    #question = "Can you recommend some good movies similar to Interstellar with space and science fiction themes?"
    question = "Recommend a portable Bluetooth speaker with good sound quality and Alexa support"

    # Automatically detect whether query is movie/product/mixed
    detected_domain = detect_domain_from_query(question)

    # Retrieve relevant context from common Qdrant collection
    context = retrieve_context_from_qdrant(
        query_text=question,
        limit=5,
        domain=detected_domain
    )

    # Print user question and detected domain
    print("Question:", question)
    print("Detected Domain:", detected_domain)

    # Build final prompt for LLM
    prompt = build_rag_prompt(question, context)

    # Send final prompt to local LLM
    answer = ask_llm(prompt)

    # Print final answer
    print("\nAnswer:")
    print(answer)
