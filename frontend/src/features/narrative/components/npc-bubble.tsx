import { InitialSeal } from "../../../assets/ornaments/seal";
import type { NPCDialogue } from "../../../shared/types";

/* NPC block "sealed" — rientro sinistro, sigillo + nome Cinzel, quote Cormorant italic.
   Nessun bordo/background per design piano: integrato nel flusso come manoscritto reale. */
export default function NPCBubble({ npc_name, dialogue, action }: NPCDialogue) {
  return (
    <div className="my-4 ml-8">
      {/* Sigillo + nome inline */}
      <div className="flex items-center gap-2 mb-0.5">
        <InitialSeal name={npc_name} size={22} />
        <span
          className="font-display text-[10px] uppercase"
          style={{ color: "var(--gold-deep)", letterSpacing: "0.22em" }}
        >
          {npc_name}
        </span>
      </div>
      {/* Quote */}
      <p
        className="font-body italic text-lg"
        style={{ color: "var(--ink-primary)" }}
      >
        &ldquo;{dialogue}&rdquo;
      </p>
      {action && (
        <p
          className="mt-0.5 font-body text-sm italic"
          style={{ color: "var(--ink-faded)" }}
        >
          *{action}*
        </p>
      )}
    </div>
  );
}
