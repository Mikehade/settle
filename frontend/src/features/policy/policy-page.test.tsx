import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { startSession } from "@/lib/session";
import { errorEnvelope, TEST_TOKEN, TEST_USER } from "@/test/fixtures";
import { policyBackend } from "@/test/msw/policy";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const signIn = () => startSession({ access_token: TEST_TOKEN, expires_in: 1800 });

const practice = () => screen.getByRole("list", { name: "When Settle acts alone" });

describe("the fairness policy page", () => {
  it("starts from the defaults when no policy is saved", async () => {
    signIn();
    renderApp("/policy");

    expect(await screen.findByText("You haven't set a policy yet")).toBeInTheDocument();
    expect(screen.getByLabelText("Confidence needed to act alone")).toHaveAttribute(
      "placeholder",
      "Default: 80%",
    );
    expect(practice()).toHaveTextContent("It is at least 80% confident in its decision.");
    expect(practice()).toHaveTextContent("The dispute is for less than 200.");
    expect(screen.getByRole("button", { name: "Save policy" })).toBeDisabled();
  });

  it("shows a saved policy, with confidence as a percentage", async () => {
    server.use(
      ...policyBackend({
        id: "policy-1",
        seller_id: TEST_USER.id,
        rules_text: "Refund in full when nothing shipped.",
        confidence_threshold: 0.75,
        human_in_loop_amount: 300,
        partial_refund_ceiling: null,
        auto_accept_max: null,
        always_refund_under: null,
        created_at: "2026-11-09T09:00:00",
        updated_at: "2026-11-09T09:00:00",
      }).handlers,
    );
    signIn();
    renderApp("/policy");

    expect(await screen.findByLabelText("Your rules")).toHaveValue(
      "Refund in full when nothing shipped.",
    );
    expect(screen.getByLabelText("Confidence needed to act alone")).toHaveValue("75");
    expect(screen.getByLabelText("Amount that always comes to you")).toHaveValue("300");
    expect(screen.queryByText("You haven't set a policy yet")).not.toBeInTheDocument();
    expect(screen.getByText(/^Saved /)).toBeInTheDocument();
  });

  it("explains changes as they're typed, then saves them with empty limits as defaults", async () => {
    const backend = policyBackend();
    server.use(...backend.handlers);
    signIn();
    const { user } = renderApp("/policy");

    await user.type(await screen.findByLabelText("Your rules"), "Refund when nothing shipped.");
    await user.type(screen.getByLabelText("Confidence needed to act alone"), "90");
    await user.type(screen.getByLabelText("Amount that always comes to you"), "100");

    expect(practice()).toHaveTextContent("It is at least 90% confident in its decision.");
    expect(
      screen.getByText(
        "The refund limit has no effect: disputes of 100 or more already come to you.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("You have unsaved changes.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save policy" }));

    expect(await screen.findByText("Fairness policy saved")).toBeInTheDocument();
    expect(backend.saved).toEqual([
      {
        rules_text: "Refund when nothing shipped.",
        confidence_threshold: 0.9,
        human_in_loop_amount: 100,
        partial_refund_ceiling: null,
        auto_accept_max: null,
        always_refund_under: null,
      },
    ]);
    expect(await screen.findByText("Saved just now")).toBeInTheDocument();
    expect(screen.getByLabelText("Confidence needed to act alone")).toHaveValue("90");
  });

  it("checks values before sending anything", async () => {
    const backend = policyBackend();
    server.use(...backend.handlers);
    signIn();
    const { user } = renderApp("/policy");

    await user.type(await screen.findByLabelText("Amount that always comes to you"), "abc");
    await user.type(screen.getByLabelText("Confidence needed to act alone"), "120");
    await user.click(screen.getByRole("button", { name: "Save policy" }));

    expect(await screen.findByText("Enter a number, like 150 or 99.50.")).toBeInTheDocument();
    expect(screen.getByText("Enter a percentage from 0 to 100.")).toBeInTheDocument();
    expect(backend.saved).toEqual([]);
  });

  it("shows the backend's objection on the field it's about", async () => {
    server.use(
      http.put("*/api/v1/policy", () =>
        HttpResponse.json(
          errorEnvelope("COMMON_VALIDATION_ERROR", "Validation failed", [
            { field: "body.partial_refund_ceiling", message: "Must be at most the review amount." },
          ]),
          { status: 422 },
        ),
      ),
    );
    signIn();
    const { user } = renderApp("/policy");

    await user.type(await screen.findByLabelText("Largest refund Settle gives alone"), "500");
    await user.click(screen.getByRole("button", { name: "Save policy" }));

    expect(await screen.findByText("Must be at most the review amount.")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't save your policy")).not.toBeInTheDocument();
  });

  it("asks before leaving with unsaved changes", async () => {
    signIn();
    const { user } = renderApp("/policy");

    await user.type(await screen.findByLabelText("Your rules"), "Be generous.");
    await user.click(screen.getByRole("link", { name: "Cases" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Leave without saving?");
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.getByLabelText("Your rules")).toHaveValue("Be generous.");

    await user.click(screen.getByRole("link", { name: "Cases" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Leave" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Cases", level: 1 })).toBeInTheDocument(),
    );
  });
});
