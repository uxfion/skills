#!/bin/bash
# usage: pubfetch.sh <doi> <out.pdf> -> open the DOI in session p2z (user's Chrome; the Zotero Connector may redirect it through the library proxy),
# take the page's citation_pdf_url (or a "Download PDF" link) and fetch it inside the page with the user's cookies.
# Prints one status line: OK <pages> <url> | GATE <title> | NOPDFLINK <title> | NOTPDF <status> <url>; exit 0 only on OK.
L=${LOG:-${TMPDIR:-/tmp}/opencli.log}

opencli browser p2z open "https://doi.org/$1" --window foreground 2>>$L >/dev/null
sleep 7
t=$(opencli browser p2z state 2>>$L | grep -m1 '^title:' | cut -c8-)
if printf %s "$t" | grep -qiE 'just a moment|verifying|robot|captcha|请稍候|sign in|log ?in|access denied|authenticat|shibboleth|single sign|webvpn|统一身份|身份认证|认证|登录|授权'; then echo "GATE $t"; exit 2; fi
u=$(opencli browser p2z eval '(()=>{const m=document.querySelector("meta[name=citation_pdf_url]");if(m&&m.content)return m.content;const a=[...document.querySelectorAll("a")].find(x=>/download pdf|view pdf|^pdf$/i.test((x.innerText||"").trim())&&x.href);return a?a.href:""})()' 2>>$L | tr -d '"')
if [ -z "$u" ]; then echo "NOPDFLINK $t"; exit 3; fi
# citation_pdf_url names the publisher host; inside a proxied page, fetch it through the proxied origin.
case "$u" in http*) host=$(printf %s "$u" | cut -d/ -f3); path=/$(printf %s "$u" | cut -d/ -f4-); here=$(opencli browser p2z eval 'location.host' 2>>$L | tr -d '"'); [ "$host" != "$here" ] && u="$path";; esac
out=$(bash "$(dirname "$0")/samefetch.sh" p2z "$u" "$2" 2>&1)
if printf %s "$out" | grep -q '^Pages'; then echo "OK $(printf %s "$out" | grep -m1 '^Pages' | tr -s ' ' | cut -d' ' -f2) $u"; exit 0; fi
echo "NOTPDF $(printf %s "$out" | head -1) $u"; exit 4
