from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

qdrant_client = QdrantClient(host="localhost", port=6333)

COLLECTION_NAME = "reviewverse_common_review_vectors"


# Common indexes
for field in ["source", "domain", "type"]:
    qdrant_client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name=field,
        field_schema=PayloadSchemaType.KEYWORD
    )


# Movie indexes
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
    field_name="rating_count",
    field_schema=PayloadSchemaType.INTEGER
)


# Shared rating field
qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="average_rating",
    field_schema=PayloadSchemaType.FLOAT
)


# Amazon/product indexes
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

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="rating",
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

qdrant_client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="do_recommend",
    field_schema=PayloadSchemaType.BOOL
)

print("Common collection payload indexes created successfully.")