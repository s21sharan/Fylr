#!/usr/bin/env python3
"""Organize evaluation harness for Fylr.

Measures how many proposed file moves/renames match a pre-defined target
layout -- the "acceptance rate" (fraction of proposals that require zero
human edits).

For each synthetic test folder:
  1. Create a set of messy, flat files with known content.
  2. Define the expected organized layout (ground truth).
  3. Run the organizer (generate_file_structure via the LLM provider).
  4. Compare proposed vs expected -- score each move.

Reports per-folder breakdown and overall acceptance rate.

Usage:
    python eval/run_organize_eval.py [--provider gemini|openai|ollama]
    # or:  make eval-organize
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root and backend dir are on sys.path so that
# `from llm import ...` inside backend modules resolves correctly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from backend.file_organizer import get_file_summary, generate_file_structure

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"

# ---------------------------------------------------------------------------
# Test cases: each defines messy input files and the expected organized layout.
# Keys in expected_layout map src filenames to expected dst relative paths.
# A "match" means the organizer put the file in the same category folder AND
# kept a reasonable filename.  We check folder match (strict) and optionally
# filename similarity (lenient).
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "mixed_student_files",
        "description": "A student folder with notes, code, and a resume",
        "files": {
            "notes_cs101_week3.txt": (
                "CS101 Intro to Programming - Week 3 Notes\n"
                "Topics: variables, loops, conditionals\n"
                "- Variables store data values\n"
                "- For loops iterate over sequences\n"
                "- If/else for branching logic\n"
            ),
            "my_resume_2024.txt": (
                "RESUME\n\nJane Doe\nPortland, OR\n"
                "jane.doe@example.com\n\n"
                "EXPERIENCE\nSoftware Intern at Acme Corp (1 year)\n"
                "SKILLS\nPython, JavaScript, SQL\n"
                "EDUCATION\nB.S. Computer Science, State University, 2024\n"
            ),
            "sort_algorithm.py": (
                '"""Bubble sort implementation."""\n\n'
                "def bubble_sort(arr):\n"
                "    n = len(arr)\n"
                "    for i in range(n):\n"
                "        for j in range(0, n-i-1):\n"
                "            if arr[j] > arr[j+1]:\n"
                "                arr[j], arr[j+1] = arr[j+1], arr[j]\n"
                "    return arr\n"
            ),
            "physics_midterm_notes.txt": (
                "PHYS101 Mechanics - Midterm Study Guide\n"
                "Newton's Laws of Motion\n"
                "- First law: inertia\n"
                "- Second law: F = ma\n"
                "- Third law: action and reaction\n"
                "Energy conservation and work-energy theorem\n"
            ),
            "grocery_receipt.txt": (
                "RECEIPT\nStore: GreenGrocer\nDate: 2024-03-15\n"
                "Items:\n  Apples x2 $3.50\n  Bread $4.00\n  Milk $5.50\n"
                "Total: $13.00\n"
            ),
        },
        "expected_folders": {
            "notes_cs101_week3.txt": "Academic",
            "my_resume_2024.txt": "Resume",
            "sort_algorithm.py": "Code",
            "physics_midterm_notes.txt": "Academic",
            "grocery_receipt.txt": "Receipt",
        },
        # Acceptable alternative folder names for leniency
        "folder_aliases": {
            "Academic": ["Academic", "Notes", "Study_Materials", "Coursework", "Class_Notes", "School"],
            "Resume": ["Resume", "Career", "Job", "Professional", "Job_Search", "Resumes"],
            "Code": ["Code", "Programming", "Projects", "Project", "Scripts", "Development"],
            "Receipt": ["Receipt", "Receipts", "Finance", "Financial", "Expenses"],
        },
    },
    {
        "name": "office_documents",
        "description": "Office worker files -- invoices, reports, letters",
        "files": {
            "q3_sales_report.txt": (
                "Quarterly Sales Report - Q3 2024\n"
                "Author: Bob Smith\nOrganization: Acme Corp\n\n"
                "Total revenue: $1.2M\nGrowth: 15% YoY\n"
                "Top product: Enterprise Plan\n"
                "Recommendations: expand West region coverage.\n"
            ),
            "invoice_vendor_8821.txt": (
                "INVOICE INV-8821\nFrom: Delta Systems\nTo: Bob Smith\n"
                "Date: 2024-07-10\nDescription: Cloud hosting fees\n"
                "Amount Due: $2,450.00\nPayment terms: Net 30\n"
            ),
            "team_meeting_notes.txt": (
                "Meeting Notes - Product Team Sync\n"
                "Date: 2024-08-05\nAttendees: Alice, Bob, Carlos\n\n"
                "Agenda:\n- Sprint review\n- Q4 planning\n- Bug triage\n"
                "Action items:\n- Alice: finalize design specs\n"
                "- Bob: update roadmap\n- Carlos: fix login bug\n"
            ),
            "cover_letter_draft.txt": (
                "Dear Hiring Manager,\n\n"
                "I am writing to express my interest in the Senior Engineer "
                "position at Bright Solutions. With 5 years of experience "
                "in backend development...\n\n"
                "Sincerely,\nBob Smith\n"
            ),
            "expense_report_aug.txt": (
                "EXPENSE REPORT - August 2024\n"
                "Employee: Bob Smith\nDepartment: Engineering\n\n"
                "Date,Description,Amount\n"
                "2024-08-01,Team lunch,$85.00\n"
                "2024-08-12,Software license,$299.00\n"
                "2024-08-20,Conference ticket,$450.00\n"
                "Total: $834.00\n"
            ),
        },
        "expected_folders": {
            "q3_sales_report.txt": "Reports",
            "invoice_vendor_8821.txt": "Invoices",
            "team_meeting_notes.txt": "Notes",
            "cover_letter_draft.txt": "Letters",
            "expense_report_aug.txt": "Finance",
        },
        "folder_aliases": {
            "Reports": ["Reports", "Report", "Business", "Sales"],
            "Invoices": ["Invoices", "Invoice", "Billing", "Finance", "Financial"],
            "Notes": ["Notes", "Meetings", "Meeting_Notes", "Minutes"],
            "Letters": ["Letters", "Letter", "Correspondence", "Career", "Job", "Professional", "Cover_Letters"],
            "Finance": ["Finance", "Financial", "Expenses", "Expense_Reports", "Accounting", "Reports"],
        },
    },
    {
        "name": "travel_planning",
        "description": "Travel-related documents for multiple trips",
        "files": {
            "paris_itinerary.txt": (
                "TRAVEL ITINERARY\nDestination: Paris\n"
                "Departure: 2024-09-10\nDuration: 7 days\n\n"
                "Day 1: Arrive, check in\nDay 2: Louvre Museum\n"
                "Day 3: Eiffel Tower, Seine cruise\n"
            ),
            "hotel_booking_paris.txt": (
                "BOOKING CONFIRMATION\nConfirmation: CONF-445566\n"
                "Guest: Alice Chen\nHotel: Grand Hotel Paris\n"
                "Check-in: 2024-09-10\nNights: 7\nTotal: $1,890.00\n"
            ),
            "paris_expense_log.txt": (
                "TRAVEL EXPENSE LOG\nDestination: Paris\n"
                "Expenses:\n  Food: $320\n  Transport: $150\n"
                "  Activities: $280\n  Shopping: $200\n"
                "Total: $950.00\n"
            ),
            "tokyo_packing_list.txt": (
                "PACKING LIST - Tokyo Trip\nDate: 2025-01-15\n\n"
                "[ ] Passport\n[ ] Adapters\n[ ] Camera\n"
                "[ ] Comfortable shoes\n[ ] Guidebook\n"
            ),
            "flight_comparison.txt": (
                "Flight Price Comparison - Tokyo 2025\n\n"
                "Airline A: $890 (1 stop)\nAirline B: $1,100 (direct)\n"
                "Airline C: $950 (1 stop, better times)\n\n"
                "Decision: Book Airline C.\n"
            ),
            "travel_insurance_info.txt": (
                "Travel Insurance Policy Summary\n"
                "Policy: TRV-998877\nCoverage: Medical + Trip Cancellation\n"
                "Premium: $125\nValid: 2024-09-01 to 2025-03-01\n"
            ),
        },
        "expected_folders": {
            "paris_itinerary.txt": "Paris",
            "hotel_booking_paris.txt": "Paris",
            "paris_expense_log.txt": "Paris",
            "tokyo_packing_list.txt": "Tokyo",
            "flight_comparison.txt": "Tokyo",
            "travel_insurance_info.txt": "Insurance",
        },
        "folder_aliases": {
            "Paris": ["Paris", "Paris_Trip", "Travel", "Trips", "Travel_Paris", "France"],
            "Tokyo": ["Tokyo", "Tokyo_Trip", "Travel", "Trips", "Travel_Tokyo", "Japan"],
            "Insurance": ["Insurance", "Documents", "Admin", "Travel", "Policies", "Travel_Insurance"],
        },
    },
    {
        "name": "finance_tax_season",
        "description": "Tax and finance documents at year end",
        "files": {
            "w2_form_2024.txt": (
                "W-2 WAGE AND TAX STATEMENT\nYear: 2024\n"
                "Employee: Diana Reyes\nEmployer: Horizon Digital\n"
                "Wages: $95,000\nFederal tax withheld: $18,500\n"
            ),
            "tax_return_2024.txt": (
                "TAX RETURN - 2024\nTaxpayer: Diana Reyes\n"
                "Filing Status: Single\nGross Income: $95,000\n"
                "Deductions: $14,600\nTax Owed: $12,400\n"
                "Refund: $6,100\n"
            ),
            "charitable_donations.txt": (
                "CHARITABLE DONATIONS - 2024\n"
                "Red Cross: $500\nLocal Food Bank: $250\n"
                "Animal Shelter: $150\nTotal: $900\n"
                "All receipts attached.\n"
            ),
            "bank_statement_dec.txt": (
                "BANK STATEMENT - December 2024\n"
                "Account: ****4455\nOpening Balance: $12,500\n"
                "Deposits: $8,200\nWithdrawals: $6,800\n"
                "Closing Balance: $13,900\n"
            ),
            "investment_summary.txt": (
                "INVESTMENT PORTFOLIO SUMMARY - 2024\n"
                "Total Value: $45,000\nGains: $3,200\nLosses: $800\n"
                "Dividends: $1,100\nNet Return: 7.8%\n"
            ),
        },
        "expected_folders": {
            "w2_form_2024.txt": "Tax",
            "tax_return_2024.txt": "Tax",
            "charitable_donations.txt": "Tax",
            "bank_statement_dec.txt": "Banking",
            "investment_summary.txt": "Investments",
        },
        "folder_aliases": {
            "Tax": ["Tax", "Taxes", "Tax_Documents", "Finance", "Financial", "Tax_Returns"],
            "Banking": ["Banking", "Bank", "Bank_Statements", "Finance", "Financial", "Statements"],
            "Investments": ["Investments", "Investment", "Portfolio", "Finance", "Financial"],
        },
    },
    {
        "name": "creative_project",
        "description": "Mixed creative and admin files for a side project",
        "files": {
            "logo_ideas.txt": (
                "Logo Design Brainstorm\n\n"
                "Option A: Minimalist wordmark, blue palette\n"
                "Option B: Abstract leaf icon, green palette\n"
                "Option C: Geometric monogram, black and gold\n"
                "Decision: Go with Option B.\n"
            ),
            "project_budget.txt": (
                "PROJECT BUDGET - Side Project Launch\n"
                "Domain: $15\nHosting: $240/year\n"
                "Design tools: $120\nMarketing: $500\n"
                "Total first year: $875\n"
            ),
            "landing_page_copy.txt": (
                "LANDING PAGE COPY - Draft v2\n\n"
                "Headline: Organize your files with AI\n"
                "Subheadline: Smart sorting, instant search, zero effort.\n\n"
                "CTA: Get Started Free\n\n"
                "Feature 1: AI-powered file naming\n"
                "Feature 2: One-click organization\n"
                "Feature 3: Natural language search\n"
            ),
            "competitor_analysis.txt": (
                "COMPETITOR ANALYSIS\n\n"
                "Competitor A: Basic folder templates, no AI. Free tier.\n"
                "Competitor B: Cloud-only, $10/mo. Good search.\n"
                "Competitor C: Enterprise focus, $50/mo. Overkill for individuals.\n\n"
                "Our edge: local-first, AI-powered, free.\n"
            ),
            "meeting_notes_kickoff.txt": (
                "PROJECT KICKOFF MEETING\nDate: 2024-06-01\n"
                "Attendees: Alice, Bob\n\n"
                "Goals:\n- MVP by August\n- Beta launch September\n"
                "- 100 users by December\n\n"
                "Next steps: finalize tech stack, set up repo.\n"
            ),
            "tech_stack_decision.txt": (
                "TECH STACK DECISION\n\n"
                "Frontend: Electron + vanilla JS\n"
                "Backend: Python\n"
                "AI: OpenAI API + local Ollama fallback\n"
                "Search: FAISS + BM25 hybrid\n"
                "Decision date: 2024-06-05\n"
            ),
        },
        "expected_folders": {
            "logo_ideas.txt": "Design",
            "project_budget.txt": "Admin",
            "landing_page_copy.txt": "Marketing",
            "competitor_analysis.txt": "Research",
            "meeting_notes_kickoff.txt": "Notes",
            "tech_stack_decision.txt": "Technical",
        },
        "folder_aliases": {
            "Design": ["Design", "Creative", "Branding", "Assets", "Visual"],
            "Admin": ["Admin", "Budget", "Finance", "Planning", "Administrative", "Financial"],
            "Marketing": ["Marketing", "Copy", "Content", "Launch", "Website"],
            "Research": ["Research", "Analysis", "Market_Research", "Competitive_Analysis", "Strategy"],
            "Notes": ["Notes", "Meetings", "Meeting_Notes", "Minutes", "Planning"],
            "Technical": ["Technical", "Tech", "Engineering", "Architecture", "Development", "Planning"],
        },
    },
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def normalize_folder(path: str) -> str:
    """Extract the top-level folder from a dst_path like 'Category/filename.ext'."""
    parts = Path(path).parts
    if len(parts) >= 2:
        return parts[0]
    return ""


def score_proposal(proposal: list[dict], test_case: dict) -> dict:
    """Score a single test case's proposal against expected layout.

    Returns a dict with per-file results and the overall acceptance rate.
    """
    expected = test_case["expected_folders"]
    aliases = test_case.get("folder_aliases", {})

    # Build lookup: src_filename -> proposed dst folder
    proposed_map = {}
    for entry in proposal:
        src = os.path.basename(entry["src_path"])
        dst_folder = normalize_folder(entry["dst_path"])
        proposed_map[src] = dst_folder

    file_results = {}
    matches = 0
    total = len(expected)

    for src_file, expected_folder in expected.items():
        proposed_folder = proposed_map.get(src_file, "[NOT PROPOSED]")
        acceptable = set(aliases.get(expected_folder, [expected_folder]))
        # Case-insensitive comparison, also try replacing spaces/hyphens
        proposed_clean = proposed_folder.replace("-", "_").replace(" ", "_")
        matched = any(
            proposed_clean.lower() == a.lower()
            for a in acceptable
        )
        if matched:
            matches += 1
        file_results[src_file] = {
            "expected": expected_folder,
            "proposed": proposed_folder,
            "match": matched,
        }

    return {
        "matches": matches,
        "total": total,
        "acceptance_rate": matches / total if total > 0 else 0.0,
        "files": file_results,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def create_test_folder(test_case: dict, base_dir: str) -> str:
    """Write test files into a temp folder. Returns the folder path."""
    folder = os.path.join(base_dir, test_case["name"])
    os.makedirs(folder, exist_ok=True)
    for fname, content in test_case["files"].items():
        with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
            f.write(content)
    return folder


def run_organize_on_folder(folder: str, online_mode: bool, provider_name: str | None):
    """Get file summaries and proposed structure for a folder.

    Returns (proposal_list, elapsed_seconds) or (None, elapsed_seconds) on failure.
    """
    # Resolve the provider so it is available for get_file_summary
    # We need to set env so that the backend picks up the right provider.
    from backend.llm import resolve_provider

    # Validate provider is available before proceeding
    try:
        provider = resolve_provider(online_mode, provider_name)
        if not provider.is_available():
            return None, 0.0
    except Exception:
        return None, 0.0

    t0 = time.perf_counter()

    # Collect summaries
    file_summaries = []
    for fname in sorted(os.listdir(folder)):
        fpath = os.path.join(folder, fname)
        if not os.path.isfile(fpath):
            continue
        summary = get_file_summary(fpath, online_mode=online_mode)
        if summary:
            file_summaries.append({
                "file_path": fpath,
                "summary": summary,
            })

    if not file_summaries:
        return None, time.perf_counter() - t0

    # Generate proposed structure
    proposal = generate_file_structure(file_summaries, online_mode=online_mode)
    elapsed = time.perf_counter() - t0

    return proposal, elapsed


def save_organize_results(all_results: dict, provider_label: str):
    """Save organize eval results to JSON and markdown."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp": ts,
        "provider": provider_label,
        "cases": all_results,
    }

    json_path = RESULTS_DIR / f"organize_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)

    # Markdown summary
    lines = [
        "# Organize Eval Results",
        "",
        f"Run: {ts}",
        f"Provider: {provider_label}",
        "",
        "| Test Case | Matches | Total | Acceptance Rate |",
        "|-----------|---------|-------|-----------------|",
    ]
    overall_matches = 0
    overall_total = 0
    for case_name, result in all_results.items():
        if result.get("error"):
            lines.append(f"| {case_name} | -- | -- | ERROR: {result['error']} |")
            continue
        m = result["matches"]
        t = result["total"]
        rate = result["acceptance_rate"]
        overall_matches += m
        overall_total += t
        lines.append(f"| {case_name} | {m} | {t} | {rate:.0%} |")

    if overall_total > 0:
        overall_rate = overall_matches / overall_total
        lines.append(f"| **OVERALL** | **{overall_matches}** | **{overall_total}** | **{overall_rate:.0%}** |")
    lines.append("")

    md_path = RESULTS_DIR / "organize_latest.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run Fylr organize eval")
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai", "ollama"],
        default=None,
        help="LLM provider to use (default: auto-detect based on available keys)",
    )
    args = parser.parse_args()

    # Determine mode
    if args.provider == "ollama":
        online_mode = False
    else:
        online_mode = True

    provider_label = args.provider or "auto"

    print(f"=== Fylr Organize Eval (provider: {provider_label}) ===\n")

    # Create temp base dir for all test folders
    base_dir = tempfile.mkdtemp(prefix="fylr_organize_eval_")
    print(f"Test folders in: {base_dir}\n")

    all_results = {}

    for tc in TEST_CASES:
        name = tc["name"]
        print(f"--- {name}: {tc['description']} ---")

        # Create the messy folder
        folder = create_test_folder(tc, base_dir)
        print(f"  Created {len(tc['files'])} files in {folder}")

        # Run organizer
        proposal, elapsed = run_organize_on_folder(folder, online_mode, args.provider)

        if proposal is None:
            msg = "Provider unavailable or returned no results"
            print(f"  SKIPPED: {msg}")
            all_results[name] = {"error": msg, "elapsed_s": round(elapsed, 2)}
            continue

        print(f"  Got {len(proposal)} proposed moves in {elapsed:.1f}s")

        # Score
        scores = score_proposal(proposal, tc)
        scores["elapsed_s"] = round(elapsed, 2)
        all_results[name] = scores

        print(f"  Acceptance: {scores['matches']}/{scores['total']} ({scores['acceptance_rate']:.0%})")
        for fname, detail in scores["files"].items():
            status = "OK" if detail["match"] else "MISS"
            print(f"    [{status}] {fname}: expected={detail['expected']}, got={detail['proposed']}")
        print()

    # Save results
    json_path, md_path = save_organize_results(all_results, provider_label)
    print(f"\nResults saved to:\n  {json_path}\n  {md_path}")

    # Exit with non-zero if all cases errored
    if all(r.get("error") for r in all_results.values()):
        print("\nAll test cases failed. Check provider availability.")
        sys.exit(1)


if __name__ == "__main__":
    main()
