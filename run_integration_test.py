import urllib.request
import urllib.parse
import json
import time
import sys
import os

API_URL = "http://localhost:8000"

def upload_file(file_path):
    print(f"Uploading {file_path} to {API_URL}/jobs/upload...")
    
    # Construct multipart form-data request manually to avoid external dependencies
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(file_path, 'rb') as f:
        file_content = f.read()
        
    filename = os.path.basename(file_path)
    
    # Form data formatting
    part_headers = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    )
    
    body = part_headers.encode('utf-8') + file_content + f"\r\n--{boundary}--\r\n".encode('utf-8')
    
    req = urllib.request.Request(
        f"{API_URL}/jobs/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body))
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            response_data = json.loads(res.read().decode('utf-8'))
            print("Upload successful:", response_data)
            return response_data.get("job_id")
    except Exception as e:
        print("Upload failed:", e)
        if hasattr(e, 'read'):
            print("Error details:", e.read().decode('utf-8'))
        sys.exit(1)

def poll_status(job_id):
    print(f"\nPolling status for job {job_id}...")
    for attempt in range(60):  # Poll for up to 60 seconds
        req = urllib.request.Request(f"{API_URL}/jobs/{job_id}/status")
        try:
            with urllib.request.urlopen(req) as res:
                job = json.loads(res.read().decode('utf-8'))
                status = job.get("status")
                progress = job.get("progress")
                print(f"Attempt {attempt+1}: Status = {status}, Progress = {progress}%")
                
                if status == "completed":
                    print("Job processing finished successfully!")
                    return True
                elif status == "failed":
                    print("Job processing failed! Error:", job.get("error_message"))
                    return False
        except Exception as e:
            print("Status fetch failed:", e)
            
        time.sleep(2)
        
    print("Polling timed out after 60 seconds.")
    return False

def get_results(job_id):
    print(f"\nRetrieving results for job {job_id}...")
    req = urllib.request.Request(f"{API_URL}/jobs/{job_id}/results")
    try:
        with urllib.request.urlopen(req) as res:
            results = json.loads(res.read().decode('utf-8'))
            summary = results.get("summary") or {}
            print("--- Analysis Report Summary ---")
            print("INR Spend Total:", summary.get("total_spend_inr"))
            print("USD Spend Total:", summary.get("total_spend_usd"))
            print("Anomaly Count:", summary.get("anomaly_count"))
            print("Narrative Summary:", summary.get("narrative"))
            print("Assigned Risk Level:", summary.get("risk_level"))
            
            # Print sample transactions
            txns = results.get("transactions", [])
            print(f"\nTransactions Processed: {len(txns)}")
            anomalies = results.get("anomalies", [])
            print(f"Anomalies Flagged: {len(anomalies)}")
            for idx, a in enumerate(anomalies[:5]):
                print(f"  [{idx+1}] Merchant: {a.get('merchant')}, Amount: {a.get('amount')}, Currency: {a.get('currency')}, Reason: {a.get('anomaly_reason')}")
                
            return results
    except Exception as e:
        print("Failed to get results:", e)
        sys.exit(1)

def get_analytics():
    print(f"\nRetrieving platform-wide dashboard analytics...")
    req = urllib.request.Request(f"{API_URL}/analytics")
    try:
        with urllib.request.urlopen(req) as res:
            analytics = json.loads(res.read().decode('utf-8'))
            print("--- Platform Dashboard KPIs ---")
            print(json.dumps(analytics, indent=2))
    except Exception as e:
        print("Failed to get analytics:", e)

def main():
    print("Waiting 5 seconds for services to fully initialize...")
    time.sleep(5)
    
    # 1. Ping healthcheck
    try:
        with urllib.request.urlopen(f"{API_URL}/health") as res:
            health = json.loads(res.read().decode('utf-8'))
            print("System Health Status:", health)
            if health.get("status") != "healthy" and health.get("status") != "degraded":
                print("System is not running correctly.")
                sys.exit(1)
    except Exception as e:
        print("Health check failed. Make sure the Docker compose containers are running.", e)
        sys.exit(1)

    # 2. Upload file
    job_id = upload_file("transactions.csv")
    
    # 3. Poll status
    success = poll_status(job_id)
    if not success:
        sys.exit(1)
        
    # 4. View results
    get_results(job_id)
    
    # 5. View platform analytics
    get_analytics()
    
    print("\nINTEGRATION TEST PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
