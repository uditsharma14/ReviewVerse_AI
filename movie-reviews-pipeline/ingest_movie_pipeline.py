import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path


RAW_DATA_PATH = Path("data/raw")

DB_PATH = "postgresql+psycopg2://review_user:review_pass123@localhost:5432/review_app"


def read_csv_files():
    movies = pd.read_csv(RAW_DATA_PATH / "movies.csv")
    ratings = pd.read_csv(RAW_DATA_PATH / "ratings.csv")
    tags = pd.read_csv(RAW_DATA_PATH / "tags.csv")
    links = pd.read_csv(RAW_DATA_PATH / "links.csv")

    return movies, ratings, tags, links


def clean_movies(movies):
    movies = movies.copy()

    movies["year"] = movies["title"].str.extract(r"\((\d{4})\)")
    movies["clean_title"] = movies["title"].str.replace(
        r"\s*\(\d{4}\)", "", regex=True
    )
    movies["genres"] = movies["genres"].replace("(no genres listed)", "Unknown")
    return movies


def clean_ratings(ratings):
    ratings = ratings.copy()
    ratings = ratings.dropna()

    ratings = ratings[
        (ratings["rating"] >= 0.5) & (ratings["rating"] <= 5.0)
    ]

    ratings["rating_timestamp"] = pd.to_datetime(
        ratings["timestamp"], unit="s"
    )

    return ratings


def clean_tags(tags):
    tags = tags.copy()
    tags = tags.dropna()

    tags["tag"] = tags["tag"].str.lower().str.strip()
    tags["tag_timestamp"] = pd.to_datetime(
        tags["timestamp"], unit="s"
    )

    return tags


def create_movie_genres(movies):
    movie_genres = movies[["movieId", "genres"]].copy()

    movie_genres["genre"] = movie_genres["genres"].str.split("|")
    movie_genres = movie_genres.explode("genre")

    return movie_genres[["movieId", "genre"]]


def create_movie_stats(ratings):
    movie_stats = ratings.groupby("movieId").agg(
        avg_rating=("rating", "mean"),
        rating_count=("rating", "count")
    ).reset_index()

    movie_stats["avg_rating"] = movie_stats["avg_rating"].round(2)

    return movie_stats


def load_to_database(movies, ratings, tags, links, movie_genres, movie_stats):
    engine = create_engine(DB_PATH)

    movies.to_sql("movies", engine, if_exists="replace", index=False)
    ratings.to_sql("ratings", engine, if_exists="replace", index=False)
    tags.to_sql("tags", engine, if_exists="replace", index=False)
    links.to_sql("links", engine, if_exists="replace", index=False)
    movie_genres.to_sql("movie_genres", engine, if_exists="replace", index=False)
    movie_stats.to_sql("movie_stats", engine, if_exists="replace", index=False)

    print("Data loaded successfully into PostgreSQL review_app database")


def run_pipeline():
    print("Reading CSV files...")
    movies, ratings, tags, links = read_csv_files()

    print("Cleaning data...")
    movies = clean_movies(movies)
    ratings = clean_ratings(ratings)
    tags = clean_tags(tags)

    print("Creating processed tables...")
    movie_genres = create_movie_genres(movies)
    movie_stats = create_movie_stats(ratings)

    print("Loading data into PostgreSQL...")
    load_to_database(movies, ratings, tags, links, movie_genres, movie_stats)

    print("Pipeline completed successfully.")


if __name__ == "__main__":
    run_pipeline()