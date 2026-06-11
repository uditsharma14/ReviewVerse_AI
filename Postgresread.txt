Use this for your **Review App** PostgreSQL container:

```bash
docker pull postgres:16
```

```bash
docker run --name review-app-postgres \
  -e POSTGRES_USER=review_user \
  -e POSTGRES_PASSWORD=review_pass123 \
  -e POSTGRES_DB=review_app \
  -p 5432:5432 \
  -d postgres:16
```

Check it is running:

```bash
docker ps
```

Connect to DB:

```bash
docker exec -it review-app-postgres psql -U review_user -d review_app
```

Connection string:

```text
postgresql://review_user:review_pass123@localhost:5432/review_app
```

If port `5432` is already used, run it on `5433`:

```bash
docker run --name review-app-postgres \
  -e POSTGRES_USER=review_user \
  -e POSTGRES_PASSWORD=review_pass123 \
  -e POSTGRES_DB=review_app \
  -p 5433:5432 \
  -d postgres:16
```
