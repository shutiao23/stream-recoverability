#!/bin/bash
# usage: fetch.sh <name> <url>
name="$1"; url="$2"
out="raw/${name}"
code=$(curl -sS -L --max-time 60 -A "Mozilla/5.0 (compatible; stream-recoverability provenance audit; +local)" -w "%{http_code}" -o "$out" "$url" 2>"raw/${name}.err")
echo -e "${name}\t${code}\t$(wc -c < "$out" 2>/dev/null)\t${url}"
