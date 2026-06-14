from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional, Union

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue


# ==========================================================
# 1. FastAPI App
# ==========================================================
app = FastAPI(
    title="ReviewVerse AI Search API",
    description="Semantic search API for movies and Amazon reviews using Qdrant",
    version="1.0.0"
)


# ==========================================================
# 2. Qdrant Configuration
# ==========================================================
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# Use the same Qdrant collection name where you saved movie and Amazon vectors.
COLLECTION_NAME = "reviewverse_movie_review_vectors"

qdrant_client = QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT
)


# ==========================================================
# 3. Embedding Model
# ==========================================================
# Important:
# This should be the same model you used while creating embeddings.
model = SentenceTransformer("all-MiniLM-L6-v2")


# ==========================================================
# 4. Response Models
# ==========================================================
class MovieSearchResult(BaseModel):
    score: float
    movie_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[Union[str, int]] = None
    genres: Optional[str] = None
    average_rating: Optional[float] = None
    rating_count: Optional[int] = None
    tags: Optional[str] = None
    text: Optional[str] = None


class AmazonSearchResult(BaseModel):
    score: float
    review_id: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    brand: Optional[str] = None
    categories: Optional[str] = None
    rating: Optional[float] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    text: Optional[str] = None


# ==========================================================
# 5. Helper Function: Create Query Embedding
# ==========================================================
def create_embedding(text: str):
    """
    Converts user search text into embedding vector.
    """
    return model.encode(text).tolist()


# ==========================================================
# 6. Movie Search API
# ==========================================================
@app.get("/search/movies", response_model=List[MovieSearchResult])
def search_movies(
    query: str = Query(..., description="Search query for movies"),
    limit: int = Query(5, description="Number of results to return")
):
    """
    Search only MovieLens vectors from Qdrant.

    Example:
    /search/movies?query=space science fiction adventure movie&limit=5
    """

    query_vector = create_embedding(query)

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

    response = []

    for point in results.points:
        payload = point.payload or {}

        response.append(
            MovieSearchResult(
                score=point.score,
                movie_id=str(payload.get("movie_id")) if payload.get("movie_id") is not None else None,
                title=payload.get("title"),
                year=payload.get("year"),
                genres=payload.get("genres"),
                average_rating=float(payload.get("average_rating")) if payload.get("average_rating") is not None else None,
                rating_count=int(payload.get("rating_count")) if payload.get("rating_count") is not None else None,
                tags=payload.get("tags"),
                text=payload.get("text")
            )
        )

    return response


# ==========================================================
# 7. Amazon Review/Product Search API
# ==========================================================
@app.get("/search/amazon", response_model=List[AmazonSearchResult])
def search_amazon_reviews(
    query: str = Query(..., description="Search query for Amazon reviews/products"),
    limit: int = Query(5, description="Number of results to return")
):
    """
    Search only Amazon review vectors from Qdrant.

    Example:
    /search/amazon?query=headphones with good battery life&limit=5
    """

    query_vector = create_embedding(query)

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

    response = []

    for point in results.points:
        payload = point.payload or {}

        response.append(
            AmazonSearchResult(
                score=point.score,
                review_id=str(payload.get("review_id")) if payload.get("review_id") is not None else None,
                product_id=str(payload.get("product_id")) if payload.get("product_id") is not None else None,
                product_name=payload.get("product_name"),
                brand=payload.get("brand"),
                categories=payload.get("categories"),
                rating=float(payload.get("rating")) if payload.get("rating") is not None else None,
                average_rating=float(payload.get("average_rating")) if payload.get("average_rating") is not None else None,
                total_reviews=int(payload.get("total_reviews")) if payload.get("total_reviews") is not None else None,
                text=payload.get("text")
            )
        )

    return response


# ==========================================================
# 8. Combined Search API
# ==========================================================
@app.get("/search/all")
def search_all(
    query: str = Query(..., description="Search query for movies and Amazon reviews"),
    limit: int = Query(10, description="Number of results to return")
):
    """
    Search both MovieLens and Amazon review vectors together.

    Example:
    /search/all?query=space movie and good headphones for movie night&limit=10
    """

    query_vector = create_embedding(query)

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit
    )

    response = []

    for point in results.points:
        payload = point.payload or {}

        response.append(
            {
                "score": point.score,
                "source": payload.get("source"),
                "type": payload.get("type"),

                # Movie fields
                "movie_id": str(payload.get("movie_id")) if payload.get("movie_id") is not None else None,
                "title": payload.get("title"),
                "year": payload.get("year"),
                "genres": payload.get("genres"),
                "tags": payload.get("tags"),

                # Amazon fields
                "review_id": str(payload.get("review_id")) if payload.get("review_id") is not None else None,
                "product_id": str(payload.get("product_id")) if payload.get("product_id") is not None else None,
                "product_name": payload.get("product_name"),
                "brand": payload.get("brand"),
                "categories": payload.get("categories"),

                # Common fields
                "rating": payload.get("rating"),
                "average_rating": payload.get("average_rating"),
                "rating_count": payload.get("rating_count"),
                "total_reviews": payload.get("total_reviews"),
                "text": payload.get("text")
            }
        )

    return response


# ==========================================================
# 9. Health Check API
# ==========================================================
@app.get("/health")
def health_check():
    """
    Simple health check endpoint.
    """

    return {
        "status": "UP",
        "service": "ReviewVerse AI Search API",
        "qdrant_host": QDRANT_HOST,
        "qdrant_port": QDRANT_PORT,
        "qdrant_collection": COLLECTION_NAME
    }