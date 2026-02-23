#!/bin/bash
# RentCast comp puller
# Usage: bash get-comps.sh "123 Main St, Miami, FL 33101"

ADDRESS="$1"
API_KEY="9cba4e7f5539467c82fdb4d9a830cb31"

if [ -z "$ADDRESS" ]; then
  echo "ERROR: No address provided"
  exit 1
fi

ENCODED=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$ADDRESS")

RESPONSE=$(curl -s "https://api.rentcast.io/v1/avm/value?address=${ENCODED}&maxRadius=1.5&daysOld=180&compCount=15&lookupSubjectAttributes=true" \
  -H "X-Api-Key: ${API_KEY}" \
  -H "accept: application/json")

python3 << PYEOF
import json, sys

data = json.loads('''$RESPONSE'''.replace("'", "\\'"))

arv = data.get('price')
low = data.get('priceRangeLow')
high = data.get('priceRangeHigh')

# Filter to sold (Inactive) properties only — Active listings are not valid ARV comps
all_comps = data.get('comparables', [])
sold_comps = [c for c in all_comps if c.get('status', '').lower() == 'inactive']
comps = sold_comps[:3]

# If fewer than 3 sold comps, note it and use what we have
comp_note = ''
if len(sold_comps) < 3:
    comp_note = f'  ⚠️ Only {len(sold_comps)} sold comp(s) found within 1.5 mi / 180 days — ARV confidence low'

def fmt(n):
    if n is None: return 'N/A'
    return '\$' + f'{round(n):,}'

def ppsf(price, sqft):
    if not price or not sqft: return 'N/A'
    return '\$' + f'{round(price/sqft):,}' + '/sqft'

print(f"ARV (RentCast): {fmt(arv)}")
print(f"ARV Range:      {fmt(low)} - {fmt(high)}")
print("Comps (sold only):")
if comp_note:
    print(comp_note)
if not comps:
    print("  No sold comps found — verify ARV manually")
else:
    for i, c in enumerate(comps, 1):
        addr = c.get('formattedAddress', 'Unknown')
        price = fmt(c.get('price'))
        pp = ppsf(c.get('price'), c.get('squareFootage'))
        dist = f"{c['distance']:.2f} mi" if c.get('distance') else '?'
        days = f"{c['daysOld']}d ago" if c.get('daysOld') else '?'
        print(f"  {i}. {addr}")
        print(f"     {price} | {pp} | {dist} | {days}")
PYEOF
