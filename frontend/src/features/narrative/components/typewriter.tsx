import { useTypewriter } from "../hooks/use-typewriter";

interface TypewriterProps {
  text: string;
  onComplete?: () => void;
  /** First turn of the saga — renders a decorative drop-cap */
  dropCap?: boolean;
}

export default function Typewriter({ text, onComplete, dropCap = false }: TypewriterProps) {
  const { displayed, isTyping } = useTypewriter({ text, onComplete });
  const paragraphs = displayed.split("\n").filter((p) => p.length > 0);

  return (
    <>
      {paragraphs.map((paragraph, i) => {
        const isFirst = i === 0 && dropCap;
        const isLast = i === paragraphs.length - 1;
        return (
          <p key={i} className="mb-4" style={{ lineHeight: 1.62 }}>
            {isFirst && paragraph.length > 0 && (
              <span
                className="float-left mr-2 font-body leading-none"
                style={{
                  fontSize: "3.2rem",
                  color: "var(--accent)",
                  lineHeight: 0.8,
                  marginTop: "0.1em",
                }}
              >
                {paragraph[0]}
              </span>
            )}
            {isFirst ? paragraph.slice(1) : paragraph}
            {isLast && isTyping && (
              <span
                className="ml-0.5 inline-block animate-pulse"
                style={{
                  width: 2,
                  height: "1em",
                  background: "var(--accent)",
                  verticalAlign: "text-bottom",
                }}
              />
            )}
          </p>
        );
      })}
    </>
  );
}
