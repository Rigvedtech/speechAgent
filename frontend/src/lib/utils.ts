import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function truncate(str: string, max: number) {
  if (str.length <= max) return str
  return `${str.slice(0, max)}…`
}

export function formatScore(score: number | null | undefined) {
  if (score == null) return '—'
  return score.toFixed(1)
}
