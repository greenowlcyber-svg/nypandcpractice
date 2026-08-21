import streamlit as st
import pandas as pd
import random
import os
import math

st.set_page_config(
    page_title="NYS Property & Casualty Exam Simulator",
    page_icon="🛡️",
    layout="centered",
)

PRIMARY_DATA_FILE = "ny_pc_exam_questions_1100_blueprint_mapped.csv"
FALLBACK_DATA_FILES = [
    "ny_pc_exam_questions_1000_blueprint_mapped.csv",
    "ny_pc_exam_questions.csv",
]

# NY DFS / PSI Series 17-56 section weights documented in the project source
# (the uploaded chat thread identifies these as the official outline weights).
BLUEPRINT_WEIGHTS = {
    "1.0": 9,
    "2.0": 9,
    "3.0": 13,
    "4.0": 6,
    "5.0": 14,
    "6.0": 11,
    "7.0": 11,
    "8.0": 8,
    "9.0": 8,
    "10.0": 7,
    "11.0": 4,
}

BLUEPRINT_TITLES = {
    "1.0": "Insurance Regulation",
    "2.0": "General Insurance",
    "3.0": "Property and Casualty Insurance Basics",
    "4.0": "Dwelling",
    "5.0": "Homeowners (2011) Policy",
    "6.0": "Auto Insurance",
    "7.0": "Commercial Package Policy (CPP)",
    "8.0": "Businessowners (2010) Policy",
    "9.0": "Workers' Compensation",
    "10.0": "Other Coverages & Options",
    "11.0": "Accident & Health",
}

BLUEPRINT_SOURCE = (
    "NY DFS Property & Casualty Agents/Brokers Series 17-56 "
    "Exam Content Topic Locator (2018–2019 document currently hosted by DFS)"
)
BLUEPRINT_SOURCE_LINK = "https://www.dfs.ny.gov/system/files/documents/2020/11/prel_pca_2018.pdf"


@st.cache_data
def load_exam_bank():
    for filename in [PRIMARY_DATA_FILE] + FALLBACK_DATA_FILES:
        if os.path.exists(filename):
            df = pd.read_csv(filename)

            # Preserve blueprint fields if present. Older files are still supported.
            if "Blueprint_Section" not in df.columns:
                df["Blueprint_Section"] = ""
            if "Blueprint_Section_Title" not in df.columns:
                df["Blueprint_Section_Title"] = ""
            if "Blueprint_Weight" not in df.columns:
                df["Blueprint_Weight"] = ""

            def assign_category(row):
                sec = str(row.get("Blueprint_Section", "")).strip()
                if sec in BLUEPRINT_TITLES:
                    return f"{sec} {BLUEPRINT_TITLES[sec]}"

                q_text = str(row.get("Question", ""))
                if "[NY-REG-" in q_text:
                    return "1.0 Insurance Regulation"
                elif "[COMM-LINE-" in q_text:
                    return "7.0 Commercial Package / Commercial Lines"
                elif "[HO-POLICY-" in q_text:
                    return "5.0 Homeowners Policies & Forms"
                elif "[LAW-PRINC-" in q_text:
                    return "2.0/3.0 Insurance Principles"
                return "General Review"

            df["Category"] = df.apply(assign_category, axis=1)
            return df, filename

    st.error(
        "No exam bank found. Put "
        f"'{PRIMARY_DATA_FILE}' in the same directory as app.py."
    )
    return None, None


def blueprint_allocation(total_questions=150):
    """
    Convert the official percentage weights into an exact integer allocation
    whose total is exactly 150. Uses largest remainder allocation.
    """
    raw = {
        section: total_questions * weight / 100
        for section, weight in BLUEPRINT_WEIGHTS.items()
    }
    allocation = {section: math.floor(value) for section, value in raw.items()}
    remaining = total_questions - sum(allocation.values())

    # Deterministic largest-remainder tie break follows blueprint section order.
    order = list(BLUEPRINT_WEIGHTS.keys())
    ranked = sorted(
        order,
        key=lambda s: (raw[s] - allocation[s], -order.index(s)),
        reverse=True,
    )
    for section in ranked[:remaining]:
        allocation[section] += 1

    return allocation


def weighted_sample(df, total_questions=150):
    """
    Build a true blueprint-weighted sample:
      * exact 150 questions
      * no normalization of weights
      * exact integer allocation derived from 9/9/13/6/14/11/11/8/8/7/4
      * sampling without replacement within each section
    """
    allocation = blueprint_allocation(total_questions)
    selected_parts = []

    for section, needed in allocation.items():
        section_df = df[df["Blueprint_Section"].astype(str) == section].copy()

        if len(section_df) < needed:
            raise ValueError(
                f"Section {section} ({BLUEPRINT_TITLES.get(section, section)}) "
                f"needs {needed} questions but the bank contains only "
                f"{len(section_df)}."
            )

        selected_parts.append(
            section_df.sample(n=needed, replace=False, random_state=None)
        )

    sampled = pd.concat(selected_parts, ignore_index=True)
    sampled = sampled.sample(frac=1, random_state=None).reset_index(drop=True)
    return sampled, allocation


def question_options(question):
    options = [
        question.get("Correct_Answer", ""),
        question.get("Wrong_Answer_1", ""),
        question.get("Wrong_Answer_2", ""),
        question.get("Wrong_Answer_3", ""),
    ]
    options = [str(x) for x in options if pd.notna(x) and str(x).strip()]
    random.shuffle(options)
    return options


df, loaded_filename = load_exam_bank()

if df is not None:
    st.title("📝 NYS Property & Casualty Exam Simulator")
    st.caption(
        "Questions/answers are for exam preparation. Verify current NY DFS/PSI "
        "requirements before relying on them for licensing decisions."
    )

    # Persistent session state
    defaults = {
        "quiz_active": False,
        "current_step": 0,
        "total_points": 0,
        "active_pool": [],
        "has_responded": False,
        "active_options": [],
        "exam_mode": None,
        "exam_allocation": {},
        "exam_source": "",
        "answered_questions": 0,
        "selected_answer": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if not st.session_state.quiz_active:
        st.subheader("⚙️ Exam Session Initialization")

        mode = st.radio(
            "Choose a test mode:",
            ["Custom Practice", "NY DFS Weighted Sample Test"],
            horizontal=True,
        )

        if mode == "NY DFS Weighted Sample Test":
            st.markdown(
                "### 🎯 150-Question Blueprint Simulation"
            )
            st.write(
                "The sample test uses the full NY DFS/PSI Series 17-56 section "
                "weights. It does **not** normalize away missing sections."
            )

            allocation = blueprint_allocation(150)
            coverage_rows = []
            for section, weight in BLUEPRINT_WEIGHTS.items():
                available = int(
                    (df["Blueprint_Section"].astype(str) == section).sum()
                )
                coverage_rows.append(
                    {
                        "Section": section,
                        "Blueprint": BLUEPRINT_TITLES[section],
                        "Weight": f"{weight}%",
                        "Sample Questions": allocation[section],
                        "Bank Available": available,
                        "Status": "✓" if available >= allocation[section] else "⚠️",
                    }
                )

            coverage_df = pd.DataFrame(coverage_rows)
            st.dataframe(coverage_df, hide_index=True, use_container_width=True)

            missing = coverage_df[coverage_df["Status"] != "✓"]
            if not missing.empty:
                st.error(
                    "The question bank cannot currently produce a true 150-question "
                    "blueprint sample because one or more sections do not contain "
                    "enough questions."
                )
                st.stop()

            st.success(
                "All 11 blueprint sections are represented. "
                "The simulator will select exactly 150 questions using the "
                "allocations shown above."
            )

            st.caption(
                "Blueprint source: NY DFS Series 17-56 Topic Locator. "
                "The project source notes that the DFS-hosted locator is labeled "
                "2018–2019; verify the current PSI/DFS outline before treating "
                "the percentages as the current live exam blueprint."
            )
            st.markdown(f"[View DFS topic locator]({BLUEPRINT_SOURCE_LINK})")

            launch = st.button("Launch 150-Question Sample Test 🚀", type="primary")

            if launch:
                try:
                    randomized_df, allocation = weighted_sample(df, 150)
                except ValueError as exc:
                    st.error(str(exc))
                    st.stop()

                st.session_state.active_pool = randomized_df.to_dict(
                    orient="records"
                )
                st.session_state.exam_allocation = allocation
                st.session_state.exam_source = loaded_filename
                st.session_state.exam_mode = "NY DFS Weighted Sample Test"
                st.session_state.quiz_active = True
                st.session_state.current_step = 0
                st.session_state.total_points = 0
                st.session_state.has_responded = False
                st.session_state.answered_questions = 0
                st.session_state.selected_answer = None
                st.session_state.active_options = question_options(
                    st.session_state.active_pool[0]
                )
                st.rerun()

        else:
            available_categories = ["All Categories"] + sorted(
                list(df["Category"].dropna().unique())
            )
            selected_category = st.selectbox(
                "Select Study Focus / Topic Module:", available_categories
            )

            if selected_category == "All Categories":
                filtered_df = df
            else:
                filtered_df = df[df["Category"] == selected_category]

            total_available = len(filtered_df)

            if total_available == 0:
                st.warning("No questions are available for this category.")
                st.stop()

            selected_limit = st.number_input(
                f"Determine problem target length (1 to {total_available}):",
                min_value=1,
                max_value=total_available,
                value=min(50, total_available),
                step=1,
            )

            if st.button("Launch New Practice Session 🚀", type="primary"):
                randomized_df = filtered_df.sample(
                    n=int(selected_limit), random_state=None
                ).reset_index(drop=True)

                st.session_state.active_pool = randomized_df.to_dict(
                    orient="records"
                )
                st.session_state.exam_allocation = {}
                st.session_state.exam_source = loaded_filename
                st.session_state.exam_mode = "Custom Practice"
                st.session_state.quiz_active = True
                st.session_state.current_step = 0
                st.session_state.total_points = 0
                st.session_state.has_responded = False
                st.session_state.answered_questions = 0
                st.session_state.selected_answer = None
                st.session_state.active_options = question_options(
                    st.session_state.active_pool[0]
                )
                st.rerun()

    else:
        current_pool = st.session_state.active_pool
        step = st.session_state.current_step
        total_len = len(current_pool)

        if step < total_len:
            active_q = current_pool[step]

            st.progress(step / total_len)
            st.markdown(f"#### 🔎 Question {step + 1} of {total_len}")

            section = str(active_q.get("Blueprint_Section", "")).strip()
            section_title = BLUEPRINT_TITLES.get(
                section,
                str(active_q.get("Blueprint_Section_Title", "")).strip()
                or str(active_q.get("Category", "General Review")),
            )

            if section in BLUEPRINT_WEIGHTS:
                st.caption(
                    f"📚 Blueprint Section: **{section} {section_title}**  •  "
                    f"DFS Weight: **{BLUEPRINT_WEIGHTS[section]}%**"
                )
            else:
                st.caption(f"📚 Current Module: **{section_title}**")

            topic_code = str(active_q.get("Blueprint_Topic_Code", "")).strip()
            topic = str(active_q.get("Blueprint_Topic", "")).strip()
            if topic_code or topic:
                st.caption(
                    f"🎯 Blueprint Topic: **{topic_code}** {topic}".strip()
                )

            st.info(active_q["Question"])

            with st.form(key=f"exam_form_{step}"):
                user_selection = st.radio(
                    "Select the best answer:",
                    st.session_state.active_options,
                )
                process_trigger = st.form_submit_button("Verify Solution")

            if process_trigger and not st.session_state.has_responded:
                st.session_state.selected_answer = user_selection
                st.session_state.has_responded = True
                st.session_state.answered_questions += 1

                if st.session_state.selected_answer == active_q["Correct_Answer"]:
                    st.session_state.total_points += 1
                st.rerun()

            if st.session_state.has_responded:
                if st.session_state.selected_answer == active_q["Correct_Answer"]:
                    st.success("🎯 Correct Response.")
                else:
                    st.error(
                        f"❌ Incorrect: {active_q['Correct_Answer']}"
                    )

                st.markdown("##### 💡 Key Learning Point")
                st.warning(active_q.get("Key_Learning_Point", ""))

                reference_title = active_q.get("Specific_Reference", "")
                reference_link = active_q.get("Reference_Link", "")
                blueprint_source = active_q.get("Blueprint_Source", "")
                blueprint_source_link = active_q.get("Blueprint_Source_Link", "")

                if pd.isna(reference_title):
                    reference_title = ""
                if pd.isna(reference_link):
                    reference_link = ""
                if pd.isna(blueprint_source):
                    blueprint_source = ""
                if pd.isna(blueprint_source_link):
                    blueprint_source_link = ""

                reference_title = str(reference_title).strip()
                reference_link = str(reference_link).strip()
                blueprint_source = str(blueprint_source).strip()
                blueprint_source_link = str(blueprint_source_link).strip()

                if reference_title and reference_link:
                    st.markdown(
                        f"🔗 **Reference:** [{reference_title}]({reference_link})"
                    )
                elif reference_link:
                    st.markdown(
                        f"🔗 **Reference:** [View source]({reference_link})"
                    )
                elif reference_title:
                    st.markdown(f"📚 **Reference:** {reference_title}")
                else:
                    st.caption("📚 Reference not provided for this question.")

                if blueprint_source_link:
                    label = blueprint_source or "DFS Blueprint Source"
                    st.markdown(
                        f"🗺️ **Blueprint source:** [{label}]"
                        f"({blueprint_source_link})"
                    )

                if st.button("Advance to Next Item ➡️"):
                    st.session_state.current_step += 1
                    st.session_state.has_responded = False
                    st.session_state.selected_answer = None

                    if st.session_state.current_step < total_len:
                        nxt_q = current_pool[st.session_state.current_step]
                        st.session_state.active_options = question_options(nxt_q)
                    st.rerun()

            st.markdown("---")
            if st.button("🛑 Quit and Score Now"):
                st.session_state.current_step = total_len
                st.rerun()

        else:
            st.balloons()
            st.subheader("🏁 Performance Review Complete")

            achieved = st.session_state.total_points
            ratio = (achieved / total_len) * 100 if total_len else 0

            st.metric(
                label="Your Score",
                value=f"{achieved} / {total_len}",
                delta=f"{ratio:.2f}%",
            )

            if st.session_state.exam_mode == "NY DFS Weighted Sample Test":
                st.success(
                    "This result came from a 150-question sample constructed "
                    "using the full 11-section blueprint allocation."
                )

                allocation = st.session_state.exam_allocation
                result_counts = {}
                for q in current_pool:
                    sec = str(q.get("Blueprint_Section", "")).strip()
                    result_counts[sec] = result_counts.get(sec, 0) + 1

                allocation_rows = []
                for section, weight in BLUEPRINT_WEIGHTS.items():
                    allocation_rows.append(
                        {
                            "Section": section,
                            "Blueprint": BLUEPRINT_TITLES[section],
                            "DFS Weight": f"{weight}%",
                            "Target Questions": allocation.get(section, 0),
                            "Actual Questions": result_counts.get(section, 0),
                        }
                    )

                st.markdown("### Blueprint Allocation Used")
                st.dataframe(
                    pd.DataFrame(allocation_rows),
                    hide_index=True,
                    use_container_width=True,
                )

                st.caption(
                    "The target and actual counts should match exactly for all "
                    "11 sections."
                )

            if ratio >= 70.0:
                st.success(
                    "🟢 Practice benchmark met: 70% or higher."
                )
            else:
                st.error(
                    "🔴 Remediation recommended: practice score is below 70%."
                )

            if st.button("Initialize Fresh Simulator Window 🔄"):
                st.session_state.quiz_active = False
                st.session_state.current_step = 0
                st.session_state.total_points = 0
                st.session_state.active_pool = []
                st.session_state.has_responded = False
                st.session_state.selected_answer = None
                st.session_state.active_options = []
                st.session_state.exam_allocation = {}
                st.session_state.exam_mode = None
                st.rerun()
