import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { startSession, useSessionStore } from "@/lib/session";
import { errorEnvelope, TEST_PASSWORD, TEST_TOKEN, TEST_USER } from "@/test/fixtures";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

describe("signing in", () => {
  it("sends a signed-out visitor to sign-in, then on to the page they asked for", async () => {
    const { user, router } = renderApp("/audit");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    // Router state can trail the first paint of the redirect target on a slow machine.
    await waitFor(() =>
      expect(router.state.location).toMatchObject({
        pathname: "/login",
        search: { redirect: "/audit" },
      }),
    );

    await user.type(screen.getByLabelText("Email"), TEST_USER.email);
    await user.type(screen.getByLabelText("Password"), TEST_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Audit trail" })).toBeInTheDocument();
    expect(screen.getAllByText(TEST_USER.email).length).toBeGreaterThan(0);
    expect(useSessionStore.getState().session?.accessToken).toBe(TEST_TOKEN);
  });

  it("explains a wrong password and clears it for another try", async () => {
    const { user } = renderApp("/login");

    await user.type(await screen.findByLabelText("Email"), TEST_USER.email);
    await user.type(screen.getByLabelText("Password"), "not-the-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("That email and password don't match")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(useSessionStore.getState().session).toBeNull();
  });

  it("shows the backend's validation errors on the matching field", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          errorEnvelope("COMMON_VALIDATION_ERROR", "Validation error", [
            { field: "body.email", message: "The domain name is a reserved name." },
          ]),
          { status: 422 },
        ),
      ),
    );
    const { user } = renderApp("/login");

    await user.type(await screen.findByLabelText("Email"), "seller@reserved.test");
    await user.type(screen.getByLabelText("Password"), TEST_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("The domain name is a reserved name.")).toBeInTheDocument();
    expect(screen.queryByText("Validation error")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveFocus();
  });

  it("checks the form before calling the backend", async () => {
    const { user } = renderApp("/login");

    await user.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
  });

  it("sends the root path to cases", async () => {
    startSession({ access_token: TEST_TOKEN, expires_in: 1800 });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Cases" })).toBeInTheDocument();
  });
});

describe("session ending", () => {
  it("returns to sign-in with an explanation when the backend rejects the token", async () => {
    startSession({ access_token: "revoked-token", expires_in: 1800 });
    renderApp("/policy");

    expect(await screen.findByText("Your session expired")).toBeInTheDocument();
    expect(useSessionStore.getState().session).toBeNull();
  });

  it("signs out from the user menu", async () => {
    startSession({ access_token: TEST_TOKEN, expires_in: 1800 });
    const { user } = renderApp("/cases");

    await user.click(await screen.findByRole("button", { name: new RegExp(TEST_USER.email) }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Your session expired")).not.toBeInTheDocument();
    expect(useSessionStore.getState().session).toBeNull();
  });
});
