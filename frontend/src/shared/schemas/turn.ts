import { z } from "zod";

const DiceOutcomeSchema = z.enum([
  "critical_failure",
  "hard_failure",
  "soft_failure",
  "partial_success",
  "full_success",
  "critical_success",
]);

const DiceRollResultSchema = z.object({
  expression: z.string(),
  rolls: z.array(z.number()),
  modifier: z.number(),
  total: z.number(),
  dc: z.number(),
  success: z.boolean(),
  outcome: DiceOutcomeSchema,
  is_critical: z.boolean(),
});

const NPCDialogueSchema = z.object({
  npc_name: z.string(),
  dialogue: z.string(),
  action: z.string().nullable().optional(),
});

const NarrationSegmentSchema = z.object({
  step: z.number(),
  text: z.string(),
  dice: z.record(z.string(),DiceRollResultSchema).nullable(),
  npc_dialogues: z.array(NPCDialogueSchema),
});

const DiceResultSchema = z.object({
  step: z.number(),
  rolls: z.record(z.string(),DiceRollResultSchema),
});

const CombatantInfoSchema = z.object({
  name: z.string(),
  initiative: z.number(),
  hp: z.number(),
  max_hp: z.number(),
  type: z.enum(["player", "enemy"]),
});

const CombatStateSchema = z.object({
  active: z.boolean(),
  round: z.number(),
  initiative_order: z.array(CombatantInfoSchema),
  current_turn_index: z.number(),
});

export const TurnResponseSchema = z.object({
  turn_number: z.number(),
  player_action: z.string().optional(),
  narration: z.string(),
  narration_segments: z.array(NarrationSegmentSchema).nullable().optional(),
  dice_results: z.array(DiceResultSchema).nullable().optional(),
  dice_rolls: z.record(z.string(),DiceRollResultSchema).nullable().optional(),
  npc_dialogues: z.array(NPCDialogueSchema).nullable().optional(),
  world_state: z.record(z.string(),z.unknown()).optional(),
  character_data: z.record(z.string(),z.unknown()).optional(),
  scene_mood: z.string().nullable(),
  combat_state: CombatStateSchema.nullable().optional(),
  tool_events: z.array(z.record(z.string(),z.unknown())).optional(),
  death_event: z
    .object({
      is_dead: z.boolean(),
      action: z.string(),
      death_mode: z.string(),
      narrative_instruction: z.string(),
      destino_lives_remaining: z.number().nullable(),
    })
    .nullable()
    .optional(),
  model_used: z.string().optional(),
  importance_score: z.number().optional(),
  time_passed_minutes: z.number().optional(),
  requires_player_action: z.boolean().optional(),
});
