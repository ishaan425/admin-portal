import { deriveBatchStats } from "./batchModel.js";
import { createDashboardPage } from "./pages/dashboardPage.js";
import { createStudentsPage } from "./pages/studentsPage.js";
import { escapeHtml, friendlyStatus, pillClass } from "./utils.js";

const TERMINAL_STATUSES = new Set(["completed", "completed_with_errors", "failed"]);

export function createAdminPortalApp({ config, elements }) {
  const {
    API_URL,
    ORGANIZATION_SLUG,
    LOCAL_CLERK_USER_ID,
    BEARER_TOKEN,
    CLERK_PUBLISHABLE_KEY,
    CLERK_FRONTEND_API_URL,
    ALLOW_LOCAL_DEV_LOGIN,
  } = config;
  const {
    authShell,
    onboardingShell,
    appPage,
    signInMount,
    authStatus,
    authSignOutButton,
    localDevButton,
    adminOnboardingForm,
    adminFullNameInput,
    adminDepartmentInput,
    adminPhoneInput,
    customPositionInput,
    positionGrid,
    adminIdentity,
    userButton,
    signOutButton,
    topbarDate,
    topbarUserInitial,
    topbarUserName,
    topbarUserEmail,
    sidebarUserInitial,
    sidebarUserName,
    sidebarUserEmail,
    sidebarLogoutButton,
    fileInput,
    dropZone,
    browseButton,
    uploadButton,
    clearButton,
    fileCount,
    fileList,
    progressTitle,
    resultBadge,
    processBar,
    liveStatus,
    batchSummary,
    friendlyResults,
    toast,
    stepUpload,
    stepParse,
    stepInvite,
    dropTitle,
    dropHint,
    dashboardNavButton,
    studentsNavButton,
    dashboardPage,
    studentsPage,
    refreshDashboardButton,
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
    sourceViewButtons,
    exportCsvButton,
    studentToggleUploadButton,
    studentUploadSection,
    studentFileInput,
    studentDropZone,
    studentBrowseButton,
    studentUploadButton,
    studentClearFilesButton,
    studentSelectedFiles,
    studentFileCount,
    studentFileList,
    studentDropTitle,
    studentDropHint,
    studentProgressWrap,
    studentProgressBar,
    studentProgressText,
    totalStudentsCount,
    invitedStudentsCount,
    progressStudentsCount,
    activeStudentsCount,
    reviewStudentsCount,
    studentSearchInput,
    studentStatusFilter,
    studentDateFilter,
    clearFiltersButton,
    refreshTableButton,
    selectAllStudents,
    studentTableBody,
    bulkActionBar,
    selectedStudentCount,
    clearSelectionButton,
  } = elements;

  let selectedFiles = [];
  let latestBatchId = "";
  let monitorTimer = null;
  let authMode = "pending";
  let currentAdmin = null;
  let selectedPosition = "";
  let latestBatchResult = null;
  let latestBatchStats = deriveBatchStats();
  const dashboardPageController = createDashboardPage(elements);
  const studentsPageController = createStudentsPage({
    elements,
    getLatestStats: () => latestBatchStats,
    showToast,
  });

function onboardingStorageKey(adminResponse = currentAdmin) {
  const admin = adminResponse?.admin || {};
  const org = adminResponse?.organization || {};
  return `growqr-admin-setup:${org.slug || ORGANIZATION_SLUG}:${admin.clerk_user_id || admin.email || "local"}`;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

async function requestHeaders() {
  if (authMode === "clerk") {
    const token = await window.Clerk?.session?.getToken();
    if (!token) throw new Error("Your admin session expired. Please sign in again.");
    return {
      Authorization: `Bearer ${token}`,
      "X-Organization-Slug": ORGANIZATION_SLUG,
    };
  }

  if (BEARER_TOKEN) {
    return {
      Authorization: `Bearer ${BEARER_TOKEN}`,
      "X-Organization-Slug": ORGANIZATION_SLUG,
    };
  }

  return {
    "X-Local-Clerk-User-Id": LOCAL_CLERK_USER_ID,
    "X-Organization-Slug": ORGANIZATION_SLUG,
  };
}

function setAuthMessage(message) {
  authStatus.textContent = message;
}

function showAuthSignOut() {
  if (window.Clerk?.isSignedIn) {
    authSignOutButton.classList.remove("hidden");
  }
}

function showAuthShell() {
  document.body.classList.remove("students-active");
  authShell.classList.remove("hidden");
  onboardingShell.classList.add("hidden");
  appPage.classList.add("hidden");
}

function showOnboardingShell(adminResponse) {
  currentAdmin = adminResponse;
  authShell.classList.add("hidden");
  appPage.classList.add("hidden");
  onboardingShell.classList.remove("hidden");
  const admin = adminResponse.admin || {};
  const storedProfile = readStoredAdminProfile(adminResponse);
  adminFullNameInput.value = storedProfile.fullName || admin.full_name || "";
  adminDepartmentInput.value = storedProfile.department || "";
  adminPhoneInput.value = storedProfile.phone || "";
  selectPosition(storedProfile.position || "");
}

function showAppShell(adminResponse) {
  currentAdmin = adminResponse;
  authShell.classList.add("hidden");
  onboardingShell.classList.add("hidden");
  appPage.classList.remove("hidden");
  const admin = adminResponse.admin || {};
  const org = adminResponse.organization || {};
  const setupProfile = readStoredAdminProfile(adminResponse);
  const displayName = setupProfile.fullName || admin.full_name || admin.email || "Admin";
  const displayEmail = admin.email || "";
  const initial = displayName.trim().charAt(0).toUpperCase() || "A";
  adminIdentity.innerHTML = `
    <strong>${escapeHtml(displayName)}</strong>
    <span>${escapeHtml(org.name || org.slug || ORGANIZATION_SLUG)}</span>
  `;
  topbarUserInitial.textContent = initial;
  topbarUserName.textContent = displayName;
  topbarUserEmail.textContent = displayEmail;
  sidebarUserInitial.textContent = initial;
  sidebarUserName.textContent = displayName;
  sidebarUserEmail.textContent = displayEmail;
  renderTopbarDate();
}

function readStoredAdminProfile(adminResponse = currentAdmin) {
  try {
    return JSON.parse(window.localStorage.getItem(onboardingStorageKey(adminResponse)) || "{}");
  } catch {
    return {};
  }
}

function isAdminSetupComplete(adminResponse = currentAdmin) {
  const profile = readStoredAdminProfile(adminResponse);
  return Boolean(profile.fullName && profile.position);
}

function continueAfterAdminVerification(adminResponse) {
  if (isAdminSetupComplete(adminResponse)) {
    showAppShell(adminResponse);
  } else {
    showOnboardingShell(adminResponse);
  }
}

function selectPosition(position) {
  selectedPosition = position;
  positionGrid.querySelectorAll(".role-tile").forEach((tile) => {
    tile.classList.toggle("selected", tile.dataset.position === position);
  });
  customPositionInput.classList.toggle("hidden", position !== "Other");
  if (position !== "Other") customPositionInput.value = "";
}

function renderTopbarDate() {
  const now = new Date();
  const today = now.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const currentTime = now.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
  topbarDate.textContent = `${today} • ${currentTime}`;
}

function loadScript(src, attributes = {}) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    script.crossOrigin = "anonymous";
    Object.entries(attributes).forEach(([key, value]) => script.setAttribute(key, value));
    script.addEventListener("load", resolve);
    script.addEventListener("error", () => reject(new Error(`Could not load ${src}`)));
    document.head.appendChild(script);
  });
}

async function verifyAdminAccess(mode) {
  authMode = mode;
  const response = await fetch(`${API_URL}/admin/me`, {
    headers: await requestHeaders(),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || "You are not an active admin for this organization.");
  }
  currentAdmin = body;
  continueAfterAdminVerification(body);
  return body;
}

async function continueAsLocalAdmin() {
  setAuthMessage("Checking local admin access...");
  try {
    await verifyAdminAccess("local");
    signOutButton.classList.remove("hidden");
    showToast("Signed in locally.");
  } catch (error) {
    setAuthMessage(error.message);
    showToast(error.message);
  }
}

async function initializeClerkAuth() {
  if (!CLERK_PUBLISHABLE_KEY) {
    setAuthMessage("Clerk publishable key is not configured for this admin frontend.");
    if (ALLOW_LOCAL_DEV_LOGIN) localDevButton.classList.remove("hidden");
    return;
  }

  try {
    setAuthMessage("Loading secure sign in...");
    await loadScript(`${CLERK_FRONTEND_API_URL}/npm/@clerk/ui@1/dist/ui.browser.js`);
    await loadScript(`${CLERK_FRONTEND_API_URL}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
      "data-clerk-publishable-key": CLERK_PUBLISHABLE_KEY,
    });
    await window.Clerk.load({
      ui: { ClerkUI: window.__internal_ClerkUICtor },
    });

    if (window.Clerk.isSignedIn) {
      try {
        await verifyAdminAccess("clerk");
        mountUserControls();
      } catch (error) {
        setAuthMessage(error.message);
        showAuthSignOut();
      }
      return;
    }

    setAuthMessage("Sign in with your GrowQR admin account.");
    signInMount.innerHTML = "";
    window.Clerk.mountSignIn(signInMount, {
      afterSignInUrl: window.location.href,
      afterSignUpUrl: window.location.href,
    });

    window.Clerk.addListener?.(async ({ session }) => {
      if (!session) {
        currentAdmin = null;
        authMode = "pending";
        adminIdentity.innerHTML = "";
        userButton.innerHTML = "";
        showAuthShell();
        return;
      }
      if (currentAdmin) return;
      try {
        await verifyAdminAccess("clerk");
        mountUserControls();
      } catch (error) {
        setAuthMessage(error.message);
        showAuthSignOut();
      }
    });
  } catch (error) {
    setAuthMessage(error.message);
    if (ALLOW_LOCAL_DEV_LOGIN) localDevButton.classList.remove("hidden");
  }
}

function mountUserControls() {
  signOutButton.classList.add("hidden");
  userButton.innerHTML = "";
  if (window.Clerk?.mountUserButton) {
    window.Clerk.mountUserButton(userButton);
  }
}

function setStepState(step, state) {
  step.classList.remove("active", "done", "error");
  if (state) step.classList.add(state);
}

function setProcess(percent, message) {
  processBar.style.setProperty("--progress", `${percent}%`);
  liveStatus.textContent = message;
  studentProgressBar.style.setProperty("--progress", `${percent}%`);
  studentProgressText.textContent = `${message} ${percent}%`;
}

function setProgressState(status, items = []) {
  const hasParsed = items.some((item) => item.parse_status === "parsed");
  const hasParseError = items.some((item) => item.parse_status === "failed");
  const hasInvite = items.some((item) => item.invite_status === "sent");
  const hasInviteError = items.some((item) => item.invite_status === "failed");

  setStepState(stepUpload, latestBatchId ? "done" : "");
  setStepState(stepParse, hasParseError ? "error" : hasParsed ? "done" : latestBatchId ? "active" : "");
  setStepState(stepInvite, hasInviteError ? "error" : hasInvite ? "done" : hasParsed ? "active" : "");

  if (status === "completed") {
    progressTitle.textContent = "Processing complete";
    resultBadge.textContent = "Complete";
    setProcess(100, "All available candidate details are ready.");
  } else if (status === "completed_with_errors") {
    progressTitle.textContent = "Completed with attention needed";
    resultBadge.textContent = "Review";
    setProcess(100, "Some resumes need a quick review.");
  } else if (status === "failed") {
    progressTitle.textContent = "Processing failed";
    resultBadge.textContent = "Failed";
    setProcess(100, "Something stopped the upload from completing.");
  } else if (status === "processing") {
    progressTitle.textContent = "Processing resumes";
    resultBadge.textContent = "Processing";
    setProcess(hasInvite ? 88 : hasParsed ? 68 : 46, "Extracting candidate details and preparing invitations.");
  } else if (status === "pending" || status === "queued") {
    progressTitle.textContent = "Upload received";
    resultBadge.textContent = "Received";
    setProcess(26, "Files received. Processing will begin automatically.");
  }
}

function renderFileRows(container) {
  container.innerHTML = "";
  if (selectedFiles.length === 0) {
    container.textContent = "No resumes selected yet.";
    return;
  }

  selectedFiles.forEach((file, index) => {
    const row = document.createElement("div");
    row.className = "file-item";
    row.style.animationDelay = `${index * 35}ms`;

    const name = document.createElement("span");
    name.className = "file-name";
    name.title = file.name;
    name.textContent = file.name;

    const remove = document.createElement("button");
    remove.className = "remove-file";
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderFiles();
    });

    row.append(name, remove);
    container.appendChild(row);
  });
}

function renderFiles() {
  fileCount.textContent = selectedFiles.length.toString();
  uploadButton.disabled = selectedFiles.length === 0;
  dropTitle.textContent = selectedFiles.length ? "Ready when you are" : "Drop resumes here";
  dropHint.textContent = selectedFiles.length
    ? `${selectedFiles.length} PDF ${selectedFiles.length === 1 ? "resume" : "resumes"} selected.`
    : "Only PDF files are accepted.";
  renderFileRows(fileList);

  studentFileCount.textContent = selectedFiles.length.toString();
  studentUploadButton.disabled = selectedFiles.length === 0;
  studentSelectedFiles.classList.toggle("hidden", selectedFiles.length === 0);
  studentDropTitle.textContent = selectedFiles.length
    ? `${selectedFiles.length} PDF ${selectedFiles.length === 1 ? "resume" : "resumes"} selected`
    : "Drag & drop PDF resumes here";
  studentDropHint.textContent = selectedFiles.length
    ? "Ready to upload and process."
    : "Invalid name/email entries are marked failed automatically.";
  renderFileRows(studentFileList);
}

function addFiles(files) {
  const incoming = Array.from(files);
  const pdfs = incoming.filter(
    (file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"),
  );
  const rejected = incoming.length - pdfs.length;
  const knownFiles = new Set(selectedFiles.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
  const newFiles = pdfs.filter((file) => !knownFiles.has(`${file.name}-${file.size}-${file.lastModified}`));
  selectedFiles = [...selectedFiles, ...newFiles];
  renderFiles();
  if (rejected > 0) showToast(`${rejected} non-PDF file ignored.`);
  if (newFiles.length > 0) showToast(`${newFiles.length} PDF ${newFiles.length === 1 ? "added" : "added"}.`);
}

function renderDashboard(result = {}) {
  latestBatchResult = result;
  latestBatchStats = deriveBatchStats(result, selectedFiles.length);
  dashboardPageController.render(result, latestBatchStats);
  studentsPageController.render(latestBatchStats);
}

function renderBatchSummary(result) {
  batchSummary.classList.add("visible");
  renderDashboard(result);
  batchSummary.innerHTML = `
    <div class="batch-tile">
      <span>Status</span>
      <strong>${friendlyStatus(result.status)}</strong>
    </div>
    <div class="batch-tile">
      <span>Total</span>
      <strong>${result.total_files ?? selectedFiles.length}</strong>
    </div>
    <div class="batch-tile">
      <span>Parsed</span>
      <strong>${result.parsed_count ?? 0}</strong>
    </div>
    <div class="batch-tile">
      <span>Needs Review</span>
      <strong>${result.failed_count ?? 0}</strong>
    </div>
  `;
}

function renderFriendlyResults(result) {
  const items = result.items || [];
  if (items.length === 0) {
    friendlyResults.textContent = "Waiting for resume processing to begin.";
    return;
  }

  friendlyResults.innerHTML = `
    <div class="result-list">
      ${items
        .map((item) => {
          const name = item.extracted_full_name || "Candidate";
          const email = item.extracted_email || "Email pending";
          const inviteStatus = item.invite_status || "not_attempted";
          const parseStatus = item.parse_status || "pending";
          const error = item.parse_error_message || item.invite_error_message || "";
          return `
            <article class="result-card">
              <strong>${escapeHtml(name)}</strong>
              <div>${escapeHtml(email)}</div>
              <div class="result-meta">
                <span class="pill ${pillClass(parseStatus)}">Resume ${friendlyStatus(parseStatus).toLowerCase()}</span>
                <span class="pill ${pillClass(inviteStatus)}">Invite ${friendlyStatus(inviteStatus).toLowerCase()}</span>
                ${item.clerk_invitation_id ? `<span class="pill good">${escapeHtml(item.clerk_invitation_id)}</span>` : ""}
              </div>
              ${error ? `<div class="pill bad">${escapeHtml(error)}</div>` : ""}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function stopMonitoring() {
  if (monitorTimer) {
    window.clearInterval(monitorTimer);
    monitorTimer = null;
  }
  document.body.classList.remove("is-monitoring");
}

async function uploadFiles() {
  if (selectedFiles.length === 0) {
    showToast("Choose at least one PDF resume.");
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files", file));

  uploadButton.disabled = true;
  uploadButton.textContent = "Uploading...";
  studentUploadButton.disabled = true;
  studentUploadButton.textContent = "Processing...";
  progressTitle.textContent = "Uploading resumes";
  resultBadge.textContent = "Uploading";
  studentProgressWrap.classList.remove("hidden");
  setProcess(12, "Sending files securely.");
  renderDashboard({
    status: "queued",
    total_files: selectedFiles.length,
    items: selectedFiles.map((file) => ({
      file_name: file.name,
      parse_status: "pending",
      invite_status: "not_attempted",
    })),
  });
  setStepState(stepUpload, "active");
  setStepState(stepParse, "");
  setStepState(stepInvite, "");
  friendlyResults.textContent = "Uploading selected files.";
  stopMonitoring();
  document.body.classList.add("is-monitoring");

  try {
    const response = await fetch(`${API_URL}/admin/resumes/bulk-upload`, {
      method: "POST",
      headers: await requestHeaders(),
      body: formData,
    });

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || `Upload failed with HTTP ${response.status}`);
    }

    latestBatchId = body.batch_id || "";
    renderBatchSummary(body);
    setProgressState(body.status, body.items || []);
    friendlyResults.textContent = "Files received. Processing will update automatically.";
    showToast("Upload received. Monitoring progress.");
    if (latestBatchId) startMonitoring();
  } catch (error) {
    resultBadge.textContent = "Failed";
    progressTitle.textContent = "Upload failed";
    friendlyResults.textContent = error.message;
    setProcess(100, "Upload failed. Please try again.");
    setStepState(stepUpload, "error");
    document.body.classList.remove("is-monitoring");
    showToast(error.message);
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "Upload Resumes";
    studentUploadButton.disabled = selectedFiles.length === 0;
    studentUploadButton.textContent = "Upload & Process";
    renderFiles();
  }
}

async function refreshBatchResult() {
  if (!latestBatchId) return;

  try {
    const response = await fetch(`${API_URL}/admin/resumes/batches/${latestBatchId}`, {
      headers: await requestHeaders(),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || `Status check failed with HTTP ${response.status}`);
    }

    renderBatchSummary(body);
    renderFriendlyResults(body);
    setProgressState(body.status, body.items || []);

    if (TERMINAL_STATUSES.has(body.status)) {
      stopMonitoring();
      if (body.status === "completed") {
        showToast("Processing complete.");
      }
    }
  } catch (error) {
    friendlyResults.textContent = `Still checking status. ${error.message}`;
  }
}

function startMonitoring() {
  stopMonitoring();
  document.body.classList.add("is-monitoring");
  refreshBatchResult();
  monitorTimer = window.setInterval(refreshBatchResult, 3000);
}

browseButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (event) => addFiles(event.target.files));
uploadButton.addEventListener("click", uploadFiles);
studentToggleUploadButton.addEventListener("click", () => {
  const isHidden = studentUploadSection.classList.toggle("hidden");
  studentToggleUploadButton.textContent = isHidden ? "Upload Resumes" : "Hide Upload";
});
studentBrowseButton.addEventListener("click", () => studentFileInput.click());
studentFileInput.addEventListener("change", (event) => addFiles(event.target.files));
studentUploadButton.addEventListener("click", uploadFiles);
studentClearFilesButton.addEventListener("click", () => {
  selectedFiles = [];
  fileInput.value = "";
  studentFileInput.value = "";
  studentProgressWrap.classList.add("hidden");
  renderFiles();
});
dashboardNavButton.addEventListener("click", () => {
  document.body.classList.remove("students-active");
  dashboardPage.classList.remove("hidden");
  studentsPage.classList.add("hidden");
  dashboardNavButton.classList.add("active");
  studentsNavButton.classList.remove("active");
});
studentsNavButton.addEventListener("click", () => {
  document.body.classList.add("students-active");
  dashboardPage.classList.add("hidden");
  studentsPage.classList.remove("hidden");
  dashboardNavButton.classList.remove("active");
  studentsNavButton.classList.add("active");
});
exportCsvButton.addEventListener("click", studentsPageController.exportCsv);
async function refreshLatestBatch() {
  if (!latestBatchId) {
    renderDashboard();
    showToast("No latest batch to refresh yet.");
    return;
  }

  await refreshBatchResult();
}
refreshDashboardButton.addEventListener("click", async () => {
  refreshDashboardButton.disabled = true;
  try {
    await refreshLatestBatch();
    showToast("Dashboard refreshed.");
  } finally {
    refreshDashboardButton.disabled = false;
  }
});
refreshTableButton.addEventListener("click", async () => {
  refreshTableButton.disabled = true;
  try {
    await refreshLatestBatch();
    showToast("Student table refreshed.");
  } finally {
    refreshTableButton.disabled = false;
  }
});
sourceViewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    sourceViewButtons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
  });
});
studentsPageController.bindEvents({
  renderAll: () => renderDashboard(latestBatchResult || {}),
});
localDevButton.addEventListener("click", continueAsLocalAdmin);

function resetSignedInUi() {
  currentAdmin = null;
  authMode = "pending";
  adminIdentity.innerHTML = "";
  userButton.innerHTML = "";
  topbarUserInitial.textContent = "A";
  topbarUserName.textContent = "Admin";
  topbarUserEmail.textContent = "admin@growqr.ai";
  sidebarUserInitial.textContent = "A";
  sidebarUserName.textContent = "Admin";
  sidebarUserEmail.textContent = "admin@growqr.ai";
  onboardingShell.classList.add("hidden");
  signOutButton.classList.add("hidden");
}

authSignOutButton.addEventListener("click", async () => {
  authSignOutButton.disabled = true;
  setAuthMessage("Signing out...");
  try {
    await window.Clerk?.signOut();
    resetSignedInUi();
    signInMount.innerHTML = "";
    authSignOutButton.classList.add("hidden");
    await initializeClerkAuth();
  } catch (error) {
    setAuthMessage(error.message || "Could not sign out.");
  } finally {
    authSignOutButton.disabled = false;
  }
});
positionGrid.addEventListener("click", (event) => {
  const tile = event.target.closest(".role-tile");
  if (!tile) return;
  selectPosition(tile.dataset.position || "");
});
adminOnboardingForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const fullName = adminFullNameInput.value.trim();
  const position = selectedPosition === "Other" ? customPositionInput.value.trim() : selectedPosition;
  if (!fullName) {
    showToast("Enter your full name.");
    adminFullNameInput.focus();
    return;
  }
  if (!position) {
    showToast("Choose your position.");
    return;
  }

  const profile = {
    fullName,
    position,
    department: adminDepartmentInput.value.trim(),
    phone: adminPhoneInput.value.trim(),
    completedAt: new Date().toISOString(),
  };
  window.localStorage.setItem(onboardingStorageKey(), JSON.stringify(profile));
  showToast("Profile setup complete.");
  showAppShell(currentAdmin);
});
signOutButton.addEventListener("click", () => {
  resetSignedInUi();
  showAuthShell();
  setAuthMessage("Signed out of local admin mode.");
});
sidebarLogoutButton.addEventListener("click", async () => {
  if (authMode === "clerk" && window.Clerk?.signOut) {
    await window.Clerk.signOut();
    signInMount.innerHTML = "";
    authSignOutButton.classList.add("hidden");
    resetSignedInUi();
    showAuthShell();
    await initializeClerkAuth();
    return;
  }
  resetSignedInUi();
  showAuthShell();
  setAuthMessage("Signed out of local admin mode.");
});
clearButton.addEventListener("click", () => {
  selectedFiles = [];
  latestBatchId = "";
  latestBatchResult = null;
  studentsPageController.clearSelection();
  stopMonitoring();
  fileInput.value = "";
  studentFileInput.value = "";
  studentProgressWrap.classList.add("hidden");
  studentsPageController.resetFilters();
  progressTitle.textContent = "Ready for upload";
  resultBadge.textContent = "Idle";
  setProcess(0, "Waiting for resumes.");
  friendlyResults.textContent = "No upload started yet.";
  batchSummary.classList.remove("visible");
  batchSummary.innerHTML = "";
  renderDashboard();
  setStepState(stepUpload, "");
  setStepState(stepParse, "");
  setStepState(stepInvite, "");
  renderFiles();
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});

dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  addFiles(event.dataTransfer.files);
});

studentDropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  studentDropZone.classList.add("dragging");
});

studentDropZone.addEventListener("dragleave", () => studentDropZone.classList.remove("dragging"));

studentDropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  studentDropZone.classList.remove("dragging");
  addFiles(event.dataTransfer.files);
});

function init() {
  renderFiles();
  renderDashboard();
  renderTopbarDate();
  window.setInterval(renderTopbarDate, 1000);
  showAuthShell();
  initializeClerkAuth();
}

return { init };
}
