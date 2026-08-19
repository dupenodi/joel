"use client";

import { cn } from "@/lib/utils";
import { useEffect, useRef } from "react";

/** Tight crop for the wordmark lockup. Hero uses a roomier box so motion doesn't clip. */
const VIEW_LOCKUP = "76 56 360 360";
const VIEW_HERO = "24 8 464 464";

function AsteriskGlyph({
  size,
  animated = false,
}: {
  size: number;
  animated?: boolean;
}) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const pupilRef = useRef<SVGEllipseElement>(null);

  useEffect(() => {
    if (!animated) return;

    const root = rootRef.current;
    const pupil = pupilRef.current;
    if (!root || !pupil) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) return;

    const MAX = Math.max(6, size * 0.028);
    let raf = 0;
    let targetX = 0;
    let targetY = 0;
    let curX = 0;
    let curY = 0;
    let tracking = false;
    let glanceTimer = 0;
    let glanceStepTimer = 0;
    let cancelled = false;

    const apply = () => {
      pupil.style.transform = `translate(${curX.toFixed(2)}px, ${curY.toFixed(2)}px)`;
    };

    const tick = () => {
      curX += (targetX - curX) * 0.14;
      curY += (targetY - curY) * 0.14;
      apply();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onMove = (e: PointerEvent) => {
      const rect = root.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy);
      const reach = Math.max(rect.width * 2.4, 260);

      if (dist < reach) {
        tracking = true;
        const scale = Math.min(1, dist / (rect.width * 0.85 || 1));
        const nx = dx / (dist || 1);
        const ny = dy / (dist || 1);
        targetX = nx * MAX * scale;
        targetY = ny * MAX * scale;
      } else if (tracking) {
        tracking = false;
        targetX = 0;
        targetY = 0;
      }
    };

    const scheduleGlance = () => {
      window.clearTimeout(glanceTimer);
      glanceTimer = window.setTimeout(() => {
        if (cancelled) return;
        if (tracking) {
          scheduleGlance();
          return;
        }

        const glances = [
          { x: MAX * 0.85, y: -MAX * 0.35 },
          { x: -MAX * 0.95, y: MAX * 0.25 },
          { x: 0, y: 0 },
        ];
        let i = 0;

        const step = () => {
          if (cancelled || tracking) {
            scheduleGlance();
            return;
          }
          const glance = glances[i++];
          if (!glance) {
            scheduleGlance();
            return;
          }
          targetX = glance.x;
          targetY = glance.y;
          glanceStepTimer = window.setTimeout(step, i === glances.length ? 0 : 780);
        };
        step();
      }, 2800 + Math.random() * 3400);
    };

    scheduleGlance();
    window.addEventListener("pointermove", onMove, { passive: true });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      window.clearTimeout(glanceTimer);
      window.clearTimeout(glanceStepTimer);
      window.removeEventListener("pointermove", onMove);
      pupil.style.transform = "";
    };
  }, [animated, size]);

  return (
    <span
      ref={rootRef}
      className={cn(
        "inline-flex overflow-visible",
        animated && "joel-mark-animated p-3",
      )}
      style={
        animated
          ? { animation: "asterisk-float 8.4s ease-in-out infinite" }
          : undefined
      }
    >
      <span
        className="inline-flex origin-center"
        style={
          animated
            ? { animation: "asterisk-breathe 3.2s ease-in-out infinite" }
            : undefined
        }
      >
        <svg
          width={size}
          height={size}
          viewBox={animated ? VIEW_HERO : VIEW_LOCKUP}
          overflow="visible"
          aria-hidden
          className="shrink-0 overflow-visible text-ink"
          style={
            animated
              ? {
                  filter: "drop-shadow(0 18px 28px rgba(19, 19, 19, 0.14))",
                }
              : undefined
          }
        >
          <g transform="translate(256 256) skewY(-10) translate(-256 -256)">
            <g transform="translate(252, 252)" fill="currentColor">
              <g
                style={
                  animated
                    ? {
                        animation: "asterisk-spin 14s linear infinite",
                        transformBox: "fill-box",
                        transformOrigin: "center",
                      }
                    : undefined
                }
              >
                <rect x="-34" y="-155" width="68" height="310" rx="26" />
                <rect
                  x="-34"
                  y="-155"
                  width="68"
                  height="310"
                  rx="26"
                  transform="rotate(45)"
                />
                <rect
                  x="-34"
                  y="-155"
                  width="68"
                  height="310"
                  rx="26"
                  transform="rotate(90)"
                />
                <rect
                  x="-34"
                  y="-155"
                  width="68"
                  height="310"
                  rx="26"
                  transform="rotate(135)"
                />
              </g>
              <g transform="scale(0.78)">
                <g
                  style={
                    animated
                      ? {
                          animation: "asterisk-blink 5.2s linear infinite",
                          transformBox: "fill-box",
                          transformOrigin: "center",
                        }
                      : undefined
                  }
                >
                  <path
                    d="M -68,-8 C -46,-42 -20,-60 4,-60 C 30,-60 54,-40 68,-8 Q 74,0 68,8 C 48,40 24,60 -4,60 C -32,60 -56,40 -68,8 Q -74,0 -68,-8 Z"
                    fill="var(--page)"
                  />
                  <ellipse
                    ref={pupilRef}
                    cx="0"
                    cy="0"
                    rx="22"
                    ry="34"
                    fill="currentColor"
                    style={
                      animated
                        ? {
                            transformBox: "fill-box",
                            transformOrigin: "center",
                            willChange: "transform",
                          }
                        : undefined
                    }
                  />
                </g>
              </g>
            </g>
          </g>
        </svg>
      </span>
    </span>
  );
}

/** Asterisk mark + optional wordmark. Canvas is cropped to the glyph. */
export function BrandMark({
  size = 36,
  className,
  withWordmark = false,
  animated = false,
}: {
  size?: number;
  className?: string;
  withWordmark?: boolean;
  animated?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <AsteriskGlyph size={size} animated={animated} />
      {withWordmark && (
        <span
          className="font-display leading-none font-semibold tracking-tight text-ink"
          style={{ fontSize: Math.round(size * 0.7) }}
        >
          Joel
        </span>
      )}
    </span>
  );
}
