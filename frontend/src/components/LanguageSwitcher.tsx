import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * Language toggle styled as a sticker pill. The trigger button is the
 * "secondary" candy style (transparent fill, ink border, fills with amber
 * on hover) so it sits next to the primary nav without competing.
 */
export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const change = (lng: "en" | "ne") => () => void i18n.changeLanguage(lng);
  const active = i18n.resolvedLanguage === "ne" ? "नेपाली" : "English";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("lang.switch")}
        className={cn(
          "inline-flex items-center gap-2 h-9 px-4 rounded-full border-2 border-ink bg-cream",
          "font-display font-semibold text-sm text-ink transition-all duration-200",
          "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
          "hover:bg-amber hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--ink)]",
          "motion-reduce:hover:transform-none",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-cream",
        )}
      >
        <Languages className="size-4" aria-hidden strokeWidth={2.5} />
        <span className="hidden sm:inline">{active}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="border-2 border-ink rounded-2xl shadow-[4px_4px_0_0_var(--ink)] bg-card"
      >
        <DropdownMenuItem onClick={change("en")} className="font-medium gap-2">
          <span aria-hidden>🇬🇧</span>
          {t("lang.english")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={change("ne")} className="font-medium gap-2">
          <span aria-hidden>🇳🇵</span>
          {t("lang.nepali")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
