import { useState, useEffect, useRef } from "react";

interface TypewriterProps {
  text: string;
  speed?: number; // chars per interval tick (default 2)
  intervalMs?: number; // ms per tick (default 16 ≈ 60fps)
  onComplete?: () => void;
}

export default function Typewriter({
  text,
  speed = 2,
  intervalMs = 16,
  onComplete,
}: TypewriterProps) {
  const [index, setIndex] = useState(0);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    // Reset when text changes (new turn)
    setIndex(0);
  }, [text]);

  useEffect(() => {
    if (index >= text.length) {
      onCompleteRef.current?.();
      return;
    }
    const timer = setTimeout(
      () => setIndex((i) => Math.min(i + speed, text.length)),
      intervalMs,
    );
    return () => clearTimeout(timer);
  }, [index, text.length, speed, intervalMs]);

  const visible = text.slice(0, index);

  return (
    <>
      {visible.split("\n").map((paragraph, i) => (
        <p key={i} className="mb-3">
          {paragraph}
          {/* blinking cursor on last paragraph while typing */}
          {i === visible.split("\n").length - 1 && index < text.length && (
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-gold-400" />
          )}
        </p>
      ))}
    </>
  );
}
