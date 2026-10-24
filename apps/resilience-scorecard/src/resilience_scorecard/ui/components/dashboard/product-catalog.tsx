/**
 * Lakelink Fiber — Product Catalog Reference Table
 * P10-APP-PRODUCT-VIEW-PREP: service_type → product mapping with SLA tiers
 *
 * Displays product_offering bridge table data:
 * - Product name + service type mapping
 * - SLA tier with color-coded badges
 * - Bandwidth options
 * - Path diversity eligibility
 * - MRC range
 *
 * Pattern: mirrors HazardSummaryTable with Suspense + ErrorBoundary.
 */
import { Suspense } from "react";
import { QueryErrorResetBoundary, useSuspenseQuery } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";

interface ProductOffering {
  product_offering_id: string;
  service_type: string;
  product_name: string;
  product_category: string;
  network_technology: string;
  technology_domain: string;
  sla_tier_default: string;
  bandwidth_options: string;
  is_diverse_eligible: boolean;
  mrc_range_usd: string;
}

const SLA_BADGE: Record<string, { label: string; className: string }> = {
  premium_plus: { label: "Premium+", className: "severity-critical" },
  premium: { label: "Premium", className: "severity-major" },
  standard: { label: "Standard", className: "severity-moderate" },
};

const SERVICE_TYPE_LABELS: Record<string, string> = {
  wavelength: "Wavelength",
  ethernet: "Ethernet",
  dark_fiber: "Dark Fiber",
  ip_vpn: "IP VPN",
  managed_security: "Managed Security",
};

const CATEGORY_LABELS: Record<string, string> = {
  optical_transport: "Optical Transport",
  packet_services: "Packet Services",
  physical_infrastructure: "Physical Infrastructure",
  ip_services: "IP Services",
  security_services: "Security Services",
};

function useProductOfferings() {
  return useSuspenseQuery<ProductOffering[]>({
    queryKey: ["productOfferings"],
    queryFn: async () => {
      const r = await fetch("/api/products");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 300_000, // reference data, cache 5 min
  });
}

function ProductCatalogContent() {
  const { data: products } = useProductOfferings();

  if (products.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <p>No product offerings available</p>
          <p className="empty-hint">The product_offering table has not been seeded yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="data-table">
      <table aria-label="Lakelink Fiber product catalog">
        <thead>
          <tr>
            {/* BUG-DW-075: scope=col on every header; percentage widths (sum 100%) replace
                fixed px widths (sum 1070px) so the table reflows at <=1023px */}
            <th scope="col" style={{ width: "19%" }}>Product</th>
            <th scope="col" style={{ width: "12%" }}>Service Type</th>
            <th scope="col" style={{ width: "14%" }}>Category</th>
            <th scope="col" style={{ width: "11%" }}>Technology</th>
            <th scope="col" style={{ width: "9%" }}>SLA Tier</th>
            <th scope="col" style={{ width: "15%" }}>Bandwidth</th>
            <th scope="col" style={{ width: "9%" }}>Diverse</th>
            <th scope="col" style={{ width: "11%" }}>MRC Range</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => {
            const sla = SLA_BADGE[p.sla_tier_default] ?? { label: p.sla_tier_default, className: "" };
            return (
              <tr key={p.product_offering_id}>
                <td className="text-medium">{p.product_name}</td>
                <td>{SERVICE_TYPE_LABELS[p.service_type] ?? p.service_type}</td>
                <td className="text-sm">{CATEGORY_LABELS[p.product_category] ?? p.product_category}</td>
                <td className="mono text-sm">{p.network_technology}</td>
                <td>
                  <span className={`badge ${sla.className}`}>{sla.label}</span>
                </td>
                <td className="mono text-sm">{p.bandwidth_options}</td>
                <td>
                  {/* BUG-DW-075: aria-label on a role-less span is prohibited (ARIA 1.2);
                      hide the glyph and rely on the visible Yes/No text */}
                  <span className={`badge ${p.is_diverse_eligible ? "completed" : "severity-moderate"}`}>
                    <span aria-hidden="true">{p.is_diverse_eligible ? "\u2713" : "\u2717"}</span>{" "}
                    {p.is_diverse_eligible ? "Yes" : "No"}
                  </span>
                </td>
                <td className="mono">${p.mrc_range_usd}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ProductCatalog() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="data-table error-fallback">
              <p>Failed to load product catalog</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div aria-busy="true" aria-label="Loading product catalog">
                <Skeleton className="h-64 w-full rounded-lg" />
              </div>
            }
          >
            <ProductCatalogContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
