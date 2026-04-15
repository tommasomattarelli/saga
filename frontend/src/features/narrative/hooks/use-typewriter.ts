import { useState, useEffect, useRef, useCallback } from "react";

interface UseTypewriterOptions {
  text: string;
  baseSpeed?: number;
  onComplete?: () => void;
  reducedMotion?: boolean;
}

interface UseTypewriterResult {
  displayed: string;
  isTyping: boolean;
  skip: () => void;
}

const PUNCTUATION_DELAYS: Record<string, number> = {
  ".": 400,
  "!": 500,
  "?": 500,
  ",": 150,
  ";": 250,
  ":": 250,
  "—": 300,
};

function getCharDelay(char: string, baseSpeed: number): number {
  const punct = PUNCTUATION_DELAYS[char];
  if (punct) return punct;
  // ±20ms jitter for human feel
  return baseSpeed + (Math.random() * 40 - 20);
}

function shouldBurst(): boolean {
  return Math.random() < 0.05;
}

export function useTypewriter({
  text,
  baseSpeed = 22,
  onComplete,
  reducedMotion = false,
}: UseTypewriterOptions): UseTypewriterResult {
  const [index, setIndex] = useState(reducedMotion ? text.length : 0);
  const [isTyping, setIsTyping] = useState(!reducedMotion && text.length > 0);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  const rafRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (reducedMotion) {
      setIndex(text.length);
      setIsTyping(false);
      onCompleteRef.current?.();
      return;
    }
    setIndex(0);
    setIsTyping(text.length > 0);
  }, [text, reducedMotion]);

  useEffect(() => {
    if (reducedMotion) return;
    if (index >= text.length) {
      setIsTyping(false);
      if (index > 0) onCompleteRef.current?.();
      return;
    }

    const currentChar = text[index];
    // Pause before opening quote — dialogue breath
    const isOpenQuote = currentChar === "\u201C" || currentChar === '"';
    const delay = isOpenQuote ? 300 : getCharDelay(currentChar, baseSpeed);
    const burst = shouldBurst() ? 3 : 1;

    rafRef.current = setTimeout(() => {
      setIndex((i) => Math.min(i + burst, text.length));
    }, delay);

    return () => {
      if (rafRef.current) clearTimeout(rafRef.current);
    };
  }, [index, text, baseSpeed, reducedMotion]);

  const skip = useCallback(() => {
    if (rafRef.current) clearTimeout(rafRef.current);
    setIndex(text.length);
    setIsTyping(false);
    onCompleteRef.current?.();
  }, [text.length]);

  return { displayed: text.slice(0, index), isTyping, skip };
}
