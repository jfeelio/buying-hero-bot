---
name: sold-post
description: Make the standardized BH Properties "SOLD" social post (Buying Hero's buyer-side DBA) — property photo with a branded hanging SOLD yard sign, Jorge's headshot, sale price, investor equity spread, a rotating BH Properties headline, plus a long Instagram caption. Use whenever Jorge sends a property photo and says it sold / closed / assigned and wants a post, graphic, "just sold" image, deal announcement, win post, or "another satisfied investor" style post — even if he only gives a photo and two numbers like "sold for $500k, $220k spread".
---

# SOLD Post

One image (1080x1350, Instagram 4:5) + caption per closed deal. Same look every time, so the
feed builds a recognizable "BH Properties closed another one" series.

**Brand = BH PROPERTIES**, not Buying Hero. BH Properties is Jorge's DBA and the brand for
buyers and for his channel; the sign rider, footer and any brand mention in the caption use it
(`BRAND` constant in sold_post.py). Its logo isn't final yet — when Jorge sends it, save it to
`D:\Brand\bh_properties_logo.png` and swap it in for the footer wordmark and sign rider text.

Code: `C:\Users\jsive\Dropbox\J Feels\Dev\sold-post\sold_post.py` (uses fonts from
`..\reel-editor\fonts`). Posts: `D:\Posts\<YYYY-MM-DD>-sold-<price-k>\` (property.png,
sold_post.png, post.json, caption.txt). Headshot lives once at `D:\Brand\jorge_headshot.png`.
**Never put property photos or posts in Dev** — Dev is pushed to a public GitHub repo.

## Audience: BUYERS ONLY (hard rule)
These posts market to investors / cash buyers only. Jorge does NOT want sellers finding him or
@officialbhproperties on Instagram. Never write seller-facing copy: no "own a property / want to
sell / we buy as-is / DM us to sell", no seller benefits ("fast sale, no repairs"), no "came
straight from the homeowner". Frame everything as what the buyer gets.

## Workflow
1. **Intake.** Need: property photo, sale price, investor equity spread, **ARV**, and city. Ask only
   for what's missing. Sanity-check the math: ARV - price should equal the spread; if not, ask. **Always ask the city** (e.g. first deal was Hialeah, FL) and pass `--area "Hialeah, FL"`;
   name the city in the caption's price line and add it as a hashtag.
   Copy pasted images from the session `images\` folder; move files Jorge links from Downloads.
2. **Privacy/accuracy check on the photo:** no visible house number, street sign, plate,
   people's faces or the seller's belongings that identify them. If the house number shows,
   tell Jorge (or crop/blur it). Numbers go on the image exactly as he gave them — never round
   up or "estimate" a spread. Reputation compounds.
3. **Render:**
   `python sold_post.py D:/Posts/<folder> --price 500000 --arv 720000 --spread 220000 --area "Hialeah, FL"`
   `--headline auto` (default) rotates through the HEADLINES list so consecutive posts never
   repeat; pass a custom line if Jorge gives one. `--sign right` puts the sign on the right and
   the headshot on the left — use it when the yard/lawn is on the right of the photo, and to
   vary the feed. Photos with a black screenshot frame are auto-trimmed.
4. **Look at the output** (Read the PNG). Check: sign standing on ground/lawn and not covering
   the front door, headshot not over anything important, all text inside the frame.
5. **Caption** → `caption.txt` + paste in chat: line 1 = the headline as a hook, then
   "📍 City, FL" / ARV / Sold for / Equity spread for our investor, each on its own line, 1 short paragraph on how the deal happened (only facts Jorge
   gave or the standard model: locked up off-market → title/liens/condition checked → sent to
   a buyer on our list), a three-arrow "what our buyers get" block (vary
   the wording each time), then **one CTA**: investors comment "DEALS" to join the buyers list. 5–7 hashtags. Never invent days-to-close, rehab budgets,
   ARVs, or buyer quotes he didn't provide.
6. Deliver: path to sold_post.png and the caption.

## Design (approved 2026-10-15)
Photo top ~56% with a fade into brand black · **city tag at the top** (dark pill, blue map-pin
badge, opposite the sign) · white post-and-arm yard sign with a blue
"BH PROPERTIES" rider and white SOLD panel in blue (#0083CA) · small head-and-shoulders headshot
(160px, thin white ring + soft shadow — Jorge found the thick blue ring and tight face crop
too strong) on the photo/panel seam · ARV and SOLD FOR side by side (white), EQUITY SPREAD FOR
OUR INVESTOR as the big blue hero number · rotating headline · footer "BH PROPERTIES ·
Off-market deals for investors". Montserrat wordmark until the BH Properties logo is final.
