import { queryOptions } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/envelope";
import { startSession } from "@/lib/session";

export interface Credentials {
  email: string;
  password: string;
}

export async function signIn(credentials: Credentials) {
  const token = await unwrap(api.POST("/api/v1/auth/login", { body: credentials }));
  return startSession(token);
}

export function currentUserQuery() {
  return queryOptions({
    queryKey: ["auth", "me"],
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/auth/me", { signal })),
    staleTime: 5 * 60_000,
  });
}
