import uuid
import hashlib
import math
import pandas as pd
from sqlalchemy import create_engine
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue


# ==========================================================
# 1. PostgreSQL Connection
# ==========================================================
DB_CONNECTION = "postgresql://review_user:review_pass123@localhost:5432/review_app"
engine = create_engine(DB_CONNECTION)


# ==========================================================
# 2. Qdrant Connection
# ==========================================================
qdrant_client = QdrantClient(host="localhost", port=6333)


# ==========================================================
# 3. Common Qdrant Collection
# ==========================================================
COLLECTION_NAME = "reviewverse_common_review_vectors"


# ==========================================================
# 4. Embedding Model
# ==========================================================
model = SentenceTransformer("all-MiniLM-L6-v2")
VECTOR_SIZE = 384


# ==========================================================
# 5. Safe Helpers
# ==========================================================
def safe_value(value, default=None):
    if value is None:
        return default

    if isinstance(value, float) and math.isnan(value):
        return default

    return value


def safe_float(value):
    value = safe_value(value)

    if value is None or value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def safe_int(value):
    value = safe_value(value)

    if value is None or value == "":
        return None

    try:
        return int(value)
    except Exception:
        return None


def safe_bool(value):
    value = safe_value(value)

    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return value

    value = str(value).lower().strip()

    if value in ["true", "yes", "1", "y"]:
        return True

    if value in ["false", "no", "0", "n"]:
        return False

    return None


# ==========================================================
# 6. Stable UUID
# ==========================================================
def create_stable_uuid(text):
    hash_value = hashlib.md5(text.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hash_value))


# ==========================================================
# 7. Chunk Text
# ==========================================================
def chunk_text(text, chunk_size=300, overlap=50):
    if text is None:
        return []

    text = str(text).strip()

    if not text:
        return []

    words = text.split()

    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])

        if chunk.strip():
            chunks.append(chunk)

        start = end - overlap

        if start >= len(words):
            break

    return chunks


# ==========================================================
# 8. Create Common Qdrant Collection
# ==========================================================
def create_qdrant_collection():
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
# 9. Load Movie Data
# ==========================================================
def load_movies():
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
# 10. Load Amazon Review Data
# ==========================================================
def load_amazon_reviews():
    query = """
        SELECT
            r.review_id,
            r.product_id,
            p.product_name,
            p.brand,
            p.categories,
            p.manufacturer,
            p.price,
            r.username,
            r.rating,
            r.review_title,
            r.review_text,
            r.clean_review_text,
            r.review_date,
            r.do_recommend,
            r.num_helpful,
            s.total_reviews,
            s.average_rating,
            s.recommend_count
        FROM amazon_reviews r
        JOIN amazon_products p
            ON r.product_id = p.product_id
        LEFT JOIN amazon_product_stats s
            ON r.product_id = s.product_id
        WHERE 
            COALESCE(r.clean_review_text, r.review_text) IS NOT NULL
            AND LENGTH(TRIM(COALESCE(r.clean_review_text, r.review_text))) > 10
    """

    df = pd.read_sql(query, engine)
    print(f"Loaded Amazon reviews: {len(df)}")
    return df


# ==========================================================
# 11. Prepare Movie Text
# ==========================================================
def prepare_movie_text(row):
    text = f"""
    Content Type: Movie Review Data
    Title: {safe_value(row.get("title"), "")}
    Clean Title: {safe_value(row.get("clean_title"), "")}
    Year: {safe_value(row.get("year"), "")}
    Genres: {safe_value(row.get("genres"), "")}
    Average Rating: {safe_value(row.get("average_rating"), "")}
    Rating Count: {safe_value(row.get("rating_count"), "")}
    Tags: {safe_value(row.get("tags"), "")}
    """

    return text.strip()


# ==========================================================
# 12. Prepare Amazon Review Text
# ==========================================================
def prepare_amazon_review_text(row):
    review_text = safe_value(row.get("clean_review_text"), "")

    if not str(review_text).strip():
        review_text = safe_value(row.get("review_text"), "")

    text = f"""
    Content Type: Amazon Product Review
    Product Name: {safe_value(row.get("product_name"), "")}
    Brand: {safe_value(row.get("brand"), "")}
    Manufacturer: {safe_value(row.get("manufacturer"), "")}
    Categories: {safe_value(row.get("categories"), "")}
    Price: {safe_value(row.get("price"), "")}
    Product Average Rating: {safe_value(row.get("average_rating"), "")}
    Total Reviews: {safe_value(row.get("total_reviews"), "")}
    Recommend Count: {safe_value(row.get("recommend_count"), "")}
    Review Rating: {safe_value(row.get("rating"), "")}
    Review Title: {safe_value(row.get("review_title"), "")}
    Review Text: {review_text}
    Helpful Votes: {safe_value(row.get("num_helpful"), "")}
    Do Recommend: {safe_value(row.get("do_recommend"), "")}
    """

    return text.strip()


# ==========================================================
# 13. Create Movie Payload
# ==========================================================
def create_movie_payload(row, chunk, chunk_index):
    return {
        "source": "movielens",
        "domain": "movie",
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
# 14. Create Amazon Payload
# ==========================================================
def create_amazon_payload(row, chunk, chunk_index):
    return {
        "source": "amazon_reviews",
        "domain": "product",
        "type": "amazon_review_chunk",

        "review_id": str(safe_value(row.get("review_id"), "")),
        "product_id": str(safe_value(row.get("product_id"), "")),
        "product_name": safe_value(row.get("product_name"), ""),
        "brand": safe_value(row.get("brand"), ""),
        "manufacturer": safe_value(row.get("manufacturer"), ""),
        "categories": safe_value(row.get("categories"), ""),
        "price": safe_float(row.get("price")),
        "rating": safe_float(row.get("rating")),
        "average_rating": safe_float(row.get("average_rating")),
        "total_reviews": safe_int(row.get("total_reviews")),
        "recommend_count": safe_int(row.get("recommend_count")),
        "do_recommend": safe_bool(row.get("do_recommend")),
        "num_helpful": safe_int(row.get("num_helpful")),

        "chunk_index": chunk_index,
        "text": chunk
    }


# ==========================================================
# 15. Save Embeddings into Common Collection
# ==========================================================
def save_embeddings_to_qdrant(chunks, payloads, embedding_batch_size=32):
    total_inserted = 0

    for start in range(0, len(chunks), embedding_batch_size):
        end = start + embedding_batch_size

        chunk_batch = chunks[start:end]
        payload_batch = payloads[start:end]

        embeddings = model.encode(
            chunk_batch,
            batch_size=embedding_batch_size,
            show_progress_bar=False
        ).tolist()

        points = []

        for chunk, payload, embedding in zip(chunk_batch, payload_batch, embeddings):
            stable_id_text = f"{payload['source']}_{payload.get('movie_id') or payload.get('review_id')}_{payload['chunk_index']}"
            point_id = create_stable_uuid(stable_id_text)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )

        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

        total_inserted += len(points)
        print(f"Inserted vectors: {total_inserted}/{len(chunks)}")


# ==========================================================
# 16. Process Movies
# ==========================================================
def process_movies():
    movies_df = load_movies()

    chunks = []
    payloads = []

    for _, row in movies_df.iterrows():
        full_text = prepare_movie_text(row)

        movie_chunks = chunk_text(
            text=full_text,
            chunk_size=250,
            overlap=40
        )

        for chunk_index, chunk in enumerate(movie_chunks):
            payload = create_movie_payload(row, chunk, chunk_index)

            chunks.append(chunk)
            payloads.append(payload)

    print(f"Movie chunks created: {len(chunks)}")

    save_embeddings_to_qdrant(
        chunks=chunks,
        payloads=payloads,
        embedding_batch_size=32
    )


# ==========================================================
# 17. Process Amazon Reviews
# ==========================================================
def process_amazon_reviews():
    amazon_df = load_amazon_reviews()

    chunks = []
    payloads = []

    for _, row in amazon_df.iterrows():
        full_text = prepare_amazon_review_text(row)

        review_chunks = chunk_text(
            text=full_text,
            chunk_size=300,
            overlap=50
        )

        for chunk_index, chunk in enumerate(review_chunks):
            payload = create_amazon_payload(row, chunk, chunk_index)

            chunks.append(chunk)
            payloads.append(payload)

    print(f"Amazon review chunks created: {len(chunks)}")

    save_embeddings_to_qdrant(
        chunks=chunks,
        payloads=payloads,
        embedding_batch_size=32
    )


# ==========================================================
# 18. Search Common Collection
# ==========================================================
def search_common_collection(query_text, domain=None, limit=5):
    query_vector = model.encode(query_text).tolist()

    query_filter = None

    # Optional filtering:
    # domain = "movie" or "product"
    if domain:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="domain",
                    match=MatchValue(value=domain)
                )
            ]
        )

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit
    )

    print("\nSearch Results")
    print("==============")

    for point in results.points:
        payload = point.payload

        print("Score:", point.score)
        print("Domain:", payload.get("domain"))
        print("Source:", payload.get("source"))

        if payload.get("domain") == "movie":
            print("Movie:", payload.get("title"))
            print("Genres:", payload.get("genres"))
            print("Average Rating:", payload.get("average_rating"))

        elif payload.get("domain") == "product":
            print("Product:", payload.get("product_name"))
            print("Brand:", payload.get("brand"))
            print("Rating:", payload.get("rating"))

        print("Text:", payload.get("text"))
        print("----------------------------")


# ==========================================================
# 19. Validate Count
# ==========================================================
def validate_qdrant_count():
    result = qdrant_client.count(
        collection_name=COLLECTION_NAME,
        exact=True
    )

    print(f"Total vectors in '{COLLECTION_NAME}': {result.count}")


# ==========================================================
# 20. Main Execution
# ==========================================================
if __name__ == "__main__":

    create_qdrant_collection()

    # Store both movie and Amazon review vectors in same collection
    process_movies()
    process_amazon_reviews()

    validate_qdrant_count()

    # Search everything
    search_common_collection(
        query_text="space science fiction movie with emotional story",
        limit=5
    )

    # Search only movies
    search_common_collection(
        query_text="space science fiction movie with emotional story",
        domain="movie",
        limit=5
    )

    # Search only products
    search_common_collection(
        query_text="headphones with good battery life and clear sound",
        domain="product",
        limit=5
    )