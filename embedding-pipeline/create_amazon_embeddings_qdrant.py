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
COLLECTION_NAME = "reviewverse_amazon_review_vectors"


# ==========================================================
# 4. Embedding Model
# ==========================================================
# all-MiniLM-L6-v2 creates 384-dimensional vectors.
model = SentenceTransformer("all-MiniLM-L6-v2")
VECTOR_SIZE = 384


# ==========================================================
# 5. Helper: Safe value handling
# ==========================================================
def safe_value(value, default=None):
    """
    Converts NaN/None values into safe values for Qdrant payload.
    Qdrant payload should not receive pandas NaN.
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


def safe_bool(value):
    """
    Safely converts value to boolean.
    """
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
# 6. Stable Qdrant ID
# ==========================================================
def create_stable_uuid(text):
    """
    Creates stable UUID from text.

    Why this is useful:
    - If you run the script again, same review chunk gets same ID.
    - Qdrant will update existing vector instead of creating duplicates.
    """
    hash_value = hashlib.md5(text.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hash_value))


# ==========================================================
# 7. Text Chunking Function
# ==========================================================
def chunk_text(text, chunk_size=300, overlap=50):
    """
    Splits large text into smaller chunks.

    Optimization:
    - If text is small, return one chunk.
    - If text is large, split using overlap to preserve context.
    """

    if text is None:
        return []

    text = str(text).strip()

    if not text:
        return []

    words = text.split()

    # Optimization: no need to chunk short text
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
# 9. Load Amazon Review Data from PostgreSQL
# ==========================================================
def load_amazon_reviews():
    """
    Loads Amazon review data from PostgreSQL.

    Optimization:
    - Only loads reviews where review text exists.
    - Joins product and stats tables so payload has useful metadata.
    """

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
# 10. Prepare Amazon Review Text for Embedding
# ==========================================================
def prepare_amazon_review_text(row):
    """
    Creates meaningful Amazon review text for embedding.

    Priority:
    - Use clean_review_text if available.
    - Otherwise use review_text.
    """

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
# 11. Create Payload for Qdrant
# ==========================================================
def create_amazon_payload(row, chunk, chunk_index):
    """
    Creates metadata payload for each review chunk.

    Payload helps later with:
    - filtering
    - ranking
    - showing product details
    - RAG explanation
    """

    return {
        "source": "amazon_reviews",
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
# 12. Save Amazon Review Embeddings into Qdrant
# ==========================================================
def save_amazon_review_embeddings_to_qdrant(reviews_df, embedding_batch_size=32, qdrant_batch_size=100):
    """
    Optimized flow:
    1. Prepare review text
    2. Chunk long text
    3. Generate embeddings in batches
    4. Insert vectors into Qdrant in batches
    5. Use stable IDs to avoid duplicate vectors
    """

    all_chunks = []
    all_payloads = []
    total_reviews_processed = 0

    print("Preparing chunks...")

    for _, row in reviews_df.iterrows():
        full_text = prepare_amazon_review_text(row)

        chunks = chunk_text(
            text=full_text,
            chunk_size=300,
            overlap=50
        )

        for chunk_index, chunk in enumerate(chunks):
            payload = create_amazon_payload(row, chunk, chunk_index)

            all_chunks.append(chunk)
            all_payloads.append(payload)

        total_reviews_processed += 1

    print(f"Total reviews processed: {total_reviews_processed}")
    print(f"Total chunks created: {len(all_chunks)}")

    if not all_chunks:
        print("No chunks found. Nothing to insert.")
        return

    total_inserted = 0

    # Process embeddings in batches
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
            stable_id_text = f"{payload['source']}_{payload['review_id']}_{payload['chunk_index']}"
            point_id = create_stable_uuid(stable_id_text)

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )

            points.append(point)

        # Insert into Qdrant
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

        total_inserted += len(points)

        print(f"Inserted chunks into Qdrant: {total_inserted}/{len(all_chunks)}")

    print(f"Completed. Total Amazon review chunks inserted/updated: {total_inserted}")


# ==========================================================
# 13. Search Amazon Reviews from Qdrant
# ==========================================================
def search_amazon_reviews(query_text, limit=5):
    """
    Searches Amazon review vectors from Qdrant.
    """

    query_vector = model.encode(query_text).tolist()

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value="amazon_reviews")
                )
            ]
        ),
        limit=limit
    )

    print("\nAmazon Review Search Results")
    print("============================")

    for point in results.points:
        print("Score:", point.score)
        print("Product:", point.payload.get("product_name"))
        print("Brand:", point.payload.get("brand"))
        print("Rating:", point.payload.get("rating"))
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

    # Step 2: Load Amazon reviews from PostgreSQL
    amazon_reviews_df = load_amazon_reviews()

    # Step 3: Create chunks, generate embeddings, and save into Qdrant
    save_amazon_review_embeddings_to_qdrant(
        reviews_df=amazon_reviews_df,
        embedding_batch_size=32,
        qdrant_batch_size=100
    )

    # Step 4: Validate Qdrant vector count
    validate_qdrant_count()

    # Step 5: Test semantic search
    search_amazon_reviews(
        query_text="headphones with good battery life and clear sound",
        limit=5
    )