"""Re-key the hand-reviewed extraction from row numbers onto buyer IDENTITY.

`extraction.EXTRACT` is keyed by row number in the ORIGINAL 143-row snapshot of
`MAIN Dispo Tab`. On 2026-08-18 a buyer (Laura Icaza) was inserted at row 109
and every row below shifted by one, so those keys now point at the wrong people.
Applying them straight would have given 34 buyers the previous buyer's buy box —
a wrong price cap or a wrong county, silently, on a record a human curated.

The fix: the `GHL Import Dry Run` tab is a frozen copy of the original snapshot
and carries `src row` + phone + name. That gives row -> identity, so the
extraction can be re-keyed onto identity and then matched against the live sheet
in whatever order it is in today.

Identity key: normalised phone when there is one, else a normalised name. Both
are needed — 21 of these buyers have no phone at all, and a name key is the only
handle on them.
"""
import re

# Keep both halves of the key namespaced so a phone can never collide with a
# name that happens to be all digits.
def phone_key(p):
    return 'p:' + p if p else ''


def name_key(first, last):
    n = re.sub(r'[^a-z]', '', (str(first) + str(last)).lower())
    return 'n:' + n if n else ''


def identity(phone, first, last):
    """Phone is authoritative; name is the fallback for the 21 phoneless rows."""
    return phone_key(phone) or name_key(first, last)


def build_map(dry_run_rows, extract):
    """dry_run_rows: list of [src_row, action, first, last, phone, ...] from the
    frozen tab. Returns {identity_key: extraction_dict} plus a report of any
    extraction entry that no longer has a row to attach to."""
    by_row = {}
    for r in dry_run_rows:
        r = list(r) + [''] * (5 - len(r))
        if not str(r[0]).strip().isdigit():
            continue
        by_row[int(r[0])] = (str(r[4]).strip(), str(r[2]).strip(), str(r[3]).strip())

    out, orphans = {}, []
    for row, ex in extract.items():
        who = by_row.get(row)
        if not who:
            orphans.append((row, 'row not in the frozen dry run'))
            continue
        key = identity(*who)
        if not key:
            orphans.append((row, 'row has neither phone nor name'))
            continue
        if key in out:
            orphans.append((row, 'identity collides with an earlier row: ' + key))
            continue
        out[key] = ex
    return out, orphans


def resolve(by_identity, phone, first, last):
    """Look an extraction up for a live sheet row. Tries phone first, then name,
    so a buyer whose phone was FILLED IN since the snapshot still matches on
    name rather than silently losing their curated buy box."""
    for k in (phone_key(phone), name_key(first, last)):
        if k and k in by_identity:
            return by_identity[k]
    return {}
