interface ClassPreset {
  label: string;
  abilities: Record<string, number>;
  baseHp: number;
  desc: string;
}

export const CLASS_PRESETS: Record<string, ClassPreset> = {
  warrior: {
    label: "Warrior",
    abilities: {
      strength: 16,
      constitution: 14,
      dexterity: 12,
      wisdom: 10,
      intelligence: 8,
      charisma: 10,
    },
    baseHp: 22,
    desc: "High STR & CON. Born for the front line.",
  },
  rogue: {
    label: "Rogue",
    abilities: {
      dexterity: 16,
      charisma: 14,
      intelligence: 12,
      constitution: 10,
      strength: 10,
      wisdom: 8,
    },
    baseHp: 20,
    desc: "High DEX & CHA. Stealth, deception, precision.",
  },
  mage: {
    label: "Mage",
    abilities: {
      intelligence: 16,
      wisdom: 14,
      charisma: 12,
      dexterity: 10,
      constitution: 8,
      strength: 10,
    },
    baseHp: 19,
    desc: "High INT & WIS. Arcane knowledge and power.",
  },
  ranger: {
    label: "Ranger",
    abilities: {
      dexterity: 16,
      wisdom: 14,
      constitution: 12,
      strength: 10,
      intelligence: 10,
      charisma: 8,
    },
    baseHp: 21,
    desc: "High DEX & WIS. Master of the wilds.",
  },
  cleric: {
    label: "Cleric",
    abilities: {
      wisdom: 16,
      constitution: 14,
      charisma: 12,
      strength: 10,
      dexterity: 10,
      intelligence: 8,
    },
    baseHp: 22,
    desc: "High WIS & CON. Divine healer and protector.",
  },
  bard: {
    label: "Bard",
    abilities: {
      charisma: 16,
      dexterity: 14,
      intelligence: 12,
      wisdom: 10,
      constitution: 10,
      strength: 8,
    },
    baseHp: 20,
    desc: "High CHA & DEX. Words are your weapon.",
  },
};

export const DEATH_MODES = [
  { value: "cronista", label: "Cronista", desc: "No permadeath. The story always continues." },
  { value: "destino", label: "Destino", desc: "Death matters. Revive once per campaign." },
  { value: "ironman", label: "Ironman", desc: "Permadeath. One life, one story." },
] as const;
