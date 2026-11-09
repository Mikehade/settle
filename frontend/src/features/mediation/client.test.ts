import { describe, expect, it } from "vitest";

import { mediationUrl } from "./client";

describe("mediationUrl", () => {
  it("keeps the path the API is mounted under", () => {
    expect(mediationUrl("t", "https://api.example.com/settle")).toBe(
      "wss://api.example.com/settle/api/v1/ws/mediation?token=t",
    );
  });

  it("uses ws for an API served over http", () => {
    expect(mediationUrl("t", "http://localhost:5173")).toBe(
      "ws://localhost:5173/api/v1/ws/mediation?token=t",
    );
  });

  it("encodes the token", () => {
    expect(mediationUrl("a+b/c=", "https://api.example.com")).toBe(
      "wss://api.example.com/api/v1/ws/mediation?token=a%2Bb%2Fc%3D",
    );
  });
});
