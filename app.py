import streamlit as st
import pandas as pd
import random

st.set_page_config(page_title="NYS Property & Casualty Exam Simulator", page_icon="🛡️", layout="centered")

@st.cache_data
def load_exam_bank():
    try:
        df = pd.read_csv('ny_pc_exam_questions.csv')
        # Dynamically map the IDs in the question text to readable categories for filtering
        def assign_category(q_text):
            if "[NY-REG-" in q_text: return "New York State Regulations"
            elif "[COMM-LINE-" in q_text: return "Commercial Lines & BOP"
            elif "[HO-POLICY-" in q_text: return "Homeowners Policies & Forms"
            elif "[LAW-PRINC-" in q_text: return "Insurance Principles & Contract Law"
            return "General Review"
        
        df['Category'] = df['Question'].apply(assign_category)
        return df
    except FileNotFoundError:
        st.error("Data file 'ny_pc_exam_questions.csv' missing! Please run your generation script first.")
        return None

df = load_exam_bank()

if df is not None:
    st.title("📝 NYS Property & Casualty Exam Simulator")
    st.caption("Questions/Answers are generated using AI. No warranty or guarantee of accuracy.")
    #st.caption("Fulfill licensing standard practice parameters with dynamic performance evaluation counters.")
    
    # Initialize Persistent Session Variables
    if 'quiz_active' not in st.session_state:
        st.session_state.quiz_active = False
        st.session_state.current_step = 0
        st.session_state.total_points = 0
        st.session_state.active_pool = []
        st.session_state.has_responded = False
        st.session_state.active_options = []

    if not st.session_state.quiz_active:
        #st.subheader("⚙️ Exam Session Initialization")
        
        # Category selection box
        available_categories = ["All Categories"] + sorted(list(df['Category'].unique()))
        selected_category = st.selectbox("Select Study Focus / Topic Module:", available_categories)
        
        # Filter dataframe based on user choice
        if selected_category == "All Categories":
            filtered_df = df
        else:
            filtered_df = df[df['Category'] == selected_category]
            
        total_available = len(filtered_df)
        
        # Prompt user for question count bounded by the selected pool size
        selected_limit = st.number_input(
            f"Determine problem target length (1 to {total_available}):", 
            min_value=1, 
            max_value=total_available, 
            value=min(50, total_available)
        )
        
        if st.button("Launch New Exam Instance 🚀"):
            # FIXED: Sample dynamically with no fixed random state to ensure strict runtime randomization
            randomized_df = filtered_df.sample(n=int(selected_limit), random_state=None).reset_index(drop=True)
            st.session_state.active_pool = randomized_df.to_dict(orient='records')
            st.session_state.quiz_active = True
            st.session_state.current_step = 0
            st.session_state.total_points = 0
            st.session_state.has_responded = False
            
            # FIXED: Correctly grab the first question from the newly randomized active pool array
            first_q = st.session_state.active_pool[0]
            pool_opts = [first_q['Correct_Answer'], first_q['Wrong_Answer_1'], first_q['Wrong_Answer_2'], first_q['Wrong_Answer_3']]
            random.shuffle(pool_opts)
            st.session_state.active_options = pool_opts
            st.rerun()

    else:
        current_pool = st.session_state.active_pool
        step = st.session_state.current_step
        total_len = len(current_pool)
        
        if step < total_len:
            active_q = current_pool[step]
            st.progress(step / total_len)
            st.markdown(f"#### 🔎 Question {step + 1} of {total_len}")
            
            # Display current category tag above question
            st.caption(f"📚 Current Module: **{active_q['Category']}**")
            st.info(active_q['Question'])
            
            with st.form(key=f"exam_form_{step}"):
                user_selection = st.radio("Select the best answer:", st.session_state.active_options)
                process_trigger = st.form_submit_button("Verify Solution")
                
            if process_trigger or st.session_state.has_responded:
                if not st.session_state.has_responded:
                    st.session_state.has_responded = True
                    if user_selection == active_q['Correct_Answer']:
                        st.session_state.total_points += 1
                    st.rerun()
                    
                # Display permanent review metrics post-submission
                if user_selection == active_q['Correct_Answer']:
                    st.success("🎯 Correct Response.")
                else:
                    st.error(f"❌ Incorrect: {active_q['Correct_Answer']}")
                
                st.markdown("##### 💡 Key Learning Points")
                st.warning(active_q['Key_Learning_Point'])
                st.markdown(f"🔗 [Review Official Department of Financial Services Reference Framework]({active_q['Reference_Link']})")
                
                if st.button("Advance to Next Item ➡️"):
                    st.session_state.current_step += 1
                    st.session_state.has_responded = False
                    if st.session_state.current_step < total_len:
                        nxt_q = current_pool[st.session_state.current_step]
                        nxt_opts = [nxt_q['Correct_Answer'], nxt_q['Wrong_Answer_1'], nxt_q['Wrong_Answer_2'], nxt_q['Wrong_Answer_3']]
                        random.shuffle(nxt_opts)
                        st.session_state.active_options = nxt_opts
                    st.rerun()
            
            # Interactive session control button to exit early
            st.markdown("---")
            if st.button("🛑 Quit and Score Now"):
                st.session_state.current_step = total_len
                st.rerun()
                
        else:
            st.balloons()
            st.subheader("🏁 Performance Review Complete")
            achieved = st.session_state.total_points
            ratio = (achieved / total_len) * 100
            st.metric(label="Your Score", value=f"{achieved} / {total_len}", delta=f"{ratio:.2f}%")
            
            if ratio >= 70.0:
                st.success("🟢 Passing Status Secured. Meets or exceeds NYS DFS structural baselines.")
            else:
                st.error("🔴 Remediation Recommended. Target score remains below the 70% state threshold boundary.")
                
            if st.button("Initialize Fresh Simulator Window 🔄"):
                st.session_state.quiz_active = False
                st.rerun()
