#!/bin/bash
# usage: samefetch.sh <session> <same-origin path or URL> <out.pdf> -> fetch inside the page (user's cookies) and save the bytes
L=${LOG:-${TMPDIR:-/tmp}/opencli.log}
opencli browser $1 eval "(async()=>{const r=await fetch('$2',{credentials:'include'});const ct=r.headers.get('content-type')||'';if(!/pdf/.test(ct))return 'NOTPDF '+r.status+' '+ct;const b=new Uint8Array(await r.arrayBuffer());let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));return btoa(s)})()" 2>>$L > "$3.b64"
if head -c 6 "$3.b64" | grep -q NOTPDF; then cat "$3.b64"; rm -f "$3.b64"; exit 1; fi
base64 -d "$3.b64" > "$3" && rm -f "$3.b64"; pdfinfo "$3" | grep -E '^Pages'; pdftotext -l 1 "$3" - | head -4
