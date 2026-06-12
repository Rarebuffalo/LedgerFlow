# Data Processing Pipeline

When a Celery worker receives a job, it runs the transaction CSV through a multi-stage data processing pipeline. This document explains the mathematical and logical operations applied at each stage.

---

## Pipeline Execution Stages

```
[Start Task] ---> 1. Clean Data (25% progress)
                       │
                       ▼
                  2. Detect Anomalies (50% progress)
                       │
                       ▼
                  3. Batch LLM Classification (75% progress)
                       │
                       ▼
                  4. Generate Summary Report (90% progress)
                       │
                       ▼
                  5. Bulk Save & Complete (100% progress)
```

---

## Stage 1: Data Cleaning & Normalization

This stage uses Pandas to clean raw inputs, dropping duplicates and malformed records.

### 1. Date Parsing & Normalization
* **Objective:** Standardize conflicting date string formats (e.g., `DD-MM-YYYY`, `YYYY/MM/DD`, `YYYY-MM-DD`) into ISO 8601 format (`YYYY-MM-DD`).
* **Implementation:** The code sequentially attempts parsing with strict format match configurations:
  * `%d-%m-%Y` (Day-Month-Year)
  * `%Y/%m/%d` (Year/Month/Day)
  * `%Y-%m-%d` (ISO format fallback)
  * Any row with a date that fails all parsing formats is discarded.

### 2. Monetary Sanitization
* **Objective:** Parse string currencies containing characters like `$` or commas into floating-point numbers.
* **Implementation:** Leading/trailing whitespaces, dollar signs, and commas are stripped. If the value cannot be cast to a float (e.g. text characters), it defaults to `0.0`.

### 3. Casing Standardization
* **Objective:** Enforce uniform database lookup values.
* **Implementation:** `status` values (such as `success` or `failed`) and `currency` values (such as `inr` or `usd`) are stripped of spaces and converted to uppercase (`SUCCESS`, `FAILED`, `PENDING`, `INR`, `USD`).

### 4. Deduplication
* **Objective:** Remove exact duplicates in raw records.
* **Implementation:** Generates a row hash signature across all fields. If an identical row has already been registered, it is discarded (keeping only the first instance).

---

## Stage 2: Anomaly Detection

We apply two primary rules to flag transactions as anomalous:

### 1. Statistical Account Outliers
* **Rule:** A transaction is an outlier if its amount exceeds three times the median transaction amount of the associated account.
* **Math:**
  $$\text{Threshold} = 3 \times \text{median}(\{A_1, A_2, \dots, A_n\})$$
  Where $\{A_1, A_2, \dots, A_n\}$ represents all transaction amounts for the given `account_id` in the uploaded dataset.
* **Handling Small Groups:** If an account has only one or two transactions, the median represents their own values. Outlier flags will not trigger because the amount cannot exceed its own multiple. Outlier flags activate when accounts show stable spending baselines and sudden large spikes.

### 2. USD Domestic Brand Chargings
* **Rule:** Flag transactions billed in `USD` for merchants known to operate strictly inside domestic regions.
* **Merchants Checked:** `Swiggy`, `Ola`, and `IRCTC` (case-insensitive).
* **Flags Applied:** Flags `is_anomaly = True` and appends `"USD Domestic Merchant"` to the anomaly reason.

---

## Stage 3: Batch LLM Classification

To minimize API network latency, rate limits, and context costs, we do not call the LLM for individual rows.

1. **Filtering:** Gathers all transaction records where the category column is missing or empty.
2. **Batching:** Collects only the **unique** merchant names from these filtered rows.
3. **Structured Query:** Sends the unique merchant list to Google Gemini 1.5 Flash in a single prompt. It asks the LLM to return a JSON array containing merchant-to-category pairs.
4. **Pydantic Validation:** The JSON response is parsed and validated using a Pydantic list schema to ensure the LLM returned valid categories from the allowed set:
   `Food`, `Shopping`, `Travel`, `Transport`, `Utilities`, `Cash Withdrawal`, `Entertainment`, `Other`
5. **Fallback:** If the LLM call fails (e.g. API down, timeout, or validation schema failure after 3 exponential backoff retries), the worker assigns a default category value of `"Uncategorised"`, sets `llm_failed = True` for the affected rows, and continues processing without crashing the pipeline.

---

## Stage 4: Summary Report Generation

Calculates the analytical metrics of the job and passes them to the LLM to generate the narrative report.

1. **Spent Totals:** Sums all transactions grouped by currency (`total_spend_inr` and `total_spend_usd`).
2. **Top Merchants:** Groups transactions by merchant name, sums their spend, and sorts them to find the top three merchants by transaction volume and spend.
3. **Category Breakdown:** Sums total spend values grouped by spending category.
4. **Narrative & Risk Level:** Sends these calculated math figures to Gemini in a single prompt to generate:
   * A concise 2-3 sentence spending narrative.
   * An overall risk level (`low`, `medium`, `high`) based on the anomaly counts.
5. **JSON Fallback:** If the LLM narrative call fails, the worker falls back to a template-driven narrative (e.g., `"Automated fallback report..."`) and sets a risk level based on simple threshold checks.

---

## Stage 5: Bulk Database Insertion

Once all calculations and classifications are complete, the worker writes the results to PostgreSQL:

* **Transactions:** The worker uses SQLAlchemy's `bulk_save_objects` to execute a single bulk batch insert for the cleaned transaction rows. This is significantly faster and more memory-efficient than executing individual `session.add()` inserts in a loop.
* **Summary:** Commits the final `JobSummary` record containing JSONB data.
* **Job State:** Updates the `Job` status to `completed`, progress to `100`, records the execution duration in `processing_time_seconds`, and commits the transaction.
