from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

qdrant_client = QdrantClient(host="localhost", port=6333)

COLLECTION_NAME = "reviewverse_movie_review_vectors"

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="source",
    field_schema=PayloadSchemaType.KEYWORD
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="type",
    field_schema=PayloadSchemaType.KEYWORD
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="movie_id",
    field_schema=PayloadSchemaType.KEYWORD
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="year",
    field_schema=PayloadSchemaType.INTEGER
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="genres",
    field_schema=PayloadSchemaType.KEYWORD
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="average_rating",
    field_schema=PayloadSchemaType.FLOAT
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="rating_count",
    field_schema=PayloadSchemaType.INTEGER
)


print("Payload indexes created successfully.")