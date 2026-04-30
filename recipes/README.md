# Recipes

One JSON file per source, named `<source_id>.json`, holding **sparse
overrides** on top of the default crawl policy. Every field is optional
except `source_id`. Missing recipes are fine — most sources crawl correctly
on defaults.

The default policy (in `src/crawler_v2/recipe.rs`):

| Field | Default |
|---|---|
| `entry_points` | `[<source.homepage_url>]` |
| `deny_paths` | `[]` (additive — built-in trap segments still apply) |
| `allow_paths` | `null` (no path-segment allow-list) |
| `max_depth` | 2 |
| `max_pdf_depth` | 3 |
| `max_html_fetches` | 250 |
| `max_total_fetches` | 1500 |
| `max_elapsed_sec` | 1200 |
| `rate_limit_ms` | 1000 |
| `respect_robots` | true |
| `allowed_subdomains` | `null` (default = public-suffix same-site rule) |
| `js_render_required` | false |

## When to write a recipe

- **Don't** for a source that crawls fine on defaults. The registry is
  authoritative; an empty/missing recipe is the right answer for ~80% of
  sources.
- **Do** when a source has a quirk: PDF archive deeper than 3, link traps
  (calendar/search/feed permutations), or it splits content across
  subdomains where the default same-site rule pulls in too much/too little.
- **The repair agent** writes recipes too — when a source is flagged
  StructurallyFailed by the health evaluator, the agent investigates and
  drops a sparse recipe here under `recipes/<source_id>.json`. Tier 3-5
  recipes are auto-applied to a `repair/<source>` branch; tier 1-2
  proposals route to human review.

## Examples

- `jirimun_gov_np.json` — minimal recipe for a Drupal palika that runs on
  defaults but with a notes field. Pattern: most palikas look like this.
- `lawcommission_gov_np.json` — PDF-heavy archive needs higher PDF budget.
- `supremecourt_gov_np.json` — trap-prone Drupal with `/calendar/` and
  `/search/` permutation bombs; needs `deny_paths` and a slower rate limit.

These three are intentionally chosen as **representative shapes** so the
repair agent has good few-shot context across the recipe vocabulary.

## Lifecycle fields

`last_repaired_at` and `repaired_by` are stamped by the agent dispatcher
when it auto-applies. Don't set them by hand.
