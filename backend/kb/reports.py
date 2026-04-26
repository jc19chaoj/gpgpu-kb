# kb/reports.py
"""Generate a daily research report."""
import datetime
import logging

from kb.database import SessionLocal
from kb.models import Paper, DailyReport
from kb.processing.llm import call_llm
from kb.config import settings

logger = logging.getLogger(__name__)


def generate_daily_report(date: datetime.date | None = None) -> DailyReport:
    """Generate a report for the given date (default: yesterday).

    If a report already exists for that date, it is updated in place rather
    than failing on the unique constraint.
    """
    if date is None:
        date = datetime.date.today() - datetime.timedelta(days=1)

    start = datetime.datetime.combine(date, datetime.time.min, tzinfo=datetime.UTC)
    end = datetime.datetime.combine(date, datetime.time.max, tzinfo=datetime.UTC)

    db = SessionLocal()
    try:
        papers = db.query(Paper).filter(
            Paper.ingested_date >= start,
            Paper.ingested_date <= end,
            Paper.is_processed == 1,
        ).order_by(Paper.impact_score.desc()).all()

        if not papers:
            papers = db.query(Paper).filter(
                Paper.is_processed == 1,
            ).order_by(Paper.ingested_date.desc()).limit(20).all()

        existing = db.query(DailyReport).filter(DailyReport.date == start).first()

        if not papers:
            content = (
                f"{date.isoformat()} 无新论文入库，请检查采集流水线。"
                if settings.language == "zh"
                else f"No new papers were ingested on {date.isoformat()}. Check the ingestion pipeline."
            )
            report = _upsert_report(db, existing, start, date, content, [])
            return report

        paper_summaries = []
        for p in papers[:15]:
            paper_summaries.append(
                f"### {p.title}\n"
                f"*Authors:* {', '.join((p.authors or [])[:5])}\n"
                f"*Type:* {p.source_type} | *Source:* {p.source_name}\n"
                f"*Originality:* {p.originality_score:.1f}/10 | *Impact:* {p.impact_score:.1f}/10\n"
                f"*Summary:* {(p.summary or '')[:500]}\n"
            )

        context = "\n\n".join(paper_summaries)

        prompt = f"""You are an expert GPGPU chip architect writing a daily research briefing.

DATE: {date.isoformat()}

Below are the top papers and articles from today. Write a comprehensive daily report in Markdown format with the following sections:

1. **Executive Summary** — 2-3 sentences on the most important developments
2. **Top Papers** — The 3-5 most impactful papers with 2-3 sentence descriptions each
3. **Key Themes** — What patterns or trends do you see across today's research?
4. **Hidden Gems** — 1-2 papers that scored lower on impact but are actually quite interesting or original
5. **Recommended Reading** — Which 2-3 papers should be read in full today?

PAPERS:
{context}

Write a professional, technical report. No fluff. Keep it concise but informative."""

        if settings.language == "zh":
            prompt += (
                "\n\nIMPORTANT: Write the entire report in Chinese (简体中文). "
                "Use the following Chinese section names instead of the English ones above:\n"
                "1. **概要** (Executive Summary)\n"
                "2. **重点论文** (Top Papers)\n"
                "3. **主题趋势** (Key Themes)\n"
                "4. **潜力之作** (Hidden Gems)\n"
                "5. **推荐阅读** (Recommended Reading)"
            )

        content = call_llm(prompt) or "(LLM produced no output)"
        report = _upsert_report(
            db, existing, start, date, content, [p.id for p in papers[:15]]
        )
        logger.info("[reports] Generated report for %s: %d papers covered", date.isoformat(), len(papers))
        return report
    finally:
        db.close()


def _upsert_report(
    db,
    existing: DailyReport | None,
    start: datetime.datetime,
    date: datetime.date,
    content: str,
    paper_ids: list[int],
) -> DailyReport:
    title = (
        f"每日研究简报 — {date.isoformat()}"
        if settings.language == "zh"
        else f"Daily Research Report — {date.isoformat()}"
    )
    if existing is not None:
        existing.title = title
        existing.content = content
        existing.paper_ids = paper_ids
        existing.generated_date = datetime.datetime.now(datetime.UTC)
        db.commit()
        db.refresh(existing)
        return existing

    report = DailyReport(date=start, title=title, content=content, paper_ids=paper_ids)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    generate_daily_report()
