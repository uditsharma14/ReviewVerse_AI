import re
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


RAW_DATA_PATH = Path("data/raw")
DB_URL = "postgresql://review_user:review_pass123@localhost:5432/review_app"


def clean_text(value):
    if pd.isna(value):
        return ""

    value = str(value)
    value = re.sub(r"<.*?>", " ", value)
    value = re.sub(r"[^a-zA-Z0-9\s.,!?'-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_price(value):
    if pd.isna(value):
        return None

    value = str(value)
    match = re.search(r"\d+(\.\d+)?", value)

    if match:
        return float(match.group())

    return None


def load_amazon_csv():
    file_path = RAW_DATA_PATH / "amazon_reviews.csv"

    df = pd.read_csv(file_path)

    products = df.rename(columns={
        "id": "product_id",
        "asins": "asin",
        "brand": "brand",
        "categories": "categories",
        "manufacturer": "manufacturer",
        "name": "product_name",
        "prices": "price",
        "dateAdded": "date_added",
        "dateUpdated": "date_updated"
    })

    product_columns = [
        "product_id",
        "asin",
        "brand",
        "categories",
        "manufacturer",
        "product_name",
        "price",
        "date_added",
        "date_updated"
    ]

    for col in product_columns:
        if col not in products.columns:
            products[col] = None

    products = products[product_columns].copy()

    products["product_id"] = products["product_id"].astype(str)
    products["price"] = products["price"].apply(parse_price)
    products["date_added"] = pd.to_datetime(products["date_added"], errors="coerce")
    products["date_updated"] = pd.to_datetime(products["date_updated"], errors="coerce")

    products = products.drop_duplicates(subset=["product_id"])

    reviews = df.rename(columns={
        "id": "product_id",
        "reviews.username": "username",
        "reviews.rating": "rating",
        "reviews.title": "review_title",
        "reviews.text": "review_text",
        "reviews.date": "review_date",
        "reviews.doRecommend": "do_recommend",
        "reviews.numHelpful": "num_helpful",
        "reviews.sourceURLs": "source_url"
    })

    review_columns = [
        "product_id",
        "username",
        "rating",
        "review_title",
        "review_text",
        "review_date",
        "do_recommend",
        "num_helpful",
        "source_url"
    ]

    for col in review_columns:
        if col not in reviews.columns:
            reviews[col] = None

    reviews = reviews[review_columns].copy()

    reviews["product_id"] = reviews["product_id"].astype(str)
    reviews["username"] = reviews["username"].fillna("").astype(str)
    reviews["rating"] = pd.to_numeric(reviews["rating"], errors="coerce")
    reviews["review_title"] = reviews["review_title"].fillna("")
    reviews["review_text"] = reviews["review_text"].fillna("")
    reviews["clean_review_text"] = reviews["review_text"].apply(clean_text)
    reviews["review_date"] = pd.to_datetime(reviews["review_date"], errors="coerce")
    reviews["num_helpful"] = pd.to_numeric(reviews["num_helpful"], errors="coerce").fillna(0).astype(int)

    reviews["do_recommend"] = reviews["do_recommend"].fillna(False)
    reviews["do_recommend"] = reviews["do_recommend"].astype(str).str.lower().isin(["true", "yes", "1"])

    reviews = reviews.dropna(subset=["rating"])
    reviews = reviews[reviews["clean_review_text"] != ""]

    return products, reviews


def create_product_stats(reviews):
    stats = reviews.groupby("product_id").agg(
        total_reviews=("rating", "count"),
        average_rating=("rating", "mean"),
        five_star_count=("rating", lambda x: (x == 5).sum()),
        four_star_count=("rating", lambda x: (x == 4).sum()),
        three_star_count=("rating", lambda x: (x == 3).sum()),
        two_star_count=("rating", lambda x: (x == 2).sum()),
        one_star_count=("rating", lambda x: (x == 1).sum()),
        recommend_count=("do_recommend", lambda x: (x == True).sum())
    ).reset_index()

    stats["average_rating"] = stats["average_rating"].round(2)

    return stats


def create_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS amazon_products (
                product_id VARCHAR(100) PRIMARY KEY,
                asin TEXT,
                brand TEXT,
                categories TEXT,
                manufacturer TEXT,
                product_name TEXT,
                price NUMERIC,
                date_added TIMESTAMP,
                date_updated TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS amazon_reviews (
                review_id SERIAL PRIMARY KEY,
                product_id VARCHAR(100),
                username TEXT,
                rating NUMERIC,
                review_title TEXT,
                review_text TEXT,
                clean_review_text TEXT,
                review_date TIMESTAMP,
                do_recommend BOOLEAN,
                num_helpful INTEGER,
                source_url TEXT
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS amazon_product_stats (
                product_id VARCHAR(100) PRIMARY KEY,
                total_reviews INTEGER,
                average_rating NUMERIC,
                five_star_count INTEGER,
                four_star_count INTEGER,
                three_star_count INTEGER,
                two_star_count INTEGER,
                one_star_count INTEGER,
                recommend_count INTEGER
            );
        """))


def write_to_postgres(products, reviews, stats):
    engine = create_engine(DB_URL)

    create_tables(engine)

    products.to_sql(
        "amazon_products",
        engine,
        if_exists="replace",
        index=False
    )

    reviews.to_sql(
        "amazon_reviews",
        engine,
        if_exists="replace",
        index=False
    )

    stats.to_sql(
        "amazon_product_stats",
        engine,
        if_exists="replace",
        index=False
    )

    return engine


def validate_counts(engine):
    query = """
    SELECT 'amazon_products' AS table_name, COUNT(*) AS total_count FROM amazon_products
    UNION ALL
    SELECT 'amazon_reviews', COUNT(*) FROM amazon_reviews
    UNION ALL
    SELECT 'amazon_product_stats', COUNT(*) FROM amazon_product_stats;
    """

    result = pd.read_sql(query, engine)
    print(result)


def main():
    print("Reading Amazon CSV...")
    products, reviews = load_amazon_csv()

    print("Creating product stats...")
    stats = create_product_stats(reviews)

    print("Writing to PostgreSQL...")
    engine = write_to_postgres(products, reviews, stats)

    print("Validating counts...")
    validate_counts(engine)

    print("Amazon CSV ingestion completed successfully.")


if __name__ == "__main__":
    main()