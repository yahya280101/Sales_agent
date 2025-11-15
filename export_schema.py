#!/usr/bin/env python3
"""Extract schema metadata from SQL Server and produce DBML and PlantUML files."""
import argparse
import pyodbc
from collections import defaultdict


TABLES_Q = """
SELECT s.name AS schema_name, t.name AS table_name
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
ORDER BY s.name, t.name;
"""

COLUMNS_Q = """
SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name,
       ty.name AS data_type, c.max_length, c.precision, c.scale,
       c.is_nullable, c.is_identity, c.column_id
FROM sys.columns c
JOIN sys.tables t ON c.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema_id
JOIN sys.types ty ON c.user_type_id = ty.user_type_id
ORDER BY s.name, t.name, c.column_id;
"""

PK_Q = """
SELECT t.name AS table_name, c.name AS column_name
FROM sys.key_constraints kc
JOIN sys.tables t ON kc.parent_object_id = t.object_id
JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id
JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
WHERE kc.type = 'PK'
"""

FK_Q = """
SELECT 
  parent.name AS parent_table, cp.name AS parent_column,
  ref.name AS ref_table, cr.name AS ref_column, fk.name AS fk_name
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables parent ON fkc.parent_object_id = parent.object_id
JOIN sys.columns cp ON fkc.parent_object_id = cp.object_id AND fkc.parent_column_id = cp.column_id
JOIN sys.tables ref ON fkc.referenced_object_id = ref.object_id
JOIN sys.columns cr ON fkc.referenced_object_id = cr.object_id AND fkc.referenced_column_id = cr.column_id
ORDER BY parent.name;
"""


def connect(conn_str):
    return pyodbc.connect(conn_str, autocommit=True)


def fetchall_dict(cursor, query):
    cursor.execute(query)
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def to_dbml(tables, cols, pk_map, fks):
    lines = []
    lines.append("Project WideWorldImporters {")
    lines.append("}")
    for t in tables:
        schema = t['schema_name']
        table = t['table_name']
        name = f"{schema}_{table}"
        lines.append(f"Table {name} {{")
        for c in [r for r in cols if r['schema_name'] == schema and r['table_name'] == table]:
            colname = c['column_name']
            dtype = c['data_type']
            nullable = "" if not c['is_nullable'] else " [null]"
            identity = " [increment]" if c['is_identity'] else ""
            pk_flag = " [pk]" if table in pk_map and colname in pk_map[table] else ""
            lines.append(f"  {colname} {dtype}{pk_flag}{identity}{nullable}")
        lines.append("}")
    for fk in fks:
        lines.append(f"Ref: {fk['parent_table']}.[{fk['parent_column']}] > {fk['ref_table']}.[{fk['ref_column']}]")
    return '\n'.join(lines)


def to_plantuml(tables, cols, pk_map, fks):
    lines = ["@startuml", "hide circle", "skinparam linetype ortho"]
    for t in tables:
        schema = t['schema_name']
        table = t['table_name']
        name = f"{schema}_{table}"
        lines.append(f"entity \"{name}\" {{")
        for c in [r for r in cols if r['schema_name'] == schema and r['table_name'] == table]:
            colname = c['column_name']
            pk = "*" if table in pk_map and colname in pk_map[table] else ""
            nullable = " (NULL)" if c['is_nullable'] else ""
            lines.append(f"  {pk}{colname} : {c['data_type']}{nullable}")
        lines.append("}")
    for fk in fks:
        left = f"{fk['parent_table']}"
        right = f"{fk['ref_table']}"
        # Escape the literal '}' in an f-string by doubling it to '}}'
        lines.append(f"{left} }}o--|| {right} : {fk['fk_name']}")
    lines.append("@enduml")
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--server', default='pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com')
    p.add_argument('--port', default='1433')
    p.add_argument('--database', default='WideWorldImporters_Base')
    p.add_argument('--user', default='hackathon_ro_08')
    p.add_argument('--password', default='', help='Database password (required)')
    p.add_argument('--driver', default='ODBC Driver 17 for SQL Server')
    p.add_argument('--encrypt', choices=['yes', 'no'], default='yes',
                   help='Whether to use TLS/SSL encryption (yes/no).')
    p.add_argument('--trust-server-certificate', choices=['yes', 'no'], default='yes',
                   help='When using encryption, whether to trust the server certificate (yes/no).')
    p.add_argument('--out-prefix', default='schema')
    args = p.parse_args()

    conn_str = (
        f"DRIVER={{{args.driver}}};"
        f"SERVER={args.server},{args.port};"
        f"DATABASE={args.database};"
        f"UID={args.user};PWD={args.password};"
        f"Encrypt={args.encrypt};TrustServerCertificate={args.trust_server_certificate};"
    )
    print('Connecting to database...')
    conn = connect(conn_str)
    cur = conn.cursor()

    tables = fetchall_dict(cur, TABLES_Q)
    cols = fetchall_dict(cur, COLUMNS_Q)
    pks = fetchall_dict(cur, PK_Q)
    fks = fetchall_dict(cur, FK_Q)

    pk_map = defaultdict(list)
    for r in pks:
        pk_map[r['table_name']].append(r['column_name'])

    dbml = to_dbml(tables, cols, pk_map, fks)
    with open(f"{args.out_prefix}.dbml", 'w') as f:
        f.write(dbml)
    print(f"Wrote {args.out_prefix}.dbml")

    puml = to_plantuml(tables, cols, pk_map, fks)
    with open(f"{args.out_prefix}.puml", 'w') as f:
        f.write(puml)
    print(f"Wrote {args.out_prefix}.puml")


if __name__ == '__main__':
    main()
