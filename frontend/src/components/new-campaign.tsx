import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createCampaign, getTemplates } from "../services/api";
import type { TemplateOption } from "../services/api";
import type { Campaign } from "../types";

const DEATH_MODES = [
  {
    value: "cronista",
    label: "Cronista",
    desc: "No permadeath. The story always continues.",
  },
  {
    value: "destino",
    label: "Destino",
    desc: "Death matters. Revive once per campaign.",
  },
  {
    value: "ironman",
    label: "Ironman",
    desc: "Permadeath. One life, one story.",
  },
];

const CLASS_PRESETS: Record<
  string,
  { label: string; abilities: Record<string, number>; baseHp: number; desc: string }
> = {
  warrior: {
    label: "Warrior",
    abilities: { strength: 16, constitution: 14, dexterity: 12, wisdom: 10, intelligence: 8, charisma: 10 },
    baseHp: 22,
    desc: "High STR & CON. Born for the front line.",
  },
  rogue: {
    label: "Rogue",
    abilities: { dexterity: 16, charisma: 14, intelligence: 12, constitution: 10, strength: 10, wisdom: 8 },
    baseHp: 20,
    desc: "High DEX & CHA. Stealth, deception, precision.",
  },
  mage: {
    label: "Mage",
    abilities: { intelligence: 16, wisdom: 14, charisma: 12, dexterity: 10, constitution: 8, strength: 10 },
    baseHp: 19,
    desc: "High INT & WIS. Arcane knowledge and power.",
  },
  ranger: {
    label: "Ranger",
    abilities: { dexterity: 16, wisdom: 14, constitution: 12, strength: 10, intelligence: 10, charisma: 8 },
    baseHp: 21,
    desc: "High DEX & WIS. Master of the wilds.",
  },
  cleric: {
    label: "Cleric",
    abilities: { wisdom: 16, constitution: 14, charisma: 12, strength: 10, dexterity: 10, intelligence: 8 },
    baseHp: 22,
    desc: "High WIS & CON. Divine healer and protector.",
  },
  bard: {
    label: "Bard",
    abilities: { charisma: 16, dexterity: 14, intelligence: 12, wisdom: 10, constitution: 10, strength: 8 },
    baseHp: 20,
    desc: "High CHA & DEX. Words are your weapon.",
  },
};

function abilityMod(score: number): string {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

export default function NewCampaign() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateOption | null>(null);
  const [form, setForm] = useState({
    campaignName: "",
    heroName: "",
    deathMode: "cronista",
    archetype: "warrior",
    background: "",
  });

  const [error, setError] = useState<string | null>(null);

  const { data: templates, isLoading } = useQuery({
    queryKey: ["templates"],
    queryFn: () => getTemplates().then((r) => r.data),
  });

  const buildCharacterData = () => {
    const preset = CLASS_PRESETS[form.archetype];
    const maxHp = preset.baseHp;
    return {
      name: form.heroName || "The Stranger",
      level: 1,
      xp: 0,
      hp: { current: maxHp, max: maxHp },
      ac: 10,
      abilities: { ...preset.abilities },
      skills: {},
      inventory: [],
      gold: 10,
      background: form.background || "adventurer",
      archetype: form.archetype,
      notes: "",
    };
  };

  const mutation = useMutation<Campaign, Error, void>({
    mutationFn: () =>
      createCampaign({
        template_id: selectedTemplate!.id,
        name: form.campaignName || `${form.heroName || "The Stranger"}'s Adventure`,
        death_mode: form.deathMode,
        character_data: buildCharacterData(),
      }).then((r) => r.data),
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      navigate(`/game/${campaign.id}`);
    },
    onError: (err) => {
      setError("Failed to create campaign. Check the backend logs.");
      console.error(err);
    },
  });

  const difficultyLabel = (d: number) => {
    if (d <= 3) return "Beginner";
    if (d <= 6) return "Moderate";
    return "Hardcore";
  };

  const selectedPreset = CLASS_PRESETS[form.archetype];

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center gap-4">
        <button
          onClick={() => navigate("/campaigns")}
          className="text-parchment-400 hover:text-parchment-200 text-sm"
        >
          &larr; Back
        </button>
        <h1 className="font-display text-3xl font-bold text-gold-400">New Saga</h1>
      </div>

      <div className="mb-8 flex gap-2">
        {[1, 2, 3].map((s) => (
          <div
            key={s}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              step >= s ? "bg-gold-500" : "bg-parchment-700/30"
            }`}
          />
        ))}
      </div>

      {/* Step 1: Template */}
      {step === 1 && (
        <div>
          <h2 className="mb-1 font-display text-xl text-parchment-200">Choose your world</h2>
          <p className="mb-6 text-sm text-parchment-500">
            Each template is a different story, setting, and challenge.
          </p>

          {isLoading && (
            <div className="py-8 text-center text-parchment-400">Loading worlds...</div>
          )}

          {!isLoading && (!templates || templates.length === 0) && (
            <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-4 text-red-400 text-sm">
              No templates found. Make sure the backend seeded the templates on startup.
            </div>
          )}

          <div className="space-y-3">
            {templates?.map((t) => (
              <button
                key={t.id}
                onClick={() => {
                  setSelectedTemplate(t);
                  setStep(2);
                }}
                className={`w-full text-left rounded-lg border p-4 transition-all ${
                  selectedTemplate?.id === t.id
                    ? "border-gold-500 bg-parchment-800/60"
                    : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/40 hover:bg-parchment-800/40"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-lg text-gold-400">{t.name}</h3>
                    <p className="mt-1 text-sm text-parchment-400">{t.description}</p>
                  </div>
                  <span className="shrink-0 text-xs text-parchment-500 mt-1">
                    {difficultyLabel(t.difficulty)} &middot; by {t.author}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {t.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-parchment-700/30 px-2 py-0.5 text-xs text-parchment-500"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step 2: Hero name + death mode */}
      {step === 2 && selectedTemplate && (
        <div>
          <h2 className="mb-1 font-display text-xl text-parchment-200">Name your hero</h2>
          <p className="mb-6 text-sm text-parchment-500">
            Playing <span className="text-gold-400">{selectedTemplate.name}</span>
          </p>

          <div className="space-y-5">
            <div>
              <label className="mb-1.5 block text-sm text-parchment-300">Hero Name</label>
              <input
                type="text"
                value={form.heroName}
                onChange={(e) => setForm({ ...form, heroName: e.target.value })}
                placeholder="Leave blank for a mysterious stranger..."
                className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm text-parchment-300">
                Campaign Name <span className="text-parchment-600">(optional)</span>
              </label>
              <input
                type="text"
                value={form.campaignName}
                onChange={(e) => setForm({ ...form, campaignName: e.target.value })}
                placeholder={`${form.heroName || "The Stranger"}'s Adventure`}
                className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm text-parchment-300">Death Mode</label>
              <div className="space-y-2">
                {DEATH_MODES.map((m) => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => setForm({ ...form, deathMode: m.value })}
                    className={`w-full rounded-lg border px-4 py-3 text-left transition-all ${
                      form.deathMode === m.value
                        ? "border-gold-500 bg-parchment-800/60"
                        : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/30"
                    }`}
                  >
                    <span className="text-sm font-medium text-parchment-200">{m.label}</span>
                    <p className="text-xs text-parchment-500 mt-0.5">{m.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep(1)}
                className="rounded-lg border border-parchment-700/30 px-4 py-2.5 text-sm text-parchment-400 hover:bg-parchment-800/40"
              >
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="flex-1 rounded-lg border border-gold-500/30 bg-gold-900/20 py-2.5 text-sm font-medium text-gold-400 transition hover:bg-gold-900/40"
              >
                Next: Create Character &rarr;
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Character creation */}
      {step === 3 && (
        <div>
          <h2 className="mb-1 font-display text-xl text-parchment-200">Create your character</h2>
          <p className="mb-6 text-sm text-parchment-500">
            Choose a class and see your stats. You can always change later in-game.
          </p>

          <div className="space-y-5">
            {/* Class selection */}
            <div>
              <label className="mb-2 block text-sm text-parchment-300">Class</label>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(CLASS_PRESETS).map(([key, preset]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setForm({ ...form, archetype: key })}
                    className={`rounded-lg border px-3 py-2.5 text-left transition-all ${
                      form.archetype === key
                        ? "border-gold-500 bg-parchment-800/60"
                        : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/30"
                    }`}
                  >
                    <span className="text-sm font-medium text-parchment-200">{preset.label}</span>
                    <p className="text-xs text-parchment-500 mt-0.5">{preset.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Background */}
            <div>
              <label className="mb-1.5 block text-sm text-parchment-300">
                Background <span className="text-parchment-600">(optional)</span>
              </label>
              <input
                type="text"
                value={form.background}
                onChange={(e) => setForm({ ...form, background: e.target.value })}
                placeholder="A wandering sellsword seeking redemption..."
                className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none"
              />
            </div>

            {/* Stats preview */}
            <div className="rounded-lg border border-parchment-700/30 bg-parchment-900/60 p-4">
              <h4 className="mb-3 text-sm font-semibold uppercase tracking-wider text-parchment-500">
                Character Preview
              </h4>
              <div className="mb-3 flex items-center justify-between">
                <span className="font-display text-lg text-gold-400">
                  {form.heroName || "The Stranger"}
                </span>
                <span className="text-sm text-parchment-400">
                  HP {selectedPreset.baseHp}/{selectedPreset.baseHp}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(selectedPreset.abilities).map(([ability, score]) => (
                  <div
                    key={ability}
                    className="rounded border border-parchment-700/20 px-2 py-1.5 text-center"
                  >
                    <div className="text-xs uppercase text-parchment-500">
                      {ability.slice(0, 3)}
                    </div>
                    <div className="font-bold text-parchment-200">{score}</div>
                    <div className="text-xs text-parchment-500">{abilityMod(score)}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex gap-4 text-sm text-parchment-400">
                <span>AC: 10</span>
                <span>Gold: 10</span>
                <span>Level: 1</span>
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-3 text-sm text-red-400">
                {error}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep(2)}
                className="rounded-lg border border-parchment-700/30 px-4 py-2.5 text-sm text-parchment-400 hover:bg-parchment-800/40"
              >
                Back
              </button>
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="flex-1 rounded-lg border border-gold-500/30 bg-gold-900/20 py-2.5 text-sm font-medium text-gold-400 transition hover:bg-gold-900/40 disabled:opacity-50"
              >
                {mutation.isPending ? "Creating..." : "Begin the Saga"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
