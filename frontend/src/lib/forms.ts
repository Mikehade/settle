import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { isApiError } from "@/lib/api/errors";

/**
 * The backend's 422 field errors (`{ field: "body.email", message }`) that belong to one of the
 * given form fields. Anything else stays with the general error.
 */
export function serverFieldErrors<T extends FieldValues>(
  error: unknown,
  fields: readonly Path<T>[],
) {
  if (!isApiError(error)) return [];
  return error.fieldErrors.flatMap(({ field, message }) => {
    const name = fields.find((candidate) => `body.${candidate}` === field);
    return name ? [{ name, message }] : [];
  });
}

/** Shows the backend's field errors on the matching inputs. Returns whether any were placed. */
export function applyServerFieldErrors<T extends FieldValues>(
  error: unknown,
  fields: readonly Path<T>[],
  setError: UseFormSetError<T>,
) {
  const matched = serverFieldErrors(error, fields);
  matched.forEach(({ name, message }, index) =>
    setError(name, { type: "server", message }, { shouldFocus: index === 0 }),
  );
  return matched.length > 0;
}
