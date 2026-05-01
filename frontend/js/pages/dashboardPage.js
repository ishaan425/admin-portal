import { escapeHtml, friendlyStatus, getInitials, pillClass } from "../utils.js";

export function createDashboardPage(elements) {
  const {
    dashboardTotalUploads,
    dashboardStudentsCreated,
    dashboardNeedsReview,
    dashboardFailedParsing,
    dashboardLifecycleTotal,
    legendActive,
    dailyTodayCount,
    dailyWeekCount,
    dailyMonthCount,
    processingDonut,
    processingDonutValue,
    legendParsed,
    legendReview,
    legendFailed,
    uploadBars,
    sourceTopLabel,
    sourceStudentsCount,
    sourceFilesCount,
    bubbleMap,
    recentUploadsTable,
  } = elements;

  function renderUploadBarsFromBatch(result = {}) {
    const items = result.items || [];
    if (items.length === 0 && !result.total_files) {
      uploadBars.classList.add("empty-chart");
      uploadBars.textContent = "No upload history yet.";
      return;
    }
    uploadBars.classList.remove("empty-chart");
    const today = new Date();
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (6 - index));
      const key = date.toISOString().slice(0, 10);
      return {
        key,
        label: date.toLocaleDateString(undefined, { weekday: "short" }),
        count: 0,
      };
    });

    const fallbackDate = (result.created_at || new Date().toISOString()).slice(0, 10);
    if (items.length > 0) {
      items.forEach((item) => {
        const key = (item.created_at || result.created_at || fallbackDate).slice(0, 10);
        const bucket = days.find((day) => day.key === key);
        if (bucket) bucket.count += 1;
      });
    } else if (result.total_files) {
      const bucket = days.find((day) => day.key === fallbackDate) || days[days.length - 1];
      bucket.count = Number(result.total_files);
    }

    const maxCount = Math.max(...days.map((day) => day.count), 1);
    uploadBars.innerHTML = days
      .map((day) => {
        const height = Math.max(8, Math.round((day.count / maxCount) * 160));
        return `
          <div class="upload-bar" title="${day.count} uploads">
            <span style="height: ${height}px"></span>
            <strong>${day.count}</strong>
            <em>${escapeHtml(day.label)}</em>
          </div>
        `;
      })
      .join("");
  }

  function renderSourceBubbles(stats) {
    sourceTopLabel.textContent = stats.total > 0 ? "Latest Resume Batch" : "No batch data";
    sourceStudentsCount.textContent = `${stats.studentsCreated} students`;
    sourceFilesCount.textContent = `${stats.items.length || stats.total} points`;

    const parsedItems = stats.items.filter((item) => item.parse_status === "parsed");
    if (parsedItems.length === 0) {
      bubbleMap.innerHTML = `<div class="bubble-empty">No processed students yet.</div>`;
      return;
    }

    const colors = ["#f97316", "#10b981", "#0ea5e9", "#6366f1", "#14b8a6", "#f59e0b"];
    bubbleMap.innerHTML = parsedItems
      .slice(0, 10)
      .map((item, index) => {
        const x = 12 + ((index * 17) % 76);
        const y = 28 + ((index * 23) % 48);
        const size = 48 + Math.min(28, (item.extracted_full_name || "").length);
        return `<span style="--x: ${x}%; --y: ${y}%; --s: ${size}px; --c: ${colors[index % colors.length]}">${escapeHtml(
          getInitials(item.extracted_full_name, item.file_name),
        )}</span>`;
      })
      .join("");
  }

  function renderRecentUploads(items = []) {
    if (items.length === 0) {
      recentUploadsTable.innerHTML = `<div class="recent-empty">No uploads yet. Upload resumes to see recent activity.</div>`;
      return;
    }

    recentUploadsTable.innerHTML = items
      .map((item) => {
        const parseStatus = item.parse_status || "pending";
        const inviteStatus = item.invite_status || "not_attempted";
        const rowStatus =
          parseStatus === "failed"
            ? "Failed"
            : inviteStatus === "failed"
              ? "Review"
              : inviteStatus === "sent"
                ? "Invite sent"
                : friendlyStatus(parseStatus);
        return `
          <div class="recent-row">
            <span title="${escapeHtml(item.file_name || "")}">${escapeHtml(item.file_name || "Resume")}</span>
            <span>${escapeHtml(item.extracted_full_name || "Pending")}</span>
            <span>${escapeHtml(item.extracted_email || "Pending")}</span>
            <span><mark class="${pillClass(parseStatus === "failed" || inviteStatus === "failed" ? "failed" : parseStatus)}">${escapeHtml(
              rowStatus,
            )}</mark></span>
          </div>
        `;
      })
      .join("");
  }

  function render(result = {}, stats) {
    dashboardTotalUploads.textContent = stats.total.toString();
    dashboardStudentsCreated.textContent = stats.studentsCreated.toString();
    dashboardNeedsReview.textContent = stats.needsReview.toString();
    dashboardFailedParsing.textContent = stats.failedParsing.toString();
    dashboardLifecycleTotal.textContent = stats.total.toString();
    processingDonut.style.setProperty("--donut", `${stats.completionPercent}%`);
    processingDonutValue.textContent = `${stats.completionPercent}%`;
    legendParsed.textContent = stats.parsed.toString();
    legendReview.textContent = stats.needsReview.toString();
    legendActive.textContent = stats.active.toString();
    legendFailed.textContent = stats.failedParsing.toString();
    dailyTodayCount.textContent = stats.total.toString();
    dailyWeekCount.textContent = stats.total.toString();
    dailyMonthCount.textContent = stats.total.toString();
    renderUploadBarsFromBatch(result);
    renderSourceBubbles(stats);
    renderRecentUploads(stats.items);
  }

  return { render };
}
