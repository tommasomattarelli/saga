import { User } from "lucide-react";
import type { NPCDialogue } from "../../../shared/types";

export default function NPCBubble({ npc_name, dialogue, action }: NPCDialogue) {
  return (
    <div className="mb-4 flex justify-start">
      <div className="max-w-[80%] rounded-lg border border-parchment-600/40 bg-parchment-900/40 px-4 py-3 shadow-sm">
        <div className="mb-1 flex items-center gap-2">
          <User className="h-4 w-4 text-parchment-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-parchment-300">
            {npc_name}
          </span>
        </div>
        <p className="font-serif text-parchment-100">&ldquo;{dialogue}&rdquo;</p>
        {action && (
          <p className="mt-1 text-sm font-serif italic text-parchment-400">*{action}*</p>
        )}
      </div>
    </div>
  );
}
