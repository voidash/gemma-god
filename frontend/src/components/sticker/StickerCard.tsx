import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * "Sticker" cards. The whole design system rides on this primitive — a card
 * with a 2px ink border and an offset hard shadow.
 *
 * `tone` controls the shadow color (the ink anchor stays).
 * `wiggle` opts into the rotate-on-hover keyframe (skip for dense lists).
 * `pop` adds a press-down animation when the card itself is interactive.
 */
const stickerCardVariants = cva(
  "relative bg-card border-2 border-ink rounded-2xl",
  {
    variants: {
      tone: {
        ink: "shadow-[6px_6px_0_0_var(--ink)]",
        violet: "shadow-[6px_6px_0_0_var(--violet)]",
        pink: "shadow-[6px_6px_0_0_var(--pink)]",
        amber: "shadow-[6px_6px_0_0_var(--amber)]",
        mint: "shadow-[6px_6px_0_0_var(--mint)]",
        sky: "shadow-[6px_6px_0_0_var(--sky)]",
        soft: "shadow-[6px_6px_0_0_#E2E8F0]",
        none: "shadow-none",
      },
      wiggle: {
        true: "transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:-rotate-1 hover:scale-[1.02] motion-reduce:transform-none motion-reduce:hover:transform-none",
        false: "",
      },
      tilt: {
        none: "",
        left: "-rotate-1",
        right: "rotate-1",
      },
    },
    defaultVariants: { tone: "ink", wiggle: false, tilt: "none" },
  },
);

type StickerCardProps = React.HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof stickerCardVariants>;

export const StickerCard = React.forwardRef<HTMLDivElement, StickerCardProps>(
  function StickerCard({ className, tone, wiggle, tilt, ...rest }, ref) {
    return (
      <div
        ref={ref}
        className={cn(stickerCardVariants({ tone, wiggle, tilt }), className)}
        {...rest}
      />
    );
  },
);

export { stickerCardVariants };
