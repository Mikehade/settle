import { test as base, type APIRequestContext } from "@playwright/test";

import { BACKEND_URL, SELLER, type Seller } from "./env";

export { expect } from "@playwright/test";

/** The browser's localStorage key for the session, as `src/lib/session.ts` persists it. */
const SESSION_KEY = "settle-session";

interface Fixtures {
  /** Who the page is signed in as when the test starts; `null` starts signed out. */
  seller: Seller | null;
}

async function signIn(request: APIRequestContext, seller: Seller) {
  const response = await request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: { email: seller.email, password: seller.password },
  });
  if (!response.ok()) throw new Error(`Signing in ${seller.email} failed: ${response.status()}`);
  const { data } = (await response.json()) as {
    data: { access_token: string; expires_in: number };
  };
  return data;
}

/**
 * Every test starts from a backend with no disputes, decisions or policy, and (unless it says
 * otherwise) signed in as the test seller. Signing in goes through the API rather than the form,
 * which `sign-in.spec.ts` covers once.
 */
export const test = base.extend<Fixtures>({
  seller: [SELLER, { option: true }],

  page: async ({ page, request, seller }, use) => {
    const reset = await request.post(`${BACKEND_URL}/__e2e__/reset`);
    if (!reset.ok()) throw new Error(`Resetting the e2e backend failed: ${reset.status()}`);

    if (seller) {
      const token = await signIn(request, seller);
      const session = {
        state: {
          session: {
            accessToken: token.access_token,
            expiresAt: Date.now() + token.expires_in * 1000,
          },
        },
        version: 0,
      };
      // Seeds the first load only, so a test that signs out stays signed out when it reloads.
      await page.addInitScript(
        ({ key, value }) => {
          if (sessionStorage.getItem("e2e-seeded")) return;
          sessionStorage.setItem("e2e-seeded", "1");
          localStorage.setItem(key, value);
        },
        { key: SESSION_KEY, value: JSON.stringify(session) },
      );
    }

    await use(page);
  },
});
