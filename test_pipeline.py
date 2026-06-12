import sys
import os
import pandas as pd

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cleaning import clean_transactions_dataframe
from app.services.anomaly import detect_anomalies_dataframe
from app.services.report import (
    generate_spend_totals,
    generate_category_breakdown,
    generate_top_merchants
)

CSV_PATH = "transactions.csv"

def run_test():
    print(f"Reading {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded raw row count: {len(df)}")
    
    # 1. Clean data
    cleaned_df, raw_count, clean_count = clean_transactions_dataframe(df)
    print(f"\n--- Cleaning Results ---")
    print(f"Raw Row Count: {raw_count}")
    print(f"Cleaned Row Count: {clean_count} (Dropped duplicates and invalid dates)")
    
    # Validate cleaning assertions
    assert not cleaned_df.duplicated().any(), "Duplicates still exist!"
    assert cleaned_df['amount'].apply(lambda x: isinstance(x, float)).all(), "Amounts contain non-floats!"
    assert cleaned_df['status'].isin(['SUCCESS', 'FAILED', 'PENDING']).all(), "Unnormalized statuses found!"
    assert cleaned_df['currency'].isin(['INR', 'USD']).all(), "Unnormalized currencies found!"
    print("Success: Cleaning assertions passed!")
    
    # Check date formatting
    print("First 3 cleaned dates:", cleaned_df['date'].head(3).tolist())
    
    # 2. Anomaly Detection
    anomalous_df = detect_anomalies_dataframe(cleaned_df)
    print(f"\n--- Anomaly Detection Results ---")
    anomalies = anomalous_df[anomalous_df['is_anomaly'] == True]
    print(f"Total Anomalies Detected: {len(anomalies)}")
    
    # Print details of anomalies
    for idx, row in anomalies.head(5).iterrows():
        print(f" - Merchant: {row['merchant']}, Amount: {row['amount']}, Currency: {row['currency']}, Account: {row['account_id']}, Reason: {row['anomaly_reason']}")
        
    # Assertions
    # Domestic Brands in USD should be flagged
    domestic_usd = anomalous_df[(anomalous_df['currency'] == 'USD') & (anomalous_df['merchant'].str.lower().isin(['swiggy', 'ola', 'irctc']))]
    assert domestic_usd['is_anomaly'].all(), "USD domestic merchant not flagged!"
    print("Success: Anomaly detection assertions passed!")
    
    # 3. Report Generation
    totals = generate_spend_totals(anomalous_df)
    breakdown = generate_category_breakdown(anomalous_df)
    top_3 = generate_top_merchants(anomalous_df, limit=3)
    
    print(f"\n--- Report Results ---")
    print(f"INR Total Spend: {totals.get('INR')}")
    print(f"USD Total Spend: {totals.get('USD')}")
    print(f"Spend Breakdown by Category: {breakdown}")
    print(f"Top 3 Merchants: {top_3}")
    
    # Verify report assertions
    assert isinstance(totals.get('INR'), float), "INR Spend should be float"
    assert len(top_3) <= 3, "Top merchants limit exceeded"
    print("Success: Reporting assertions passed!")
    
    print("\nALL LOCAL PIPELINE VALIDATION TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_test()
