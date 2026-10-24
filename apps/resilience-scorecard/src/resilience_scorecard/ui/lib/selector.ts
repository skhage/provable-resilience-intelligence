/**
 * Query-option selector used by components as `useXxxSuspense(selector())` or
 * `useXxxSuspense({ params, ...selector() })`.
 * The apx-generated version unwrapped an axios-style `{ data }` envelope; our
 * hand-written client in lib/api.ts already returns the JSON payload, so this
 * only supplies shared query defaults.
 */
import type { QueryOptions } from "./api";

export default function selector(
  overrides: QueryOptions["query"] = {},
): Pick<QueryOptions, "query"> {
  return { query: { staleTime: 30_000, ...overrides } };
}
