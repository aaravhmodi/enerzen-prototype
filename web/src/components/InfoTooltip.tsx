"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function InfoTooltip({ text }: { text: string }) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; flip: boolean } | null>(null);

  function show() {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const flip = rect.top < 90; // not enough room above -> show below instead
    setPos({
      top: flip ? rect.bottom + 8 : rect.top - 8,
      left: rect.left + rect.width / 2,
      flip,
    });
  }

  function hide() {
    setPos(null);
  }

  return (
    <span
      className="inline-flex shrink-0 align-middle"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span
        ref={triggerRef}
        tabIndex={0}
        aria-label={text}
        className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-stone-300 text-[9px] font-bold leading-none text-stone-400 outline-none transition hover:border-emerald-400 hover:text-emerald-600 focus-visible:border-emerald-400 focus-visible:text-emerald-600"
      >
        i
      </span>
      {pos &&
        typeof document !== "undefined" &&
        createPortal(
          <span
            role="tooltip"
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              transform: pos.flip ? "translate(-50%, 0)" : "translate(-50%, -100%)",
            }}
            className="pointer-events-none z-[9999] w-52 rounded-lg bg-stone-900 px-2.5 py-2 text-[10px] font-normal leading-4 normal-case text-white shadow-lg"
          >
            {text}
          </span>,
          document.body
        )}
    </span>
  );
}
