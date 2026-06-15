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
  hp: { current: number; max: number };
  ac: number;
  abilities: Record<string, number>;
  skills: Record<string, SkillData>;
  inventory: InventoryItem[];
  equipped: EquippedItems;
  gold: number;
  background: string;
  archetype?: string;
  notes: string;
  reputation: Record<string, number>;
  active_quests: string[];
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

export interface EquippedItems {
  weapon?: string;
  armor?: string;
  shield?: string;
  accessory?: string;
  [slot: string]: string | undefined;
}

export interface Quest {
  name: string;
  description: string;
  status: "active" | "completed" | "failed";
  objectives: string[];
}

export interface CombatState {
  active: boolean;
  round: number;
  initiative_order: CombatantInfo[];
  current_turn_index: number;
}

export interface CombatantInfo {
  name: string;
  initiative: number;
  hp: number;
  max_hp: number;
  type: "player" | "companion" | "enemy";
}

export interface WorldState {
  meta?: { schema_version: number; world_name: string; current_season: string };
  clock?: {
    total_minutes: number;
    current_hour: number;
    current_day: number;
    current_season: string;
    time_of_day: string;
  };
  combat_state?: CombatState;
  destino_lives?: number;
  time_of_day?: string;
  weather?: string;
  location?: string;
  companions?: Record<string, CompanionData>;
  factions?: Record<string, FactionData>;
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

export type DiceOutcome =
  | "critical_failure"
  | "hard_failure"
  | "soft_failure"
  | "partial_success"
  | "full_success"
  | "critical_success";

export interface DiceRollResult {
  expression: string;
  rolls: number[];
  modifier: number;
  total: number;
  dc: number;
  success: boolean;
  outcome: DiceOutcome;
  is_critical: boolean;
}

export interface NPCDialogue {
  npc_name: string;
  dialogue: string;
  action?: string | null;
}

export interface NarrationSegment {
  step: number;
  text: string;
  dice: Record<string, DiceRollResult> | null;
  npc_dialogues: NPCDialogue[];
}

export interface DiceResult {
  step: number;
  rolls: Record<string, DiceRollResult>;
}

export interface TurnResponse {
  turn_number: number;
  player_action?: string;
  narration: string;
  narration_segments?: NarrationSegment[] | null;
  dice_results?: DiceResult[] | null;
  /** @deprecated use dice_results — journal endpoint backward-compat */
  dice_rolls?: Record<string, DiceRollResult> | null;
  npc_dialogues?: NPCDialogue[] | null;
  world_state?: Record<string, unknown>;
  character_data?: Record<string, unknown>;
  scene_mood: string | null;
  combat_state?: CombatState | null;
  tool_events?: Record<string, unknown>[];
  death_event?: {
    is_dead: boolean;
    action: string;
    death_mode: string;
    narrative_instruction: string;
    destino_lives_remaining: number | null;
  } | null;
  model_used?: string;
  importance_score?: number;
  time_passed_minutes?: number;
  requires_player_action?: boolean;
  suggested_actions?: string[] | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
