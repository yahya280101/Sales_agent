#!/usr/bin/env python3
"""Render a PlantUML `.puml` file to PNG using the public PlantUML server."""
import argparse
import zlib
import base64
import requests


def plantuml_encode(plantuml_text: str) -> str:
    data = plantuml_text.encode('utf-8')
    compressed = zlib.compress(data)[2:-4]
    encoded = base64.b64encode(compressed)
    # plantuml uses a custom base64 alphabet; use the URL-safe base64 then translate
    s = encoded.decode('utf-8')
    trans = s.translate(str.maketrans('+/', '-_'))
    return trans


def get_png(plantuml_text: str) -> bytes:
    enc = plantuml_encode(plantuml_text)
    url = f'https://www.plantuml.com/plantuml/img/{enc}'
    print('Requesting', url)
    r = requests.get(url)
    r.raise_for_status()
    return r.content


def main():
    p = argparse.ArgumentParser()
    p.add_argument('puml', help='Input .puml file')
    p.add_argument('-o', '--out', default='schema.png')
    args = p.parse_args()

    with open(args.puml, 'r') as f:
        text = f.read()
    png = get_png(text)
    with open(args.out, 'wb') as f:
        f.write(png)
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
