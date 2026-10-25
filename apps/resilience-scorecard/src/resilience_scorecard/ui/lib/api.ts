/**
 * Lakelink Fiber — typed API client + React Query hooks for the FastAPI backend.
 * Hand-written replacement for the apx-generated client (P24-APP-BUILD-SCAFFOLD).
 * Hook names mirror backend operation_ids in backend/router.py; query keys are
 * [operationId, params] so invalidateQueries({ queryKey: ["listActions"] }) works.
 * Hooks return the JSON payload directly as `data`.
 */
import {
  useMutation,
  useQuery,
  useSuspenseQuery,
  type UseMutationOptions,
} from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Types (loose mirrors of backend/models.py — the backend is the source of truth)
// ---------------------------------------------------------------------------
/* eslint-disable @typescript-eslint/no-explicit-any */
export type Health = { status: string; data_source?: string; [k: string]: any };
export type ResilienceScore = { service_id: string; resilience_score: number; [k: string]: any };
export type ResilienceSummary = {
  avg_resilience_score: number;
  critical_count: number;
  [k: string]: any;
};
export type RiskDistributionBucket = { [k: string]: any };
export type HazardListItem = { [k: string]: any };
export type HazardSummary = { active_hazards: number; [k: string]: any };
export type ProductOffering = { [k: string]: any };
export type HazardCrosswalkRow = { [k: string]: any };
export type HazardCrosswalkSummary = { [k: string]: any };
export type TopologyRegionSummary = { [k: string]: any };
export type TopologySite = { [k: string]: any };
export type TopologyConduit = { [k: string]: any };
export type ServicePathHop = { [k: string]: any };
export type ServiceDiversity = { [k: string]: any };
export type SrlgMember = { [k: string]: any };
export type HazardOverlay = { [k: string]: any };
export type ProactiveAction = { action_id: string; status: string; [k: string]: any };
export type ActionQueueSummary = {
  critical_pending: number;
  pending_count: number;
  in_progress_count: number;
  completed_count: number;
  [k: string]: any;
};
// P35-APP-CONDUIT-COVERAGE-BADGE (v4 shadow: physical_resource_conduit_v4_candidate)
// Live v4 (B2): REAL_SEGMENTED | BB_SEGMENTED | INVENTORY_ONLY. BB_ONLY is the superseded P35 value.
// The backend types this as str, so the UI must tolerate unknown classes.
export type SpanCoverageClass = "REAL_SEGMENTED" | "BB_SEGMENTED" | "BB_ONLY" | "INVENTORY_ONLY";
export type ConduitCoverage = {
  conduit_id: string;
  conduit_name: string | null;
  corridor: string | null;
  conduit_type: string | null;
  owner: string | null;
  region: string | null;
  length_km: number;
  span_coverage_class: SpanCoverageClass | string;
  segmented_km: number;
  coverage_pct: number;
  site_a_id: string | null;
  site_z_id: string | null;
  lat_a: number | null;
  lon_a: number | null;
  lat_z: number | null;
  lon_z: number | null;
};
export type ConduitCoverageSummary = {
  total_conduits: number;
  classes: {
    span_coverage_class: SpanCoverageClass | string;
    conduit_count: number;
    length_km: number;
    segmented_km: number;
  }[];
  source_table: string;
};
export type ActionStatus = "pending" | "in_progress" | "completed" | "cancelled";
export type ActionStatusUpdate = {
  status: ActionStatus | string;
  resolution_notes?: string | null;
  assigned_to?: string | null;
};
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------
type ParamValue = string | number | boolean | null | undefined;
export type Params = Record<string, ParamValue>;

export interface QueryOptions {
  params?: Params;
  query?: { staleTime?: number; refetchInterval?: number | false; enabled?: boolean };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildUrl(path: string, params?: Params): string {
  const sp = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") sp.append(k, String(v));
    }
  }
  const q = sp.toString();
  return q ? `${path}?${q}` : path;
}

const seg = (v: string) => encodeURIComponent(v);

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j && typeof j.detail === "string") detail = j.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// Only forward options that were actually set, so QueryClient defaults are not
// overridden with `undefined`.
function definedOnly<T extends object>(o: T | undefined): Partial<T> {
  if (!o) return {};
  return Object.fromEntries(
    Object.entries(o).filter(([, v]) => v !== undefined),
  ) as Partial<T>;
}

function suspenseHook<T>(operationId: string, path: string) {
  return (opts: QueryOptions = {}) => {
    const { enabled: _ignored, ...rest } = opts.query ?? {};
    return useSuspenseQuery<T>({
      queryKey: [operationId, opts.params ?? {}],
      queryFn: () => request<T>("GET", buildUrl(path, opts.params)),
      ...definedOnly(rest),
    });
  };
}

function queryHook<T>(operationId: string, path: string) {
  return (opts: QueryOptions = {}) =>
    useQuery<T>({
      queryKey: [operationId, opts.params ?? {}],
      queryFn: () => request<T>("GET", buildUrl(path, opts.params)),
      ...definedOnly(opts.query),
    });
}

// ---------------------------------------------------------------------------
// Raw API functions
// ---------------------------------------------------------------------------
export const api = {
  getHealth: () => request<Health>("GET", "/api/health"),
  getServiceScore: (serviceId: string) =>
    request<ResilienceScore>("GET", `/api/scores/${seg(serviceId)}`),
  getServicePathTrace: (serviceId: string) =>
    request<ServicePathHop[]>("GET", `/api/topology/path-trace/${seg(serviceId)}`),
  getServiceDiversity: (serviceId: string) =>
    request<ServiceDiversity>("GET", `/api/topology/diversity/${seg(serviceId)}`),
  getAction: (actionId: string) =>
    request<ProactiveAction>("GET", `/api/actions/${seg(actionId)}`),
  updateActionStatus: (actionId: string, data: ActionStatusUpdate) =>
    request<ProactiveAction>("PATCH", `/api/actions/${seg(actionId)}`, data),
};

// ---------------------------------------------------------------------------
// Scorecard
// ---------------------------------------------------------------------------
export const useGetHealth = queryHook<Health>("getHealth", "/api/health");
export const useListResilienceScoresSuspense = suspenseHook<ResilienceScore[]>("listResilienceScores", "/api/scores");
export const useListResilienceScores = queryHook<ResilienceScore[]>("listResilienceScores", "/api/scores");
export const useGetResilienceSummarySuspense = suspenseHook<ResilienceSummary>("getResilienceSummary", "/api/scores/summary");
export const useGetRiskDistributionSuspense = suspenseHook<RiskDistributionBucket[]>("getRiskDistribution", "/api/scores/risk-distribution");
export const useListProductOfferingsSuspense = suspenseHook<ProductOffering[]>("listProductOfferings", "/api/products");

export function useGetServiceScore(serviceId: string | undefined) {
  return useQuery({
    queryKey: ["getServiceScore", serviceId],
    queryFn: () => api.getServiceScore(serviceId as string),
    enabled: !!serviceId,
  });
}

// ---------------------------------------------------------------------------
// Hazards
// ---------------------------------------------------------------------------
export const useListHazardsSuspense = suspenseHook<HazardListItem[]>("listHazards", "/api/hazards");
export const useGetHazardSummarySuspense = suspenseHook<HazardSummary>("getHazardSummary", "/api/hazards/summary");
export const useListHazardCrosswalkSuspense = suspenseHook<HazardCrosswalkRow[]>("listHazardCrosswalk", "/api/hazards/crosswalk");
export const useGetHazardCrosswalkSummarySuspense = suspenseHook<HazardCrosswalkSummary>("getHazardCrosswalkSummary", "/api/hazards/crosswalk/summary");

// ---------------------------------------------------------------------------
// Topology
// ---------------------------------------------------------------------------
export const useListTopologyRegions = queryHook<TopologyRegionSummary[]>("listTopologyRegions", "/api/topology/regions");
export const useListTopologySites = queryHook<TopologySite[]>("listTopologySites", "/api/topology/sites");
export const useListTopologyConduits = queryHook<TopologyConduit[]>("listTopologyConduits", "/api/topology/conduits");
export const useListTopologySrlgs = queryHook<SrlgMember[]>("listTopologySrlgs", "/api/topology/srlgs");
export const useListTopologyHazards = queryHook<HazardOverlay[]>("listTopologyHazards", "/api/topology/hazards");

// ---------------------------------------------------------------------------
// Conduit coverage (P35-APP-CONDUIT-COVERAGE-BADGE)
// ---------------------------------------------------------------------------
export const useListConduitCoverageSuspense = suspenseHook<ConduitCoverage[]>("listConduitCoverage", "/api/conduits");
export const useGetConduitCoverageSummarySuspense = suspenseHook<ConduitCoverageSummary>("getConduitCoverageSummary", "/api/conduits/coverage-summary");

export function useGetServicePathTrace(serviceId: string | undefined) {
  return useQuery({
    queryKey: ["getServicePathTrace", serviceId],
    queryFn: () => api.getServicePathTrace(serviceId as string),
    enabled: !!serviceId,
  });
}

export function useGetServiceDiversity(serviceId: string | undefined) {
  return useQuery({
    queryKey: ["getServiceDiversity", serviceId],
    queryFn: () => api.getServiceDiversity(serviceId as string),
    enabled: !!serviceId,
  });
}

// ---------------------------------------------------------------------------
// Action queue (Lakebase-backed state)
// ---------------------------------------------------------------------------
export const useListActionsSuspense = suspenseHook<ProactiveAction[]>("listActions", "/api/actions");
export const useGetActionSummarySuspense = suspenseHook<ActionQueueSummary>("getActionSummary", "/api/actions/summary");

export function useGetAction(actionId: string | undefined) {
  return useQuery({
    queryKey: ["getAction", actionId],
    queryFn: () => api.getAction(actionId as string),
    enabled: !!actionId,
  });
}

export type UpdateActionStatusVars = { actionId: string; data: ActionStatusUpdate };

export function useUpdateActionStatus(
  opts: {
    mutation?: Omit<
      UseMutationOptions<ProactiveAction, ApiError, UpdateActionStatusVars>,
      "mutationFn"
    >;
  } = {},
) {
  return useMutation<ProactiveAction, ApiError, UpdateActionStatusVars>({
    mutationKey: ["updateActionStatus"],
    mutationFn: ({ actionId, data }) => api.updateActionStatus(actionId, data),
    ...opts.mutation,
  });
}
