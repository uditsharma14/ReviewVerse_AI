import uuid
import hashlib
import math
import pandas as pd
from sqlalchemy import create_engine
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.models import Filter, FieldCondition, MatchValue


# ==========================================================
# 1. PostgreSQL Database Connection
# ==========================================================
DB_CONNECTION = "postgresql://review_user:review_pass123@localhost:5432/review_app"
engine = create_engine(DB_CONNECTION)


# ==========================================================
# 2. Qdrant Vector Database Connection
# ==========================================================
# Make sure Qdrant is running:
# docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
qdrant_client = QdrantClient(host="localhost", port=6333)


# ==========================================================
# 3. Qdrant Collection Name
# ==========================================================
COLLECTION_NAME = "reviewverse_movie_review_vectors"


# ==========================================================
# 4. Embedding Model
# ==========================================================
# all-MiniLM-L6-v2 creates 384-dimensional embeddings.
model = SentenceTransformer("all-MiniLM-L6-v2")
VECTOR_SIZE = 384


# ==========================================================
# 5. Helper: Safe Value Handling
# ==========================================================
def safe_value(value, default=None):
    """
    Converts None/NaN values into safe values.
    This prevents Qdrant payload errors.
    """
    if value is None:
        return default

    if isinstance(value, float) and math.isnan(value):
        return default

    return value


def safe_float(value):
    """
    Safely converts value to float.
    """
    value = safe_value(value)

    if value is None or value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def safe_int(value):
    """
    Safely converts value to int.
    """
    value = safe_value(value)

    if value is None or value == "":
        return None

    try:
        return int(value)
    except Exception:
        return None


# ==========================================================
# 6. Stable Qdrant ID
# ==========================================================
def create_stable_uuid(text):
    """
    Creates stable UUID from text.

    Why this is useful:
    - If you run the script again, the same movie chunk gets the same ID.
    - Qdrant updates the existing vector instead of creating duplicates.
    """
    hash_value = hashlib.md5(text.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hash_value))


# ==========================================================
# 7. Text Chunking Function
# ==========================================================
def chunk_text(text, chunk_size=250, overlap=40):
    """
    Splits large text into smaller chunks.

    Optimization:
    - If text is small, return it as one chunk.
    - If text is large, split it with overlap to preserve context.
    """

    if text is None:
        return []

    text = str(text).strip()

    if not text:
        return []

    words = text.split()

    # Optimization: no need to chunk short movie text
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])

        if chunk.strip():
            chunks.append(chunk)

        # Move forward but keep overlap words
        start = end - overlap

        if start >= len(words):
            break

    return chunks


# ==========================================================
# 8. Create Qdrant Collection
# ==========================================================
def create_qdrant_collection():
    """
    Creates Qdrant collection if it does not already exist.
    """

    collections = qdrant_client.get_collections().collections
    existing_collections = [collection.name for collection in collections]

    if COLLECTION_NAME not in existing_collections:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )

        print(f"Created Qdrant collection: {COLLECTION_NAME}")

    else:
        print(f"Qdrant collection already exists: {COLLECTION_NAME}")


# ==========================================================
# 9. Load Movie Data from PostgreSQL
# ==========================================================
def load_movies():
    """
    Loads MovieLens data from PostgreSQL.

    Expected tables:
    - movies
    - movie_stats
    - tags

    Your current columns appear to be:
    - movies: movieId, title, genres, year, clean_title
    - movie_stats: movieId, avg_rating, rating_count
    - tags: movieId, tag
    """

    query = """
        SELECT
            m."movieId" AS movie_id,
            m.title,
            m.clean_title,
            m.genres,
            m.year,
            COALESCE(ms.avg_rating, 0) AS average_rating,
            COALESCE(ms.rating_count, 0) AS rating_count,
            COALESCE(
                STRING_AGG(DISTINCT t.tag, ', '),
                ''
            ) AS tags
        FROM movies m
        LEFT JOIN movie_stats ms
            ON m."movieId" = ms."movieId"
        LEFT JOIN tags t
            ON m."movieId" = t."movieId"
        GROUP BY
            m."movieId",
            m.title,
            m.clean_title,
            m.genres,
            m.year,
            ms.avg_rating,
            ms.rating_count
    """

    df = pd.read_sql(query, engine)

    print(f"Loaded movies: {len(df)}")

    return df


# ==========================================================
# 10. Prepare Movie Text for Embedding
# ==========================================================
def prepare_movie_text(row):
    """
    Creates meaningful movie text for embedding.

    This is the text that will be converted into a vector.
    """

    text = f"""
    Content Type: Movie
    Movie Title: {safe_value(row.get("title"), "")}
    Clean Title: {safe_value(row.get("clean_title"), "")}
    Year: {safe_value(row.get("year"), "")}
    Genres: {safe_value(row.get("genres"), "")}
    Average Rating: {safe_value(row.get("average_rating"), "")}
    Rating Count: {safe_value(row.get("rating_count"), "")}
    Tags: {safe_value(row.get("tags"), "")}
    """

    return text.strip()


# ==========================================================
# 11. Create Movie Payload for Qdrant
# ==========================================================
def create_movie_payload(row, chunk, chunk_index):
    """
    Creates metadata payload for each movie chunk.

    Payload helps later with:
    - filtering
    - ranking
    - showing movie details
    - RAG explanation
    """

    return {
        "source": "movielens",
        "type": "movie_chunk",
        "movie_id": str(safe_value(row.get("movie_id"), "")),
        "title": safe_value(row.get("title"), ""),
        "clean_title": safe_value(row.get("clean_title"), ""),
        "year": safe_int(row.get("year")),
        "genres": safe_value(row.get("genres"), ""),
        "average_rating": safe_float(row.get("average_rating")),
        "rating_count": safe_int(row.get("rating_count")),
        "tags": safe_value(row.get("tags"), ""),
        "chunk_index": chunk_index,
        "text": chunk
    }


# ==========================================================
# 12. Save Movie Embeddings into Qdrant
# ==========================================================
def save_movie_embeddings_to_qdrant(movies_df, embedding_batch_size=32):
    """
    Optimized flow:
    1. Prepare movie text
    2. Chunk text
    3. Generate embeddings in batches
    4. Insert vectors into Qdrant in batches
    5. Use stable IDs to avoid duplicate vectors
    """

    all_chunks = []
    all_payloads = []
    total_movies_processed = 0

    print("Preparing movie chunks...")

    for _, row in movies_df.iterrows():
        full_text = prepare_movie_text(row)

        chunks = chunk_text(
            text=full_text,
            chunk_size=250,
            overlap=40
        )

        for chunk_index, chunk in enumerate(chunks):
            payload = create_movie_payload(row, chunk, chunk_index)

            all_chunks.append(chunk)
            all_payloads.append(payload)

        total_movies_processed += 1

    print(f"Total movies processed: {total_movies_processed}")
    print(f"Total movie chunks created: {len(all_chunks)}")

    if not all_chunks:
        print("No movie chunks found. Nothing to insert.")
        return

    total_inserted = 0

    # Generate embeddings in batches
    for start in range(0, len(all_chunks), embedding_batch_size):
        end = start + embedding_batch_size

        chunk_batch = all_chunks[start:end]
        payload_batch = all_payloads[start:end]

        # Optimization: batch embedding instead of one-by-one embedding
        embeddings = model.encode(
            chunk_batch,
            batch_size=embedding_batch_size,
            show_progress_bar=False
        ).tolist()

        points = []

        for chunk, payload, embedding in zip(chunk_batch, payload_batch, embeddings):
            stable_id_text = f"{payload['source']}_{payload['movie_id']}_{payload['chunk_index']}"
            point_id = create_stable_uuid(stable_id_text)

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )

            points.append(point)

        # Insert batch into Qdrant
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

        total_inserted += len(points)

        print(f"Inserted movie chunks into Qdrant: {total_inserted}/{len(all_chunks)}")

    print(f"Completed. Total movie chunks inserted/updated: {total_inserted}")


# ==========================================================
# 13. Search Movies from Qdrant
# ==========================================================
def search_movies(query_text, limit=5):
    """
    Searches movie vectors from Qdrant.
    """

    query_vector = model.encode(query_text).tolist()

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value="movielens")
                )
            ]
        ),
        limit=limit
    )

    print("\nMovie Search Results")
    print("====================")

    for point in results.points:
        print("Score:", point.score)
        print("Movie:", point.payload.get("title"))
        print("Year:", point.payload.get("year"))
        print("Genres:", point.payload.get("genres"))
        print("Average Rating:", point.payload.get("average_rating"))
        print("Rating Count:", point.payload.get("rating_count"))
        print("Tags:", point.payload.get("tags"))
        print("Text:", point.payload.get("text"))
        print("----------------------------")


# ==========================================================
# 14. Validate Qdrant Count
# ==========================================================
def validate_qdrant_count():
    """
    Checks how many vectors are stored in Qdrant collection.
    """

    result = qdrant_client.count(
        collection_name=COLLECTION_NAME,
        exact=True
    )

    print(f"Total vectors in Qdrant collection '{COLLECTION_NAME}': {result.count}")


# ==========================================================
# 15. Main Execution
# ==========================================================
if __name__ == "__main__":

    # Step 1: Create Qdrant collection
    create_qdrant_collection()

    # Step 2: Load MovieLens movie data from PostgreSQL
    movies_df = load_movies()

    # Step 3: Create chunks, generate embeddings, and save into Qdrant
    save_movie_embeddings_to_qdrant(
        movies_df=movies_df,
        embedding_batch_size=32
    )

    # Step 4: Validate Qdrant vector count
    validate_qdrant_count()

    # Step 5: Test semantic search
    search_movies(
        query_text="emotional science fiction movie about space and time travel",
        limit=5
    )