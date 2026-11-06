"""Bounded, read-only PostgreSQL table ingestion for the local interactive app."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Any
import pandas as pd


def make_engine(*,host:str,port:int,database:str,user:str,password:str,sslmode:str="prefer"):
    from sqlalchemy import create_engine, URL
    if not 1<=int(port)<=65535:
        raise ValueError("Invalid PostgreSQL port")
    if sslmode not in {"disable","allow","prefer","require","verify-ca","verify-full"}:
        raise ValueError("Unsupported sslmode")
    url=URL.create("postgresql+psycopg",username=user,password=password,
                   host=host,port=int(port),database=database,query={"sslmode":sslmode})
    return create_engine(url,pool_pre_ping=True,connect_args={"connect_timeout":5},future=True)


def list_tables(engine):
    from sqlalchemy import inspect
    inspector=inspect(engine)
    return [(schema,table) for schema in inspector.get_schema_names()
            if schema not in {"information_schema"} and not schema.startswith("pg_")
            for table in inspector.get_table_names(schema=schema)]


def list_columns(engine, schema:str, table:str):
    from sqlalchemy import inspect
    available=set(list_tables(engine))
    if (schema,table) not in available:
        raise ValueError("Selected table does not exist or is not accessible")
    return [x["name"] for x in inspect(engine).get_columns(table,schema=schema)]


def fetch_table(engine, *,schema:str,table:str,columns:list[str]|None=None,
                timestamp_column:str|None=None,start=None,end=None,max_rows:int=100_000,preview:bool=False):
    """SQLAlchemy constructs all identifiers; values use bound SQL parameters.
    Never accepts user-provided SQL. Uses a read-only transaction on PostgreSQL.
    Note max_rows+1 identifies truncation and returns an error rather than partial input.
    """
    from sqlalchemy import MetaData,Table,select,bindparam
    if not 1<=int(max_rows)<=500_000:
        raise ValueError("max_rows must be between 1 and 500,000")
    allowed=list_columns(engine,schema,table)
    columns=columns or allowed
    if not columns or any(c not in allowed for c in columns):
        raise ValueError("Unrecognized or empty column selection")
    if timestamp_column and timestamp_column not in allowed:
        raise ValueError("Unknown timestamp column")
    table_obj=Table(table,MetaData(),schema=schema,autoload_with=engine)
    q=select(*(table_obj.c[c] for c in columns))
    if start is not None or end is not None:
        if not timestamp_column:
            raise ValueError("Time filtering requires timestamp_column")
        if start is not None:
            q=q.where(table_obj.c[timestamp_column]>=bindparam("start"))
        if end is not None:
            q=q.where(table_obj.c[timestamp_column]<bindparam("end"))
    q=q.limit(int(max_rows)+1)
    params={}
    if start is not None:params["start"]=pd.Timestamp(start).to_pydatetime()
    if end is not None:params["end"]=pd.Timestamp(end).to_pydatetime()
    with engine.connect() as connection:
        if engine.dialect.name=="postgresql":
            from sqlalchemy import text
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                data=pd.read_sql(q,connection,params=params)
        else:
            data=pd.read_sql(q,connection,params=params)
    if len(data)>max_rows and preview:
        return data.head(max_rows).copy()
    if len(data)>max_rows:
        raise ValueError(f"Query exceeded the {max_rows:,}-row safety limit; narrow the date range")
    return data
