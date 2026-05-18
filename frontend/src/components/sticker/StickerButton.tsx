import * as React from "react";
import { Slot as SlotNS } from "radix-ui";

const Slot = SlotNS.Slot;
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * "Candy" buttons. Pill silhouette, dark border, hard offset shadow that
 * slides on press — the entire control feels like a physical sticker you
 * lift off the page.
 *
 * Hover lifts the button up-and-left and grows the shadow to 8px.
 * Active presses it back down so the shadow shrinks to 2px and looks tapped.
 * `motion-reduce:` variants strip the transform so reduced-motion users only
 * see the color change.
 */
const stickerButtonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap select-none",
    "rounded-full border-2 border-ink font-display font-bold",
    "transition-[transform,box-shadow,background-color] duration-200",
    "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[8px_8px_0_0_var(--ink)]",
    "active:translate-x-1 active:translate-y-1 active:shadow-[2px_2px_0_0_var(--ink)]",
    "motion-reduce:transform-none motion-reduce:transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-cream",
    "disabled:opacity-50 disabled:pointer-events-none",
  ].join(" "),
  {
    variants: {
      tone: {
        violet: "bg-violet text-white shadow-[4px_4px_0_0_var(--ink)]",
        pink: "bg-pink text-ink shadow-[4px_4px_0_0_var(--ink)]",
        amber: "bg-amber text-ink shadow-[4px_4px_0_0_var(--ink)]",
        mint: "bg-mint text-ink shadow-[4px_4px_0_0_var(--ink)]",
        ink: "bg-ink text-cream shadow-[4px_4px_0_0_var(--violet)] hover:shadow-[8px_8px_0_0_var(--violet)] active:shadow-[2px_2px_0_0_var(--violet)]",
        ghost:
          "bg-transparent text-ink shadow-none border-ink hover:bg-amber hover:shadow-[4px_4px_0_0_var(--ink)]",
        outline:
          "bg-card text-ink shadow-[4px_4px_0_0_var(--ink)] hover:bg-cream",
      },
      size: {
        sm: "h-9 px-4 text-sm",
        md: "h-11 px-5 text-sm",
        lg: "h-12 px-6 text-base",
        xl: "h-14 px-8 text-base",
        icon: "h-11 w-11 p-0",
      },
    },
    defaultVariants: { tone: "violet", size: "md" },
  },
);

type StickerButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof stickerButtonVariants> & {
    asChild?: boolean;
  };

export const StickerButton = React.forwardRef<
  HTMLButtonElement,
  StickerButtonProps
>(function StickerButton({ className, tone, size, asChild, ...rest }, ref) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      ref={ref as React.Ref<HTMLButtonElement>}
      className={cn(stickerButtonVariants({ tone, size }), className)}
      {...rest}
    />
  );
});

export { stickerButtonVariants };
