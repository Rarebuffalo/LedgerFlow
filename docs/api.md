# API Reference

LedgerFlow exposes endpoints to upload files, monitor background jobs, download reports, search database records, and render dashboard analytics. 

Interactive documentation is automatically generated and accessible via Swagger UI at `http://localhost:8000/docs`.

---

## Job Management Endpoints

### 1. Upload Transactions CSV
* **Path:** `POST /jobs/upload`
* **Request Format:** `multipart/form-data`
* **Request Fields:**
  * `file`: Binary file upload (must have a `.csv` extension).
* **Workflow:**
  1. Saves the raw file to `/app/uploads/job_<job_id>.csv`.
  2. Registers a pending job record in PostgreSQL.
  3. Enqueues processing onto Celery and returns immediately.
* **Response (`201 Created`):**
  ```json
  {
    "job_id": "629e5cb6-4074-407d-b8dd-c6d86f7a195a",
    "status": "pending",
    "progress": 0
  }
  ```

### 2. Poll Job Status
* **Path:** `GET /jobs/{job_id}/status`
* **Path Parameters:**
  * `job_id`: Unique job identifier.
* **Response (`200 OK`):**
  ```json
  {
    "filename": "transactions.csv",
    "id": "629e5cb6-4074-407d-b8dd-c6d86f7a195a",
    "status": "completed",
    "progress": 100,
    "row_count_raw": 95,
    "row_count_clean": 85,
    "processing_time_seconds": 17.86,
    "error_message": null,
    "created_at": "2026-06-12T07:22:01.932858Z",
    "completed_at": "2026-06-12T07:22:21.443660Z"
  }
  ```

### 3. Retrieve Job Analysis Results
* **Path:** `GET /jobs/{job_id}/results`
* **Path Parameters:**
  * `job_id`: Unique job identifier.
* **Workflow:** If the job status is not `completed`, returns the current status and progress with empty results. If the job is `completed`, returns the full analytical report.
* **Response (`200 OK`):**
  ```json
  {
    "job_id": "629e5cb6-4074-407d-b8dd-c6d86f7a195a",
    "status": "completed",
    "progress": 100,
    "summary": {
      "id": 1,
      "job_id": "629e5cb6-4074-407d-b8dd-c6d86f7a195a",
      "total_spend_inr": 1339923,
      "total_spend_usd": 74185.14,
      "top_merchants": [
        {
          "merchant": "IRCTC",
          "total_spend": 450697.69,
          "transaction_count": 12
        }
      ],
      "category_breakdown": {
        "Food": 108384.89,
        "Travel": 92470.33
      },
      "anomaly_count": 5,
      "narrative": "Automated fallback report. Processed 85 financial transactions. Calculated spend includes INR 1339923.0 and USD 74185.14. Identified 5 potential anomalies.",
      "risk_level": "medium"
    },
    "transactions": [
      {
        "id": 1,
        "job_id": "629e5cb6-4074-407d-b8dd-c6d86f7a195a",
        "txn_id": "TXN1065",
        "date": "2024-09-04",
        "merchant": "Flipkart",
        "amount": 10882.55,
        "currency": "INR",
        "status": "SUCCESS",
        "category": "Shopping",
        "account_id": "ACC003",
        "notes": "Refund expected",
        "is_anomaly": false,
        "anomaly_reason": null,
        "llm_category": null,
        "llm_failed": false
      }
    ],
    "anomalies": []
  }
  ```

### 4. Download Cleaned CSV
* **Path:** `GET /jobs/{job_id}/download`
* **Path Parameters:**
  * `job_id`: Unique job identifier.
* **Response (`200 OK`):** Streams the cleaned and structured transactions as a CSV file download (`attachment; filename=cleaned_transactions_{job_id}.csv`).

### 5. List Jobs
* **Path:** `GET /jobs`
* **Query Parameters:**
  * `status` (Optional): Filter by `pending`, `processing`, `completed`, or `failed`.
  * `limit` (Optional): Pagination limit (Default: 20, Max: 100).
  * `offset` (Optional): Pagination offset (Default: 0).

---

## Platform Search & Analytics

### 6. Search Transactions
Allows looking up transactions across all historical jobs in the system.
* **Path:** `GET /transactions/search`
* **Query Parameters:**
  * `query`: Search merchant names (case-insensitive substring match).
  * `category`: Filter by spending category (exact match).
  * `is_anomaly`: Filter by anomaly status (`true` / `false`).
  * `min_amount`: Minimum numeric transaction amount.
  * `max_amount`: Maximum numeric transaction amount.
  * `limit`: Max records to return (Default: 50, Max: 200).

### 7. Global Dashboard Metrics
Aggregates KPIs across all completed jobs. Excellent for rendering charts or summary cards.
* **Path:** `GET /analytics`
* **Response (`200 OK`):**
  ```json
  {
    "overall_spend_inr": 1339923.00,
    "overall_spend_usd": 74185.14,
    "total_anomalies_detected": 5,
    "total_jobs_processed": 1,
    "total_transactions_stored": 85,
    "category_distribution": {
      "Food": 12,
      "Shopping": 24
    },
    "job_risk_distribution": {
      "medium": 1
    }
  }
  ```
