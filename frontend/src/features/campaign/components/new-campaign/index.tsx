import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createCampaign, getTemplates } from "../../../../shared/api/client";
import type { TemplateOption } from "../../../../shared/api/client";
import type { Campaign } from "../../../../shared/types";
import { CLASS_PRESETS } from "../../data/class-presets";
import StepWorld from "./steps/step-world";
import StepHero from "./steps/step-hero";
import StepCharacter from "./steps/step-character";

interface WizardForm {
  campaignName: string;
  heroName: string;
  deathMode: string;
  archetype: string;
  background: string;
}

export default function NewCampaign() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateOption | null>(null);
  const [form, setForm] = useState<WizardForm>({
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
      console.error(err);
      setError("Failed to create campaign. Please try again.");
    },
  });

  const patch = (p: Partial<WizardForm>) => setForm((f) => ({ ...f, ...p }));

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center gap-4">
        <button
          onClick={() => navigate("/campaigns")}
          aria-label="Back to campaigns"
          className="text-sm text-parchment-400 hover:text-parchment-200"
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

      {step === 1 && (
        <StepWorld
          templates={templates}
          isLoading={isLoading}
          selectedTemplate={selectedTemplate}
          onSelect={(t) => {
            setSelectedTemplate(t);
            setStep(2);
          }}
        />
      )}

      {step === 2 && selectedTemplate && (
        <StepHero
          form={form}
          selectedTemplate={selectedTemplate}
          onChange={patch}
          onBack={() => setStep(1)}
          onNext={() => setStep(3)}
        />
      )}

      {step === 3 && (
        <StepCharacter
          form={form}
          onChange={patch}
          onBack={() => setStep(2)}
          onSubmit={() => mutation.mutate()}
          isPending={mutation.isPending}
          error={error}
        />
      )}
    </div>
  );
}
