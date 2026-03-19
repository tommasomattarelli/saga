export interface User {
  id: string;
  username: string;
  email: string;
  preferred_language: string;
}

export interface Campaign {
  id: string;
  name: string;
  template_id: string;
  status: CampaignStatus;
  death_mode: DeathMode;
  turn_number: number;
  character_data: CharacterData;
  world_state: WorldState;
  quests: Record<string, Quest[]>;
  created_at: string;
  updated_at: string;
}

export type CampaignStatus = "active" | "paused" | "completed" | "abandoned";
export type DeathMode = "ironman" | "destino" | "cronista";

export interface CharacterData {
  name: string;
  level: number;
  xp: number;
  hp: number;
  max_hp: number;
  ac: number;
  abilities: Record<string, number>;
  skills: Record<string, SkillData>;
  inventory: InventoryItem[];
  gold: number;
  background: string;
  notes: string;
}

export interface SkillData {
  level: number;
  uses: number;
  progress: number;
}

export interface InventoryItem {
  name: string;
  description?: string;
  quantity: number;
  type: string;
}

export interface Quest {
  name: string;
  description: string;
  status: "active" | "completed" | "failed";
  objectives: string[];
}

export interface WorldState {
  time?: { hour: number; time_of_day: string };
  weather?: string;
  location?: string;
  companions?: Record<string, CompanionData>;
  factions?: Record<string, FactionData>;
  in_combat?: boolean;
  [key: string]: unknown;
}

export interface CompanionData {
  name: string;
  hp: number;
  max_hp: number;
  loyalty: number;
  trust: number;
  mood: string;
  personality: string;
}

export interface FactionData {
  name: string;
  disposition: number;
  active_plan?: string;
}

export interface TurnResponse {
  turn_number: number;
  narration: string;
  dice_rolls: Record<string, DiceRollResult> | null;
  companion_actions: Record<string, string> | null;
  world_updates: Record<string, unknown> | null;
  scene_mood: string | null;
  suggested_actions: string[] | null;
  model_used: string;
}

export interface DiceRollResult {
  expression: string;
  rolls: number[];
  total: number;
  dc: number;
  success: boolean;
}

export interface SavePoint {
  id: string;
  campaign_id: string;
  name: string;
  turn_number: number;
  scene_summary: string;
  is_auto: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
