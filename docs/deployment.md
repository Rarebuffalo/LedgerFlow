# Deployment & Database Migrations

LedgerLens is designed to run in containerized environments. It manages PostgreSQL schemas using Alembic migrations, allowing automated database upgrades on container startup.

---

## Docker Compose Services

The `docker-compose.yml` file provisions four distinct services:

1. **`db` (PostgreSQL):** Uses the official `postgres:15-alpine` image.
   * **Persistence:** Mounts a local Docker volume (`postgres_data`) to persist PostgreSQL records on container restarts.
   * **Healthcheck:** Pings the engine using `pg_isready -U postgres -d ledgerlens` at 5-second intervals.
2. **`redis` (Redis Cache/Broker):** Uses `redis:7-alpine`.
   * **Healthcheck:** Runs `redis-cli ping` to test availability before worker execution begins.
3. **`api` (FastAPI Server):** Builds using `Dockerfile.api`.
   * **Startup Chaining:** It waits until `db` and `redis` are reported healthy. Once healthy, it runs `alembic upgrade head` to apply schema updates, then starts the `uvicorn` web server.
4. **`worker` (Celery background worker):** Builds using `Dockerfile.worker`.
   * **Staging Area Access:** Shares a Docker volume (`uploads_data`) at `/app/uploads` with the `api` container.

---

## Database Migrations via Alembic

To support schema updates without database down-time, migrations are managed through **Alembic**.

### Migration Configuration
* **`alembic.ini`:** Points to the migration directory structure (`script_location = alembic`) and overrides the database connection URL using environment variables.
* **`alembic/env.py`:** Reads the `DATABASE_URL` dynamically from the environment configuration class (`Settings`) and links the database engine to our models:
  ```python
  from app.models import Base
  target_metadata = Base.metadata
  ```

### Common Commands

All alembic commands can be run from the host terminal inside the virtual environment or inside the running API container:

#### 1. Generate a new Migration
If you modify the database models (e.g. adding columns to the Transaction or Job models), run this to automatically detect changes and generate a migration script:
```bash
# Executing inside the API container
docker compose exec api alembic revision --autogenerate -m "description_of_change"
```
*(The script will be created under `alembic/versions/` on your host filesystem due to compose mounting configurations).*

#### 2. Apply Migrations manually
To manually upgrade your database state to the latest revision:
```bash
docker compose exec api alembic upgrade head
```

#### 3. View Migration History
```bash
docker compose exec api alembic history --verbose
```

#### 4. Rollback the last migration
```bash
docker compose exec api alembic downgrade -1
```
