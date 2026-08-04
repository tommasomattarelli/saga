import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { createCampaign, getWorlds } from "../../../../shared/api/client";
import type { WorldOption } from "../../../../shared/api/client";
import type { Campaign } from "../../../../shared/types";
import { CLASS_PRESETS } from "../../data/class-presets";
import { WizardStepper } from "./wizard-stepper";
import StepWorld from "./steps/step-world";
import StepHero from "./steps/step-hero";
import StepFate from "./steps/step-fate";

interface WizardForm {
  campaignName: string;
  heroName: string;
  difficulty: string;
  archetype: string;
  background: string;
}

export default function NewCampaign() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [direction, setDirection] = useState<1 | -1>(1);
  const [selectedWorld, setSelectedWorld] = useState<WorldOption | null>(null);
  const [form, setForm] = useState<WizardForm>({
    campaignName: "",
    heroName: "",
    difficulty: "easy",
    archetype: "warrior",
    background: "",
  });
  const [error, setError] = useState<string | null>(null);

  const { data: worlds, isLoading } = useQuery({
    queryKey: ["worlds"],
    queryFn: () => getWorlds().then((r) => r.data),
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
        world_id: selectedWorld!.slug,
        name: form.campaignName || `${form.heroName || "The Stranger"}'s Adventure`,
        difficulty: form.difficulty,
        character_data: buildCharacterData(),
      }).then((r) => r.data),
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      navigate(`/game/${campaign.id}`);
    },
    onError: (err) => {
      console.error(err);
      setError(t("wizard.create_failed"));
    },
  });

  const patch = (p: Partial<WizardForm>) => setForm((f) => ({ ...f, ...p }));

  const go = (next: 1 | 2 | 3) => {
    setDirection(next > step ? 1 : -1);
    setStep(next);
  };

  return (
    <div className="min-h-screen w-full" style={{ background: "var(--parchment-shadow)" }}>
      <div className="mx-auto max-w-[820px] px-6 py-10">
        <div className="mb-8 flex items-center justify-between">
          <button
            onClick={() => navigate("/campaigns")}
            className="font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--ink-faded)" }}
          >
            ← {t("wizard.back_link")}
          </button>
          <h1
            className="font-display text-base font-semibold"
            style={{ color: "var(--ink-primary)" }}
          >
            {t("wizard.title")}
          </h1>
          <span className="w-[100px]" aria-hidden="true" />
        </div>

        <WizardStepper step={step} />

        <div
          className="rounded-xl px-8 py-8"
          style={{
            background: "var(--parchment-base)",
            border: "1px solid var(--line-strong)",
            minHeight: 520,
          }}
        >
          <AnimatePresence mode="wait" initial={false} custom={direction}>
            <motion.div
              key={step}
              custom={direction}
              initial={{ opacity: 0, x: direction > 0 ? 24 : -24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: direction > 0 ? -24 : 24 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              {step === 1 && (
                <StepWorld
                  worlds={worlds}
                  isLoading={isLoading}
                  selectedWorld={selectedWorld}
                  onSelect={(world) => {
                    setSelectedWorld(world);
                    go(2);
                  }}
                />
              )}
              {step === 2 && selectedWorld && (
                <StepHero
                  form={form}
                  selectedWorld={selectedWorld}
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
      </div>
    </div>
  );
}
