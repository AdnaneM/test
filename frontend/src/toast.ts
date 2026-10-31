import { useEffect, useState } from "react";

export type ToastKind = "info" | "success" | "error";

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

type Listener = (items: ToastItem[]) => void;

let items: ToastItem[] = [];
let seq = 0;
const listeners = new Set<Listener>();

function emit(): void {
  for (const l of listeners) l(items);
}

/** Affiche un message éphémère en bas de l'écran. */
export function toast(message: string, kind: ToastKind = "info", ttl = 3500): void {
  const t: ToastItem = { id: ++seq, message, kind };
  items = [...items, t].slice(-3);
  emit();
  window.setTimeout(() => {
    items = items.filter((x) => x.id !== t.id);
    emit();
  }, ttl);
}

export function useToasts(): ToastItem[] {
  const [list, setList] = useState<ToastItem[]>(items);
  useEffect(() => {
    listeners.add(setList);
    return () => {
      listeners.delete(setList);
    };
  }, []);
  return list;
}
