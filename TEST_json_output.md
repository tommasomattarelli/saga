

```json

{

"narration": "Il freddo acciaio della tua lama scivola fuori dal fodero con un sibilo sinistro che sovrasta il rombo della cascata. Elian sgrana gli occhi, realizzando troppo tardi che la tua 'logica' non si ferma al sacrificio dei compagni, ma si estende all'eliminazione di chiunque rappresenti un peso o un testimone scomodo. Il vecchio tenta di sollevare il mazzuolo in un gesto disperato di difesa, ma le sue mani tremano violentemente e il suo respiro si trasforma in un rantolo di puro terrore. 'No, Tom! Per gli dei, pietà!' grida, inciampando sui propri piedi mentre cerca di arretrare nell'oscurità del tunnel. La luce fioca della cascata brilla sulla punta della tua spada mentre sferri il colpo, mirando alla carne e all'osso dell'uomo che ti ha appena mostrato la via per la salvezza.",

"invoke_npcs": [

"Elian"

],

"dice_required": [

{

"name": "melee_attack",

"dc": 12,

"modifier": 2

}

],

"scene_mood": "combat_fury",

"time_passed_minutes": 1,

"companion_actions": null,

"world_updates": {

"key": "combat_start",

"target": "combat",

"change": {

"enemies": [

{

"name": "Elian (Carpentiere)",

"hp": 10,

"max_hp": 10

}

]

}

},

"suggested_actions": [

"Affonda il colpo",

"Disarma Elian",

"Fermati all'ultimo istante"

],

"ambient_detail": "L'odore di ruggine e pietra bagnata si mescola al puzzo improvviso del terrore umano.",

"scene_image_prompt": "A dark stone tunnel behind a waterfall, a cruel warrior swinging a sword at a terrified old man holding a wooden mallet."

}

``````json

{

"narration": "Il tuo fendente, guidato da una fredda crudeltà, sibila nell'aria umida ma la pietra viscida del tunnel tradisce il tuo equilibrio proprio nell'istante cruciale. La punta della spada scintilla contro la parete rocciosa in un inutile sprazzo di scintille, mentre Elian, spinto da un istinto di sopravvivenza disperato, barcolla all'indietro evitando il colpo per un soffio. Il vecchio emette un gemito di puro terrore e, approfittando del tuo sbilanciamento, solleva il pesante mazzuolo di legno con entrambe le mani per colpirti al petto.",

"invoke_npcs": ["Elian"],

"dice_required": [{"name": "dexterity_save", "dc": 13, "modifier": 0}],

"scene_mood": "combat_fury",

"time_passed_minutes": 1,

"companion_actions": null,

"world_updates": {"key": "combat_damage", "target": "Tom", "change": 0},

"suggested_actions": ["Para il colpo", "Schiva lateralmente", "Afferra il mazzuolo"],

"ambient_detail": "Il suono del metallo sulla pietra rimbomba nel tunnel, coprendo per un attimo il fragore della cascata.",

"scene_image_prompt": "A cramped, wet stone tunnel where a man with a sword has just missed a strike against a terrified old carpenter holding a mallet."

}

```

L'odore di ruggine e pietra bagnata si mescola al puzzo improvviso del terrore umano.

Affonda il colpo
Disarma Elian
Fermati all'ultimo istante
combat fury

constitution_save
Roll!
```json

{

"narration": "Elian, spinto dal puro terrore e dalla disperazione di un uomo che non ha più nulla da perdere, cala il pesante mazzuolo di legno con una forza che non credevi possibile per la sua età. Il colpo ti raggiunge in pieno petto con un tonfo sordo e brutale. Senti l'aria scappare dai polmoni in un rantolo strozzato e un dolore acuto divampa tra le costole, facendoti barcollare all'indietro contro la parete viscida del tunnel. La vista ti si appanna per un istante e il sapore metallico del sangue ti riempie la bocca mentre cerchi di recuperare l'equilibrio. Il vecchio carpentiere ansima, il mazzuolo che trema tra le sue mani nodose, le lacrime che gli rigano il volto sporco di segatura. 'Mostro! Sei un mostro!' urla, la sua voce che rimbomba caoticamente tra le pareti di pietra. Nonostante il dolore, senti l'adrenalina scorrere: Elian è terrorizzato, ma ora è anche pericoloso.",

"invoke_npcs": [

"Elian"

],

"dice_required": [

{

"name": "constitution_save",

"dc": 14,

"modifier": 0

}

],

"scene_mood": "combat_fury",

"time_passed_minutes": 1,

"companion_actions": null,

"world_updates": {

"key": "combat_start",

"target": "combat",

"change": {

"enemies": [

{

"name": "Elian il Falegname",

"hp": 12,

"max_hp": 12

}

]

},

"player_damage": {

"key": "combat_damage",

"target": "Tom",

"change": -6

}

},

"suggested_actions": [

"Attacca Elian con la spada",

"Cerca di disarmarlo",

"Spingilo via per riprendere fiato",

"Fuggi più profondamente nel tunnel"

],

"ambient_detail": "L'odore di legno vecchio e muffa si mescola al puzzo del sangue e all'umidità della cascata.",

"scene_image_prompt": "A dark, wet stone tunnel behind a waterfall. An old man with a wooden mallet stands over a man clutching his chest in pain. Dim light filters through the water curtain."

}

```Il colpo del mazzuolo ti schianta il petto con una forza devastante, frantumando una costola con un rumore secco e sinistro. I polmoni ti si bloccano all'istante, impedendoti di respirare, e crolli sulle ginocchia mentre il mondo intorno a te inizia a oscurarsi e a ruotare freneticamente. Elian, vedendoti accasciato e inerme, singhiozza in preda al terrore puro, ma solleva di nuovo il suo strumento di lavoro per sferrare un colpo di grazia alla tua testa esposta.