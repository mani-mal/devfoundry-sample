import { clsx } from 'clsx';

export function cn(...classes: Array<string | undefined | null | false>) {
  return clsx(...classes);
}
