import pandas as pd
from typing import Dict, List, Any

def generate_spend_totals(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calculates total spend by currency (primarily INR and USD).
    """
    totals = {"INR": 0.0, "USD": 0.0}
    if df.empty:
        return totals
        
    spend_by_curr = df.groupby('currency')['amount'].sum().to_dict()
    for curr, val in spend_by_curr.items():
        totals[curr.upper()] = round(float(val), 2)
        
    return totals

def generate_category_breakdown(df: pd.DataFrame) -> Dict[str, float]:
    """
    Generates total spend grouped by transaction category.
    """
    if df.empty:
        return {}
        
    # Replace None/NaN with 'Uncategorised' for the report
    df_temp = df.copy()
    df_temp['category'] = df_temp['category'].fillna('Uncategorised')
    
    breakdown = df_temp.groupby('category')['amount'].sum().to_dict()
    return {cat: round(float(amt), 2) for cat, amt in breakdown.items()}

def generate_top_merchants(df: pd.DataFrame, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Retrieves the top N merchants by total spend, including transaction count.
    """
    if df.empty:
        return []
        
    merchant_stats = df.groupby('merchant').agg(
        total_spend=('amount', 'sum'),
        transaction_count=('amount', 'count')
    ).reset_index()
    
    top_merchants = merchant_stats.sort_values(by='total_spend', ascending=False).head(limit)
    
    return [
        {
            "merchant": str(row['merchant']),
            "total_spend": round(float(row['total_spend']), 2),
            "transaction_count": int(row['transaction_count'])
        }
        for _, row in top_merchants.iterrows()
    ]
