"""Load only the first 80% of the synthetic records to simulate subsequent arrivals.

Demo writer credentials come from a local env var (or the explicitly labeled
local-demo fallback). The Streamlit reader account cannot modify the table.
"""
from __future__ import annotations
import argparse,os
from pathlib import Path
from sqlalchemy import create_engine,URL,text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import MetaData,Table
from anomaly_monitor.demo import generate_wide_demo


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['seed','append'],help='Seed first 80% or append remaining 20%')
    args=parser.parse_args()
    url=URL.create('postgresql+psycopg',username='demo_writer',
        password=os.environ.get('DEMO_DB_WRITER_PASSWORD','demo_writer_LOCAL_ONLY'),
        host='localhost',port=5433,database='anomaly_demo')
    engine=create_engine(url)
    data=generate_wide_demo().sort_values(['BusinessDate','StoreID'])
    cut=int(len(data)*.8)
    section=data.iloc[:cut] if args.action=='seed' else data.iloc[cut:]
    rows=section.copy()
    rows['BusinessDate']=rows['BusinessDate'].dt.date
    for col in ('Washes','Opportunities','Conversions'):
        rows[col]=rows[col].astype(int)
    records=rows.to_dict(orient='records')
    table=Table('daily_metrics',MetaData(),schema='public',autoload_with=engine)
    with engine.begin() as conn:
        for idx in range(0,len(records),250):
            q=insert(table).values(records[idx:idx+250])
            conn.execute(q.on_conflict_do_nothing(index_elements=['BusinessDate','StoreID']))
        count=conn.execute(text('SELECT COUNT(*) FROM public.daily_metrics')).scalar()
    engine.dispose()
    print(f"{args.action}: {len(records)} synthetic input rows; {count} rows in PostgreSQL")

if __name__=='__main__': main()
