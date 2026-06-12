import pandas as pd

def detect_anomalies_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies statistical anomaly rules to a cleaned transactions DataFrame:
    1. Statistical outlier: Amount > 3x the account's median transaction amount.
    2. Currency anomaly: Currency is USD but merchant is a domestic-only brand (Swiggy, Ola, IRCTC).
    
    Returns the DataFrame with populated is_anomaly and anomaly_reason fields.
    """
    if df.empty:
        df['is_anomaly'] = False
        df['anomaly_reason'] = None
        return df

    # 1. Account amount median calculation
    # We group by account_id and calculate the median amount
    medians = df.groupby('account_id')['amount'].transform('median')
    
    # Outliers: Amount > 3 * median
    is_outlier = df['amount'] > (3 * medians)
    
    # 2. USD Domestic Brand detection
    # Brands are case-insensitive
    domestic_brands = {"swiggy", "ola", "irctc"}
    is_domestic_usd = (df['currency'] == 'USD') & (df['merchant'].str.lower().isin(domestic_brands))
    
    # Initialize fields if they don't exist
    df['is_anomaly'] = False
    df['anomaly_reason'] = None
    
    # Vectorized assignment
    df.loc[is_outlier, 'is_anomaly'] = True
    df.loc[is_outlier, 'anomaly_reason'] = "Amount exceeds 3x account median"
    
    # Combine reasons if a transaction triggers both
    def combine_reasons(row):
        reasons = []
        if is_outlier.loc[row.name]:
            reasons.append("Amount exceeds 3x account median")
        if is_domestic_usd.loc[row.name]:
            reasons.append("USD Domestic Merchant")
        return "; ".join(reasons) if reasons else None

    # Apply combining logic for records flagged as anomalous
    anomalous_mask = is_outlier | is_domestic_usd
    if anomalous_mask.any():
        df.loc[anomalous_mask, 'is_anomaly'] = True
        df.loc[anomalous_mask, 'anomaly_reason'] = df[anomalous_mask].apply(combine_reasons, axis=1)
        
    return df
