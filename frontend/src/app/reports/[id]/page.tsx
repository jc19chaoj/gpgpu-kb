"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getReport } from "@/lib/api";
import { DailyReport } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getReport(Number(id)).then(setReport).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-zinc-900" />
        <Skeleton className="h-96 w-full bg-zinc-900" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-16 text-zinc-500">
        <p>Report not found.</p>
        <Link href="/reports" className="text-sm text-emerald-400 hover:underline mt-2 inline-block">
          Back to reports
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link href="/reports" className="text-xs text-zinc-500 hover:text-zinc-300 mb-4 inline-block">
        ← Back to reports
      </Link>
      <div className="flex items-center gap-3 mb-6">
        <Calendar className="h-5 w-5 text-emerald-400" />
        <div>
          <h1 className="text-lg font-semibold">{report.title}</h1>
          <p className="text-sm text-zinc-500">
            {new Date(report.date).toLocaleDateString("en-US", {
              weekday: "long", year: "numeric", month: "long", day: "numeric",
            })}
          </p>
        </div>
      </div>
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-6">
          <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report.content}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
