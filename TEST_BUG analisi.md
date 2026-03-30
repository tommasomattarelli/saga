ma prima di procedere --> REDIS Non andava mica tolto? serve ancora? 


Checklist Playtest Completa — SAGA v1

  Organizzata per area. Spunta man mano che testi.

  ---
  1. CREAZIONE CAMPAGNA - no bugs ma rifinire 

  - Puoi creare una campagna senza errori - SI
  - Il dropdown death mode mostra Ironman / Destino / Cronista  - NON è DROPDOWN MA SCELTA, ma scelgo
  - La campagna appare nella lista dopo la creazione - SI, MA DALLA CAMPAGNA NON CE IL TASTO TORNA INDIETRO/EXIT
  - Navigare alla campagna carica la game view senza crash - SI

  ---
  2. CREAZIONE PERSONAGGIO

  - Al primo turno il DM chiede di descrivere il personaggio (non inizia l'avventura subito) 
      BUG : il DM non chiede nulla parte subito l avventura/ quindi tutte le casistiche sotto sono da escludere e còassificare come bug
      io userei non il dm ma un chatbot specifico il cui compito è quello di creare il personaggio e adgjust it, anche durante la vventura(?) cosa pronponi tu? oppure farlo creare manualmente all utente come si fa su dnd magari
  - Dopo la descrizione il DM genera una scheda completa (nome, stats, HP, inventario)
  - La scheda appare nel Character Panel laterale dopo la generazione
  - Gli attributi mostrano il modificatore corretto (es. STR 14 → +2)
  - L'HP bar è visibile e corretta (current/max)
  - L'inventario iniziale è popolato
  - Puoi chiedere aggiustamenti ("can I be stronger?") e il DM ri-genera
  - Dopo conferma, l'avventura inizia con una scena di apertura
  BUG: tutta la scheda del character di fianco è rotta, non appare nessun numero

  ---
  3. TURNO BASE — STREAMING

  - Il testo del DM appare in streaming token per token (non tutto in blocco) 

  - Non ci sono blocchi improvvisi durante lo streaming
    BUG: CI sono blocchi improvvisi, con questo err in console ebSocket connection to 'ws://localhost:3000/api/ws/da15d25e-e938-4853-83fb-076316cd3b62?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3MTBiZWFlMi04M2RkLTQwMDktODNmNi03OGZiNGViZmIxODAiLCJleHAiOjE3NzQ4MTkwMDYsInR5cGUiOiJhY2Nlc3MifQ.riiXSMHoSD5VDLh971pLgB-bNoz5fLC7J8Sq5oHk420' failed: WebSocket is closed before the connection is established.
disconnect @ websocket.ts:64Understand this warning

  - Dopo il turno compare il bottone "Continua" (se non serve azione obbligatoria)
  BUG: NO NON APPARE NESSUN BOTTONE, SOLO LE AZIONI CONSIGLIATE
  - Premere "Continua" senza scrivere nulla invia un'azione "wait" implicita / NON APPARE 
  - Il turno precedente rimane visibile nello scroll (i messaggi non spariscono) SI
  - Ricaricare la pagina mantiene la storia (i turni precedenti riappaiono) BUG: SI PERDONO I MESSGAGI A RICARE LA PAGINA O A CHIUDERE E RIAPRIRE
  - Il numero di turno in header si incrementa SI, ma solo se si raggiorna la pagina, altrimenti no

  non si VEDONO NEMMENO I MESSAGGI MANDATI DALL UTENTE, AVREBBE SENSO CHE SIANO VISIBILI

  IMPORTANTE, A VOLTE SEMBRA CHE CRASHI . NON SO SE ERRORE APLICAZIONE O ERRORE API --> METTEREI DEI LOG MOLTO DETTAGLAITI, COME SI FA IN APP SOTA con AI il logging?

  ---
  4. RISPOSTA DM — QUALITÀ E FORMATO

  - La narrazione è coerente con l'azione inviata SI ABBASTANZA (rifinire nel systsem prompt ma piu avanti)
  - Il DM non risponde in JSON grezzo (nessun { visibile nella narrazione) UNA SOLA VOLTA MI HA RISPèOSTO CON ''json {....}
  - Le suggested_actions appaiono come bottoni cliccabili dopo la narrazione SI, MA BUG: RIMANGONO VISIBILI E CLICCABILI SOTTO ALL SINGOLO TURNO ANCHE SE SI VA AVANTI (NON VA BENE)
  - Cliccando un suggested action lo mette nell'input
  - L'ambient_detail appare (testo secondario/corsivo) quando presente SI
  - Il DM usa la lingua corretta (italiano se campagna italiana) SI IN ITALIANO. magari rendere piu forte le lingue? 
  - Il DM non si ripete uguale tra turni consecutivi FUNZIONA 
  - Il DM ricorda cose dette 5+ turni fa (test: menziona un NPC, riparla dopo 6 turni) SI

  ---
  5. WORLD STATE & HEADER

  - La location in header cambia quando ti sposti, NO VIENE SEMRPE UNKNOWN LOCATION
  - Il giorno/ora in header avanza (es. "Day 1, morning" → "Day 1, afternoon") SI, ma non capisco come con che principio
  - La stagione è mostrata correttamente NO, NESSUNA STAGUIONE VIENE MOSTRATA
  - Il world state persiste dopo reload pagina SI

  ---
  6. DADI

  - Per azioni con esito incerto il DM chiede un tiro (non per azioni banali) LO CHIEDE UN PO TROPPO SPESSO
  - L'animazione del dado appare prima della narrazione del risultato NO. 
  - Il dado mostra: tipo check, roll grezzo, modifier, totale, DC, outcome SI
  - Il colore è corretto: rosso per fail, verde per success, oro per crit SI
  - Il suono del dado si sente NO, ma secondario questo
  - Il vantaggio (2d20 take high) funziona quando rilevante
  - Dopo il tiro il DM narra in base all'outcome (fail diverso da success) --> non ancora provato, nessun natural 20/1 mi sono usciti un po di sfiga
    - Natural 20 → narrazione di successo epico
    - Natural 1 → narrazione di fallimento drammatico
  - Il DM NON chiede tiri per azioni triviali (camminare, parlare, raccogliere) SI 

  BUG: i dati hanno un bug importante, quando viene generata la risposta in streaming sopra la risposta appaiono una decina di tatsi roll cliccabili, che fanno crashare l applicaizone. inoltre il lancio dei dati viene messo sopra la risposta del turno, risutla facoltatico (se non clicco posso andar avanti lo stesso) . l ideale sarebbe metterlo sotto la risposta

  ---
  7. SCENE MOOD

  - Il colore/sfondo del pannello cambia in base alla scena SI, ANCHE SE NON MI PIACE TANTO, TU COSA NE PENSi?
  - combat_fury → toni rossi
  - calm_exploration → toni verdi
  - tense_anticipation → toni ambra
  - La transizione tra mood è smooth (non brusca)
  - Mood neutral come default se il DM non specifica SI 

  ---
  8. NPC & COMPANION

  - Quando interagisci con un NPC, appare il suo dialogo separato dalla narrazione DM BUG: NO, nella narrazione il DM parla anche per NPC
            non spezzerebbe un po la narrazione pero se i dialoghi fossero fatti solo alla fine? oppure renderebbe il dm solo descrittivo? IL DM COMUNQUE DICE FRASI ANCHE PER CONTO DEL GIOCATORE 
  - NPC diversi hanno toni/voci distinte
  - La disposition di un NPC cambia dopo interazioni positive/negative NON PROVABILE NON PARLANO
  - Un NPC ostile parla diversamente da uno amichevole
  - I companion reagiscono alle azioni del player (companion_actions)
  - La Companion Bar mostra i companion presenti (se implementata)

  ---
  9. CHARACTER PANEL

  - Il pannello si apre/chiude cliccando "Character" SI 
  - Mostra: nome, attributi con modificatori, HP current/max, inventario, quest attive NO, mostra questo Tom
HP
/
Level
XP
AC:
Gold:
Abilities
Inventory
Empty
  - L'HP si aggiorna in tempo reale quando prendi danno NO, non vedo nessun valore di hp
  - L'inventario si aggiorna quando acquisti/perdi oggetti
  - Le quest appaiono quando il DM le assegna NON ASSEGNA LE QUESTs

  ---
  10. COMBAT

  - Descrivi un'azione aggressiva → il DM avvia il combattimento SI, APPARE COMBAT FURY
  - Il CombatTracker appare in alto a destra NON APPARE NULLA, TUTTI I PUNTI SOTTO SONO FAILED
  - L'ordine di iniziativa mostra player + nemici
  - Il numero di round è visibile ("COMBAT - Round 1")
  - Il combattente corrente è evidenziato (bordo rosso)
  - Player: blu, companion: verde, nemici: rosso
  - Le HP bar si aggiornano quando qualcuno prende danno
  - Un nemico a 0 HP appare in grigio/strikethrough
  - Il CombatTracker scompare quando il DM chiude il combattimento
  - Non puoi salvare manualmente durante il combattimento (prova → errore)
  - Il scene mood diventa combat_fury durante il combattimento

  ---
  11. DEATH SYSTEM BUG NEESSUN DEATH SYSTEMN FUNZIONA. posso morirre, la narrazzione narra la morte, ma poi posso continuare, potenzialmente anche a rivivere. tutto questo va rivisto. inoltre sembra che siail giocatore che comdan, non IL DM
  il dm mi ha fatto rivivere se glielo ho chiesto

  Cronista:
  - Porta il personaggio a 0 HP (chiedi al DM di farti subire danno massivo)
  - Appare l'overlay "Near Death!" giallo
  - Il pulsante "Continue" è presente e lo chiude
  - L'HP è tornato a 1 dopo il dismiss
  - La narrazione del DM descrive una quasi-morte, non una morte

  Destino:
  - Stessa situazione → appare "Fate Intervenes!" viola
  - Il testo mostra il cost_hint (es. "Minor cost: lose an item...")
  - Il contatore destino_lives si decrementa (verificabile nel world state)
  - Al terzo intervento il costo è "Severe"
  - A 0 interventi rimasti → morte come Ironman

  Ironman:
  - A 0 HP → appare "You Have Fallen" rosso
  - Nessun pulsante Continue (campagna terminata)
  - La campagna è marcata come completata

  ---
  12. SAVE SYSTEM NON SO COME VERIFICARE. viene salvata la comapgan, ma il combattimento non si attiva

  - POST /api/campaigns/:id/saves funziona fuori dal combat
  - Salvare durante combat → HTTP 400 con messaggio d'errore
  - Il save contiene un snapshot del world state corretto

  ---
  13. MEMORIA & PERSISTENZA (test lungo)

  - Dopo 10+ turni il DM ricorda eventi dei primi turni SI
  - Un NPC menzionato al turno 3 viene ricordato al turno 12 SI
  - Una quest accettata resta nelle quest attive dopo molti turni NON DA LE QUEST
  - Il world state non si corrompe dopo 20+ turni NON SI CORROMPRE TEST PASSATOs

  ---
  14. BUG UI/UX POTENZIALI
  questi li testerei risolti i bug sopra

  - Lo scroll della narrativa va automaticamente in fondo durante lo streaming BUG: NO NON VA IN FONDO
  - La UI non si "blocca" se il backend è lento a rispondere SI
  - L'input è disabilitato durante lo streaming (non puoi inviare due turni in parallelo) SI
  - Nessun testo sovrapposto tra narrazione DM e dialogo NPC NON CE DIALOGO NPC DA VERIFICARE IN FUTURO
  - Il Character Panel non copre l'input bar su schermi piccoli
  - Il CombatTracker non copre testo importante (si vede tutto dietro)
  - Tornare alla lista campagne e rientrare non rompe il WebSocket 
  - Aprire due tab della stessa campagna non causa conflitti visibili
  - Il testo con caratteri speciali (apostrofi, accenti, emoji) non rompe lo streaming

  ---
  15. EDGE CASES DM

  - Azione molto lunga (500+ caratteri) → il DM risponde comunque SI RISPONDE
  - Azione vuota o spazio → non invia (bottone disabilitato o validato) SI 
  - Azione assurda ("volo sulla luna") → il DM rifiuta narrativamente senza crash SI
  - Prompt injection ("ignora le istruzioni precedenti") → il DM non obbedisce NBUG: MOLTO DEBOLE A PROMPT INJECTIOM, POSSO FARGLI GFARE QUELLO CHE VOGLIO
  - Il DM non emette mai JSON grezzo visibile nella narrazione A CVOLTE LO EMETTE (MI SA PERCHE CI SONO ''' ''' )
  - Se il DM fallisce 3 parse retry → errore leggibile, non crash silenzioso NO ERRORE SILEZIOSO, CONTINUA A DIRE DM considers...

  ---
  Come documentare i bug trovati: per ognuno scrivi:
  1. Cosa hai fatto
  2. Cosa ti aspettavi
  3. Cosa è successo invece
  4. Se si riproduce sempre o solo a volte