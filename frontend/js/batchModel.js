function countItems(items, predicate) {
  return items.filter(predicate).length;
}

export function getStudentStatus(item = {}) {
  if (item.parse_status === "failed" || item.invite_status === "failed") return "review";
  if (item.invite_status === "accepted") return "active";
  if (item.invite_status === "sent") return "invited";
  return "in_progress";
}

export function getStudentStatusLabel(status) {
  const labels = {
    invited: "Invited",
    in_progress: "In Progress",
    active: "Active",
    review: "Expired",
  };
  return labels[status] || "In Progress";
}

export function getStudentStatusClass(status) {
  if (status === "active" || status === "invited") return "good";
  if (status === "review") return "bad";
  return "warn";
}

export function normalizeStudentItem(item = {}, index = 0) {
  const id = item.resume_parse_item_id || item.id || `${item.file_name || "resume"}-${index}`;
  const name = item.extracted_full_name || "Pending";
  const email = item.extracted_email || "Pending";
  const status = getStudentStatus(item);
  return {
    ...item,
    id,
    displayName: name,
    displayEmail: email,
    displayStatus: status,
    displayStatusLabel: getStudentStatusLabel(status),
    createdDate: item.created_at ? new Date(item.created_at) : null,
  };
}

export function deriveBatchStats(result = {}, fallbackTotal = 0) {
  const items = (result.items || []).map(normalizeStudentItem);
  const total = Number(result.total_files ?? items.length ?? fallbackTotal ?? 0);
  const parsed = Number(
    result.parsed_count ?? countItems(items, (item) => item.parse_status === "parsed"),
  );
  const failedParsing = Number(
    result.failed_count ??
      result.parse_failed_count ??
      countItems(items, (item) => item.parse_status === "failed"),
  );
  const inviteFailures = countItems(items, (item) => item.invite_status === "failed");
  const needsReview = Math.max(
    failedParsing + inviteFailures,
    countItems(items, (item) => item.parse_status === "failed" || item.invite_status === "failed"),
  );
  const invited = countItems(items, (item) => item.displayStatus === "invited");
  const active = countItems(items, (item) => item.displayStatus === "active");
  const inProgress = Math.max(
    0,
    countItems(items, (item) => item.displayStatus === "in_progress"),
  );
  const studentsCreated = Number(result.invited_count ?? invited + active);

  return {
    total,
    parsed,
    failedParsing,
    needsReview,
    studentsCreated,
    invited,
    active,
    inProgress,
    completionPercent: total > 0 ? Math.round((parsed / total) * 100) : 0,
    items,
  };
}
