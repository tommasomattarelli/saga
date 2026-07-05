import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createCampaign, getTemplates } from "../../../../shared/api/client";
import type { TemplateOption } from "../../../../shared/api/client";
import type { Campaign } from "../../../../shared/types";
import { CLASS_PRESETS } from "../../data/class-presets";
import { OrnateFrame } from "../../../../shared/ui/ornate-frame";
import { Candle } from "../../../../assets/ornaments/candle";
import { WizardStepper } from "./wizard-stepper";
import StepWorld from "./steps/step-world";
import StepHero from "./steps/step-hero";
import StepFate from "./steps/step-fate";

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
  const [direction, setDirection] = useState<1 | -1>(1);
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

  const go = (next: 1 | 2 | 3) => {
    setDirection(next > step ? 1 : -1);
    setStep(next);
  };

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{ background: "var(--parchment-base)" }}
    >
      {/* Candle bg — flanking ornaments */}
      <div className="pointer-events-none absolute left-6 top-8 opacity-70">
        <Candle height={140} />
      </div>
      <div className="pointer-events-none absolute right-6 top-8 opacity-70">
        <Candle height={140} />
      </div>

      <div className="relative mx-auto max-w-[820px] px-6 py-12">
        <div className="mb-6 flex items-center justify-between">
          <button
            onClick={() => navigate("/campaigns")}
            aria-label="Back to the shelf"
            className="font-display text-xs uppercase focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
            style={{
              color: "var(--ink-faded)",
              letterSpacing: "0.25em",
            }}
          >
            ← Return to the shelf
          </button>
          <h1
            className="font-display text-3xl uppercase"
            style={{ color: "var(--gold-bright)", letterSpacing: "0.2em" }}
          >
            A New Saga
          </h1>
          <span className="w-[140px]" aria-hidden="true" />
        </div>

        <WizardStepper step={step} />

        <OrnateFrame variant="large" className="relative" color="var(--gold-deep)">
          <div style={{ perspective: 1600, minHeight: 520 }}>
            <AnimatePresence mode="wait" initial={false} custom={direction}>
              <motion.div
                key={step}
                custom={direction}
                initial={{ rotateY: direction > 0 ? 90 : -90, opacity: 0 }}
                animate={{ rotateY: 0, opacity: 1 }}
                exit={{ rotateY: direction > 0 ? -90 : 90, opacity: 0 }}
                transition={{ duration: 0.6, ease: [0.77, 0, 0.175, 1] }}
                style={{ transformStyle: "preserve-3d", transformOrigin: "center" }}
              >
                {step === 1 && (
                  <StepWorld
                    templates={templates}
                    isLoading={isLoading}
                    selectedTemplate={selectedTemplate}
                    onSelect={(t) => {
                      setSelectedTemplate(t);
                      go(2);
                    }}
                  />
                )}
                {step === 2 && selectedTemplate && (
                  <StepHero
                    form={form}
                    selectedTemplate={selectedTemplate}
                    onChange={patch}
                    onBack={() => go(1)}
                    onNext={() => go(3)}
                  />
                )}
                {step === 3 && (
                  <StepFate
                    form={form}
                    onChange={patch}
                    onBack={() => go(2)}
                    onSubmit={() => mutation.mutate()}
                    isPending={mutation.isPending}
                    error={error}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </OrnateFrame>
      </div>
    </div>
  );
}
