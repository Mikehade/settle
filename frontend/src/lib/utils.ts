import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Document title for a page, e.g. "Cases · Settle". */
export function pageTitle(title: string) {
  return `${title} · Settle`;
}
