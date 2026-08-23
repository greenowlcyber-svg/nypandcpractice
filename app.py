"""
NY Property & Casualty Insurance Producer — Exam Prep Quiz
Run with:  streamlit run quiz_app1.py
"""

import math
import random
import csv
from pathlib import Path

import streamlit as st

CANDIDATE_DATA_FILES = [
    "questions.csv",
    "ny_pc_exam_questions.csv",
    "ny_pc_exam_questions_1000_blueprint_mapped.csv",
    "ny_pc_exam_questions_1100_blueprint_mapped.csv",
]

st.set_page_config(page_title="NY P&C Exam Prep Quiz", page_icon="📋", layout="centered")

DISCLAIMER_TEXT = (
    "⚠️ **Study aid only — not affiliated with or endorsed by NY DFS.** "
    "The questions, answer choices, and explanations in this tool were "
    "generated with AI assistance and have **not** been independently "
    "verified against current NY DFS regulations or the official exam "
    "content outline. No warranty or guarantee is made as to their "
    "accuracy, completeness, or currency, and this tool cannot guarantee "
    "a passing score. Always verify current rules, limits, and statutes "
    "against official NY DFS materials and your approved pre-licensing "
    "course before relying on anything here for your exam."
)

# ---------------------------------------------------------------------------
# NY DFS Series 17-56 blueprint weights (Property & Casualty Agents/Brokers
# Exam Content Topic Locator). These are the official section weight
# percentages, mirrored from the reference simulator (app.py).
# Source: https://www.dfs.ny.gov/system/files/documents/2020/11/prel_pca_2018.pdf
# ---------------------------------------------------------------------------
BLUEPRINT_WEIGHTS = {
    "Insurance Regulation": 9,
    "General Insurance": 9,
    "Property and Casualty Insurance Basics": 13,
    "Dwelling": 6,
    "Homeowners (2011) Policy": 14,
    "Auto Insurance": 11,
    "Commercial Package Policy (CPP)": 11,
    "Businessowners (2010) Policy": 8,
    "Workers' Compensation": 8,
    "Other Coverages & Options": 7,
    "Accident & Health": 4,
}

BLUEPRINT_SOURCE_LINK = "https://www.dfs.ny.gov/system/files/documents/2020/11/prel_pca_2018.pdf"

# Keyword fallback used to map this app's free-text "category" column onto
# the official blueprint sections above. Since categories in questions.csv
# aren't guaranteed to match the blueprint titles exactly, this does a
# best-effort keyword match. If your questions.csv uses different category
# names, adjust this map so coverage is accurate.
CATEGORY_KEYWORDS = {
    "Insurance Regulation": ["regulat", "licens", "ethic", "dfs law", "producer law"],
    "General Insurance": ["general insur", "insurance basics", "principle", "contract law", "legal concept"],
    "Property and Casualty Insurance Basics": [
        "p&c basics", "underwrit", "claims", "loss", "policy provision", "contract",
    ],
    "Dwelling": ["dwelling", "df"],
    "Homeowners (2011) Policy": ["homeowner", "ho-3", "ho policy"],
    "Auto Insurance": ["auto", "no-fault", "no fault", "vehicle"],
    "Commercial Package Policy (CPP)": ["commercial", "cpp", "liability", "general liability"],
    "Businessowners (2010) Policy": ["businessowner", "bop"],
    "Workers' Compensation": ["workers", "workers'", "comp "],
    "Other Coverages & Options": ["umbrella", "bond", "excess", "other coverage", "endorsement"],
    "Accident & Health": ["accident", "health"],
}


def map_to_blueprint_section(category):
    """Best-effort match of a free-text category to an official blueprint
    section. Returns None if no reasonable match is found."""
    if not category:
        return None
    c = category.strip().lower()

    # Exact / substring match against the official titles first.
    for section in BLUEPRINT_WEIGHTS:
        if section.lower() == c or section.lower() in c or c in section.lower():
            return section

    # Keyword fallback.
    for section, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in c for kw in keywords):
            return section

    return None


def blueprint_allocation(total_questions):
    """Convert the official percentage weights into an exact integer
    allocation that sums to total_questions, via largest-remainder rounding."""
    raw = {
        section: total_questions * weight / 100
        for section, weight in BLUEPRINT_WEIGHTS.items()
    }
    allocation = {section: math.floor(value) for section, value in raw.items()}
    remaining = total_questions - sum(allocation.values())

    order = list(BLUEPRINT_WEIGHTS.keys())
    ranked = sorted(
        order,
        key=lambda s: (raw[s] - allocation[s], -order.index(s)),
        reverse=True,
    )
    for section in ranked[:remaining]:
        allocation[section] += 1

    return allocation


def compute_section_availability(all_questions):
    """Count how many loaded questions map to each blueprint section."""
    available = {section: 0 for section in BLUEPRINT_WEIGHTS}
    unclassified = 0
    for q in all_questions:
        section = q.get("blueprint_section")
        if section:
            available[section] += 1
        else:
            unclassified += 1
    return available, unclassified


def adjust_allocation_for_availability(target_allocation, available):
    """Cap each section's target at what's actually available, then
    redistribute any shortfall to sections with spare capacity so the
    requested total is still reached whenever the bank allows it."""
    final_allocation = {}
    shortfall = 0
    spare_capacity = {}

    for section, target in target_allocation.items():
        avail = available.get(section, 0)
        take = min(target, avail)
        final_allocation[section] = take
        if avail < target:
            shortfall += target - avail
        elif avail > target:
            spare_capacity[section] = avail - target

    while shortfall > 0 and spare_capacity:
        section = max(spare_capacity, key=lambda s: spare_capacity[s])
        final_allocation[section] += 1
        spare_capacity[section] -= 1
        shortfall -= 1
        if spare_capacity[section] == 0:
            del spare_capacity[section]

    return final_allocation, shortfall


def build_weighted_sample(all_questions, n):
    """Build an NY DFS blueprint-weighted sample of up to n questions."""
    available, unclassified = compute_section_availability(all_questions)
    target_allocation = blueprint_allocation(n)
    final_allocation, shortfall = adjust_allocation_for_availability(target_allocation, available)

    pool = []
    for section, count in final_allocation.items():
        if count <= 0:
            continue
        section_questions = [q for q in all_questions if q.get("blueprint_section") == section]
        pool.extend(random.sample(section_questions, count))

    random.shuffle(pool)
    return pool, target_allocation, final_allocation, shortfall, unclassified


# ---------------------------------------------------------------------------
# Data loading
#
# Supports two CSV schemas so this app works with either a simple hand-built
# bank or the full DFS-blueprint-mapped bank produced by the exam simulator:
#
#   Legacy schema:  question, option_a, option_b, option_c, option_d,
#                   correct_option (A/B/C/D), category, explanation, link
#
#   Blueprint schema: Question, Correct_Answer, Wrong_Answer_1, Wrong_Answer_2,
#                   Wrong_Answer_3, Blueprint_Section_Title, Key_Learning_Point,
#                   Reference_Link (this is the schema of
#                   ny_pc_exam_questions.csv)
# ---------------------------------------------------------------------------
def find_data_file():
    base_dir = Path(__file__).parent
    for filename in CANDIDATE_DATA_FILES:
        candidate = base_dir / filename
        if candidate.exists():
            return candidate
    return None


def normalize_row(raw):
    """Convert a raw CSV row (either supported schema) into a common dict:
    question, category, options (list of 4 texts), correct_text,
    explanation, link, blueprint_section (resolved once here so downstream
    code never has to re-guess it)."""
    if "question" in raw and "option_a" in raw:
        letter = raw["correct_option"].strip().upper()
        options = [raw["option_a"], raw["option_b"], raw["option_c"], raw["option_d"]]
        correct_text = raw.get(f"option_{letter.lower()}", "")
        category = (raw.get("category") or "Uncategorized").strip()

        # Prefer an explicit blueprint_section column if the CSV provides
        # one and it's a recognized official section; otherwise fall back
        # to best-effort keyword matching on the display category.
        explicit_section = (raw.get("blueprint_section") or "").strip()
        section = explicit_section if explicit_section in BLUEPRINT_WEIGHTS else map_to_blueprint_section(category)

        return {
            "question": raw["question"],
            "category": category,
            "options": [o for o in options if o and o.strip()],
            "correct_text": correct_text,
            "explanation": raw.get("explanation", ""),
            "link": (raw.get("link") or "").strip(),
            "blueprint_section": section,
        }
    else:
        options = [
            raw.get("Correct_Answer", ""),
            raw.get("Wrong_Answer_1", ""),
            raw.get("Wrong_Answer_2", ""),
            raw.get("Wrong_Answer_3", ""),
        ]
        category = (raw.get("Blueprint_Section_Title") or "Uncategorized").strip()
        section = category if category in BLUEPRINT_WEIGHTS else map_to_blueprint_section(category)
        return {
            "question": raw["Question"],
            "category": category,
            "options": [o for o in options if o and o.strip()],
            "correct_text": raw.get("Correct_Answer", ""),
            "explanation": raw.get("Key_Learning_Point", ""),
            "link": (raw.get("Reference_Link") or "").strip(),
            "blueprint_section": section,
        }


@st.cache_data
def load_questions():
    data_file = find_data_file()
    if data_file is None:
        st.error(
            "No question bank found. Place one of the following files next to "
            f"this script: {', '.join(CANDIDATE_DATA_FILES)}"
        )
        st.stop()
    with open(data_file, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))
    rows = [normalize_row(r) for r in raw_rows]
    # Drop any malformed rows that ended up without a valid correct answer
    # or fewer than 2 answer options.
    rows = [r for r in rows if r["correct_text"] and len(r["options"]) >= 2]
    return rows


def build_shuffled_choices(row):
    """Return (choice_texts_in_random_order, correct_text)."""
    choices = list(row["options"])
    random.shuffle(choices)
    return choices, row["correct_text"]


# ---------------------------------------------------------------------------
# Session state setup
# ---------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("stage", "setup")   # setup -> quiz -> finished
    ss.setdefault("quiz_questions", [])
    ss.setdefault("current_index", 0)
    ss.setdefault("score", 0)
    ss.setdefault("answered", False)
    ss.setdefault("selected_choice", None)
    ss.setdefault("shuffled_choices", None)
    ss.setdefault("correct_text", None)
    ss.setdefault("missed_questions", [])
    ss.setdefault("quiz_mode", "custom")          # "custom" or "dfs_weighted"
    ss.setdefault("dfs_target_allocation", {})
    ss.setdefault("dfs_final_allocation", {})
    ss.setdefault("dfs_shortfall", 0)
    ss.setdefault("dfs_unclassified", 0)


init_state()
all_questions = load_questions()
total_available = len(all_questions)


def restart():
    ss = st.session_state
    ss.stage = "setup"
    ss.quiz_questions = []
    ss.current_index = 0
    ss.score = 0
    ss.answered = False
    ss.selected_choice = None
    ss.missed_questions = []
    ss.quiz_mode = "custom"
    ss.dfs_target_allocation = {}
    ss.dfs_final_allocation = {}
    ss.dfs_shortfall = 0
    ss.dfs_unclassified = 0


def submit_answer(choice_text):
    ss = st.session_state
    ss.answered = True
    ss.selected_choice = choice_text
    q = ss.quiz_questions[ss.current_index]
    if choice_text == ss.correct_text:
        ss.score += 1
    else:
        ss.missed_questions.append(q)


def next_question():
    ss = st.session_state
    ss.current_index += 1
    ss.answered = False
    ss.selected_choice = None
    ss.shuffled_choices = None
    ss.correct_text = None
    if ss.current_index >= len(ss.quiz_questions):
        ss.stage = "finished"


# ---------------------------------------------------------------------------
# UI: Setup screen
# ---------------------------------------------------------------------------
st.title("📋 NY Property & Casualty Insurance Exam Prep")

if st.session_state.stage == "setup":
    st.markdown(
        f"""
This study tool covers core Property & Casualty producer exam topics — insurance
basics, contract law, policy provisions, homeowners, auto (including New York's
No-Fault law), commercial liability, workers' compensation, underwriting/claims,
and New York licensing law and ethics.

**Question bank available: {total_available} questions.**
"""
    )
    st.warning(DISCLAIMER_TEXT)

    mode_label = st.radio(
        "Choose a quiz mode:",
        ["Custom Practice", "NY DFS Weighted Sample Test"],
        horizontal=True,
    )

    if mode_label == "NY DFS Weighted Sample Test":
        st.markdown("### 🎯 Blueprint-Weighted Sample Test")
        st.write(
            "This mode samples questions using the official NY DFS Series 17-56 "
            "section weights, so the mix of topics mirrors the real exam's "
            "content outline rather than being evenly or randomly distributed."
        )

        default_n = min(150, total_available)
        num_dfs_questions = st.number_input(
            f"How many questions in this weighted sample? (1–{total_available})",
            min_value=1,
            max_value=total_available,
            value=default_n,
            step=1,
        )

        available, unclassified = compute_section_availability(all_questions)
        preview_allocation = blueprint_allocation(int(num_dfs_questions))
        coverage_rows = []
        for section, weight in BLUEPRINT_WEIGHTS.items():
            target = preview_allocation[section]
            avail = available[section]
            coverage_rows.append(
                {
                    "Section": section,
                    "Weight": f"{weight}%",
                    "Target": target,
                    "Available": avail,
                    "Status": "✓" if avail >= target else "⚠️ short",
                }
            )
        st.dataframe(coverage_rows, hide_index=True, width='stretch')

        if unclassified:
            st.caption(
                f"ℹ️ {unclassified} question(s) in the bank didn't match a blueprint "
                "section by category name and are excluded from this mode's pool."
            )

        short_sections = [row for row in coverage_rows if row["Status"] != "✓"]
        if short_sections:
            st.info(
                "Some sections don't have enough questions to hit their exact "
                "target weight. Shortfalls are redistributed to other sections "
                "where possible, so the total question count is still met, but "
                "the exact percentage mix may shift slightly."
            )

        st.caption(
            "Blueprint source: NY DFS Series 17-56 Exam Content Topic Locator. "
            "Verify the current PSI/DFS outline before treating these percentages "
            "as the live exam blueprint."
        )
        st.markdown(f"[View DFS topic locator]({BLUEPRINT_SOURCE_LINK})")

        if st.button("Start Weighted Sample Test", type="primary"):
            pool, target_allocation, final_allocation, shortfall, unclassified = build_weighted_sample(
                all_questions, int(num_dfs_questions)
            )
            if not pool:
                st.error(
                    "Couldn't build a weighted sample — no questions matched any "
                    "blueprint section. Check that your questions.csv category "
                    "names align with the blueprint sections."
                )
            else:
                st.session_state.quiz_questions = pool
                st.session_state.current_index = 0
                st.session_state.score = 0
                st.session_state.answered = False
                st.session_state.selected_choice = None
                st.session_state.missed_questions = []
                st.session_state.shuffled_choices = None
                st.session_state.correct_text = None
                st.session_state.quiz_mode = "dfs_weighted"
                st.session_state.dfs_target_allocation = target_allocation
                st.session_state.dfs_final_allocation = final_allocation
                st.session_state.dfs_shortfall = shortfall
                st.session_state.dfs_unclassified = unclassified
                st.session_state.stage = "quiz"
                st.rerun()

    else:
        num_questions = st.number_input(
            f"How many questions would you like in this quiz? (1–{total_available})",
            min_value=1,
            max_value=total_available,
            value=min(20, total_available),
            step=1,
        )

        categories = sorted(set(q["category"] for q in all_questions))
        with st.expander("Filter by category (optional)"):
            selected_categories = st.multiselect(
                "Only include these categories:", categories, default=categories
            )

        if st.button("Start Quiz", type="primary"):
            filtered = [q for q in all_questions if q["category"] in selected_categories]
            if not filtered:
                st.error("No questions match the selected categories.")
            else:
                if num_questions > len(filtered):
                    st.warning(
                        f"Only {len(filtered)} questions available for the selected "
                        f"categories. Starting quiz with all {len(filtered)} of them instead."
                    )
                n = min(num_questions, len(filtered))
                pool = filtered.copy()
                random.shuffle(pool)
                st.session_state.quiz_questions = pool[:n]
                st.session_state.current_index = 0
                st.session_state.score = 0
                st.session_state.answered = False
                st.session_state.selected_choice = None
                st.session_state.missed_questions = []
                st.session_state.shuffled_choices = None
                st.session_state.correct_text = None
                st.session_state.quiz_mode = "custom"
                st.session_state.stage = "quiz"
                st.rerun()

# ---------------------------------------------------------------------------
# UI: Quiz screen
# ---------------------------------------------------------------------------
elif st.session_state.stage == "quiz":
    ss = st.session_state
    q = ss.quiz_questions[ss.current_index]
    total_in_quiz = len(ss.quiz_questions)

    st.progress((ss.current_index) / total_in_quiz)
    st.caption(f"Question {ss.current_index + 1} of {total_in_quiz}  •  Category: {q['category']}  •  Score so far: {ss.score}/{ss.current_index}")

    if ss.quiz_mode == "dfs_weighted":
        section = q.get("blueprint_section")
        if section:
            st.caption(f"📚 Blueprint Section: **{section}**  •  DFS Weight: **{BLUEPRINT_WEIGHTS[section]}%**")

    st.subheader(q["question"])

    if ss.shuffled_choices is None:
        choices, correct_text = build_shuffled_choices(q)
        ss.shuffled_choices = choices
        ss.correct_text = correct_text

    if not ss.answered:
        with st.form(key=f"answer_form_{ss.current_index}"):
            selected = st.radio(
                "Choose your answer:",
                options=ss.shuffled_choices,
                index=None,
                key=f"radio_{ss.current_index}",
            )
            submitted = st.form_submit_button("Submit Answer", type="primary")

        if submitted:
            if selected is None:
                st.warning("Please select an answer before submitting.")
            else:
                submit_answer(selected)
                st.rerun()
    else:
        for choice in ss.shuffled_choices:
            if choice == ss.correct_text:
                label = f"✅ {choice}"
                if choice == ss.selected_choice:
                    label += "  ← Your answer"
                st.success(label)
            elif choice == ss.selected_choice:
                st.error(f"❌ {choice}  ← Your answer")
            else:
                st.write(f"　{choice}")

        if ss.selected_choice == ss.correct_text:
            st.info("**Correct!**")
        else:
            st.warning("**Not quite.**")

        st.markdown(f"**Key learning point:** {q['explanation']}")
        if q.get("link"):
            st.markdown(f"[Learn more]({q['link']})")

        button_label = "Next question →" if ss.current_index + 1 < total_in_quiz else "See results →"
        if st.button(button_label, type="primary"):
            next_question()
            st.rerun()

    st.divider()
    if st.button("End quiz early"):
        st.session_state.stage = "finished"
        st.rerun()

# ---------------------------------------------------------------------------
# UI: Results screen
# ---------------------------------------------------------------------------
elif st.session_state.stage == "finished":
    ss = st.session_state
    answered_count = ss.current_index if ss.current_index <= len(ss.quiz_questions) else len(ss.quiz_questions)
    answered_count = max(answered_count, 1) if ss.score or ss.missed_questions else answered_count
    pct = round(100 * ss.score / answered_count, 1) if answered_count else 0

    st.header("Quiz Results")
    st.metric("Score", f"{ss.score} / {answered_count}", f"{pct}%")

    if pct >= 90:
        st.success("Excellent! You're in strong shape for this material.")
    elif pct >= 75:
        st.info("Good work — review your missed questions below to close the gaps.")
    else:
        st.warning("Keep studying — revisit the categories below where you missed questions.")

    if ss.quiz_mode == "dfs_weighted":
        st.subheader("Blueprint Allocation Used")
        st.caption(
            "How this sample's topic mix compared to the official NY DFS "
            "Series 17-56 section weights."
        )
        actual_counts = {}
        for q in ss.quiz_questions:
            section = q.get("blueprint_section")
            if section:
                actual_counts[section] = actual_counts.get(section, 0) + 1

        allocation_rows = []
        for section, weight in BLUEPRINT_WEIGHTS.items():
            allocation_rows.append(
                {
                    "Section": section,
                    "DFS Weight": f"{weight}%",
                    "Target Questions": ss.dfs_target_allocation.get(section, 0),
                    "Actual Questions": actual_counts.get(section, 0),
                }
            )
        st.dataframe(allocation_rows, hide_index=True, width='stretch')

        if ss.dfs_shortfall:
            st.caption(
                f"⚠️ {ss.dfs_shortfall} question(s) short of the exact blueprint "
                "target due to limited questions in one or more sections."
            )

    if ss.missed_questions:
        st.subheader("Review — Questions You Missed")
        for q in ss.missed_questions:
            with st.expander(f"[{q['category']}] {q['question']}"):
                st.markdown(f"**Correct answer:** {q['correct_text']}")
                st.markdown(f"**Key learning point:** {q['explanation']}")
                if q.get("link"):
                    st.markdown(f"[Learn more]({q['link']})")
    else:
        st.balloons()
        st.write("No missed questions — nice work!")

    if st.button("Take another quiz", type="primary"):
        restart()
        st.rerun()

st.divider()
st.caption(
    "⚠️ Study aid only — not affiliated with or endorsed by NY DFS. Questions "
    "and explanations were AI-generated and are provided with no warranty or "
    "guarantee of accuracy. Always verify current rules, limits, and statutes "
    "against official NY DFS materials and your approved pre-licensing course "
    "before your exam."
)

st.sidebar.title("About")
st.sidebar.markdown(
    """
**NY P&C Exam Prep Quiz**

- Questions are randomly drawn and ordered each run
- Answer choices are shuffled every time a question is shown
- Explanations + reference links appear after each answer
- An optional NY DFS Weighted Sample Test mode mirrors the official
  Series 17-56 section weighting

**⚠️ Disclaimer:** This tool's questions, answer choices, and explanations
were generated with AI assistance. They have not been independently
verified, and no warranty or guarantee is made as to their accuracy,
completeness, or currency. This app is a study aid only, is not affiliated
with or endorsed by NY DFS, and cannot guarantee a passing score. Always
confirm anything here against official DFS materials and your approved
pre-licensing course.

**Official resources:**
- [NY DFS Licensing](https://www.dfs.ny.gov/licensing)
- [NY DFS Auto Insurance / No-Fault](https://www.dfs.ny.gov/consumers/auto_insurance/no_fault_insurance)
- [NY Workers' Compensation Board](https://www.wcb.ny.gov)
- [NY Insurance Law (full text)](https://www.nysenate.gov/legislation/laws/ISC)
- [NY DFS Series 17-56 Topic Locator](https://www.dfs.ny.gov/system/files/documents/2020/11/prel_pca_2018.pdf)
"""
)
