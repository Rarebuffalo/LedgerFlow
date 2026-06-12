import pandas as pd
import numpy as np
from typing import Tuple

def parse_date(val):
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    
    # Try expected formats
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return pd.to_datetime(val_str, format=fmt).date()
        except (ValueError, TypeError):
            continue
            
    # General parser fallback
    try:
        return pd.to_datetime(val_str).date()
    except (ValueError, TypeError):
        return None

def clean_amount(val) -> float:
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip()
    if not val_str:
        return 0.0
    
    # Remove currency symbol like $ or commas
    cleaned = val_str.replace('$', '').replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def clean_transactions_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, int, int]:
    """
    Cleans the transactions DataFrame:
    1. Normalizes date formats to ISO 8601 Date objects.
    2. Strips currency symbols from amounts and converts to float.
    3. Uppercases status and currency values.
    4. Keeps missing categories as None (does not fill uncategorized immediately).
    5. Trims strings.
    6. Removes exact duplicates.
    
    Returns (cleaned_df, raw_row_count, clean_row_count)
    """
    raw_row_count = len(df)
    
    # Trim column names
    df.columns = [c.strip() for c in df.columns]
    
    # 1. Trim all string values in the dataframe
    for col in df.select_dtypes(include=['object']):
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
        # Convert empty strings to None/NaN
        df[col] = df[col].replace(r'^\s*$', None, regex=True)
    
    # 2. Date normalization
    df['date'] = df['date'].apply(parse_date)
    # Drop rows without a valid date (essential field)
    df = df.dropna(subset=['date'])
    
    # 3. Amount cleanup
    df['amount'] = df['amount'].apply(clean_amount)
    
    # 4. Status and Currency normalization
    df['status'] = df['status'].apply(lambda s: str(s).upper() if pd.notna(s) else 'PENDING')
    df['currency'] = df['currency'].apply(lambda c: str(c).upper() if pd.notna(c) else 'INR')
    
    # Ensure category remains None/NaN if missing
    df['category'] = df['category'].apply(lambda x: None if pd.isna(x) or str(x).strip() == "" else str(x).strip())
    
    # 5. Remove exact duplicate rows
    # Keep the first occurrence
    df = df.drop_duplicates()
    
    clean_row_count = len(df)
    
    return df, raw_row_count, clean_row_count
