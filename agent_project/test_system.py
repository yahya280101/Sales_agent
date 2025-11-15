"""Unit tests for data retrieval, LLM analysis, and plotting."""
import os
import sys
from datetime import datetime

# Environment variables should be set before running this test
# Example setup:
# export DB_SERVER="pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com"
# export DB_PORT="1433"
# export DB_NAME="WideWorldImporters_Base"
# export DB_USER="hackathon_ro_08"
# export DB_PASSWORD="<your_password>"
# export DB_DRIVER="ODBC Driver 18 for SQL Server"
# export OPENAI_API_KEY="<your_openai_key>"

import pandas as pd
from analytics import get_conn, monthly_revenue, monthly_cogs, compute_roi, plot_timeseries
from agent import summarize_dataframe, analyze_patterns

print("=" * 80)
print("TEST 1: Database Connection")
print("=" * 80)
try:
    conn = get_conn()
    print("✅ Database connection successful")
    conn.close()
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST 2: Monthly Revenue Query")
print("=" * 80)
try:
    rev = monthly_revenue(start_date='2015-01-01', end_date='2016-12-31')
    print(f"✅ Revenue query returned {len(rev)} rows")
    print(f"   Columns: {rev.columns.tolist()}")
    print(f"   Date range: {rev['month'].min()} to {rev['month'].max()}")
    print(f"   Revenue stats:")
    print(f"     Total: {rev['revenue'].sum():,.2f}")
    print(f"     Mean: {rev['revenue'].mean():,.2f}")
    print(f"     Max: {rev['revenue'].max():,.2f}")
    print(f"\n   First 5 rows:")
    print(rev.head())
except Exception as e:
    print(f"❌ Revenue query failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 3: Monthly COGS Query")
print("=" * 80)
try:
    cogs = monthly_cogs(start_date='2015-01-01', end_date='2016-12-31')
    print(f"✅ COGS query returned {len(cogs)} rows")
    print(f"   Date range: {cogs['month'].min()} to {cogs['month'].max()}")
    print(f"   COGS stats:")
    print(f"     Total: {cogs['cogs'].sum():,.2f}")
    print(f"     Mean: {cogs['cogs'].mean():,.2f}")
    print(f"     Max: {cogs['cogs'].max():,.2f}")
    print(f"\n   First 5 rows:")
    print(cogs.head())
except Exception as e:
    print(f"❌ COGS query failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 4: ROI Computation")
print("=" * 80)
try:
    roi_df = compute_roi(start_date='2015-01-01', end_date='2016-12-31')
    print(f"✅ ROI computation successful")
    print(f"   Rows: {len(roi_df)}")
    print(f"   Columns: {roi_df.columns.tolist()}")
    print(f"   Data types: {roi_df.dtypes.to_dict()}")
    print(f"\n   Full data:")
    print(roi_df)
    print(f"\n   Statistics:")
    print(roi_df.describe())
except Exception as e:
    print(f"❌ ROI computation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 5: Plot Generation")
print("=" * 80)
try:
    roi_df = compute_roi(start_date='2015-01-01', end_date='2016-12-31')
    os.makedirs('agent_outputs', exist_ok=True)
    out_path = plot_timeseries(roi_df, ['revenue', 'cogs', 'gross_margin'], 
                               'Monthly Revenue / COGS / Gross Margin', 
                               'agent_outputs/test_plot.png')
    if os.path.exists(out_path):
        size = os.path.getsize(out_path)
        print(f"✅ Plot generated successfully")
        print(f"   Path: {out_path}")
        print(f"   Size: {size:,} bytes")
    else:
        print(f"❌ Plot file not created")
except Exception as e:
    print(f"❌ Plot generation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 6: Pattern Analysis (No LLM)")
print("=" * 80)
try:
    roi_df = compute_roi(start_date='2015-01-01', end_date='2016-12-31')
    analysis = analyze_patterns(roi_df, "What are the trends?")
    print(f"✅ Pattern analysis successful")
    print(f"   Result: {analysis}")
except Exception as e:
    print(f"❌ Pattern analysis failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST 7: LLM Analysis (With OpenAI)")
print("=" * 80)
try:
    roi_df = compute_roi(start_date='2015-01-01', end_date='2016-12-31')
    if len(roi_df) > 0:
        analysis = summarize_dataframe(roi_df, "Analyze revenue and margin trends")
        print(f"✅ LLM analysis attempted")
        print(f"   Result (first 300 chars):")
        print(f"   {analysis[:300]}...")
    else:
        print(f"⚠️  No data to analyze")
except Exception as e:
    print(f"❌ LLM analysis failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("All tests completed. Check results above for failures.")
