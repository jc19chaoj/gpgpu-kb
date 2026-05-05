"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DailyConflictError,
  attachDailyStream,
  getDailyStatus,
  listReports,
  runDailyStream,
} from "@/lib/api";
import {
  DailyReport,
  DailyStageName,
  DailyStreamEvent,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  Calendar,
  Check,
  Loader2,
  Play,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/i18n/provider";
import { formatLongDate } from "@/lib/i18n/format";
import type { TranslationKey } from "@/lib/i18n/translations";

const STAGE_ORDER: DailyStageName[] = [
  "ingestion",
  "processing",
  "embedding",
  "report",
];

const STAGE_LABEL_KEY: Record<DailyStageName, TranslationKey> = {
  ingestion: "reports.run.stage.ingestion",
  processing: "reports.run.stage.processing",
  embedding: "reports.run.stage.embedding",
  report: "reports.run.stage.report",
};

// Cap the in-memory log buffer so a 100k-line cold-start run can't OOM the
// browser tab. The DOM-attached <ScrollArea> would also grind if this got
// too large; 2k is comfortable for hours of pipeline output.
const MAX_LOG_LINES = 2000;

type RunPhase = "idle" | "starting" | "running" | "done" | "error";

interface RunState {
  phase: RunPhase;
  startedAt: string | null;
  // Index of the latest stage that was emitted *or finished*. STAGE_ORDER[i]
  // for i < activeIndex are done, STAGE_ORDER[activeIndex] is running, the
  // rest pending. -1 means no stage seen yet.
  activeIndex: number;
  errorMessage: string | null;
  conflict: boolean;
}

const INITIAL_RUN_STATE: RunState = {
  phase: "idle",
  startedAt: null,
  activeIndex: -1,
  errorMessage: null,
  conflict: false,
};

export default function ReportsPage() {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const { locale, t } = useLocale();

  const [run, setRun] = useState<RunState>(INITIAL_RUN_STATE);
  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const logContainerRef = useRef<HTMLDivElement | null>(null);

  const appendLog = useCallback((line: string) => {
    setLogs((prev) => {
      const next = prev.length >= MAX_LOG_LINES
        ? prev.slice(prev.length - MAX_LOG_LINES + 1)
        : prev.slice();
      next.push(line);
      return next;
    });
  }, []);

  // Drains an SSE stream and applies each event to the run state. Returns
  // whether the stream ended on a terminal frame (vs a dropped connection).
  // Shared by mount-time reattach and the Run-Now button so they handle
  // events identically — the only thing that differs is which fetch the
  // generator wraps.
  const consumeAndApply = useCallback(async (
    stream: AsyncGenerator<DailyStreamEvent>,
    signal: AbortSignal,
  ): Promise<boolean> => {
    let sawTerminal = false;
    for await (const ev of stream) {
      if (signal.aborted) break;
      applyEvent(ev, { setRun, appendLog });
      if (ev.type === "done" || ev.type === "error") sawTerminal = true;
    }
    return sawTerminal;
  }, [appendLog]);

  // Initial load: fetch reports + reattach to an in-flight run if there
  // is one (page refresh / dropped network during a pipeline run). We
  // request a full replay (`since=-1`) so the buffered `started` /
  // `stage` / `log` events repopulate the UI before we tail live.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;

    listReports(30).then((rows) => {
      if (!cancelled) setReports(rows);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    (async () => {
      let status;
      try {
        status = await getDailyStatus();
      } catch {
        // Status endpoint failure (network / 401) is non-fatal — leave
        // the page in idle state so the report list is still usable.
        return;
      }
      if (cancelled || !status.running) return;

      const stageIdx = status.current_stage
        ? STAGE_ORDER.indexOf(status.current_stage)
        : -1;
      setRun({
        phase: "running",
        startedAt: status.started_at,
        activeIndex: stageIdx,
        errorMessage: null,
        conflict: false,
      });
      // Reset the local log buffer; the `since=-1` replay will refill it
      // with everything the in-flight run has emitted so far.
      setLogs([]);
      setShowLogs(true);

      try {
        const sawTerminal = await consumeAndApply(
          attachDailyStream({ since: -1, signal: controller.signal }),
          controller.signal,
        );
        if (cancelled) return;
        if (!sawTerminal) {
          setRun((prev) => prev.phase === "running" ? {
            ...prev,
            phase: "error",
            errorMessage: t("reports.run.connectionLost"),
          } : prev);
        } else {
          listReports(30).then(setReports).catch(() => { /* leave stale */ });
        }
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        if (cancelled) return;
        setRun((prev) => ({
          ...prev,
          phase: "error",
          errorMessage:
            (err instanceof Error && err.message)
              ? err.message
              : t("reports.run.failed"),
        }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    })();

    return () => {
      cancelled = true;
      // Drop the SSE connection on unmount. The pipeline keeps running
      // on the server; reopening /reports will detect it and reattach.
      abortRef.current?.abort();
    };
  }, [consumeAndApply, t]);

  // Auto-scroll logs to the bottom as new lines arrive. Set scrollTop on
  // the container directly instead of scrollIntoView, which would also
  // scroll every ancestor (including the page) to bring the sentinel into
  // view.
  useEffect(() => {
    if (!showLogs) return;
    const el = logContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs, showLogs]);

  const handleRun = useCallback(async () => {
    if (run.phase === "starting" || run.phase === "running") return;

    setRun({
      phase: "starting",
      startedAt: null,
      activeIndex: -1,
      errorMessage: null,
      conflict: false,
    });
    setLogs([]);
    setShowLogs(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let sawTerminal: boolean;
      try {
        sawTerminal = await consumeAndApply(
          runDailyStream({ signal: controller.signal }),
          controller.signal,
        );
      } catch (err) {
        if (err instanceof DailyConflictError) {
          // Another tab/client already started the run — reattach to it
          // instead of leaving the user with a dead-end error UI.
          setRun({
            phase: "running",
            startedAt: null,
            activeIndex: -1,
            errorMessage: null,
            conflict: false,
          });
          setLogs([]);
          sawTerminal = await consumeAndApply(
            attachDailyStream({ since: -1, signal: controller.signal }),
            controller.signal,
          );
        } else {
          throw err;
        }
      }

      if (!sawTerminal) {
        // Stream ended without `done`/`error` — connection dropped
        // mid-flight. The server-side run may still be live; a refresh
        // will reattach via the mount effect's status check.
        setRun((prev) => prev.phase === "running" ? {
          ...prev,
          phase: "error",
          errorMessage: t("reports.run.connectionLost"),
        } : prev);
      } else {
        listReports(30).then(setReports).catch(() => { /* leave stale */ });
      }
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") {
        // User-initiated cancel (component unmount). Don't flip to error.
        return;
      }
      setRun((prev) => ({
        ...prev,
        phase: "error",
        errorMessage:
          (err instanceof Error && err.message)
            ? err.message
            : t("reports.run.failed"),
      }));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [run.phase, t, consumeAndApply]);

  const startedRelative = run.startedAt ? formatRelativeTime(run.startedAt, locale) : null;
  const isBusy = run.phase === "starting" || run.phase === "running";
  const buttonDisabled = isBusy || run.conflict;

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h1 className="text-base sm:text-lg font-semibold">{t("reports.title")}</h1>
        <Button
          onClick={handleRun}
          disabled={buttonDisabled}
          size="sm"
          className="shrink-0"
          aria-busy={isBusy}
        >
          {isBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          <span>{isBusy ? t("reports.run.busy") : t("reports.run.button")}</span>
        </Button>
      </div>

      {(run.phase !== "idle" || run.conflict) && (
        <RunPanel
          run={run}
          logs={logs}
          showLogs={showLogs}
          onToggleLogs={() => setShowLogs((v) => !v)}
          onReload={() => {
            setLoading(true);
            listReports(30)
              .then(setReports)
              .finally(() => setLoading(false));
            setRun(INITIAL_RUN_STATE);
          }}
          startedRelative={startedRelative}
          logContainerRef={logContainerRef}
        />
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full bg-card" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((report) => (
            <Link key={report.id} href={`/reports/${report.id}`}>
              <Card className="bg-card border-border hover:border-primary/40 transition-colors cursor-pointer">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <Calendar className="h-4 w-4 text-primary shrink-0" />
                    <div>
                      <h3 className="text-sm font-medium">{report.title}</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {formatLongDate(report.date, locale)}
                        {" · "}
                        {t("reports.papersCovered", { count: report.paper_ids.length })}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
          {reports.length === 0 && (
            <p className="text-muted-foreground text-center py-12">{t("reports.empty")}</p>
          )}
        </div>
      )}
    </div>
  );
}

interface RunPanelProps {
  run: RunState;
  logs: string[];
  showLogs: boolean;
  onToggleLogs: () => void;
  onReload: () => void;
  startedRelative: string | null;
  logContainerRef: React.RefObject<HTMLDivElement | null>;
}

function RunPanel({
  run,
  logs,
  showLogs,
  onToggleLogs,
  onReload,
  startedRelative,
  logContainerRef,
}: RunPanelProps) {
  const { t } = useLocale();
  const isError = run.phase === "error";
  const isDone = run.phase === "done";

  return (
    <Card
      className={`bg-card mb-4 ${
        isError ? "border-red-500/40" : isDone ? "border-emerald-500/40" : "border-border"
      }`}
    >
      <CardContent className="p-4 space-y-3">
        {/* Header line: status + relative start time */}
        <div className="flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-muted-foreground min-w-0">
            {isError ? (
              <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
            ) : isDone ? (
              <Check className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            ) : (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
            )}
            <span className="truncate">
              {isError
                ? run.errorMessage || t("reports.run.failed")
                : isDone
                  ? t("reports.run.complete")
                  : run.conflict
                    ? t("reports.run.alreadyRunning")
                    : t("reports.run.busy")}
            </span>
          </div>
          {startedRelative && (
            <span className="text-muted-foreground shrink-0">
              {t("reports.run.startedAt", { when: startedRelative })}
            </span>
          )}
        </div>

        {/* Stage progress dots */}
        <ol className="flex items-center gap-1 sm:gap-2 text-[11px] sm:text-xs">
          {STAGE_ORDER.map((stage, idx) => (
            <StagePill
              key={stage}
              label={t(STAGE_LABEL_KEY[stage])}
              state={stageStateFor(idx, run)}
              showSeparator={idx < STAGE_ORDER.length - 1}
            />
          ))}
        </ol>

        {/* Logs toggle + content */}
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onToggleLogs}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showLogs ? t("reports.run.hideLogs") : t("reports.run.viewLogs")}
            {logs.length > 0 ? ` (${logs.length})` : ""}
          </button>
          {(isDone || isError) && (
            <Button
              onClick={onReload}
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
            >
              <RotateCcw className="h-3 w-3" />
              <span>{t("reports.run.reload")}</span>
            </Button>
          )}
        </div>

        {showLogs && (
          <div
            ref={logContainerRef}
            className="rounded border border-border bg-zinc-950/60 px-3 py-2 max-h-72 overflow-y-auto overscroll-contain"
          >
            {logs.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">
                {t("reports.run.logsEmpty")}
              </p>
            ) : (
              <pre className="text-[11px] sm:text-xs leading-relaxed font-mono whitespace-pre-wrap break-words text-zinc-300">
                {logs.join("\n")}
              </pre>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StagePill({
  label,
  state,
  showSeparator,
}: {
  label: string;
  state: "pending" | "running" | "done" | "error";
  showSeparator: boolean;
}) {
  const colorByState: Record<typeof state, string> = {
    pending: "bg-zinc-800 text-zinc-500 border-zinc-800",
    running: "bg-primary/15 text-primary border-primary/40",
    done: "bg-emerald-500/15 text-emerald-500 border-emerald-500/40",
    error: "bg-red-500/15 text-red-500 border-red-500/40",
  };
  return (
    <>
      <li
        className={`flex items-center gap-1 rounded border px-2 py-0.5 ${colorByState[state]}`}
        aria-current={state === "running" ? "step" : undefined}
      >
        {state === "done" && <Check className="h-3 w-3" />}
        {state === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
        {state === "error" && <AlertCircle className="h-3 w-3" />}
        <span className="truncate">{label}</span>
      </li>
      {showSeparator && <li aria-hidden className="text-zinc-700">·</li>}
    </>
  );
}

function stageStateFor(idx: number, run: RunState): "pending" | "running" | "done" | "error" {
  if (run.phase === "error") {
    if (idx < run.activeIndex) return "done";
    if (idx === run.activeIndex) return "error";
    return "pending";
  }
  if (run.phase === "done") return "done";
  // running / starting / conflict
  if (idx < run.activeIndex) return "done";
  if (idx === run.activeIndex) return "running";
  return "pending";
}

function applyEvent(
  ev: DailyStreamEvent,
  ctx: {
    setRun: React.Dispatch<React.SetStateAction<RunState>>;
    appendLog: (line: string) => void;
  },
) {
  switch (ev.type) {
    case "started":
      ctx.setRun((prev) => ({
        ...prev,
        phase: "running",
        startedAt: ev.started_at || prev.startedAt,
      }));
      return;
    case "stage": {
      const idx = STAGE_ORDER.indexOf(ev.name);
      ctx.setRun((prev) => ({
        ...prev,
        phase: "running",
        activeIndex: idx >= 0 ? idx : prev.activeIndex,
      }));
      return;
    }
    case "log":
      if (ev.line) ctx.appendLog(ev.line);
      return;
    case "error":
      ctx.setRun((prev) => ({
        ...prev,
        phase: "error",
        errorMessage: ev.message || "Pipeline failed",
      }));
      return;
    case "done":
      ctx.setRun((prev) => ({
        ...prev,
        phase: "done",
        // Mark all stages as done so the pills go fully green.
        activeIndex: STAGE_ORDER.length,
      }));
      return;
  }
}

// Minimal relative-time formatter. We only need 4 buckets; a full
// IntlRelativeTimeFormat per render would be overkill.
function formatRelativeTime(iso: string, locale: "en" | "zh"): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const deltaSec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (deltaSec < 30) return locale === "zh" ? "刚刚" : "just now";
  if (deltaSec < 3600) {
    const m = Math.round(deltaSec / 60);
    return locale === "zh" ? `${m} 分钟前` : `${m}m ago`;
  }
  if (deltaSec < 86_400) {
    const h = Math.round(deltaSec / 3600);
    return locale === "zh" ? `${h} 小时前` : `${h}h ago`;
  }
  const d = Math.round(deltaSec / 86_400);
  return locale === "zh" ? `${d} 天前` : `${d}d ago`;
}
