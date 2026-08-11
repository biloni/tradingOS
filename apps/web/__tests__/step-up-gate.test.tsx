import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StepUpGate } from "@/components/ui/StepUpGate";

function renderGated() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <StepUpGate reason="doing the sensitive thing">
        <button type="button">Protected action</button>
      </StepUpGate>
    </QueryClientProvider>,
  );
}

function mockSessionFetch({ steppedUp }: { steppedUp: boolean }) {
  let currentlySteppedUp = steppedUp;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";

      if (path === "/api/v1/auth/session" && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              authenticated: true,
              stepped_up: currentlySteppedUp,
              expires_at: "2026-08-10T22:00:00-07:00",
            }),
        });
      }
      if (path === "/api/v1/auth/step-up" && method === "POST") {
        const body = init?.body ? JSON.parse(init.body as string) : {};
        if (body.password !== "correct-password") {
          return Promise.resolve({
            ok: false,
            status: 401,
            json: () => Promise.resolve({ detail: "Incorrect password." }),
          });
        }
        currentlySteppedUp = true;
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              authenticated: true,
              stepped_up: true,
              expires_at: "2026-08-10T22:00:00-07:00",
            }),
        });
      }
      return Promise.reject(new Error(`No mock handler for ${method} ${path}`));
    }),
  );
}

describe("StepUpGate", () => {
  it("renders children immediately when the session is already stepped up", async () => {
    mockSessionFetch({ steppedUp: true });
    renderGated();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Protected action" })).toBeInTheDocument(),
    );
  });

  it("blocks children behind a password prompt when not stepped up", async () => {
    mockSessionFetch({ steppedUp: false });
    renderGated();

    await waitFor(() =>
      expect(screen.getByTestId("step-up-password")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Protected action" })).not.toBeInTheDocument();
    expect(screen.getByText(/doing the sensitive thing/)).toBeInTheDocument();
  });

  it("reveals children after a correct password confirmation", async () => {
    mockSessionFetch({ steppedUp: false });
    const user = userEvent.setup();
    renderGated();

    await waitFor(() => expect(screen.getByTestId("step-up-password")).toBeInTheDocument());
    await user.type(screen.getByTestId("step-up-password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Protected action" })).toBeInTheDocument(),
    );
  });

  it("surfaces an incorrect password without revealing children", async () => {
    mockSessionFetch({ steppedUp: false });
    const user = userEvent.setup();
    renderGated();

    await waitFor(() => expect(screen.getByTestId("step-up-password")).toBeInTheDocument());
    await user.type(screen.getByTestId("step-up-password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(screen.getByText("Incorrect password.")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Protected action" })).not.toBeInTheDocument();
  });
});
