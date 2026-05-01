import { getStudentStatusClass } from "../batchModel.js";
import { escapeHtml } from "../utils.js";

export function createStudentsPage({ elements, getLatestStats, showToast }) {
  const {
    totalStudentsCount,
    invitedStudentsCount,
    progressStudentsCount,
    activeStudentsCount,
    reviewStudentsCount,
    studentSearchInput,
    studentStatusFilter,
    studentDateFilter,
    clearFiltersButton,
    selectAllStudents,
    studentTableBody,
    bulkActionBar,
    selectedStudentCount,
    clearSelectionButton,
  } = elements;

  let selectedStudentIds = new Set();

  function passesDateFilter(item) {
    const filter = studentDateFilter.value;
    if (filter === "all" || !item.createdDate) return true;

    const now = new Date();
    const ageMs = now.getTime() - item.createdDate.getTime();
    if (filter === "today") return item.createdDate.toDateString() === now.toDateString();
    if (filter === "week") return ageMs <= 7 * 24 * 60 * 60 * 1000;
    if (filter === "month") return ageMs <= 31 * 24 * 60 * 60 * 1000;
    return true;
  }

  function getFilteredItems(items = getLatestStats().items) {
    const search = studentSearchInput.value.trim().toLowerCase();
    const status = studentStatusFilter.value;
    return items.filter((item) => {
      const haystack = `${item.displayName} ${item.displayEmail} ${item.file_name || ""}`.toLowerCase();
      const matchesSearch = !search || haystack.includes(search);
      const matchesStatus = status === "all" || item.displayStatus === status;
      return matchesSearch && matchesStatus && passesDateFilter(item);
    });
  }

  function renderBulkActionBar() {
    selectedStudentCount.textContent = selectedStudentIds.size.toString();
    bulkActionBar.classList.toggle("hidden", selectedStudentIds.size === 0);
  }

  function renderTable(items = getLatestStats().items) {
    const filteredItems = getFilteredItems(items);
    const filteredIds = new Set(filteredItems.map((item) => item.id));
    selectedStudentIds = new Set([...selectedStudentIds].filter((id) => filteredIds.has(id)));
    selectAllStudents.checked =
      filteredItems.length > 0 && filteredItems.every((item) => selectedStudentIds.has(item.id));
    renderBulkActionBar();

    if (filteredItems.length === 0) {
      studentTableBody.innerHTML = `<div class="table-empty">No students found</div>`;
      return;
    }

    studentTableBody.innerHTML = filteredItems
      .map((item) => {
        const checked = selectedStudentIds.has(item.id) ? "checked" : "";
        const created = item.createdDate ? item.createdDate.toLocaleDateString() : "-";
        const inviteLabel = item.clerk_invitation_id ? "Sent" : item.invite_status === "failed" ? "Failed" : "Waiting";
        return `
          <div class="student-row" data-student-id="${escapeHtml(item.id)}">
            <span><input class="student-checkbox" type="checkbox" ${checked} aria-label="Select ${escapeHtml(
              item.displayName,
            )}" /></span>
            <span class="student-name" title="${escapeHtml(item.file_name || "")}">${escapeHtml(item.displayName)}</span>
            <span class="muted-text">${escapeHtml(item.displayEmail)}</span>
            <span>${escapeHtml(inviteLabel)}</span>
            <span><mark class="${getStudentStatusClass(item.displayStatus)}">${escapeHtml(item.displayStatusLabel)}</mark></span>
            <span class="muted-text">${escapeHtml(created)}</span>
            <span class="table-actions">
              <button class="icon-button view-student-button" type="button" aria-label="View ${escapeHtml(item.displayName)}">View</button>
            </span>
          </div>
        `;
      })
      .join("");
  }

  function render(stats) {
    totalStudentsCount.textContent = stats.total.toString();
    invitedStudentsCount.textContent = stats.invited.toString();
    progressStudentsCount.textContent = stats.inProgress.toString();
    activeStudentsCount.textContent = stats.active.toString();
    reviewStudentsCount.textContent = stats.needsReview.toString();
    renderTable(stats.items);
  }

  function exportCsv() {
    const rows = getFilteredItems();
    if (rows.length === 0) {
      showToast("No students to export.");
      return;
    }

    const headers = ["Name", "Email", "Status", "File", "Created"];
    const csvRows = rows.map((item) =>
      [
        item.displayName,
        item.displayEmail,
        item.displayStatusLabel,
        item.file_name || "",
        item.createdDate ? item.createdDate.toISOString() : "",
      ]
        .map((value) => {
          const safeValue = String(value).replaceAll('"', '""');
          return safeValue.includes(",") || safeValue.includes('"') || safeValue.includes("\n")
            ? `"${safeValue}"`
            : safeValue;
        })
        .join(","),
    );
    const blob = new Blob([[headers.join(","), ...csvRows].join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `students_latest_batch_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function resetFilters() {
    selectedStudentIds.clear();
    studentSearchInput.value = "";
    studentStatusFilter.value = "all";
    studentDateFilter.value = "all";
  }

  function clearSelection() {
    selectedStudentIds.clear();
    renderTable();
  }

  function bindEvents({ renderAll }) {
    studentSearchInput.addEventListener("input", renderAll);
    studentStatusFilter.addEventListener("change", renderAll);
    studentDateFilter.addEventListener("change", renderAll);
    clearFiltersButton.addEventListener("click", () => {
      resetFilters();
      renderAll();
    });
    selectAllStudents.addEventListener("change", () => {
      const visibleItems = getFilteredItems();
      if (selectAllStudents.checked) {
        visibleItems.forEach((item) => selectedStudentIds.add(item.id));
      } else {
        visibleItems.forEach((item) => selectedStudentIds.delete(item.id));
      }
      renderTable();
    });
    studentTableBody.addEventListener("click", (event) => {
      const row = event.target.closest(".student-row");
      if (!row) return;
      const id = row.dataset.studentId;
      if (event.target.classList.contains("student-checkbox")) {
        if (event.target.checked) {
          selectedStudentIds.add(id);
        } else {
          selectedStudentIds.delete(id);
        }
        renderBulkActionBar();
        return;
      }
      if (event.target.classList.contains("view-student-button")) {
        const item = getLatestStats().items.find((student) => student.id === id);
        showToast(
          item?.displayEmail && item.displayEmail !== "Pending"
            ? item.displayEmail
            : item?.file_name || "Student details pending.",
        );
      }
    });
    clearSelectionButton.addEventListener("click", clearSelection);
  }

  return {
    bindEvents,
    clearSelection,
    exportCsv,
    getFilteredItems,
    render,
    resetFilters,
  };
}
