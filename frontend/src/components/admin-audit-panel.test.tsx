import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminAuditPage from "@/app/(app)/admin/audit/page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
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

describe("AdminAuditPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads audit events and shows real integrity result", async () => {
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
    render(<AdminAuditPage />);

    expect(await screen.findByText("LOGIN")).toBeInTheDocument();
    expect(
      screen.getAllByText("DENIED").some((el) => el.tagName === "SPAN"),
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: /Verify chain/i }));
    await waitFor(() => {
      expect(screen.getByText(/Chain invalid/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Stored event_hash does not match recalculated hash/i),
    ).toBeInTheDocument();
    // Must not treat HTTP success as chain validity.
    expect(screen.queryByText(/^Chain valid$/i)).not.toBeInTheDocument();
  });

  it("applies outcome filter to the API request", async () => {
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
    await user.click(screen.getByRole("button", { name: /Apply filters/i }));

    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({ outcome: "DENIED" }),
        expect.anything(),
      );
    });
  });
});
