#!/bin/bash

for f in priklady/*.txt; do
    echo $f
    ./manage.py import_otazky $1 -f "$f"
done