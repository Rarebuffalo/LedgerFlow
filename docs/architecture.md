# Platform Architecture

LedgerLens is designed as a distributed, containerized platform for processing financial transaction data asynchronously. The architecture prioritizes separation of concerns, decoupling heavy I/O and AI computations from the client-facing HTTP interface.

## System Topology

The system is split into four primary services managed by Docker Compose:

```
               +-------------------+
               |    Web Client     |
               +-------------------+
                         │
                         │ HTTP
                         ▼
               +-------------------+
               |  FastAPI API (api)|
               +-------------------+
                 │      │        │
      Write Job  │      │        │ Enqueue Job
                 │      │        │ (redis://)
                 ▼      │        ▼
+------------------+    │   +------------------+
| PostgreSQL (db)  |    │   |   Redis Broker   |
+------------------+    │   +------------------+
                 ▲      │        ▲
                 │      │        │ Fetch Job
      Read/Write │      │        │
      Clean Data │      │        │
                 │      ▼        │
               +-------------------+
               |  Celery Worker    |
               +-------------------+
```

---

## Component Roles

### 1. Web API Layer (FastAPI)
* **Purpose:** Handles inbound HTTP requests, file uploads, status polling, and database queries.
* **Key Design Decisions:**
  * **Asynchronous File Staging:** Large CSV uploads are staged to a shared volume (`/app/uploads`) immediately. The API writes a `PENDING` job record to PostgreSQL and enqueues a Celery task.
  * **Fast Response Time:** By offloading processing to Celery, the API returns a `201 Created` status with the job ID within milliseconds, preventing client timeout issues.
  * **Pydantic Serialization:** Data validation and response formatting are strictly defined via Pydantic models.

### 2. Message Broker (Redis)
* **Purpose:** Acts as the message broker and backend store for Celery.
* **Key Design Decisions:**
  * Configured as a transient queue utilizing the `celery` default exchange.
  * Decouples api and worker scaling. If task load spikes, more workers can be spawned without changing the API configuration.

### 3. Task Processing Engine (Celery Worker)
* **Purpose:** Executes the data pipeline stages sequentially in the background.
* **Key Design Decisions:**
  * **Task Acks Late:** Task acknowledgment occurs after completion (`task_acks_late=True`) to ensure tasks are retried or logged on worker crashes rather than silently lost.
  * **Prefetch Multiplier:** Prefetch is limited to `1` (`worker_prefetch_multiplier=1`) to balance load distribution across multiple workers processing files of varying sizes.

### 4. Persistence Layer (PostgreSQL)
* **Purpose:** Structured storage for job states, parsed transaction records, and aggregated reports.
* **Key Design Decisions:**
  * **Relational Schema:** Defines explicit constraints (such as `ON DELETE CASCADE` from jobs to transactions and summaries).
  * **Indexes:** Explicit indexes are defined on status columns, created-at timestamps, and foreign key relations to optimize analytical queries (like dashboard rendering and transaction searches).
  * **Postgres Native Types:** Uses native PostgreSQL `ENUM` types for job states and `JSONB` binary formats for transaction summary categories and metadata, allowing fast indexing and rich document queries.

---

## Shared Storage Design
Since the API and Celery workers run in isolated containers, they must share access to raw uploaded files.
* **Mechanism:** A shared Docker volume (`uploads_data`) is mounted at `/app/uploads` in both containers.
* **Lifecycle:** 
  1. API receives the upload, writes the raw file to `/app/uploads/job_<job_id>.csv`, and passes the file path to Celery.
  2. The Worker reads the file from the same location, cleans it, processes it, and updates the database.
  3. This eliminates the overhead of sending raw binary payloads through Redis or implementing complex S3 staging configurations for local deployments.
