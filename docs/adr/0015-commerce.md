# ADR 0015 — Commerce: prices, shops, haggling, services

- **Status**: Proposed (all structural forks closed by owner interview 2026-07-12/13, incl. a
  closing backcheck round that surfaced and resolved four world-defined-content holes.
  Provisional values tagged Refined settle at implementation. Flips to Accepted after
  implementation + playtest. Implementation is **gated behind 0010 S4** — item records,
  currency item, first rail slice.)
- **Date**: 2026-07-13.
- **Context items**: TODO backlog line "ADR futuro: commercio e compravendita" (declared out
  of scope by 0010-I7, 2026-07-12); owner interview 2026-07-12/13.

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values at
implementation. **TODO** = consciously open.

## 1. Context

0010 §I gave SAGA the substrate commerce needs: every item is a typed record (I1), coins are
just a stackable rulebook item (I7 — which explicitly deferred prices/shops/trading here),
every NPC has an inventory drawn from `npc_class` pools (I8), loot moves records
deterministically, and equip/use are structured rail actions the DM narrates but cannot
mutate (I6). 0014 added atomic `transfer_item`. What's missing is everything on top: what
things cost, who sells, how a transaction executes without letting the LLM near the money,
and how the 0005 psychology and 0003 checks make bargaining a game instead of a menu.

Binding constraint throughout: **prices are computed by the engine only**. "Sell it to me
for 1 coin" prompt-injection, DM-hallucinated prices, and free-number tools are excluded by
construction — the same posture 0003 took with damage and 0010 with progression values.

## 2. Decisions

### A. Prices

- **A1 — Value: authored number | authored range | class-derived range (Decided).**
  Rulebook item definitions gain an optional `value`: a single number = that price; a
  `[min, max]` = an RNG range. Absent → the engine derives a range from the item's
  mechanical classes (`base[class] × tier` table in `saga.config.yaml`). Ad-hoc items
  (0010-I2) are **always** class-derived — the DM never utters a price (flavor-only ad-hoc
  → negligible value). Rejected: *authored-only* (ad-hoc and pre-0015 worlds unsellable);
  *formula-only* (the plot relic priced like a common sword).
- **A2 — The draw happens per transaction (Decided).** No `value` field on runtime records:
  the price is drawn when trading — same sword, different merchant, different price (a live
  market for free). Cached per `(item def-ref | ad-hoc record uuid, npc uuid, game day)` —
  no re-roll spam. Rejected: *stamp at mint* (a field on every record; flat market;
  merchant variability rebuilt on top anyway).
- **A3 — Anti-arbitrage invariant (Decided).** Player sells at `price × sell_ratio` (config,
  < 1). **Hard engine clamp**: after ALL modifiers (shop mult, disposition, haggling),
  `sell < buy` for the same item at the same merchant — an invariant, not a convention.

### B. Merchants, shops, currency

- **B1 — Anyone trades; the shop is an enhancement (Decided).** Base trade works with any
  living NPC present (uniform I8 records + coins; willingness is C2's disposition, and
  fiction). A **merchant** is an NPC with a `shop` block: dedicated stock, restock, real
  wallet, better multiplier. The farmer buys your sword — at a bad price, with two coins to
  his name. Rejected: *flagged-merchants-only* (spontaneous barter forbidden by code);
  *no shop block* (shops — the point of this ADR — unmodeled).
- **B2 — `shop_classes` in the world taxonomy (Decided — owner-driven).** The `npc_classes`
  pattern applied to commerce: world-defined shop types (butcher / armory / inn / magic
  emporium — a low-magic world simply doesn't declare the last) each declaring stock pool,
  services offered, restock cadence (game days), wallet range, price multiplier, base
  `haggle_difficulty`, and a stock-size cap (anti record-inflation). The NPC `shop` block is
  `{class: <shop_class>, overrides…, last_restock}`. **Restock is lazy**: evaluated when
  trade opens (`last_restock + cadence < clock` → regenerate stock + wallet) — no global
  clock scans. Stock **is** the NPC inventory (no separate shop entity).
- **B3 — Finite wallets (Decided).** NPC money = currency items in their inventory (I7/I8
  pools). A broke merchant can't buy your loot: structured engine reject, a fact not a
  narration.
- **B4 — Fixed shops are authored content; mobile merchants are the same mechanism
  (Decided).** The physical shop (inn, magic shop) = an authored 0008 node + an authored
  NPC with `location` there and a `shop` block. The wandering merchant = the same NPC shape
  without a fixed post — and the 0006 Director can move them (an ordinary `move_npc`).
  Accepted consequence: shopkeeper killed = shop dead, stock lootable per I8 — "kill the
  merchant instead of paying" is answered by narrative consequences (psychology, factions,
  Director), not engine guards.
- **B5 — Currency: 1-3 denominations, schema-capped (Decided).** The rulebook marks its
  currency items: 1 to 3 denominations with integer conversion rates to the base unit
  (gold/silver/copper covers the genre), tier-3 validated. **All price math runs in the
  base unit**; display makes greedy change. The cap is a complexity bound (change-making,
  wallets, UI), not a gameplay knob — hence schema, not config. **No currency declared →
  no priced commerce**: validation blocks `shop_classes`, transfer/gifts/loot keep working
  (0014 + I8); **barter is an explicit TODO** with its own mini-design (balance tolerance,
  change-in-kind). Rejected: *unbounded denominations* (complexity for a case the genre
  never uses); *barter v1* (real design done badly in passing beats no design never).

### C. The transaction

- **C1 — Deterministic on player acceptance; two initiators (Decided).** The DM **never
  moves money**. (1) *Player-initiated*: a rail action opens the trade session — engine
  returns stock + computed prices (cached draws); buy/sell are deterministic rail actions,
  records + coins moved atomically (0014 machinery). (2) *NPC-initiated*: a structured
  `propose_trade` tool — the engine computes the price and creates a **pending offer**
  (capped list in `world_state.pending_trade_offers`, expiry in turns/scene change —
  config); the DM/npc_director dresses it narratively but the figure is the engine's; the
  player accepts via rail → deterministic execution. Every transaction/haggle injects its
  fact into the DM turn context (0010-I6 pattern). Exact UI shapes **Refined at S3** (owner:
  "va vista bene quando ci arriviamo"). For promoted NPCs, emitting `propose_trade` from
  the 0014 acting call is a future integration — v1 the DM tool suffices. Rejected: *DM
  buy/sell tools* (LLM in the loop of every trade; prices narrated before known); *both
  surfaces day one* (anti-exploit invariants guaranteed twice).
- **C2 — Trade disposition: a derived 0-100 scalar (Decided — owner-driven, replaces the
  interim per-band mapping).** The engine computes each NPC's willingness to trade with the
  player as a normalized weighted sum of their 0005 psychology axes. **Weights are
  world-defined** (optional per-axis `commerce_weight` in the taxonomy psychology block —
  e.g. trust +0.6, fear −0.4; the bundled default ships them; the engine never assumes an
  axis exists — the 0014-A3 rule). **Thresholds and curves live in `saga.config.yaml`**:
  below the refuse threshold (provisional 20) the NPC won't trade at all; above it the
  scalar drives the price multiplier and shifts the haggle difficulty. No weights declared
  anywhere → neutral 50. One scalar, three effects — no conflicting per-axis signals.
- **C3 — Haggling: passive + active (Decided).** *Passive*: C2's disposition multiplier,
  automatic. *Active*: a *rail action inside the trade session* (so once-per-(merchant,
  game-day) is enforceable and the DM stays away from money) → a 0003 check (6 levels,
  advantage possible): base difficulty from `shop_class`, shifted by disposition; success
  moves the price within a config band (±X%); **critical failure irritates the merchant**
  (negative `axis_changes` — real risk, not a slot machine). The skill that rolls is a
  **rulebook pointer, never a hardcoded name** (worlds in any language):

  ```yaml
  commerce:
    haggle:
      enabled: true          # false = no haggling in this world, ever
      skill: mercanteggiare  # ref into the world's own rulebook, tier-3 validated
                             # absent/null = plain 0003 check, no bonus for anyone
  ```

  Rejected: *psychology-only* (bargaining, the roleplay beat, has no mechanic);
  *check-only* (the adoring and the hating merchant sell at the same price — 0005 wasted).

### D. Services

- **D1 — Services are virtual items (Decided).** Rulebook kind `service`: a `value` (same
  A1 rules) + an effect from a **closed v1 enum** reusing existing vocabulary:
  `{heal: <heal_class>}` (0003-B7) · `{rest}` (restore resources) · `{advance_minutes: n}`
  · `{grant_item: <ref>}`. Buying = pay + engine applies the effect; nothing enters the
  inventory. Declared per `shop_class`/shop block. Inn room, healer's touch, ferry fare —
  the genre's most common commerce — covered with zero new vocabulary. Food/alcohol are
  ordinary consumables in the inn's stock pool; **drunkenness as a real status is gated on
  0012's status/duration system** (v1: flavor or a mild hazard-class draw). Rejected:
  *services deferred* (the first playtest inn can't charge for a room); *rest-only* (the
  healer uses the same existing vocabulary — excluding it saves nothing).

### E. Integrity (anti-exploit, collected)

Invariant A3 over everything; price-draw cache per game day (A2); haggle once per
(merchant, game day), critical-fail cost (C3); refuse threshold (C2); selling an equipped
item auto-unequips first; stackables sell in partial quantity; all moves atomic — records
never duplicated (0014 machinery); finite wallets (B3); stock cap per shop_class (B2);
merchant-killing answered narratively (B4). Stolen-goods fencing is fiction, not schema —
theft is already an I8 record transfer.

## 3. Decided vs Open — quick index

**Decided**: A1-A3, B1-B5, C1-C3, D1, E.
**Refined**: all config numbers (`sell_ratio`, haggle band, refuse threshold, disposition
curves, base value table, offer expiry, stock caps), trade-session and offer UI shapes (S3),
cache-key details, editor form layouts.
**TODO**: **barter** for currencyless worlds (balance tolerance, change-in-kind — own
mini-design); multi-currency beyond 3 denominations (rejected for now, revisit only on real
demand); Director-driven price dynamics / "prices spiked" rumors (compose 0006 + this ADR
later); drunkenness status (lands with 0012's status system); `propose_trade` via the 0014
acting call.

## 4. Rejected alternatives (with reasons)

Collected per decision: authored-only / formula-only value (A1); stamp-at-mint draw (A2);
flagged-merchants-only / no-shop-block (B1); unbounded denominations, barter-v1 (B5); DM
buy/sell tools, double surface day one (C1); config-level axis mapping — **replaced during
the interview** by taxonomy weights + config curves after the world-defined-axes
contradiction was caught (C2); psychology-only / check-only haggling (C3); hardcoded haggle
skill name — replaced by the rulebook pointer (C3); services deferred / rest-only (D1).

## 5. Consequences

- **Positive**: commerce is deterministic where it counts (engine prices, atomic swaps,
  hard invariants) and alive where it should be (per-merchant draws, psychology-priced
  relationships, haggling with real risk, restocking shops, movable merchants); shop types
  are world content like everything else (P0 pattern); services make money matter beyond
  gear; every anti-exploit is engine-enforced, none is prompt discipline.
- **Trade-off**: gated behind 0010 S4 (records, currency item, rail slice) — this ADR stays
  Proposed until that stack lands.
- **Trade-off**: a new derived scalar (trade disposition) whose quality depends on
  world-declared weights — undeclared worlds fall to neutral, losing the psychology-pricing
  link (accepted: engine must not assume axes).
- **Trade-off**: currencyless worlds lose shops entirely until the barter TODO is designed
  (accepted: a declared hole beats a lame barter).

## 6. Relationship to other ADRs

- **0003** — haggle rolls through the 6-level resolver; service heals are heal-class draws;
  alcohol's optional bite is a hazard-class draw; no free numbers anywhere.
- **0005** — psychology prices the relationship via world-declared weights; critical-fail
  haggling writes `axis_changes`; the refuse threshold is how "he hates you" becomes "he
  won't sell to you".
- **0006** — the Director moves wandering merchants (`move_npc`); price dynamics /
  scarcity rumors are an explicit future composition, not v1.
- **0008** — fixed shops are authored nodes + NPCs; nothing new in the world tree.
- **0010** — hard dependency: item records (I1/I2), currency item (I7 — extended here to
  1-3 marked denominations), NPC pools (I8), rail slice (I6); rulebook gains `value`,
  `service` kind, `commerce.haggle`; taxonomy gains `shop_classes` + per-axis
  `commerce_weight`.
- **0012** — trade/haggle/accept ride the structured rail; drunkenness waits for its status
  system.
- **0014** — atomic transfer machinery reused; `propose_trade` from the acting call is the
  noted future integration; companions can be given/sold nothing special — they're NPCs.

## 7. Implementation plan (fixed; after 0010 S4)

- **S1 — Price & transaction engine (zero LLM).** `value` + currency denominations +
  `commerce.haggle` in the rulebook schema (tier-3); `shop_classes` in taxonomy; price
  pipeline (draw, cache, multipliers, A3 clamp); wallets + structured rejects; lazy
  restock; atomic buy/sell; unequip-before-sell; integration tests per §E.
- **S2 — The live layer.** Trade disposition (weights → scalar → config curves, refuse
  threshold); haggle check (0003 wiring, once/day, critical-fail deltas); `propose_trade`
  tool + `pending_trade_offers` (rung at implementation) + expiry; services (closed effect
  enum); transaction facts into the DM context.
- **S3 — FE + editor.** Trade session UI + offer cards (shapes decided here, per C1);
  editor: `value` field, `shop_classes` section, NPC shop block form, currency + haggle
  config; en/it strings.

## 8. Notes / sources

Decisions stand on first principles and the 0003/0005/0008/0010/0012/0014 contracts fixed in
prior design passes; grounded in code where premises were load-bearing (0010 §I re-read
in-session; no external validation needed). The closing backcheck caught four holes — three
of the same species (engine assuming world-defined content: haggle skill, axis mapping,
haggle difficulty owner) plus the silently-assumed single currency — all closed by the same
move: **the world declares, the engine reads, config tunes.**
