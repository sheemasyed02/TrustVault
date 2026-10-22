import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminAuditPage from "@/app/(app)/admin/audit/page";
import AdminAuditIntegrityPage from "@/app/(app)/admin/audit/integrity/page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/admin/audit",
}));

const handleUnauthorized = vi.hoisted(() => () => false);

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    status: "authenticated",
    accessToken: "tok",
    user: {
      id: "00000000-0000-0000-0000-000000000099",
      name: "Admin",
      email: "admin@example.com",
      role: "ADMIN",
    },
  }),
  useHandleUnauthorized: () => handleUnauthorized,
}));

describe("AdminAuditLogsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads audit events without embedding integrity verification", async () => {
    vi.spyOn(api, "listAuditEventsRequest").mockResolvedValue({
      results: [
        {
          id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          created_at: "2026-10-21T12:00:00+00:00",
          actor_id: "00000000-0000-0000-0000-000000000001",
          action: "LOGIN",
          document_id: null,
          target_user_id: null,
          outcome: "DENIED",
          reason_code: "INVALID_CREDENTIALS",
          request_id: "r1",
          metadata: {},
          previous_hash: null,
          event_hash: "a".repeat(64),
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });

    render(<AdminAuditPage />);

    expect(await screen.findByRole("heading", { name: /audit logs/i })).toBeInTheDocument();
    // Desktop table + mobile card both render the action label.
    expect(screen.getAllByText("LOGIN").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Denied").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByRole("link", { name: /audit integrity/i }),
    ).toHaveAttribute("href", "/admin/audit/integrity");
    expect(
      screen.queryByRole("button", { name: /Verify chain|Run integrity/i }),
    ).toBeNull();
  });

  it("applies outcome and owner filters to the API request", async () => {
    const listSpy = vi.spyOn(api, "listAuditEventsRequest").mockResolvedValue({
      results: [],
      page: 1,
      page_size: 20,
      total: 0,
      total_pages: 0,
    });

    const user = userEvent.setup();
    render(<AdminAuditPage />);
    await screen.findByText(/No audit events match/i);

    await user.selectOptions(screen.getByDisplayValue("Any"), "DENIED");
    await user.type(
      screen.getByPlaceholderText(/Document owner UUID/i),
      "00000000-0000-0000-0000-000000000010",
    );
    await user.click(screen.getByRole("button", { name: /Apply filters/i }));

    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({
          outcome: "DENIED",
          owner_id: "00000000-0000-0000-0000-000000000010",
        }),
        expect.anything(),
      );
    });
  });
});

describe("AdminAuditIntegrityPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows real integrity result and never pretends HTTP success is chain validity", async () => {
    vi.spyOn(api, "verifyAuditIntegrityRequest").mockResolvedValue({
      valid: false,
      event_count: 3,
      checked_count: 1,
      first_failure_index: 1,
      first_failure_event_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      reason_code: "EVENT_HASH_MISMATCH",
      detail: "Stored event_hash does not match recalculated hash",
    });

    const user = userEvent.setup();
    render(<AdminAuditIntegrityPage />);

    expect(
      screen.getByText(/No check has run yet/i),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /Run integrity check/i }),
    );
    await waitFor(() => {
      expect(
        screen.getByText(/Stored event_hash does not match recalculated hash/i),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/^Verified$/i)).not.toBeInTheDocument();
  });
});
