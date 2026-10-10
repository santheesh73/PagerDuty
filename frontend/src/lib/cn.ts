import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Conditional class names where later Tailwind utilities override earlier ones (w-36 beats w-full). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
