export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function friendlyStatus(status) {
  const labels = {
    queued: "Received",
    pending: "Received",
    processing: "Processing",
    parsed: "Parsed",
    sent: "Sent",
    not_attempted: "Waiting",
    completed: "Complete",
    completed_with_errors: "Review",
    failed: "Failed",
  };
  return labels[status] || "Waiting";
}

export function pillClass(value) {
  if (value === "parsed" || value === "sent" || value === "completed") return "good";
  if (value === "failed") return "bad";
  return "warn";
}

export function getInitials(name, fallback) {
  const source = (name || fallback || "ST").trim();
  const words = source.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}
