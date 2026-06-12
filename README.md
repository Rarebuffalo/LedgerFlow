# LedgerFlow — Asynchronous Financial Data Processing & Intelligence Platform

LedgerFlow is a production-grade fintech intelligence platform that automates financial data cleaning, classification, statistical anomaly detection, and narrative summary report generation. Built using a modern asynchronous backend stack, it scales to handle large datasets by utilizing a job processing pipeline.

---

## Technology Stack
* **API Framework:** FastAPI (high performance, ASGI compliant, auto-generated Swagger documentation).
* **Database:** PostgreSQL (production-grade SQL database supporting indexed queries and relational integrity).
* **Job Queue:** Celery + Redis (decouples long-running LLM and data analysis tasks from HTTP request/response cycles).
* **AI/LLM:** Google Gemini 1.5 Flash (used in bulk batches to classify categories and construct spending narrative summaries).
* **Database Migrations:** Alembic (tracks schema changes and ensures database integrity across deployments).
* **Containerization:** Docker & Docker Compose (fully containerized with startup orchestration via healthchecks).

---

## System Architecture & Data Flow

```text
       [ Client ] 
           │  (1) POST /jobs/upload
           ▼
     [ FastAPI API ] ──(2) Save CSV File ──► [ uploads/ Shared Volume ]
           │
           ├─(3) Write Job (PENDING) ──► [ PostgreSQL ]
           │
           └─(4) Push Task (job_id) ──► [ Redis Queue ]
                                               │
                                               ▼
                                      [ Celery Worker ]
                                               │
                                               ├─(5) Load CSV ◄── [ uploads/ Shared Volume ]
                                               │
                                               ├─(6) Clean Data (Pandas)
                                               │
                                               ├─(7) Flag Anomalies (Outliers & Currency)
                                               │
                                               ├─(8) Batch Category Classification ◄──► [ Gemini LLM ]
                                               │
                                               ├─(9) Generate Narrative Report ◄──► [ Gemini LLM ]
                                               │
                                               └─(10) Bulk Insert Results ──► [ PostgreSQL ]
```

### Request Lifecycle:
1. **Upload:** Client uploads a transactions CSV file via `POST /jobs/upload`.
2. **Persistence:** The API saves the file to a shared folder `/app/uploads` and creates a `Job` record in the database with status `PENDING` and progress `0%`.
3. **Queueing:** The API pushes a `process_csv_task` background task (passing only the `job_id`) onto Redis. The API immediately returns the `job_id` to the client.
4. **Execution:** The Celery worker fetches the task, loads the CSV file using Pandas, and updates status to `PROCESSING` (10% progress).
5. **Data Cleaning:** Normalizes dates, strips currency symbols, normalizes statuses and casing, and removes exact duplicate rows (25% progress).
6. **Anomaly Detection:** Flags statistical outliers (amount > 3x account median) and currency anomalies (USD charged by domestic brands like Swiggy, Ola, or IRCTC) (50% progress).
7. **LLM Classification:** Gathers unique merchants with missing categories and does a single batch call to Gemini. If the LLM call fails, the pipeline uses `"Uncategorised"` as a fallback and marks `llm_failed = True` for transparency (75% progress).
8. **Summary Generation:** Calculates total spends, top merchants, and anomalies count. Calls Gemini to construct a structured spending narrative and risk level (90% progress).
9. **Finalization:** Commits transactions using bulk inserts and saves the report summary. Marks job as `COMPLETED` and progress `100%`. The client polls `GET /jobs/{id}/status` or retrieves results via `GET /jobs/{id}/results`.

---

## How to Run

### Prerequisites
* Docker and Docker Compose installed.

### Setup & Run
1. Create a `.env` file from the template and configure your `GEMINI_API_KEY`:
   ```bash
   cp .env.example .env
   ```
2. Start the entire application:
   ```bash
   docker compose up --build
   ```
3. Once running, you can access the interactive Swagger documentation at:
   * **API Docs:** http://localhost:8000/docs
   * **Health Check:** http://localhost:8000/health

---

## API Reference

### 1. Upload Transactions CSV
* **Endpoint:** `POST /jobs/upload`
* **Content-Type:** `multipart/form-data`
* **Response:**
  ```json
  {
    "job_id": "8c0b3418-896e-4cef-8e9c-0df8f1ac2228",
    "status": "pending",
    "progress": 0
  }
  ```
* **Example curl:**
  ```bash
  curl -X POST -F "file=@transactions.csv" http://localhost:8000/jobs/upload
  ```

### 2. Poll Job Status
* **Endpoint:** `GET /jobs/{job_id}/status`
* **Response:**
  ```json
  {
    "id": "8c0b3418-896e-4cef-8e9c-0df8f1ac2228",
    "filename": "transactions.csv",
    "status": "processing",
    "progress": 50,
    "row_count_raw": 96,
    "row_count_clean": null,
    "processing_time_seconds": null,
    "error_message": null,
    "created_at": "2026-06-12T12:00:00Z",
    "completed_at": null
  }
  ```
* **Example curl:**
  ```bash
  curl http://localhost:8000/jobs/8c0b3418-896e-4cef-8e9c-0df8f1ac2228/status
  ```

### 3. Get Analysis Results
* **Endpoint:** `GET /jobs/{job_id}/results`
* **Response (when completed):** Contains narrative summaries, top merchants, anomaly metrics, category spending distributions, and the full cleaned data list.
* **Example curl:**
  ```bash
  curl http://localhost:8000/jobs/8c0b3418-896e-4cef-8e9c-0df8f1ac2228/results
  ```

### 4. Download Cleaned CSV
* **Endpoint:** `GET /jobs/{job_id}/download`
* **Response:** Streams the cleaned CSV dataset as a file attachment.
* **Example curl:**
  ```bash
  curl -O http://localhost:8000/jobs/8c0b3418-896e-4cef-8e9c-0df8f1ac2228/download
  ```

### 5. Historical Job List
* **Endpoint:** `GET /jobs?status=completed`
* **Example curl:**
  ```bash
  curl http://localhost:8000/jobs?status=completed
  ```

### 6. Platform Analytics & Dashboard
* **Endpoint:** `GET /analytics`
* **Response:** Platform-wide aggregates (INR/USD total spends, anomaly rates, category distributions, risk distribution).
* **Example curl:**
  ```bash
  curl http://localhost:8000/analytics
  ```

### 7. Global Transaction Search
* **Endpoint:** `GET /transactions/search?query=Swiggy&is_anomaly=true`
* **Example curl:**
  ```bash
  curl "http://localhost:8000/transactions/search?query=Swiggy&is_anomaly=true"
  ```

---

## Documentation
For detailed guides on specific components and system operations, see:
* [System Architecture & Topology](docs/architecture.md)
* [Data Processing Pipeline Stages](docs/pipeline.md)
* [API Reference & curl Examples](docs/api.md)
* [Deployment & Database Migrations](docs/deployment.md)

---

## Scalability, Bottlenecks & Production Readiness

### The Breaking Points (At 100x Scale)
1. **Disk I/O and Memory (Large File Uploads):** Reading massive CSVs with `pd.read_csv()` in workers loads the whole dataset into memory, causing Out-Of-Memory (OOM) failures for multi-gigabyte files.
2. **Database Connection Pool Exhaustion:** Simultaneous insertions of hundreds of thousands of transaction records in bulk blocks the DB connection pool.
3. **LLM Rate-Limiting & I/O Blocks:** Even with batching, synchronous calls to Gemini API block Celery workers and hit API quota limits rapidly.

### Next-Iteration Enterprise Design
1. **Chunking & Streaming:** Use `pd.read_csv(..., chunksize=N)` or stream the raw data straight into a data lake (like AWS S3) instead of local disks, processing records in distributed batches.
2. **DB Batching & Vectorized Copy:** Use PostgreSQL `COPY` command (via psycopg2 `copy_expert` or SQLALchemy Core) which is up to 10-20x faster than bulk insert mappings for high-volume transactions.
3. **Asynchronous LLM calls & Workers Partitioning:** Migrate LLM task execution to asynchronous clients (`httpx` or Async Gemini SDK) and separate Celery worker queues (e.g., separating the lightweight data cleaning tasks from the heavy network-bound LLM tasks) to prevent job starvation.
4. **Caching Layer:** Introduce Redis caching for `/analytics` and `/transactions/search` queries.
