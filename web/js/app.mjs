export function formatStatus(s) {
  return String(s ?? "").trim();
}

export function boot() {
  return { package: "opsledger", ready: true };
}
