import { z } from "zod";

export const CampaignStatusSchema = z.enum(["active", "paused", "completed", "abandoned"]);
export const DeathModeSchema = z.enum(["ironman", "destino", "cronista"]);

export const CharacterDataSchema = z.object({
  name: z.string(),
  level: z.number(),
  xp: z.number(),
  hp: z.object({ current: z.number(), max: z.number() }),
  ac: z.number(),
  abilities: z.record(z.string(), z.number()),
  skills: z.record(z.string(), z.object({ level: z.number(), uses: z.number(), progress: z.number() })),
  inventory: z.array(
    z.object({
      name: z.string(),
      description: z.string().optional(),
      quantity: z.number(),
      type: z.string(),
    }),
  ),
  equipped: z.record(z.string(), z.string().optional()),
  gold: z.number(),
  background: z.string(),
  notes: z.string(),
  reputation: z.record(z.string(), z.number()),
  active_quests: z.array(z.string()),
});

export const CampaignSchema = z.object({
  id: z.string(),
  name: z.string(),
  template_id: z.string(),
  status: CampaignStatusSchema,
  death_mode: DeathModeSchema,
  turn_number: z.number(),
  character_data: z.record(z.string(), z.unknown()),
  world_state: z.record(z.string(), z.unknown()),
  quests: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});

export type CampaignParsed = z.infer<typeof CampaignSchema>;
