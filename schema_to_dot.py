#!/usr/bin/env python3
"""Convert schema.dbml to Graphviz DOT format and render to PNG."""
import re
import subprocess
import sys

def parse_dbml(dbml_text):
    """Extract tables and Ref lines from DBML."""
    tables = set()
    refs = []
    
    # Extract table names
    table_pattern = r'Table\s+(\w+)\s+\{'
    for match in re.finditer(table_pattern, dbml_text):
        tables.add(match.group(1))
    
    # Extract references
    ref_pattern = r'Ref:\s+(\w+)\.\[(\w+)\]\s+>\s+(\w+)\.\[(\w+)\]'
    for match in re.finditer(ref_pattern, dbml_text):
        src_table, src_col, dst_table, dst_col = match.groups()
        refs.append((src_table, src_col, dst_table, dst_col))
    
    return tables, refs

def to_dot(tables, refs):
    """Generate Graphviz DOT syntax."""
    lines = [
        'digraph WideWorldImporters {',
        '  rankdir=LR;',
        '  node [shape=box, style=filled, fillcolor=lightblue];',
    ]
    
    # Add nodes
    for table in sorted(tables):
        lines.append(f'  "{table}";')
    
    # Add edges
    for src, src_col, dst, dst_col in refs:
        label = f"{src_col}→{dst_col}"
        lines.append(f'  "{src}" -> "{dst}" [label="{label}", fontsize=8];')
    
    lines.append('}')
    return '\n'.join(lines)

def main():
    with open('schema.dbml', 'r') as f:
        dbml = f.read()
    
    tables, refs = parse_dbml(dbml)
    dot = to_dot(tables, refs)
    
    with open('schema.dot', 'w') as f:
        f.write(dot)
    print("Wrote schema.dot")
    
    # Try to render with graphviz
    try:
        subprocess.run(['dot', '-Tpng', 'schema.dot', '-o', 'schema.png'], check=True)
        print("Wrote schema.png")
    except FileNotFoundError:
        print("graphviz not installed; install with: brew install graphviz")
        print("Then run: dot -Tpng schema.dot -o schema.png")
    except subprocess.CalledProcessError as e:
        print(f"Error rendering: {e}")

if __name__ == '__main__':
    main()
