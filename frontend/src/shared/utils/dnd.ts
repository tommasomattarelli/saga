import type { CharacterData } from "../types";

export function abilityMod(score: number): string {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

export function abilityModNum(score: number): number {
  return Math.floor((score - 10) / 2);
}

export function getHP(char: CharacterData): { current: number; max: number; percent: number } {
  const { current, max } = char.hp;
  return { current, max, percent: clampPercent(max > 0 ? (current / max) * 100 : 0) };
}

export function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}
