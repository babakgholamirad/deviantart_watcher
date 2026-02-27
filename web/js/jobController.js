/*
Module: jobController.js

Variables tracked internally:
- `activeJob`: latest server-side `/api/job/status` snapshot.
- `jobPollTimer`: interval timer id for periodic status refresh.
- `transientLoadingCount`: number of short UI actions currently in progress.
- `startRequestInFlight`: whether `/api/run` request itself is in progress.
- `lastFinishedJobIdShown`: prevents duplicate completion messages.

How this module works:
1. Keeps spinner/start-button state consistent while allowing non-start actions.
2. Polls job status so running/completed state survives page refresh.
3. Emits status text and optional completion callback when jobs finish.
*/

export function createJobController({
  startButton,
  spinner,
  statusText,
  fetchJobStatus,
  onJobFinished,
}) {
  let activeJob = null;
  let jobPollTimer = null;
  let transientLoadingCount = 0;
  let startRequestInFlight = false;
  let lastFinishedJobIdShown = 0;

  function normalizeJob(rawJob) {
    if (!rawJob || typeof rawJob !== "object") {
      return null;
    }
    return rawJob;
  }

  function refreshLoadingUi() {
    const jobRunning = Boolean(activeJob && activeJob.running);
    const hasTransientLoading = transientLoadingCount > 0;
    const shouldShowSpinner = jobRunning || startRequestInFlight || hasTransientLoading;

    startButton.disabled = jobRunning || startRequestInFlight;
    spinner.classList.toggle("show", shouldShowSpinner);
  }

  function setActiveJob(job) {
    activeJob = normalizeJob(job);
    refreshLoadingUi();
  }

  function setTransientLoading(isLoading) {
    if (isLoading) {
      transientLoadingCount += 1;
    } else {
      transientLoadingCount = Math.max(0, transientLoadingCount - 1);
    }
    refreshLoadingUi();
  }

  function setStartRequestLoading(isLoading) {
    startRequestInFlight = Boolean(isLoading);
    refreshLoadingUi();
  }

  function setStatus(message, type = "") {
    statusText.textContent = message;
    statusText.classList.remove("error", "success");
    if (type) {
      statusText.classList.add(type);
    }
  }

  function formatJobStats(job) {
    const stats = job && typeof job.stats === "object" ? job.stats : {};
    const downloaded = Number(stats.downloaded ?? 0);
    const newItems = Number(stats.new_items ?? 0);
    const skipped = Number(stats.skipped ?? 0);
    return `downloaded=${downloaded}, new=${newItems}, skipped=${skipped}`;
  }

  function formatJobPageRange(job) {
    const pagination = job && typeof job.pagination === "object" ? job.pagination : {};
    const start = pagination.start_page;
    const end = pagination.end_page;
    if (Number.isInteger(start) && Number.isInteger(end)) {
      return `pages=${start}-${end}`;
    }
    return "";
  }

  function formatRunningUsers(job) {
    const usernames = Array.isArray(job?.requested_usernames)
      ? job.requested_usernames.filter((item) => typeof item === "string" && item.trim())
      : [];
    if (!usernames.length) {
      return "";
    }
    return usernames.map((name) => `@${name}`).join(", ");
  }

  function buildRunningJobMessage(job) {
    const usersText = formatRunningUsers(job);
    const pagesText = formatJobPageRange(job);
    const segments = [];

    if (usersText) {
      segments.push(`targets: ${usersText}`);
    }
    if (pagesText) {
      segments.push(pagesText);
    }

    return segments.length
      ? `Download is running (${segments.join(" | ")}).`
      : "Download is running.";
  }

  function buildFinishedJobMessage(job) {
    const statsText = formatJobStats(job);
    const pagesText = formatJobPageRange(job);
    const sections = [statsText];
    if (pagesText) {
      sections.push(pagesText);
    }

    if (job && job.ok === false) {
      const firstError = Array.isArray(job.errors) && job.errors.length ? String(job.errors[0]) : "";
      if (firstError) {
        return `Download completed with errors. ${sections.join(", ")}. ${firstError}`;
      }
      return `Download completed with errors. ${sections.join(", ")}.`;
    }

    return `Download completed. ${sections.join(", ")}.`;
  }

  function stopPolling() {
    if (!jobPollTimer) {
      return;
    }
    window.clearInterval(jobPollTimer);
    jobPollTimer = null;
  }

  function startPolling() {
    if (jobPollTimer) {
      return;
    }

    jobPollTimer = window.setInterval(async () => {
      await syncStatus({ refreshGalleryOnFinish: true, allowFinishedStatus: true });
    }, 1400);
  }

  async function syncStatus(options = {}) {
    const refreshGalleryOnFinish = options.refreshGalleryOnFinish !== false;
    const allowFinishedStatus = options.allowFinishedStatus !== false;
    const forceFinishedStatus = Boolean(options.forceFinishedStatus);

    try {
      const rawJob = await fetchJobStatus();
      const job = normalizeJob(rawJob);
      if (!job) {
        return null;
      }

      const previousJob = activeJob;
      const previousRunning = Boolean(previousJob && previousJob.running);
      const previousJobId = Number(previousJob?.job_id ?? 0);

      setActiveJob(job);

      if (job.running) {
        startPolling();
        setStatus(buildRunningJobMessage(job), "");
        return job;
      }

      stopPolling();

      const jobId = Number(job.job_id ?? 0);
      const becameFinished = previousRunning && jobId > 0;
      const unseenFinishedJob = jobId > lastFinishedJobIdShown && !previousRunning && previousJobId !== 0;

      if (allowFinishedStatus && (forceFinishedStatus || becameFinished || unseenFinishedJob)) {
        lastFinishedJobIdShown = Math.max(lastFinishedJobIdShown, jobId);
        setStatus(buildFinishedJobMessage(job), job.ok === false ? "error" : "success");
        if (refreshGalleryOnFinish && typeof onJobFinished === "function") {
          await onJobFinished(job);
        }
      }

      return job;
    } catch (_error) {
      return null;
    }
  }

  function onJobStarted(job) {
    const normalized = normalizeJob(job);
    setActiveJob(normalized);
    if (normalized) {
      startPolling();
      setStatus(buildRunningJobMessage(normalized), "");
    } else {
      setStatus("Download job started.", "success");
    }
  }

  function onRunConflict(job, fallbackMessage) {
    const normalized = normalizeJob(job);
    setActiveJob(normalized);

    if (normalized && normalized.running) {
      startPolling();
      setStatus(buildRunningJobMessage(normalized), "");
      return;
    }

    setStatus(fallbackMessage || "A download job is already running.", "error");
  }

  function getActiveJob() {
    return activeJob;
  }

  function dispose() {
    stopPolling();
  }

  return {
    setTransientLoading,
    setStartRequestLoading,
    setStatus,
    syncStatus,
    onJobStarted,
    onRunConflict,
    getActiveJob,
    dispose,
  };
}
