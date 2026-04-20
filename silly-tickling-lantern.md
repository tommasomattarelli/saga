# SAGA Frontend — Audit Fix + Full UI Rewrite

## Context

Il frontend React di SAGA è tecnicamente funzionante ma soffre di due problemi distinti:

1. **Debito architetturale post-migrazione LangGraph**: `services/websocket.ts` è codice morto (zero import in app), `game-view.handleAction` è una god-function con dynamic import insensato e cast `as never`, `new-campaign.tsx` è 438 righe (viola CLAUDE.md rule #12 <300), `TurnResponse` ha campi legacy e nuovi non distinti, nessuna validazione runtime dei payload backend, refresh token race in `api.ts`, duplicazioni auth/ability-mod, manca la feature "elimina campagna".

2. **UX/UI generica "AI slop"**: il seme atmosferico esiste (palette parchment, Cinzel, mood system CSS) ma l'esecuzione è una dashboard SaaS tinta seppia. Nessuna texture, nessun ornamento, typography sottoutilizzata, PlayerBubble stile Discord che rompe l'immersione, combat-tracker con inline styles incoerenti, character-sheet come form Bootstrap, action-input come contact form, zero motion layer serio, accessibility rotta (`focus:outline-none` ovunque). Il target è un motore TTRPG narrativo immersivo, non un CRM.

**Outcome intended**: riportare il codice a standard SOTA (Sprint 1 — logica) e poi rifare il frontend con una direzione estetica forte e coerente di "grimoire illuminato" (Sprint 2 — UI rewrite), accessibile, motion-ricco, desktop-first.

**Divisione in due sprint**: Sprint 1 è condizione necessaria per Sprint 2 (tipi puliti, hooks riusabili, schema turni stabile, feature-based folders pronti ad accogliere la nuova UI).

---

# SPRINT 1 — Logica & Architettura

Obiettivo: rimuovere debito, stabilizzare tipi/flussi, preparare scaffolding per il rewrite UI. Nessun cambio visivo significativo in questo sprint — solo cleanup interno e feature "delete campaign" che era mancante.

## 1.1 Cleanup codice morto

- **Eliminare** `frontend/src/services/websocket.ts` (zero import verificati, backend non espone più `/api/ws/:id`).
- **Eliminare** `frontend/src/services/websocket.test.ts` (testa codice morto → coverage bugiarda).
- **Rimuovere commento residuo** in `frontend/src/components/narrative/dice-roller.tsx:66` ("No WebSocket message needed…").

## 1.2 Riorganizzazione file (feature-based)

Nuova struttura:
```
src/
├── App.tsx
├── main.tsx
├── index.css
├── setupTests.ts
├── assets/
│   └── ornaments/            ← SVG components creati on-demand in Sprint 2
├── features/
│   ├── auth/
│   │   ├── components/{login-form,register-form}.tsx
│   │   ├── hooks/use-auth-flow.ts
│   │   └── __tests__/
│   ├── campaign/
│   │   ├── components/{campaign-select,new-campaign/*}.tsx
│   │   ├── hooks/{use-campaigns,use-delete-campaign}.ts
│   │   └── __tests__/
│   ├── game/
│   │   ├── components/{game-view,action-input,header}.tsx
│   │   ├── hooks/{use-submit-action,use-campaign-data}.ts
│   │   └── __tests__/
│   ├── narrative/
│   │   ├── components/{narrative-stream,turn-block,dm-paragraphs,npc-block,player-action,dm-loading,dice-roller,typewriter}.tsx
│   │   ├── hooks/use-typewriter.ts
│   │   └── __tests__/
│   ├── combat/
│   │   ├── components/combat-tracker.tsx
│   │   └── __tests__/
│   └── character/
│       ├── components/{character-sheet,companion-section}.tsx
│       └── __tests__/
├── shared/
│   ├── api/{client,endpoints,refresh-mutex}.ts
│   ├── schemas/{turn,campaign,character,user}.ts   ← Zod
│   ├── stores/{auth,game,ui}-store.ts
│   ├── ui/                   ← primitivi (Drawer, Modal, Button) — Sprint 2
│   ├── types/index.ts
│   ├── utils/{dnd,format,hash}.ts
│   └── i18n/{config,en}.ts
├── styles/
│   ├── index.css
│   ├── mood.css
│   └── tokens.css            ← Sprint 2
└── types/ (cancellata — migrata in shared/types)
```

Le cartelle vuote `hooks/` e `utils/` sono assorbite dentro `features/*` e `shared/`. `assets/` è mantenuta e popolata in Sprint 2.

## 1.3 Schema / tipi — allineamento backend LangGraph

**File nuovo**: `shared/schemas/turn.ts`
- Leggere `backend/app/schemas/turn_response.py` (e correlati) per ricavare lo schema Pydantic attuale post-LangGraph.
- Definire `TurnResponseSchema` Zod con solo i campi vivi: `narration_segments`, `dice_results`, `world_state`, `turn_number`, `mood`, `suggested_actions`, `combat_state`. Rimuovere `narration` (flat legacy), `dice_rolls`, `companion_actions`, `world_updates`, `invoke_npcs`, `ambient_detail`.
- Stesso pattern per `shared/schemas/campaign.ts` e `shared/schemas/character.ts` (in particolare: `hp` canonico come `{current:number, max:number}` — niente più union `number | {…}`).

**File modificato**: `shared/types/index.ts`
- Tipi derivati da `z.infer<typeof TurnResponseSchema>` etc. → single source of truth.
- Eliminare cast `as never` in `game-view:82-83` (non servono più con tipi allineati).

**File modificato**: `shared/api/client.ts`
- Ogni response è validata via `.safeParse()` al boundary. Failure → throw `ValidationError` strutturato (intercettato dall'error boundary).
- Dipendenza nuova: `zod@^3`.

## 1.4 Hooks estratti (eliminano god-components e duplicazioni)

### `features/game/hooks/use-submit-action.ts`
Sostituisce `game-view.handleAction:62-100`.
- React Query `useMutation` che chiama `submitAction(campaignId, action)`.
- `onSuccess`: valida turn con Zod, aggiunge al `game-store.turnHistory`, aggiorna `worldState`, `character`, `turnNumber`, `mood`, gestisce branching `combat_state`.
- Elimina dynamic import di `submitAction` (anti-pattern corrente).
- Elimina race su unmount (React Query gestisce `AbortController`).

### `features/auth/hooks/use-auth-flow.ts`
Unifica la logica duplicata in `login-form:19-29` e `register-form:20-31`.
- Signature: `useAuthFlow(mode: 'login' | 'register')` → `{ submit, isPending, error }`.
- Internamente: `login/register` → `getMe` → `setTokens` + `setUser` → `navigate('/campaigns')`.
- Error handling tipizzato: differenzia 4xx (credentials) vs 5xx (backend down) vs network.

### `features/game/hooks/use-campaign-data.ts`
Sostituisce `useEffect` con doppia-fetch in `game-view:39-59`.
- Un solo `useQuery(['campaign', id])` che ritorna `{campaign, turns, character, worldState}`.
- Sync automatico verso `game-store` tramite `onSuccess` (non effect).

### `features/campaign/hooks/use-delete-campaign.ts`
**Feature nuova richiesta dall'utente.**
- `useMutation` che chiama `DELETE /api/campaigns/:id` (verificare/creare endpoint backend se mancante).
- `onSuccess`: invalida query `['campaigns']`, mostra conferma inline. Hard delete.

### `features/narrative/hooks/use-typewriter.ts`
Estratto da `typewriter.tsx` corrente ma **umanizzato** (lo stile è Sprint 2, ma l'API hook è Sprint 1):
- Input: `{ text, baseSpeed, onComplete, reducedMotion }`.
- Algoritmo base `requestAnimationFrame` (no più `setTimeout` ogni 16ms → meno CPU su testi lunghi).
- Hook esposto in Sprint 1 con implementazione base; decorazioni (pause punteggiatura, jitter random, burst mode) aggiunte in Sprint 2 dietro flag.
- Rispetta `prefers-reduced-motion`: se attivo → rende subito l'intero testo e chiama `onComplete`.

## 1.5 Refresh token mutex

File: `shared/api/refresh-mutex.ts` (nuovo) + modifica `shared/api/client.ts:25-43`.
- Singleton `refreshPromise: Promise<string> | null`.
- Tutte le 401 concorrenti aspettano la stessa promise. Dopo resolve/reject si resetta.
- Se `refreshToken == null` → logout immediato + redirect `/login` (oggi si entra in loop 401).
- Nessuna dipendenza esterna (implementazione custom ~30 righe).

## 1.6 Utils estratti

File: `shared/utils/dnd.ts`
- `abilityMod(score: number): number` (duplicato in character-sheet:69-70 e new-campaign:110-113).
- `getHP(char: CharacterData): {current, max, percent}` (normalizzazione eliminata grazie a schema canonico, ma il formatter `percent` serve).
- `clampPercent(value: number): number` (fix potenziale overflow in `companion-bar.tsx`).

## 1.7 Error boundary globale

File: `App.tsx` + `shared/ui/error-boundary.tsx` (nuovo).
- `<ErrorBoundary>` wrappa `<Routes>` in `App.tsx`.
- Fallback in Sprint 1 = testuale neutro ("Something went wrong. Reload.") + button reload.
- In Sprint 2 il fallback diventerà pergamena ornata ("The Weave tears…"). L'API è stabile qui.
- Cattura `ValidationError` di Zod + React query errors unhandled.
- **Niente toast system** (per volontà utente): errori restano inline nei form.

## 1.8 Split `new-campaign.tsx` (438 → < 300)

File: `features/campaign/components/new-campaign/`
- `index.tsx` — orchestratore + wizard state machine (step state, navigazione).
- `steps/step-world.tsx` — scelta template.
- `steps/step-hero.tsx` — classe + stats preview.
- `steps/step-fate.tsx` — nome + death mode.
- `data/class-presets.ts` — dati statici (oggi inline a righe 26-108).
- Ogni file target < 200 righe.

## 1.9 Store selectors (performance)

Modifiche puntuali:
- `action-input.tsx:11` — sostituire `useGameStore()` con `useGameStore(state => state.campaignId)` (selector) per evitare re-render a ogni cambio store.
- Check generale di tutti i `useGameStore()` / `useAuthStore()` senza selector.

## 1.10 Delete campaign — backend check

Verificare se `DELETE /api/campaigns/:id` esiste già nel backend. Se no, creare endpoint minimale:
- `backend/app/api/campaigns.py` → route `DELETE` con authorization check (owner match).
- Cascade su turns/saves/journal a livello SQL.
- Test unit backend.

## 1.11 Testing Sprint 1

- **Elimina**: `services/websocket.test.ts`.
- **Nuovi test**:
  - `features/game/hooks/__tests__/use-submit-action.test.ts` — mutation + store update + branching combat.
  - `features/auth/hooks/__tests__/use-auth-flow.test.ts` — happy + 401 + 500 + network.
  - `features/game/hooks/__tests__/use-campaign-data.test.ts` — query + store sync.
  - `features/narrative/hooks/__tests__/use-typewriter.test.ts` — base typing + reduced motion fallback.
  - `shared/stores/__tests__/game-store.test.ts` — **oggi non esiste**, critico aggiungerlo.
  - `shared/api/__tests__/refresh-mutex.test.ts` — due 401 concorrenti → un solo refresh.
  - `features/campaign/hooks/__tests__/use-delete-campaign.test.ts`.
- Test componenti esistenti: migrazione percorso ma nessun rewrite (verranno riscritti in Sprint 2 insieme ai componenti).

## 1.12 File toccati in Sprint 1 (riepilogo)

**Nuovi**: vedi struttura in 1.2. Principali: `shared/schemas/*.ts`, `shared/api/refresh-mutex.ts`, `shared/utils/dnd.ts`, `shared/ui/error-boundary.tsx`, tutti gli `hooks/` in `features/`, `features/campaign/components/new-campaign/steps/*`.

**Modificati**: `App.tsx`, tutti i componenti migrati in `features/` (path change + uso hook), `shared/api/client.ts`, `shared/stores/game-store.ts` (tipi da schema).

**Eliminati**: `services/websocket.ts`, `services/websocket.test.ts`, `types/index.ts` (migrato), cartelle vuote `hooks/`, `utils/`.

**Backend (se necessario)**: `backend/app/api/campaigns.py` (endpoint DELETE).

## 1.13 Verifica fine Sprint 1

1. `cd frontend && npm run lint && npm run test` → tutto verde.
2. `cd frontend && npx tsc --noEmit` → zero errori, zero `any`, zero `as never`.
3. `cd frontend && npm run dev` e manuale: login → campaign list → new campaign → submit action → delete campaign. Flussi identici a prima ma senza WS morto, senza cast, senza race.
4. `cd backend && uv run pytest tests/unit tests/integration` → verde (specialmente delete campaign se endpoint nuovo).
5. Nessun file > 300 righe in `src/features/**`.

---

# SPRINT 2 — Full UI Rewrite (Grimoire illuminato)

Obiettivo: rifare completamente la veste grafica del frontend con direzione estetica coerente **"Grimoire / pergamena illuminata"** — fantasy editoriale, caldo, letterario, con ornamenti ricchi e illuminazioni.

## 2.1 Aesthetic direction — Riepilogo decisioni

| Aspetto | Decisione |
|---|---|
| **Stile globale** | Grimoire / pergamena illuminata |
| **Tema** | **Dual**: LIGHT (pergamena chiara #F4E8D0 + inchiostro seppia) per narrazione in-game; DARK (pergamena bruciata #2A1A10 + oro) per auth, campaign select, menu, overlay cinematografici |
| **Ornamenti** | Ricchi e illuminati — grana globale + vignette + pattern floreali ai bordi + divisori ornamentali tra sezioni + drop-cap illuminati |
| **Typography** | **Display**: Cinzel Decorative (titoli drammatici). **Body**: Cormorant Garamond (serif elegante, italic espressivo, small-caps native) |
| **Palette accenti** | Oro (#B8860B / #D4AF37), Rosso sangue / ceralacca (#8B0000 / #6B0F0F), Blu notte / arcano (#1E3A5F / #2D4A6B) |
| **Motion** | Page transitions route + turn reveal staggered + mood crossfade atmosferico + typewriter umanizzato avanzato |
| **Accessibility** | Rispetta `prefers-reduced-motion` OS → fallback immediato senza animazione |
| **Responsive** | Desktop-first only. Mobile deliberatamente fuori scope |
| **Copy i18n** | Conservativo: label sistema standard (Settings, Save, Cancel, Logout). Solo content narrativo (loading, empty, errors, CTA hero) è in-character |
| **Asset grafici** | Decisione per singolo asset quando arriva (no commitment upfront su game-icons vs SVG custom) |
| **Dipendenze nuove** | `framer-motion`, `@radix-ui/react-*` (Dialog, Popover, Dropdown, Tooltip), Google Fonts (Cinzel Decorative, Cormorant Garamond) |

## 2.2 Design system — tokens

File: `styles/tokens.css` (nuovo)

CSS custom properties organizzate per livelli:

```css
:root {
  /* ink & parchment — base */
  --ink-primary: #2a1a10;
  --ink-secondary: #5a4530;
  --ink-faded: #8a6f50;
  --parchment-base: #f4e8d0;
  --parchment-aged: #ead5a8;
  --parchment-shadow: #d4b888;

  /* accents */
  --gold: #b8860b;
  --gold-bright: #d4af37;
  --gold-deep: #8b6914;
  --blood: #8b0000;
  --blood-dark: #5a0a0a;
  --arcane: #1e3a5f;
  --arcane-deep: #0f1d30;

  /* ornaments */
  --ornament-stroke: var(--gold-deep);
  --divider-flourish: url('#flourish-a');

  /* motion */
  --page-turn: 600ms cubic-bezier(0.77, 0, 0.175, 1);
  --ink-draw: 1200ms cubic-bezier(0.22, 1, 0.36, 1);
  --mood-crossfade: 1800ms ease-in-out;
}

[data-theme="dark"] {
  --ink-primary: #f0e4cc;
  --parchment-base: #2a1a10;
  --parchment-aged: #1a0f08;
  --parchment-shadow: #0a0504;
  /* accents INVARIATI — oro/sangue/arcano lavorano su entrambi */
}
```

Tailwind config esteso per referenziare queste variabili (niente più `parchment-900` piatto): `bg-ink`, `bg-parchment`, `text-gold`, etc.

Integrazione Cinzel Decorative + Cormorant Garamond in `index.html` via Google Fonts + `font-family: var(--font-display)` / `var(--font-body)`.

## 2.3 Texture & ornamenti globali

File: `styles/tokens.css` + `assets/ornaments/` (SVG components da creare on-demand)

- **Grana SVG globale**: `<div class="noise-overlay">` con `feTurbulence` SVG a 0.85 opacity, `mix-blend-mode: multiply` su tema light, `screen` su dark. Fisso su body, pointer-events none.
- **Vignette**: radial gradient fixed, dark mode più pronunciato.
- **Pattern floreali ai bordi**: SVG decorativo ripetuto su top/bottom delle pagine main, tenuto tenue (`opacity: 0.08` su light, `0.15` su dark — oro).
- **Divisori ornamentali**: componente `<OrnamentDivider variant="flourish-a|b|c" />` che renderizza SVG tra sezioni — usati tra turni narrativi, tra sezioni character sheet, etc.
- **Cornici**: componente `<OrnateFrame>` con 4 corner-flourish SVG + border continuo, usato per card campagna, auth card, combat drawer.

## 2.4 Componenti — specifica dettagliata

### 2.4.1 Auth (login + register) — `features/auth/components/`

**Layout**: FULL-BLEED mappa antica + card "tomo aperto".

- **Sfondo**: SVG/PNG mappa fantasy stilizzata (continenti, rosa dei venti, creature marine marginali) in tema DARK. Rotazione lenta molto sottile (30s loop, ±1°) via Framer Motion. Vignette dark aggressiva ai bordi.
- **Card centrale**: `<OrnateFrame>` max-w-[720px] che simula un libro aperto a doppia pagina.
  - Pagina sinistra: titolo "SAGA" in Cinzel Decorative text-6xl uppercase letter-spacing 0.15em, oro bright, con sigillo SVG sotto (pentagramma stilizzato o equivalente). Sottotitolo Cormorant italic small "An endless tale awaits". Separatore flourish verticale tra le due pagine.
  - Pagina destra: form. Label Cinzel small-caps text-xs text-gold-deep. Input con border-bottom dorato (no box), focus espande sottolineatura con ink-draw animation. Password con toggle eye in-character (occhio stilizzato).
- **CTA**: button "Cross the Threshold" (login) / "Begin Thy Tale" (register) — border doppio dorato, background `ink-primary`, testo `gold-bright` Cinzel uppercase tracking 0.2em, hover: inner glow pulse oro. Ceralacca SVG animata a sinistra del text al hover (trickle down).
- **Errori**: inline sotto il form, Cormorant italic rosso blood, icona gocce d'inchiostro rosse. Messaggi differenziati per 4xx/5xx/network (dal hook `useAuthFlow`).
- **Switch login↔register**: testo piccolo in basso, link sottolineato oro.

Accessibility: `<label htmlFor>`, `focus-visible:ring-2 ring-gold-bright ring-offset-2`, errori con `aria-live="polite"`.

### 2.4.2 Campaign select — `features/campaign/components/campaign-select.tsx`

**Layout**: "The Shelf of Tales" — griglia di tomi su scaffale.

- **Sfondo**: tema DARK con texture legno scaffale in basso (SVG venature), pattern floreale tenue, vignette.
- **Header**: titolo "The Shelf of Tales" Cinzel Decorative text-5xl centrato, divisore flourish sotto.
- **Tomi**: grid-cols-5 gap-6 (desktop-only). Ogni tomo = SVG book spine verticale h-64:
  - Colore del dorso = hash stabile dal seed `campaign.hero_class` (mappa classe → colore, es. fighter → crimson, wizard → arcane blue, rogue → shadow).
  - Sigillo centrale = SVG generato da hash del `campaign.id` (geometria stabile, 6-8 pattern riutilizzati).
  - Titolo saga in Cinzel Decorative sul dorso, ruotato 90°.
  - HP ring dorato come fibbia inferiore (progresso = turn_number normalizzato).
  - Ironman: fibbia supplementare in rosso ceralacca in alto.
- **Hover**: il tomo "esce" leggermente dallo scaffale (translate-y -8px + rotate -3°), glow dorato tenue attorno, tooltip Radix con metadata (hero name, chapter, last turn preview).
- **Click**: transition page-turn → game-view.
- **"+" Begin a New Saga**: tomo speciale senza titolo, copertina bianca virgin con solo "+" dorato centrale. Hover: stesso effetto ma glow più luminoso.
- **Delete campaign** (feature nuova): Radix Dropdown trigger da icon "⋯" on hover del singolo tomo (top-right corner). Voci: "View details", "Export", "Delete". Click Delete → Radix Dialog con conferma standard "Are you sure? This action cannot be undone." + [Cancel] [Delete] (testo rosso). Nessun rituale brucia-tomo (per scelta utente, preferenza "Semplice conferma").

### 2.4.3 New campaign wizard — `features/campaign/components/new-campaign/`

**Stile**: rituale a 3 pagine di grimorio, full-screen DARK.

- **Background**: nero profondo + candela animata SVG (fiamma flicker via Framer Motion keyframes: scale 0.98→1.02, rotate -2°→2° random). Cera che cola molto lenta (pseudo-statica).
- **Container**: pergamena srotolata centrale max-w-[800px], cornice ornata OrnateFrame.
- **Stepper**: tre sigilli SVG in alto (es. ✷ ❖ ⚔), sigillo attivo illuminato (oro bright + glow), altri fade. Linea dorata sottile che connette.
- **Transizione tra step**: page-turn animation (Framer Motion AnimatePresence + 3D rotateY). Durata 600ms.

**Step 1 — "The World Awaits"**:
- Titolo Cinzel Decorative text-4xl.
- Template preset come card pergamena (3-4 per riga). Ogni card: icona SVG del regno (forest/castle/dungeon/sea) + nome + descrizione Cormorant italic 2 righe. Hover: bordo oro + lift.
- Radio invisibile, card selezionata = bordo oro doppio + ceralacca centrale.

**Step 2 — "The Hero"**:
- Split 2 colonne: sinistra = classi come portrait illustrati (SVG/icon fantasy da definire per asset), destra = stats preview live (STR/DEX/CON/INT/WIS/CHA come piccoli sigilli circolari con valore al centro + modifier calcolato via `dnd.abilityMod`).
- Classe selezionata: glow oro + fiamma candela si riflette nell'aura del portrait.
- Campo "Hero Name": input minimal con linea inchiostro, Cormorant italic, placeholder "What shall they call thee?".

**Step 3 — "The Fate"**:
- Campo "Campaign Name" (Cormorant italic large).
- Death mode: 3 scelte come sigilli di ceralacca da premere (Radix RadioGroup):
  - **Mercy** — "Deaths are but pauses in thy tale." (sigillo standard)
  - **Grim** — "Death marks thee. Consequences endure." (sigillo rosso scuro)
  - **Ironman** — "One life. One chance. Permanent death." (sigillo rosso sangue con crepa SVG, animazione pulse)
- Click su sigillo = animazione ceralacca fonde + impronta sigillo dorata (Framer Motion layout animation).
- CTA finale: "Begin thy Saga" — ornate button grande.

### 2.4.4 Game view layout — `features/game/components/game-view.tsx`

**Struttura principale**: narrazione centrale + drawer animati on-demand.

```
┌────────────────────────────────────────────────────────┐
│  ≡ [Banner ornamentale: Saga · Chapter N · Sigillo ]  ≡ │  ← fixed header
│────────────────────────────────────────────────────────│
│                                                        │
│          [ narrative-stream — max-w-[70ch] ]           │
│                                                        │
│          scroll verticale continuo stile "libro"       │
│                                                        │
│          [ cartiglio action-input — centered ]         │
│                                                        │
│                      ⚔  ✦  ⚖  ☰                       │  ← action toolbar
└────────────────────────────────────────────────────────┘
```

- **Banner ornamentale fisso**: top, h-16. Contenuto: nome campagna in Cinzel Decorative text-xl centrato, divisore flourish SVG sui lati, "Chapter {turn_number}" piccolo in uppercase Cinzel tracking largo a sinistra, sigillo campagna a destra, icona exit `←` all'estrema sinistra. Background pergamena leggermente più scura del main (`parchment-aged`) con bordo inferiore ornamentale.
- **Main column**: scroll continuo, max-w-[70ch] centered, padding generoso verticale. Background pergamena base + grana + vignette sottile.
- **Action toolbar** (bottom floating, centered): 4 icone ornate in linea — `⚔ Character`, `✦ Journal`, `⚖ Settings`, `☰ (extra)`. Tooltip Radix. Click apre il drawer corrispondente. Durante combat, la toolbar include un 5° glifo `🛡 Combat` che apre il combat drawer.
- **Drawers**: Radix Dialog variant "sheet" (da implementare come componente custom in `shared/ui/drawer.tsx`). Entra da destra con Framer Motion `{ x: '100%' → 0 }`, durata 400ms. Overlay scuro tenue dietro. ESC o click-overlay chiude. Dentro: pergamena srotolata verticale.

### 2.4.5 Narrative stream — `features/narrative/components/`

**Il cuore del prodotto**. Deve sembrare un manoscritto reale.

#### `narrative-stream.tsx`
- Lista di `<TurnBlock>` verticale, scroll continuo.
- Ogni turno preceduto da `<OrnamentDivider variant="flourish-{hash}" />` (4-5 varianti SVG ruotanti per diversità).
- **Drop-cap SOLO sul primo turno** del chapter (o del session restart): prima lettera del primo paragrafo in Cinzel Decorative text-7xl float-left, letter-spacing -0.02em, padding-right 0.2em, color gold, con stroke-draw animation al reveal (SVG text con `stroke-dasharray` animato).
- `aria-live="polite"` per nuovi turni → screen reader support.

#### `turn-block.tsx`
Contiene sequenza:
1. Divisore ornamentale (stagger delay 0ms)
2. DM narration paragraphs (stagger 150ms each)
3. NPC blocks (se presenti, inline dove appaiono)
4. Player action cartouche (stagger +200ms dopo narration)
5. DM follow-up narration (se c'è)
6. Dice result inline (se presente)
7. Suggested actions pill (stagger +300ms)

**Staggered reveal**: Framer Motion `staggerChildren: 0.15`, opacity 0→1 + translate-y 8px→0. Rispetta `reduced-motion`.

#### `dm-paragraphs.tsx`
- Cormorant Garamond text-lg leading-loose ink-primary.
- First-line-indent 2em (stile editorial), tranne primo paragrafo del chapter (drop-cap).
- Typewriter attivo solo sull'ULTIMO turno (turni storici sono statici).
- Italic utilizzato per pensieri/descrizioni interne (tag `_..._` mappati a `<em>`).

#### `npc-block.tsx`
Decisione: **blocchetto rientrato "sealed"** — non wrapper chat, non inline puro.
```
[paragraph DM]

   ⦿ THE INNKEEPER
   "What brings ye here,
    stranger? We see few
    travelers these days."

[paragraph DM che continua]
```
- Rientro sinistro 2rem.
- Riga 1: sigillo circolare SVG (⦿ placeholder, in realtà glyph generato da hash del nome NPC, colore dal hash hue stabile) + nome in Cinzel Decorative uppercase text-xs letter-spacing 0.2em color gold-deep. Inline.
- Righe successive: quote tra virgolette dorate (usare U+201C/201D con stile `color: gold`), Cormorant Garamond italic text-lg ink-primary.
- Nessun background, nessun bordo. Solo rientro + sigillo+nome.
- Se backend mandasse flag `npc_type: 'major'` in futuro → variant con `<OrnateFrame>` attorno; oggi tutti uguali.

#### `player-action.tsx` (cartiglio inline rientrato a destra)
**Decisione confermata**: cartiglio rientrato a destra, distinto ma integrato.
```
[DM paragraph]

              ╭─ॐ─────────────╮
              │ (T) Tomma acts: │
              │                 │
              │ I draw my sword │
              │ and step forward│
              ╰─────────────────╯

[DM paragraph]
```
- `<OrnateFrame variant="small">` con corner-flourish SVG.
- `ml-auto mr-0 max-w-[50ch]` → rientrato a destra.
- Background `parchment-shadow` (leggermente più scuro del main).
- Header riga: sigillo circolare con iniziale del PG (first letter di `character.name`, font Cinzel, colore hash stabile da nome) + "{name} acts:" in Cinzel small-caps text-xs color gold-deep.
- Testo azione: Cormorant Garamond italic text-lg color ink-primary.

#### `dm-loading.tsx`
- Quando il turno è pending (mutation in flight):
- Piccolo blocco rientrato sotto l'ultimo turno: "⦿ THE DM" con sigillo pulsante oro + testo Cormorant italic rotating:
  - "The dice are carved..."
  - "Ink dries on the page..."
  - "The Loom weaves thy fate..."
  - "Stars align..."
  - "The Weave trembles..."
- Rotation random ogni 2s. Array in `shared/i18n/en.ts` sotto `loading.dm`.
- Three dots animation (...) aggiunti dopo il testo rotante come typewriter pulse.

#### `dice-roller.tsx` (inline + SVG 2D + rolling effect)
- **Inline nel flusso** (dentro turn-block, dove il DM chiede il tiro).
- SVG d20 stilizzato (hexagon piatto con numeri nascosti all'inizio).
- **Rolling phase** (1.2s): numero centrale ruota random (simile a implementazione attuale, mantenere perché "va bene" — user feedback), dado SVG ha animazione shake + rotate.
- **Reveal phase**: numero finale appare con ink-blot SVG che si espande (macchia dorata, ~200ms).
- **Crit 20**: fiamma dorata SVG effimera sopra il dado (0.6s), particelle gold scattering, screen-glow sottile giallo.
- **Crit 1**: macchia sangue SVG che cola sotto il dado, screen-shake subtle (translate-x ±2px 80ms).
- Dopo reveal resta come "timbro" nel testo: `◆ 17 — STR save ✓` in Cinzel tracking large color gold.
- Audio: `new Audio()` → preload-once su mount (fix latency issue). Volume controllabile da settings (Sprint 2 settings drawer).

### 2.4.6 Action input — `features/game/components/action-input.tsx`

**Decisione confermata**: cartiglio rituale.

```
  ╭─⊜───────────────────⊜─╮
  │  what do you do?        │
  │  _____________________  │
  │              [ seal ]   │
  ╰─⊜───────────────────⊜─╯
```

- Width max-w-[65ch] centered sotto l'ultimo turno, margin-top 4rem.
- `<OrnateFrame>` con 2 sigilli ornamentali SVG sui lati (⊜ placeholder — decidere asset).
- Background `parchment-aged` tenue.
- Label dentro: "What do you do?" in Cinzel small-caps text-xs color gold-deep, top-left.
- Textarea multiline (non più input single-line):
  - Font Cormorant Garamond italic text-lg ink-primary.
  - Border: nessuno. Solo underline dorata tenue che cresce animata al focus (scale-x 0→1 ink-draw).
  - Placeholder: rotating, "I draw my sword...", "I search the chamber...", "I speak softly to the stranger..." (Cormorant italic faded).
  - Auto-grow su multiline fino max 6 righe.
- Submit button "[ Seal ]": bottom-right dentro il cartiglio. Ornate: Cinzel tracking 0.2em, wax-stamp SVG che appare on hover (goccia ceralacca rossa che cade). Disabled stato = grayed gold-deep. Click = animation stamp-press (scale 1→0.95→1 200ms).
- Shortcut: Ctrl+Enter per submit (tooltip Radix).
- **Suggested actions**: sotto il cartiglio, strip di 3-4 pill ornate (border oro, Cormorant italic, background parchment-aged). Click auto-popola textarea. Label prima delle pill: "Possibilities:" small-caps faded.

### 2.4.7 Character sheet (tomo a doppia pagina modal) — `features/character/components/character-sheet.tsx`

**Decisione confermata**: modal fullscreen libro aperto (NON drawer).

Apertura: click `⚔ Character` nella action toolbar → Radix Dialog fullscreen con overlay dim. Framer Motion: book apre con 3D rotateY da 90° → 0 (effetto "tomo che si apre") durata 700ms.

```
╔══════════════════╦══════════════════╗
║  (portrait)      ║  Inventory       ║
║    ⚜ TOMMA ⚜    ║  ⚖ longsword     ║
║                  ║  ⚖ potion x2     ║
║  STR ●  16 +3    ║  ⚖ rope 50ft     ║
║  DEX ●  14 +2    ║                  ║
║  CON ●  13 +1    ║  Skills          ║
║  INT ●  10 +0    ║  ◈ athletics    ║
║  WIS ●  12 +1    ║  ◈ perception   ║
║  CHA ●   8 -1    ║                  ║
║                  ║  Companions      ║
║  HP [███████░░]  ║  (⦿) Miriam      ║
║     28/40        ║   HP █████░       ║
║                  ║   mood: Loyal    ║
╠══════════════════╩══════════════════╣
║        ◈ Background & Bio ◈         ║
║   (Cormorant italic prose)          ║
╚═════════════════════════════════════╝
```

**Pagina sinistra (Stats & Identity)**:
- Portrait circolare (200px) con OrnateFrame custom (4 corner flourish). Placeholder: iniziale grande in Cinzel Decorative + fondo gradient hash-based. Se asset portrait futuro, sostituire.
- Nome PG sotto in Cinzel Decorative text-3xl centered, flankato da due flourish SVG orizzontali.
- Class + level piccoli in Cormorant italic.
- **Stats**: grid 2-col di 6 sigilli circolari. Ogni sigillo (80px) = SVG cerchio ornato con nome stat in small-caps top arc (STR/DEX/etc.), valore grande al centro (Cinzel text-2xl gold), modifier in basso (+3/-1) small. Hover: sigillo pulse + tooltip con descrizione stat.
- **HP bar**: ceralacca rossa liquida dentro cornice dorata (SVG mask custom a forma di pergamena rettangolare). Animata con ink-flow quando cambia.
- **XP bar** (se presente): simile ma gold liquid.

**Pagina destra (Gear & Skills & Companions)**:
- **Inventory**: elenco manoscritto. Bullet = ⚖ SVG custom. Cormorant Garamond text-base. Hover item: Radix Tooltip con descrizione + stats.
- **Skills/proficiencies**: elenco simile con ◈ bullets.
- **Companions**: blocchetti "sealed" (stesso pattern NPC block) con portrait mini circolare + nome Cinzel small-caps + HP bar small + mood glyph. Click companion → sub-modal dettaglio companion (opzionale Sprint 2.5).

**Strip bottom (full-width)**: background & bio, prose Cormorant italic. Text area ornata con corner flourish.

Close: X in top-right (ornate), ESC, click-overlay.

### 2.4.8 Combat tracker — `features/combat/components/combat-tracker.tsx`

**Decisione confermata**: bottom drawer con lista iniziativa araldica, **attivo solo durante combat**.

- Si apre automaticamente quando `game-store.combat_state.active === true`, si chiude quando diventa false (fade-out down 400ms).
- Position: fixed bottom-0 left-0 right-0, h-48. Max-w-[1200px] centered. Slide-up da `{y: '100%'}` → `{y: 0}` con Framer Motion, durata 500ms.
- OrnateFrame variant large, background `parchment-aged`.
- Header: "⚔ INITIATIVE" Cinzel Decorative tracking 0.3em gold, divisore flourish.
- Body: lista orizzontale (flex) partecipanti. Ogni partecipante = card h-24 w-32:
  - Top: sigillo/iniziale + nome in Cinzel small-caps (player = ❖ oro, enemy = ▒ rosso blood).
  - HP bar ceralacca (rossa per enemy, oro per player) con cornice.
  - Conditions/status come mini-icon SVG sotto (veleno ☠, stunned ⚡, etc.).
- **Current turn evidenziato**: glow pulsante oro + "◀ your turn" in Cormorant italic dorato sotto. Altri fade.
- Scroll orizzontale se > 6 partecipanti.
- Close button: niente — il tracker si chiude solo quando combat termina (stato backend).

### 2.4.9 Quest / journal drawer — `features/game/components/journal-drawer.tsx`

**Decisione confermata**: drawer "ledger" pergamena.

- Apertura da `✦ Journal` toolbar → Radix Dialog sheet-right. W-[480px] full-height. Slide-in da destra.
- Header: "The Ledger" Cinzel Decorative text-3xl, divisore flourish, subtitle "Deeds & Oaths" small-caps.
- **Sezioni**:
  - **Active Quests**: elenco manoscritto. Ogni quest = entry:
    - Titolo Cinzel Decorative text-lg gold + sigillo ornato mini a sinistra.
    - Descrizione Cormorant italic ink-primary.
    - Obiettivi come checklist: bullet = ◇ (pending) / ◆ (complete). Completati con strikethrough + inchiostro rosso.
  - **Completed** (collapsible Radix Accordion): quest done, barrate in rosso, timestamp in Cormorant italic small.
- Scroll interno. Footer sottile con count "X active, Y completed".

### 2.4.10 Settings drawer — `features/game/components/settings-drawer.tsx`

**Nome utente-facing**: "Hand of Fate" (in-character per questo drawer specifico, unica eccezione al principio conservativo perché è il naming di una superficie narrativa).

- Apertura da `⚖ Settings` toolbar (sia in game-view CHE dalla home/campaign-select — accessibilità globale). Radix Dialog sheet-right w-[420px].
- Titolo "Hand of Fate" Cinzel Decorative + flourish.
- **Sezioni** (Radix Accordion o tab verticale):
  - **Audio**: toggle musica ambient (on/off), toggle dice sound, toggle typewriter scratch sound (if implementato), slider volume master.
  - **Motion**: radio "Auto (follow OS)" / "Reduced" / "Full". Default Auto.
  - **Display**: toggle dark/light override (default = auto per context: narrative light, menu dark), slider font-size (base 18px → range 14-24).
  - **Account**: email (readonly), button "Manage API Keys" (sub-dialog), button "Depart" (logout — label conservativa standard).
  - **Campaign** (solo in game-view, nascosta in home):
    - Button "Inscribe" (save manuale).
    - Button "Recall" (load — apre sub-modal con save list).
    - Button "Export as Tome" (download JSON).
  - **Danger Zone** (solo in campaign select): inline text "To burn a tome, open the menu from the bookshelf."

Tutti i label sistema (save, load, volume, reset) restano standard/traducibili. Solo le sezioni hanno nomi atmosferici.

### 2.4.11 Typewriter — `features/narrative/hooks/use-typewriter.ts` (versione umanizzata Sprint 2)

Decorazioni attive (sopra base Sprint 1):

1. **Pause variabili su punteggiatura**:
   - `.` → 400ms
   - `,` → 150ms
   - `!` / `?` → 500ms
   - `;` / `:` → 250ms
   - `—` (em dash) → 300ms
   - paragraph break (`\n\n`) → 800ms
2. **Variabilità random sulla velocità base**: ogni carattere `baseSpeed + random(-20ms, +20ms)`.
3. **Burst mode**: 5% chance per carattere di scrivere 3-4 caratteri insieme (simula accelerazione dattilografo).
4. **Respiro prima del dialogo**: pause 300ms quando arriva `"` o `“` (ma non se è fine quote).

**Non attivato** (per scelta utente): scratch sound pennino.

**Reduced motion**: short-circuit — intero testo reso subito.

API del hook:
```ts
const { displayed, isTyping, skip } = useTypewriter({
  text,
  baseSpeed: 22,   // ms per char
  onComplete,
  reducedMotion,
});
```
Tap/click sull'area narrativa attiva `skip()` → testo completo istantaneo (UX fast-forward).

### 2.4.12 Mood crossfade — `styles/mood.css` + hook

- Mood viene dal backend nel turno (`turn.mood`).
- Mapping mood → gradient + overlay:
  - `tense` → gradient radial scuro centro, vignette nera intensa.
  - `peaceful` → gradient warm parchment-aged, light leak dorato sottile top-left.
  - `mysterious` → overlay nebbia SVG animata (slow drift + opacity pulse).
  - `combat` → overlay rosso tenue ai bordi, vignette più stretta, sottile pulse.
  - `sacred` → light leak gold centrale alto.
  - `cursed` → overlay verde-nero ai bordi, sottile glitch.
  - `default` → nessun overlay extra.
- Transizione: CSS `transition: 1.8s ease-in-out` su `background-color`, `opacity` degli overlay layer. Framer Motion per overlay SVG con `AnimatePresence` su mood change.
- Layer DOM: `<MoodLayer>` fixed inset-0 pointer-events-none z-0 dentro `App.tsx`.

### 2.4.13 Page transitions — Framer Motion

`<AnimatePresence mode="wait">` in `App.tsx` wrappa `<Routes>`.

- Auth → Campaign select: fade + slight scale (0.98→1). 400ms.
- Campaign select → Game view: **page-turn** effect. Rotate Y 0→-180° + fade. 600ms. Evocativo di "aprire il tomo".
- Game view → Campaign select: reverse page-turn.
- Dentro game view (drawer apertura): gestito da Radix + Framer dentro Drawer component.

Rispetta reduced motion → fade semplice 200ms.

### 2.4.14 Error boundary visual — Sprint 2 upgrade

Fallback ornato: full-screen pergamena strappata, testo "The Weave tears…" Cinzel Decorative, sub "Something has gone awry." Cormorant italic, button "Restore" (reload).

## 2.5 Copy / i18n Sprint 2

File: `shared/i18n/en.ts`

**Invariato (conservativo)**: tutti i label di sistema — Settings, Save, Load, Cancel, Submit, Email, Password, Sign In, Sign Out, etc.

**Cambiato / nuovo (in-character content)**:
- Loading DM (rotating, 5 varianti — vedi 2.4.5 dm-loading).
- Empty campaigns: "The shelf is empty. Begin thy first saga."
- Empty quests: "No deeds yet inscribed."
- Narrative stream empty: "Thy tale awaits the first word…"
- Error auth: "The gate does not yield." (4xx) / "The Weave is silent." (5xx).
- CTA auth: "Cross the Threshold" (login) / "Begin Thy Tale" (register).
- CTA action: "Seal" (submit action).
- CTA new campaign: "Begin thy Saga".
- Header sections: "The Ledger" (journal), "Hand of Fate" (settings only as section name).
- Textarea placeholders rotating (action input — vedi 2.4.6).

Tutti questi strings in `en.ts` con namespace chiaro (`loading.dm`, `empty.campaigns`, `cta.auth.login`, etc.) per future traduzioni.

## 2.6 Accessibility sweep (Sprint 2)

Tutti i fix critici identificati nell'audit:
- `focus:outline-none` → `focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright focus-visible:ring-offset-2 focus-visible:ring-offset-parchment-base` (token utility).
- Tutti i `<label>` con `htmlFor` + input `id`.
- `aria-label` su icon-only buttons (`←`, `⋯`, close X).
- `aria-live="polite"` su narrative stream new turns + loading.
- Semantic landmarks: `<main>`, `<nav>`, `<aside>` dove opportuno.
- Skip-link invisible in top-of-page per keyboard users.
- Color contrast audit (axe-core): tutti i testi su pergamena ≥ 4.5:1 (ink-primary su parchment-base OK, ma verificare gold-deep e ink-faded).
- Keyboard nav: drawer chiudibili ESC, dialog con focus-trap (Radix gestisce), arrow keys in stepper nuovo-campaign.
- `prefers-reduced-motion` rispettato ovunque (typewriter, page transitions, stagger, mood).

## 2.7 Asset grafici

**Decisione utente**: decidere asset-by-asset quando il componente viene implementato, non commitment upfront.

Per ogni asset, al momento dell'implementazione valuteremo tra:
1. SVG custom scritto inline (preferito per cornici, divisori, drop-cap, sigilli astratti).
2. `react-game-icons` library (CC-BY game-icons.net) per glifi concreti (sword, shield, potion, companion icons).
3. Asset esterni (fonts, noise texture base64).

Asset "signature" da creare custom (non disponibili in library):
- OrnateFrame 3 varianti (small/medium/large).
- Divisori flourish A/B/C/D (4 rotazioni).
- Sigillo SAGA (logo).
- Drop-cap per A-Z (o runtime-rendered via SVG text + stroke).
- D20 ornato SVG.
- Mappa antica background per auth.
- Candela animata.

## 2.8 Dipendenze nuove

```json
{
  "framer-motion": "^11",
  "@radix-ui/react-dialog": "^1",
  "@radix-ui/react-dropdown-menu": "^2",
  "@radix-ui/react-popover": "^1",
  "@radix-ui/react-tooltip": "^1",
  "@radix-ui/react-accordion": "^1",
  "@radix-ui/react-radio-group": "^1"
}
```

Google Fonts (via `<link>` in index.html):
- Cinzel Decorative (400, 700, 900)
- Cormorant Garamond (300, 400, 500, 600 + italic variants)

## 2.9 Testing Sprint 2

- Rewrite visual tests esistenti per ogni componente rifatto (login-form, register-form, campaign-select, new-campaign, character-sheet, narrative-stream, combat-tracker, companion integrato).
- Nuovi test:
  - `drawer.test.tsx` (primitivo condiviso).
  - `ornate-frame.test.tsx`.
  - `mood-layer.test.tsx` (crossfade on mood change).
  - `page-turn-transition.test.tsx`.
  - `dice-roller.test.tsx` (crit fail + crit success effects).
  - `delete-campaign-dialog.test.tsx`.
- Visual regression (Playwright screenshots opzionale Sprint 2.5): snapshot di auth, campaign-select, game-view baseline.
- `axe-core` run su ogni route principale.

## 2.10 File toccati in Sprint 2 (riepilogo)

**Nuovi (ricchi)**: tutti i componenti in `features/*/components/` rifatti, `shared/ui/{drawer,ornate-frame,ornament-divider,modal}.tsx`, `assets/ornaments/*.tsx` (SVG components), `styles/tokens.css`, `styles/mood.css` esteso, componenti layer `<MoodLayer>`, `<NoiseOverlay>`, `<VignetteLayer>`.

**Modificati**: `App.tsx` (layout layer, page transitions, error boundary visual), `index.html` (Google Fonts), `tailwind.config.ts` (tokens), `index.css` (base reset per tema dual).

## 2.11 Verifica fine Sprint 2

1. `cd frontend && npm run lint && npm run test && npm run build` → tutto verde.
2. `cd frontend && npm run dev` — checklist manuale flussi:
   - [ ] Landing: login full-bleed mappa + card tomo apre a scena.
   - [ ] Login happy path → campaign-select con tomi su scaffale.
   - [ ] Hover tomo → lift + tooltip.
   - [ ] Delete campaign: dropdown → dialog conferma → refresh lista.
   - [ ] "+ Begin New Saga" → wizard 3 step con page-turn.
   - [ ] Ogni step wizard: selezione con feedback (glow, ceralacca).
   - [ ] Game view: banner ornamentale, narrazione con drop-cap primo turno, divisori tra turni.
   - [ ] Submit action → cartiglio rituale + typewriter umanizzato risposta.
   - [ ] NPC dialogue appare con blocchetto sealed, non chat bubble.
   - [ ] Dice roll inline con rolling + reveal + crit effects.
   - [ ] Toolbar bottom → drawer character (tomo modal) / quest (ledger) / settings.
   - [ ] Combat: drawer bottom appare quando combat active, scompare quando finisce.
   - [ ] Mood change: crossfade atmosferico visibile tra turni.
   - [ ] Page transition campaign-select → game-view con effetto tomo-apre.
3. Accessibility audit: `axe` CLI → zero violations critiche.
4. Reduced motion: abilita OS setting → typewriter diventa istantaneo, page transitions → fade breve, stagger disabilitato.
5. Font check: Cinzel Decorative + Cormorant Garamond caricati (Network tab conferma).
6. Performance: Lighthouse ≥ 85 performance (desktop), ≥ 95 accessibility.

---

## File critici di riferimento (entrambi gli sprint)

### Backend (lettura per allineamento)
- `backend/app/schemas/turn_response.py` — per Zod schema frontend.
- `backend/app/api/campaigns.py` — delete endpoint check/add.
- `backend/app/core/dm/*` — per capire quali campi DM produce (mood, combat_state).

### Frontend (già esistenti, da toccare)
- `frontend/src/App.tsx` — routing + layer globali.
- `frontend/src/services/api.ts` → `shared/api/client.ts` (refresh mutex + Zod validation).
- `frontend/src/stores/game-store.ts` → `shared/stores/game-store.ts` (tipi da schema).
- `frontend/src/components/narrative/*` → `features/narrative/components/*` (rewrite completo Sprint 2).
- `frontend/src/components/game-view.tsx` → `features/game/components/game-view.tsx` (layout nuovo).
- `frontend/src/components/new-campaign.tsx` → split in `features/campaign/components/new-campaign/*` (Sprint 1 split, Sprint 2 re-skin).
- `frontend/tailwind.config.ts` — estesa con tokens in Sprint 2.
- `frontend/index.html` — fonts Google in Sprint 2.

### Riutilizzo di codice esistente
- `frontend/src/styles/mood.css` — base già presente, esteso in Sprint 2 con overlay SVG.
- `frontend/src/hooks/` (oggi .gitkeep) — riempito con hook estratti.
- Mapping classe→colore per tomi su scaffale può riusare logica di `new-campaign.tsx:26-108` (class presets) spostata in `features/campaign/data/class-presets.ts`.
