import { cn } from "@/lib/utils";

/**
 * Decorative shapes used to fill the negative space around content blocks.
 * The brief calls this "Stable Grid, Wild Decoration" — content stays in
 * predictable rectangles, but the surrounding area is full of these shapes.
 *
 * All decor is `pointer-events-none aria-hidden` so it never interferes
 * with reading or interaction.
 */

type DecorBaseProps = React.SVGProps<SVGSVGElement> & {
  size?: number;
  className?: string;
};

const baseSvgClass = "pointer-events-none";

/** Wavy underline / divider — pair with section headings. */
export function Squiggle({
  size = 120,
  className,
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={(size * 14) / 120}
      viewBox="0 0 120 14"
      fill="none"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path
        d="M2 7 Q 12 1, 22 7 T 42 7 T 62 7 T 82 7 T 102 7 T 118 7"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Three short pen strokes pointing diagonally — emphasis around a word. */
export function Sparkle({
  size = 28,
  className,
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path d="M14 2 L14 10 M14 18 L14 26 M2 14 L10 14 M18 14 L26 14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M5 5 L9 9 M19 19 L23 23 M5 23 L9 19 M19 9 L23 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
    </svg>
  );
}

/** Filled triangle — confetti shape. */
export function Triangle({
  size = 24,
  className,
  fill = "currentColor",
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path
        d="M12 3 L22 21 L2 21 Z"
        fill={fill}
        stroke="var(--ink)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Filled circle with ink border. */
export function Dot({
  size = 18,
  className,
  fill = "currentColor",
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <circle cx="9" cy="9" r="7" fill={fill} stroke="var(--ink)" strokeWidth="2" />
    </svg>
  );
}

/** A 4-arm "burst" star, perfect rotated 15° on a badge. */
export function BurstStar({
  size = 80,
  className,
  fill = "currentColor",
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path
        d="M40 4 L46 26 L68 20 L52 38 L76 44 L52 50 L62 70 L42 56 L40 76 L38 56 L18 70 L28 50 L4 44 L28 38 L12 20 L34 26 Z"
        fill={fill}
        stroke="var(--ink)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Filled "leaf" — asymmetric blob shape. */
export function Leaf({
  size = 60,
  className,
  fill = "currentColor",
  ...rest
}: DecorBaseProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 60 60"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path
        d="M8 30 Q 8 8, 30 8 Q 52 8, 52 30 Q 30 52, 8 52 Z"
        fill={fill}
        stroke="var(--ink)"
        strokeWidth="2"
      />
    </svg>
  );
}

/** Dashed line that connects two boxes diagonally. Decorative path. */
export function DashedConnector({
  className,
  width = 200,
  height = 80,
  ...rest
}: DecorBaseProps & { width?: number; height?: number }) {
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      aria-hidden
      className={cn(baseSvgClass, className)}
      {...rest}
    >
      <path
        d={`M0 ${height / 2} Q ${width / 2} 0, ${width} ${height / 2}`}
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="6 6"
        strokeLinecap="round"
      />
    </svg>
  );
}
