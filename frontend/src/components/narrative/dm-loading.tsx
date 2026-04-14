export default function DmLoading() {
  return (
    <div className="mb-6 animate-pulse space-y-3 py-4">
      <div className="h-4 w-3/4 rounded bg-parchment-700/30" />
      <div className="h-4 w-full rounded bg-parchment-700/20" />
      <div className="h-4 w-5/6 rounded bg-parchment-700/25" />
      <div className="h-4 w-2/3 rounded bg-parchment-700/15" />
      <div className="mt-1 flex items-center gap-2 pt-2 text-parchment-500">
        <span className="flex gap-1">
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400/60" />
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400/60" />
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400/60" />
        </span>
        <span className="text-xs text-parchment-500">The DM considers your action…</span>
      </div>
    </div>
  );
}
