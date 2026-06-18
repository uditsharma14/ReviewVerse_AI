from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

qdrant_client = QdrantClient(host="localhost", port=6333)

COLLECTION_NAME = "reviewverse_amazon_review_vectors"

# Keyword fields - good for exact match filters
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
    field_name="product_id",
    field_schema=PayloadSchemaType.KEYWORD
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="brand",
    field_schema=PayloadSchemaType.KEYWORD
)

# Numeric fields - good for range filters
qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="rating",
    field_schema=PayloadSchemaType.FLOAT
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="average_rating",
    field_schema=PayloadSchemaType.FLOAT
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="total_reviews",
    field_schema=PayloadSchemaType.INTEGER
)

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="num_helpful",
    field_schema=PayloadSchemaType.INTEGER
)

# Boolean field
qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="do_recommend",
    field_schema=PayloadSchemaType.BOOL
)

print("Payload indexes created successfully.")