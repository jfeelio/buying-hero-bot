---
name: sold-post
description: Make Buying Hero's standardized "SOLD" social post — property photo with a branded hanging SOLD yard sign, Jorge's headshot, sale price, investor equity spread, a rotating Buying Hero headline, plus a long Instagram caption. Use whenever Jorge sends a property photo and says it sold / closed / assigned and wants a post, graphic, "just sold" image, deal announcement, win post, or "another satisfied investor" style post — even if he only gives a photo and two numbers like "sold for $500k, $220k spread".
---

# SOLD Post

One image (1080x1350, Instagram 4:5) + caption per closed deal. Same look every time, so the
feed builds a recognizable "Buying Hero closed another one" series.

Code: `C:\Users\jsive\Dropbox\J Feels\Dev\sold-post\sold_post.py` (uses fonts from
`..\reel-editor\fonts`). Posts: `D:\Posts\<YYYY-MM-DD>-sold-<price-k>\` (property.png,
sold_post.png, post.json, caption.txt). Headshot lives once at `D:\Brand\jorge_headshot.png`.
**Never put property photos or posts in Dev** — Dev is pushed to a public GitHub repo.

## Workflow
1. **Intake.** Need: property photo, sale price, investor equity spread. Ask only for what's
   missing. Area defaults to "Miami-Dade" — confirm if the deal is elsewhere in South Florida.
   Copy pasted images from the session `images\` folder; move files Jorge links from Downloads.
2. **Privacy/accuracy check on the photo:** no visible house number, street sign, plate,
   people's faces or the seller's belongings that identify them. If the house number shows,
   tell Jorge (or crop/blur it). Numbers go on the image exactly as he gave them — never round
   up or "estimate" a spread. Reputation compounds.
3. **Render:**
   `python sold_post.py D:/Posts/<folder> --price 500000 --spread 220000`
   `--headline auto` (default) rotates through the HEADLINES list so consecutive posts never
   repeat; pass a custom line if Jorge gives one. `--sign right` puts the sign on the right and
   the headshot on the left — use it when the yard/lawn is on the right of the photo, and to
   vary the feed. Photos with a black screenshot frame are auto-trimmed.
4. **Look at the output** (Read the PNG). Check: sign standing on ground/lawn and not covering
   the front door, headshot not over anything important, all text inside the frame.
5. **Caption** → `caption.txt` + paste in chat: line 1 = the headline as a hook, the two
   numbers on their own lines, 1 short paragraph on how the deal happened (only facts Jorge
   gave or the standard model: direct from homeowner → under contract → title/liens/condition
   checked → matched with a buyer from our list), the three-arrow "how it works" block (vary
   the wording each time), then **two CTAs**: investors comment "DEALS" to join the buyers
   list; owners DM to sell as-is. 5–7 hashtags. Never invent days-to-close, rehab budgets,
   ARVs, or buyer quotes he didn't provide.
6. Deliver: path to sold_post.png and the caption.

## Design (approved 2026-10-15)
Photo top ~56% with a fade into brand black · white post-and-arm yard sign with a blue
"BUYING HERO" rider and white SOLD panel in blue (#0083CA) · headshot in a white + blue ring on
the photo/panel seam · "SOLD FOR" (white) and "EQUITY SPREAD FOR OUR INVESTOR" (blue)
numbers in Montserrat Black · rotating headline · footer "BUYING HERO · Off-market deals ·
<area>". The real logo font (Dunbar Tall Bold) isn't installed — if Jorge supplies a logo
PNG, put it in D:\Brand and swap the footer wordmark for it.
