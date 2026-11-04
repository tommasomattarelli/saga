import { z } from "zod";

const DiceOutcomeSchema = z.enum([
  "critical_failure",
  "hard_failure",
  "soft_failure",
  "partial_success",
  "full_success",
  "critical_success",
]);

const DifficultyLevelSchema = z.enum([
  "trivial",
  "easy",
  "normal",
  "hard",
  "very_hard",
  "near_impossible",
]);

const DiceRollResultSchema = z.object({
  expression: z.string(),
  rolls: z.array(z.number()),
  modifier: z.number(),
  total: z.number(),
  difficulty: DifficultyLevelSchema,
  difficulty_draw: z.number(),
  success: z.boolean(),
  outcome: DiceOutcomeSchema,
  is_critical: z.boolean(),
  hazard_damage: z.number().optional(),
});

const NarrationPartSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({
    type: z.literal("npc_speech"),
    npc_id: z.string(),
    npc_name: z.string(),
    line_index: z.number(),
    dialogue: z.string(),
  }),
]);

const NarrationSegmentSchema = z.object({
  step: z.number(),
  parts: z.array(NarrationPartSchema),
  dice: z.record(z.string(), DiceRollResultSchema).nullable(),
});

const DiceResultSchema = z.object({
  step: z.number(),
  rolls: z.record(z.string(), DiceRollResultSchema),
});

const QuestSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  objectives: z.array(z.string()),
});

const QuestRegistrySchema = z.object({
  active: z.array(QuestSchema),
  completed: z.array(QuestSchema),
  failed: z.array(QuestSchema),
  abandoned: z.array(QuestSchema),
});

export const TurnResponseSchema = z.object({
  turn_number: z.number(),
  player_action: z.string().optional(),
  narration: z.string(),
  narration_segments: z.array(NarrationSegmentSchema).nullable().optional(),
  dice_results: z.array(DiceResultSchema).nullable().optional(),
  dice_rolls: z.record(z.string(), DiceRollResultSchema).nullable().optional(),
  world_state: z.record(z.string(), z.unknown()).optional(),
  character_data: z.record(z.string(), z.unknown()).optional(),
  quests: QuestRegistrySchema.optional(),
  scene_mood: z.string().nullable(),
  tool_events: z.array(z.record(z.string(), z.unknown())).optional(),
  death_event: z
    .object({
      is_dead: z.boolean(),
      action: z.string(),
      difficulty: z.string(),
      narrative_instruction: z.string(),
      fate_interventions_remaining: z.number().nullable(),
    })
    .nullable()
    .optional(),
  model_used: z.string().optional(),
  importance_score: z.number().optional(),
  time_passed_minutes: z.number().optional(),
  requires_player_action: z.boolean().optional(),
});
