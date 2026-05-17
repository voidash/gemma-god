import { Link, NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { cn } from "@/lib/utils";

const navItem = ({ isActive }: { isActive: boolean }) =>
  cn(
    "px-3 py-1.5 rounded-full font-display text-sm font-semibold transition-all duration-200",
    "ease-[cubic-bezier(0.34,1.56,0.64,1)]",
    isActive
      ? "bg-ink text-cream"
      : "text-ink/70 hover:text-ink hover:bg-amber/40 hover:-translate-y-0.5 motion-reduce:hover:transform-none",
  );

/**
 * The site chrome. Sits behind a soft dot-grid wash so the cream background
 * doesn't read as flat paper. The brand mark uses an inline ink-bordered
 * circle (sticker style) instead of a literal logo image.
 */
export function SiteHeader() {
  const { t } = useTranslation();

  return (
    <header className="sticky top-0 z-30 w-full border-b-2 border-ink bg-cream/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link
          to="/"
          className="flex items-center gap-2.5 font-display font-extrabold text-ink"
        >
          <span
            aria-hidden
            className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-ink bg-amber text-base shadow-[2px_2px_0_0_var(--ink)]"
          >
            🇳🇵
          </span>
          <span className="hidden sm:inline text-sm tracking-tight">
            {t("nav.brand")}
          </span>
        </Link>
        <nav className="ml-2 flex items-center gap-1">
          <NavLink to="/chat" className={navItem}>
            {t("nav.chat")}
          </NavLink>
          <NavLink to="/interview" className={navItem}>
            {t("nav.interview")}
          </NavLink>
          <NavLink to="/admin" className={navItem}>
            {t("nav.admin")}
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  );
}
