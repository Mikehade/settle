/**
 * Where the end-to-end run serves the app and its backend, and who can sign in to it.
 *
 * The ports differ from the dev servers' (5173 and 8000), so a run never touches your own backend
 * or its database. The sellers exist only on the throwaway database `e2e/backend.py` creates;
 * their passwords are test values that work nowhere else.
 */
export const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5174);
export const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
export const WEB_URL = `http://localhost:${WEB_PORT}`;

export interface Seller {
  email: string;
  password: string;
  full_name: string;
}

export const SELLER: Seller = {
  email: "e2e-seller@settle.example",
  password: "e2e-only-password",
  full_name: "Sam Seller",
};

export const SELLERS = [SELLER];
