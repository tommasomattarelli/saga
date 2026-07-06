import type { NPCDialogue } from "../../../shared/types";

/* Desaturated speaker hues — ink pigments, not neon; deterministic per name */
const NPC_HUES = ["#c9a8a4", "#b8ab8d", "#a9bda5", "#a3aec6"];

function npcHue(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return NPC_HUES[Math.abs(hash) % NPC_HUES.length];
}

/* NPC dialogue — flow-integrated, no box; the colored name is the only marker */
export default function NPCBubble({ npc_name, dialogue, action }: NPCDialogue) {
  return (
    <div className="my-4 ml-6">
      <div className="font-display text-xs font-semibold mb-1" style={{ color: npcHue(npc_name) }}>
        {npc_name}
      </div>
      <p className="font-body italic text-lg" style={{ color: "var(--ink-primary)" }}>
        &ldquo;{dialogue}&rdquo;
      </p>
      {action && (
        <p className="mt-0.5 font-body text-sm italic" style={{ color: "var(--ink-faded)" }}>
          {action}
        </p>
      )}
    </div>
  );
}
