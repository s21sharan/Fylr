#!/usr/bin/env python3
"""Synthetic corpus generator for Fylr eval.

Produces ~200 deterministic fake files across realistic categories.
No personal or real data -- everything is synthetic.

Usage:
    python eval/build_corpus.py [target_dir]

Default target: eval/corpus/
"""

import argparse
import os
import random
import sys
from pathlib import Path

SEED = 42

# ---------------------------------------------------------------------------
# Name pools (all fake)
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Alice", "Bob", "Carlos", "Diana", "Elena", "Frank", "Grace", "Hiro",
    "Irene", "James", "Kira", "Leo", "Maya", "Noah", "Olga", "Priya",
    "Quinn", "Rafael", "Sara", "Tomas", "Uma", "Victor", "Wendy", "Xander",
    "Yuki", "Zara",
]
LAST_NAMES = [
    "Anderson", "Baker", "Chen", "Delgado", "Evans", "Fernandez", "Garcia",
    "Huang", "Ito", "Jensen", "Kim", "Larson", "Martinez", "Nguyen", "Olsen",
    "Patel", "Quinn", "Reyes", "Singh", "Torres", "Ueda", "Vasquez", "Wang",
    "Xu", "Yamada", "Zhang",
]
COMPANIES = [
    "Acme Corp", "Bright Solutions", "Cascade Labs", "Delta Systems",
    "Evergreen Inc", "Foxglove Tech", "Granite Works", "Horizon Digital",
    "Indigo Partners", "Jade Consulting",
]
CITIES = [
    "Portland", "Austin", "Denver", "Chicago", "Boston", "Seattle",
    "San Diego", "Nashville", "Minneapolis", "Raleigh",
]
STATES = [
    "OR", "TX", "CO", "IL", "MA", "WA", "CA", "TN", "MN", "NC",
]
COURSES = [
    "CS101 Intro to Programming", "CS201 Data Structures",
    "CS301 Algorithms", "CS401 Machine Learning",
    "MATH150 Linear Algebra", "MATH250 Probability",
    "PHYS101 Mechanics", "PHYS201 Electromagnetism",
    "ECON101 Microeconomics", "ECON201 Macroeconomics",
    "ENG101 Composition", "ENG201 Technical Writing",
    "BIO101 Cell Biology", "CHEM101 General Chemistry",
]
STORES = [
    "TechMart", "OfficeDepot Plus", "CloudBooks", "GreenGrocer",
    "AutoParts Central", "FitGear", "PetWorld", "HomeBase",
]
TRAVEL_DESTINATIONS = [
    "Tokyo", "Paris", "London", "Rome", "Barcelona",
    "Sydney", "Vancouver", "Berlin", "Seoul", "Lisbon",
]


def _rand_name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _rand_date(rng, year_range=(2022, 2025)):
    y = rng.randint(*year_range)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


def _rand_amount(rng, lo=5.0, hi=5000.0):
    return round(rng.uniform(lo, hi), 2)


def _rand_phone(rng):
    return f"({rng.randint(200,999)}) {rng.randint(200,999)}-{rng.randint(1000,9999)}"


# ---------------------------------------------------------------------------
# Category generators -- each returns (relative_path, content)
# ---------------------------------------------------------------------------

def gen_receipts(rng, count=25):
    files = []
    for i in range(count):
        store = rng.choice(STORES)
        date = _rand_date(rng)
        amount = _rand_amount(rng, 3.0, 500.0)
        items_count = rng.randint(1, 6)
        item_lines = []
        for _ in range(items_count):
            item_name = rng.choice([
                "USB-C Cable", "Notebook", "Pen Set", "Desk Lamp",
                "Mouse Pad", "Headphones", "Webcam", "Keyboard",
                "Monitor Stand", "Laptop Sleeve", "Printer Paper",
                "Binder Clips", "Sticky Notes", "Whiteboard Markers",
            ])
            qty = rng.randint(1, 3)
            price = _rand_amount(rng, 2.0, 120.0)
            item_lines.append(f"  {item_name} x{qty}  ${price:.2f}")
        items_text = "\n".join(item_lines)
        slug = store.lower().replace(" ", "_")
        fname = f"receipt_{slug}_{date}.txt"
        content = (
            f"RECEIPT\n"
            f"Store: {store}\n"
            f"Date: {date}\n"
            f"Transaction ID: TXN-{rng.randint(100000,999999)}\n\n"
            f"Items:\n{items_text}\n\n"
            f"Subtotal: ${amount:.2f}\n"
            f"Tax: ${amount * 0.08:.2f}\n"
            f"Total: ${amount * 1.08:.2f}\n"
            f"Payment: {'Credit Card' if rng.random() > 0.3 else 'Cash'}\n"
        )
        files.append((f"receipts/{fname}", content))
    return files


def gen_invoices(rng, count=20):
    files = []
    for i in range(count):
        company = rng.choice(COMPANIES)
        client = _rand_name(rng)
        date = _rand_date(rng)
        inv_num = f"INV-{rng.randint(1000,9999)}"
        amount = _rand_amount(rng, 500.0, 15000.0)
        desc = rng.choice([
            "Web development services", "Consulting hours",
            "Software license renewal", "Cloud hosting fees",
            "Design and branding package", "Data analysis project",
            "Security audit", "API integration work",
        ])
        slug = company.lower().replace(" ", "_")
        fname = f"invoice_{slug}_{inv_num}.txt"
        content = (
            f"INVOICE {inv_num}\n"
            f"From: {company}\n"
            f"To: {client}\n"
            f"Date: {date}\n"
            f"Due: Net 30\n\n"
            f"Description: {desc}\n"
            f"Hours: {rng.randint(10, 120)}\n"
            f"Rate: ${rng.randint(50, 200)}/hr\n"
            f"Amount Due: ${amount:.2f}\n\n"
            f"Payment terms: Wire transfer or check.\n"
            f"Contact: billing@{slug}.example.com\n"
        )
        files.append((f"invoices/{fname}", content))
    return files


def gen_class_notes(rng, count=30):
    files = []
    for i in range(count):
        course = rng.choice(COURSES)
        code = course.split()[0]
        date = _rand_date(rng)
        week = rng.randint(1, 15)
        topics = rng.sample([
            "sorting algorithms", "graph traversal", "dynamic programming",
            "linear regression", "matrix multiplication", "eigenvalues",
            "Newton's laws", "Ohm's law", "supply and demand",
            "market equilibrium", "thesis statements", "citation formats",
            "cell division", "chemical bonding", "recursion",
            "binary search trees", "hash tables", "neural networks",
            "gradient descent", "Bayes theorem",
        ], k=rng.randint(2, 4))
        topics_text = ", ".join(topics)
        notes_body = []
        for t in topics:
            notes_body.append(f"\n## {t.title()}\n")
            for _ in range(rng.randint(2, 5)):
                notes_body.append(f"- {_fake_sentence(rng)}")
        fname = f"{code}_week{week:02d}_{date}.md"
        content = (
            f"# {course} - Week {week} Notes\n"
            f"Date: {date}\n"
            f"Topics: {topics_text}\n"
            + "\n".join(notes_body) + "\n"
        )
        files.append((f"class_notes/{fname}", content))
    return files


def gen_resumes(rng, count=15):
    files = []
    for i in range(count):
        name = _rand_name(rng)
        city = rng.choice(CITIES)
        state = rng.choice(STATES)
        phone = _rand_phone(rng)
        email = name.lower().replace(" ", ".") + "@example.com"
        title = rng.choice([
            "Software Engineer", "Data Analyst", "Product Manager",
            "UX Designer", "DevOps Engineer", "Marketing Manager",
            "Financial Analyst", "Research Scientist",
        ])
        company = rng.choice(COMPANIES)
        years = rng.randint(1, 8)
        skills = rng.sample([
            "Python", "JavaScript", "SQL", "React", "AWS", "Docker",
            "Kubernetes", "TensorFlow", "Tableau", "Excel", "Figma",
            "Git", "REST APIs", "Agile", "Machine Learning",
        ], k=rng.randint(4, 8))
        slug = name.lower().replace(" ", "_")
        fname = f"resume_{slug}.txt"
        content = (
            f"RESUME\n\n"
            f"{name}\n"
            f"{city}, {state}\n"
            f"{phone} | {email}\n\n"
            f"EXPERIENCE\n"
            f"{title} at {company} ({years} years)\n"
            f"- Led cross-functional team on key deliverables\n"
            f"- Improved system performance by {rng.randint(10,60)}%\n"
            f"- Managed budget of ${rng.randint(50,500)}K\n\n"
            f"SKILLS\n"
            f"{', '.join(skills)}\n\n"
            f"EDUCATION\n"
            f"B.S. from State University, {rng.randint(2010,2023)}\n"
        )
        files.append((f"resumes/{fname}", content))
    return files


def gen_travel_docs(rng, count=20):
    files = []
    for i in range(count):
        dest = rng.choice(TRAVEL_DESTINATIONS)
        date = _rand_date(rng)
        traveler = _rand_name(rng)
        doc_type = rng.choice(["itinerary", "booking", "packing_list", "expense_log"])
        fname = f"{doc_type}_{dest.lower()}_{date}.txt"

        if doc_type == "itinerary":
            days = rng.randint(3, 10)
            day_lines = []
            for d in range(1, days + 1):
                activity = rng.choice([
                    "Visit museum", "Walking tour", "Local food tour",
                    "Day trip to countryside", "Shopping district",
                    "Historical site visit", "Beach day", "Hiking trail",
                ])
                day_lines.append(f"  Day {d}: {activity}")
            content = (
                f"TRAVEL ITINERARY\n"
                f"Traveler: {traveler}\n"
                f"Destination: {dest}\n"
                f"Departure: {date}\n"
                f"Duration: {days} days\n\n"
                + "\n".join(day_lines) + "\n"
            )
        elif doc_type == "booking":
            conf = f"CONF-{rng.randint(100000,999999)}"
            hotel = f"{rng.choice(['Grand', 'Royal', 'Park', 'City'])} Hotel {dest}"
            content = (
                f"BOOKING CONFIRMATION\n"
                f"Confirmation: {conf}\n"
                f"Guest: {traveler}\n"
                f"Hotel: {hotel}\n"
                f"Check-in: {date}\n"
                f"Nights: {rng.randint(2, 7)}\n"
                f"Room: {'Standard' if rng.random() > 0.5 else 'Deluxe'}\n"
                f"Total: ${_rand_amount(rng, 200, 2000):.2f}\n"
            )
        elif doc_type == "packing_list":
            items = rng.sample([
                "Passport", "Chargers", "Adapters", "Medications",
                "Sunscreen", "Umbrella", "Camera", "Guidebook",
                "Snacks", "Water bottle", "Jacket", "Comfortable shoes",
                "Toiletries", "First aid kit", "Travel pillow",
            ], k=rng.randint(6, 12))
            content = (
                f"PACKING LIST - {dest} Trip\n"
                f"Traveler: {traveler}\n"
                f"Date: {date}\n\n"
                + "\n".join(f"[ ] {item}" for item in items) + "\n"
            )
        else:  # expense_log
            expense_lines = []
            total = 0.0
            for _ in range(rng.randint(5, 15)):
                cat = rng.choice(["Food", "Transport", "Lodging", "Activities", "Shopping"])
                amt = _rand_amount(rng, 5, 300)
                total += amt
                expense_lines.append(f"  {cat}: ${amt:.2f}")
            content = (
                f"TRAVEL EXPENSE LOG\n"
                f"Traveler: {traveler}\n"
                f"Destination: {dest}\n"
                f"Trip Date: {date}\n\n"
                f"Expenses:\n"
                + "\n".join(expense_lines)
                + f"\n\nTotal: ${total:.2f}\n"
            )

        files.append((f"travel/{fname}", content))
    return files


def gen_code_files(rng, count=20):
    files = []
    templates = [
        (
            "sort_{alg}.py",
            '"""Implementation of {alg} sort."""\n\n'
            "def {alg}_sort(arr):\n"
            '    """Sort array using {alg} method."""\n'
            "    n = len(arr)\n"
            "    # {alg} sort logic\n"
            "    for i in range(n):\n"
            "        for j in range(0, n - i - 1):\n"
            "            if arr[j] > arr[j + 1]:\n"
            "                arr[j], arr[j + 1] = arr[j + 1], arr[j]\n"
            "    return arr\n"
        ),
        (
            "utils_{domain}.py",
            '"""Utility functions for {domain} processing."""\n\n'
            "import os\n"
            "import json\n\n\n"
            "def load_{domain}_config(path):\n"
            '    """Load {domain} config from JSON file."""\n'
            '    with open(path, "r") as f:\n'
            "        return json.load(f)\n\n\n"
            "def validate_{domain}_input(data):\n"
            '    """Validate {domain} input data."""\n'
            "    if not isinstance(data, dict):\n"
            '        raise ValueError("Expected dict")\n'
            "    return True\n"
        ),
        (
            "test_{module}.py",
            '"""Tests for {module} module."""\n\n'
            "import unittest\n\n\n"
            "class Test{Module}(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        self.data = [{sample_data}]\n\n"
            "    def test_basic(self):\n"
            "        self.assertTrue(len(self.data) > 0)\n\n"
            "    def test_empty(self):\n"
            "        self.assertEqual(len([]), 0)\n\n\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        ),
        (
            "api_{service}.py",
            '"""API client for {service} service."""\n\n'
            "import requests\n\n"
            "BASE_URL = \"https://api.{service}.example.com/v1\"\n\n\n"
            "def get_{service}_data(endpoint, params=None):\n"
            '    """Fetch data from {service} API."""\n'
            "    url = f\"{{BASE_URL}}/{{endpoint}}\"\n"
            "    response = requests.get(url, params=params)\n"
            "    response.raise_for_status()\n"
            "    return response.json()\n"
        ),
    ]
    algs = ["bubble", "merge", "quick", "insertion", "selection", "heap"]
    domains = ["data", "image", "text", "audio", "network", "auth"]
    modules = ["parser", "validator", "transformer", "encoder", "decoder", "cache"]
    services = ["weather", "inventory", "payments", "notifications", "analytics", "users"]

    for i in range(count):
        tmpl_idx = i % len(templates)
        fname_tmpl, content_tmpl = templates[tmpl_idx]
        if tmpl_idx == 0:
            alg = algs[i % len(algs)]
            fname = fname_tmpl.format(alg=alg)
            content = content_tmpl.format(alg=alg)
        elif tmpl_idx == 1:
            domain = domains[i % len(domains)]
            fname = fname_tmpl.format(domain=domain)
            content = content_tmpl.format(domain=domain)
        elif tmpl_idx == 2:
            mod = modules[i % len(modules)]
            fname = fname_tmpl.format(module=mod)
            sample = ", ".join(str(rng.randint(1, 100)) for _ in range(5))
            content = content_tmpl.format(module=mod, Module=mod.capitalize(), sample_data=sample)
        else:
            svc = services[i % len(services)]
            fname = fname_tmpl.format(service=svc)
            content = content_tmpl.format(service=svc)

        files.append((f"code/{fname}", content))
    return files


def gen_spreadsheets(rng, count=20):
    files = []
    for i in range(count):
        sheet_type = rng.choice([
            "budget", "expense_tracker", "inventory", "grade_book",
            "project_timeline", "sales_report",
        ])
        date = _rand_date(rng)
        fname = f"{sheet_type}_{date}.csv"

        if sheet_type == "budget":
            rows = ["Category,Planned,Actual,Difference"]
            for cat in ["Housing", "Food", "Transport", "Utilities", "Entertainment", "Savings"]:
                planned = _rand_amount(rng, 200, 2000)
                actual = planned + rng.uniform(-200, 200)
                rows.append(f"{cat},{planned:.2f},{actual:.2f},{planned - actual:.2f}")
            content = "\n".join(rows) + "\n"
        elif sheet_type == "expense_tracker":
            rows = ["Date,Description,Category,Amount"]
            for _ in range(rng.randint(10, 25)):
                d = _rand_date(rng)
                desc = rng.choice(["Coffee", "Groceries", "Gas", "Lunch", "Subscription",
                                   "Parking", "Books", "Gym", "Dinner", "Supplies"])
                cat = rng.choice(["Food", "Transport", "Personal", "Work"])
                amt = _rand_amount(rng, 3, 150)
                rows.append(f"{d},{desc},{cat},{amt:.2f}")
            content = "\n".join(rows) + "\n"
        elif sheet_type == "inventory":
            rows = ["Item,SKU,Quantity,Unit_Price,Total_Value"]
            for _ in range(rng.randint(8, 20)):
                item = rng.choice(["Widget A", "Widget B", "Gadget X", "Part Y",
                                   "Component Z", "Module Q", "Sensor R", "Board S"])
                sku = f"SKU-{rng.randint(1000,9999)}"
                qty = rng.randint(1, 500)
                price = _rand_amount(rng, 1, 200)
                rows.append(f"{item},{sku},{qty},{price:.2f},{qty * price:.2f}")
            content = "\n".join(rows) + "\n"
        elif sheet_type == "grade_book":
            students = [_rand_name(rng) for _ in range(rng.randint(8, 15))]
            rows = ["Student,Assignment1,Assignment2,Midterm,Final,Average"]
            for s in students:
                scores = [rng.randint(50, 100) for _ in range(4)]
                avg = sum(scores) / len(scores)
                rows.append(f"{s},{scores[0]},{scores[1]},{scores[2]},{scores[3]},{avg:.1f}")
            content = "\n".join(rows) + "\n"
        elif sheet_type == "project_timeline":
            rows = ["Task,Owner,Start_Date,End_Date,Status"]
            for _ in range(rng.randint(6, 12)):
                task = rng.choice(["Design", "Development", "Testing", "Review",
                                   "Deployment", "Documentation", "Planning", "Research"])
                owner = _rand_name(rng)
                start = _rand_date(rng)
                status = rng.choice(["Not Started", "In Progress", "Complete", "Blocked"])
                rows.append(f"{task},{owner},{start},{start},{status}")
            content = "\n".join(rows) + "\n"
        else:  # sales_report
            rows = ["Month,Product,Units_Sold,Revenue,Region"]
            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            for m in months:
                product = rng.choice(["Pro Plan", "Basic Plan", "Enterprise", "Starter"])
                units = rng.randint(10, 500)
                rev = units * rng.randint(10, 200)
                region = rng.choice(["North", "South", "East", "West"])
                rows.append(f"{m},{product},{units},{rev},{region}")
            content = "\n".join(rows) + "\n"

        files.append((f"spreadsheets/{fname}", content))
    return files


def gen_reports(rng, count=20):
    files = []
    for i in range(count):
        report_type = rng.choice([
            "quarterly_review", "project_status", "incident_report",
            "research_summary", "performance_review", "market_analysis",
        ])
        author = _rand_name(rng)
        company = rng.choice(COMPANIES)
        date = _rand_date(rng)
        fname = f"{report_type}_{date}.md"
        paragraphs = []
        for _ in range(rng.randint(3, 6)):
            sentences = [_fake_sentence(rng) for _ in range(rng.randint(3, 6))]
            paragraphs.append(" ".join(sentences))
        body = "\n\n".join(paragraphs)
        content = (
            f"# {report_type.replace('_', ' ').title()}\n\n"
            f"Author: {author}\n"
            f"Organization: {company}\n"
            f"Date: {date}\n\n"
            f"## Summary\n\n{body}\n\n"
            f"## Recommendations\n\n"
            f"1. {_fake_sentence(rng)}\n"
            f"2. {_fake_sentence(rng)}\n"
            f"3. {_fake_sentence(rng)}\n"
        )
        files.append((f"reports/{fname}", content))
    return files


def gen_letters(rng, count=15):
    files = []
    for i in range(count):
        sender = _rand_name(rng)
        recipient = _rand_name(rng)
        date = _rand_date(rng)
        letter_type = rng.choice([
            "cover_letter", "recommendation", "complaint",
            "thank_you", "resignation", "offer_acceptance",
        ])
        company = rng.choice(COMPANIES)
        city = rng.choice(CITIES)
        fname = f"{letter_type}_{sender.lower().replace(' ', '_')}_{date}.txt"
        body_lines = [_fake_sentence(rng) for _ in range(rng.randint(4, 8))]
        body = " ".join(body_lines)
        content = (
            f"{sender}\n"
            f"{city}\n"
            f"{date}\n\n"
            f"Dear {recipient},\n\n"
            f"Re: {letter_type.replace('_', ' ').title()} - {company}\n\n"
            f"{body}\n\n"
            f"Sincerely,\n"
            f"{sender}\n"
        )
        files.append((f"letters/{fname}", content))
    return files


def gen_tax_docs(rng, count=10):
    """Tax-related documents that cross-reference with receipts."""
    files = []
    for i in range(count):
        year = rng.randint(2022, 2025)
        name = _rand_name(rng)
        doc_type = rng.choice(["tax_return", "w2_form", "1099_form", "tax_prep_notes", "deductions_summary"])
        fname = f"{doc_type}_{year}.txt"
        income = _rand_amount(rng, 30000, 150000)
        tax = income * rng.uniform(0.15, 0.35)
        content = (
            f"TAX DOCUMENT - {doc_type.replace('_', ' ').upper()}\n"
            f"Tax Year: {year}\n"
            f"Taxpayer: {name}\n"
            f"Filing Status: {'Single' if rng.random() > 0.5 else 'Married Filing Jointly'}\n\n"
            f"Gross Income: ${income:.2f}\n"
            f"Federal Tax: ${tax:.2f}\n"
            f"State Tax: ${tax * 0.3:.2f}\n"
            f"Deductions: ${_rand_amount(rng, 5000, 25000):.2f}\n\n"
            f"Prepared by: {rng.choice(COMPANIES)}\n"
            f"Date Filed: {year + 1}-04-{rng.randint(1,15):02d}\n"
        )
        files.append((f"finance/{fname}", content))
    return files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTENCE_TEMPLATES = [
    "The {adj} {noun} was {verb} by the team during {period}.",
    "Results showed a {pct}% {direction} in {metric} over the {period}.",
    "The project required {num} additional {resource} to meet the deadline.",
    "Key stakeholders {verb} the {adj} proposal for {noun} improvements.",
    "Analysis of {metric} data revealed {adj} trends in {noun} performance.",
    "The {noun} department reported {adj} outcomes for the {period} review.",
    "New {noun} policies were {verb} to address {adj} operational needs.",
    "The team identified {num} critical {noun} issues requiring attention.",
]
_ADJS = ["significant", "notable", "preliminary", "comprehensive", "detailed",
         "critical", "strategic", "operational", "quarterly", "annual"]
_NOUNS = ["system", "process", "workflow", "initiative", "framework",
          "platform", "procedure", "methodology", "infrastructure", "resource"]
_VERBS = ["reviewed", "approved", "implemented", "evaluated", "proposed",
          "developed", "analyzed", "optimized", "assessed", "completed"]
_METRICS = ["revenue", "efficiency", "throughput", "retention", "engagement",
            "cost", "productivity", "satisfaction", "utilization", "adoption"]
_PERIODS = ["Q1", "Q2", "Q3", "Q4", "first half", "second half", "fiscal year"]
_RESOURCES = ["engineers", "analysts", "consultants", "developers", "specialists"]


def _fake_sentence(rng):
    tmpl = rng.choice(_SENTENCE_TEMPLATES)
    return tmpl.format(
        adj=rng.choice(_ADJS),
        noun=rng.choice(_NOUNS),
        verb=rng.choice(_VERBS),
        period=rng.choice(_PERIODS),
        pct=rng.randint(2, 45),
        direction=rng.choice(["increase", "decrease", "improvement"]),
        metric=rng.choice(_METRICS),
        num=rng.randint(2, 15),
        resource=rng.choice(_RESOURCES),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_corpus(target_dir: str, seed: int = SEED) -> list[str]:
    """Generate all corpus files. Returns list of relative paths created."""
    rng = random.Random(seed)
    target = Path(target_dir)

    generators = [
        gen_receipts,
        gen_invoices,
        gen_class_notes,
        gen_resumes,
        gen_travel_docs,
        gen_code_files,
        gen_spreadsheets,
        gen_reports,
        gen_letters,
        gen_tax_docs,
    ]

    all_files = []
    for gen_fn in generators:
        all_files.extend(gen_fn(rng))

    # Deduplicate paths by appending a counter to collisions
    seen: dict[str, int] = {}
    created = []
    for rel_path, content in all_files:
        if rel_path in seen:
            seen[rel_path] += 1
            base, ext = os.path.splitext(rel_path)
            rel_path = f"{base}_{seen[rel_path]}{ext}"
        else:
            seen[rel_path] = 0
        full_path = target / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        created.append(rel_path)

    return created


def main():
    parser = argparse.ArgumentParser(description="Build synthetic eval corpus")
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "corpus"),
        help="Directory to write corpus files into (default: eval/corpus/)",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed")
    args = parser.parse_args()

    print(f"Building corpus in {args.target_dir} (seed={args.seed}) ...")
    created = build_corpus(args.target_dir, args.seed)

    # Print summary by category
    cats = {}
    for p in created:
        cat = p.split("/")[0]
        cats[cat] = cats.get(cat, 0) + 1

    print(f"\nCreated {len(created)} files:")
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
