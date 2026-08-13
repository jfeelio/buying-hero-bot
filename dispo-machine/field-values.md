# Dispo Machine — Picklist Values

Source of truth for the multi-select fields created in GHL during Phase 0.
Edit here, then re-sync to GHL. Companion to [`PLAN.md`](PLAN.md).

---

## `buy_counties` — multi-select

All 67 Florida counties. Deliberately unrestricted: the match engine only ever
reads what's populated on a buyer, so listing counties we don't work today
costs nothing and avoids a schema change the first time a JV deal lands
somewhere new.

Alachua · Baker · Bay · Bradford · Brevard · **Broward** · Calhoun · Charlotte ·
Citrus · Clay · Collier · Columbia · DeSoto · Dixie · Duval · Escambia ·
Flagler · Franklin · Gadsden · Gilchrist · Glades · Gulf · Hamilton · Hardee ·
Hendry · Hernando · Highlands · Hillsborough · Holmes · Indian River · Jackson ·
Jefferson · Lafayette · Lake · Lee · Leon · Levy · Liberty · Madison · Manatee ·
Marion · Martin · **Miami-Dade** · Monroe · Nassau · Okaloosa · Okeechobee ·
Orange · Osceola · **Palm Beach** · Pasco · Pinellas · Polk · Putnam ·
St. Johns · St. Lucie · Santa Rosa · Sarasota · Seminole · Sumter · Suwannee ·
Taylor · Union · Volusia · Wakulla · Walton · Washington

**Bold = core operating market.** Treasure Coast (St. Lucie, Martin, Indian
River) and Central FL see deal flow via InvestorBase imports.

> ⚠️ **Liberty County vs Liberty City.** Florida has a *Liberty County* in the
> panhandle. *Liberty City* is a Miami-Dade neighborhood. They are unrelated
> and live in different fields. Never let one auto-complete into the other —
> a buyer tagged for a panhandle county they've never heard of will quietly
> stop matching real deals.

---

## `buy_neighborhoods` — multi-select

Sub-market refinement. Holds both true neighborhoods (Liberty City, Wynwood)
and municipalities (Coral Gables, Homestead) — buyers describe their box in
both, so the field accepts both. Label it **"Neighborhoods / Sub-Markets of
Interest"** in the GHL UI so nobody wastes time debating the distinction.

Seeded for the core three counties. Add as buyers tell us.

### Miami-Dade

Allapattah · Aventura · Bal Harbour · Bay Harbor Islands · Brickell ·
Coconut Grove · Coral Gables · Coral Way · Cutler Bay · Doral ·
Downtown Miami · Edgewater · El Portal · Florida City · Golden Glades ·
Hialeah · Hialeah Gardens · Homestead · Kendall · Key Biscayne ·
**Liberty City** · Little Haiti · Little Havana · Miami Beach ·
Miami Gardens · Miami Lakes · Miami Shores · Miami Springs · Model City ·
North Bay Village · North Miami · North Miami Beach · Opa-locka · Overtown ·
Palmetto Bay · Perrine · Pinecrest · Richmond Heights · South Miami ·
Sunny Isles Beach · Surfside · Sweetwater · The Roads · Upper Eastside ·
Virginia Gardens · West Miami · Westchester · Wynwood

### Broward

Coconut Creek · Cooper City · Coral Springs · Dania Beach · Davie ·
Deerfield Beach · Fort Lauderdale · Hallandale Beach · Hollywood ·
Lauderdale Lakes · Lauderhill · Lighthouse Point · Margate · Miramar ·
North Lauderdale · Oakland Park · Parkland · Pembroke Pines · Plantation ·
Pompano Beach · Sunrise · Tamarac · Weston · Wilton Manors

### Palm Beach

Belle Glade · Boca Raton · Boynton Beach · Delray Beach · Greenacres ·
Jupiter · Lake Worth Beach · Lantana · Loxahatchee · Palm Beach Gardens ·
Riviera Beach · Royal Palm Beach · Wellington · West Palm Beach

### Other

`Other` — free text on the contact, reviewed monthly and promoted to a real
value once it shows up more than once.

---

## How the two fields interact

This rule is the entire reason for splitting them. Without it, having both
fields is worse than having one.

```
IF buy_neighborhoods is EMPTY
    → buyer matches ANY deal in their buy_counties
IF buy_neighborhoods is POPULATED
    → buyer matches ONLY deals inside those neighborhoods,
      even if the deal is elsewhere in a county they selected
```

`buy_counties` is the coarse filter. `buy_neighborhoods` **narrows** it — it
never widens it.

The concrete case from the master sheet: *"Gables, Pinecrest only, Hialeah
warehouses."* That buyer gets `buy_counties = [Miami-Dade]` and
`buy_neighborhoods = [Coral Gables, Pinecrest, Hialeah]`. Under this rule they
never receive a Homestead deal — which is what would happen if the neighborhood
detail were flattened into the county field, and is exactly how a good buyer
learns to ignore our texts.

Inverse case: *"Broward only"* with no neighborhoods → `buy_counties =
[Broward]`, neighborhoods empty → matches county-wide. Correct.

**The AI extraction pass must populate both fields from prose**, and must not
infer a neighborhood constraint the buyer never stated. Silence means
county-wide, not a guess.
