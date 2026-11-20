import { Fragment } from "react";

function inline(text: string, onCite?: (index: number) => void) {
  const parts = text.split(/(\[\d+\]|\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (/^\[\d+\]$/.test(part)) {
      const number = Number(part.slice(1, -1));
      return (
        <button key={index} className="cite-ref" onClick={() => onCite?.(number)} title="查看原文位置">
          {part}
        </button>
      );
    }
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export default function RichText({
  text,
  onCite,
}: {
  text: string;
  onCite?: (index: number) => void;
}) {
  const lines = text.split("\n");
  return (
    <div className="rich-text">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={index} className="rich-gap" />;
        if (trimmed.startsWith("#")) {
          return (
            <div key={index} className="rich-h">
              {inline(trimmed.replace(/^#+\s*/, ""), onCite)}
            </div>
          );
        }
        if (/^[-•]\s+/.test(trimmed)) {
          return (
            <div key={index} className="rich-li">
              <span className="rich-bullet">•</span>
              <span>{inline(trimmed.replace(/^[-•]\s+/, ""), onCite)}</span>
            </div>
          );
        }
        if (/^\d+[.、]\s*/.test(trimmed)) {
          const match = trimmed.match(/^(\d+)[.、]\s*(.*)$/);
          return (
            <div key={index} className="rich-li">
              <span className="rich-num">{match?.[1]}</span>
              <span>{inline(match?.[2] ?? trimmed, onCite)}</span>
            </div>
          );
        }
        return (
          <p key={index} className="rich-p">
            {inline(trimmed, onCite)}
          </p>
        );
      })}
    </div>
  );
}
