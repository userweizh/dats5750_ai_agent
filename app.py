import streamlit as st
from google import genai
from google.genai import types
from google.cloud import firestore  # ➕ Import Firestore SDK

# 1. Initialize Clients
@st.cache_resource
def get_ai_client():
    return genai.Client()

@st.cache_resource
def get_db_client():
    # Automatically uses your authenticated GCP project credentials
    return firestore.Client(project="patheon-ai", database="guest-list")

client = get_ai_client()
db = get_db_client()

# 2. Database-backed Persona Library Initialization
# Instead of hardcoding everything in temporary RAM, we sync with Firestore
if "persona_library" not in st.session_state:
    # A. Setup the default starting lineup
    defaults = {
        "Confucius": "You are Confucius. Speak with ancient philosophical wisdom. Focus heavily on ethics, social harmony, virtue, and respect.",
        "Albert Einstein": "You are Albert Einstein. Approach topics from a deeply scientific, curious, and humanitarian perspective.",
        "Donald Trump": "You are Donald Trump. Speak in your signature style: short, highly confident, punchy sentences.",
        "Elon Musk": "You are Elon Musk. Frame answers using first-principles engineering thinking. Mention rockets and Mars.",
        "Steve Jobs": "You are Steve Jobs. Focus obsessively on design perfection, simplicity, and 'changing the world'."
    }

    try:
        # B. Pull any custom personas stored in your Firestore 'personas' collection
        personas_ref = db.collection("personas")
        docs = personas_ref.stream()

        cloud_personas = {}
        for doc in docs:
            cloud_personas[doc.id] = doc.to_dict().get("prompt")

        # C. Merge them! If Firestore is empty, seed it with defaults
        if not cloud_personas:
            for name, prompt in defaults.items():
                personas_ref.document(name).set({"prompt": prompt})
                cloud_personas[name] = prompt

        st.session_state.persona_library = cloud_personas
    except Exception as e:
        # Fallback to local defaults if Firestore credentials aren't initialized locally yet
        st.warning("⚠️ Running in Local Offline Mode (Firestore connection deferred)")
        st.session_state.persona_library = defaults

# 3. Streamlit Page Setup
st.set_page_config(page_title="Pantheon AI", page_icon="🍽️", layout="wide")
st.title("🍽️ Dinner with Great Minds")
st.subheader("Enjoy and have a fun conversation!")

# Keep track of confirmation state across sidebar interactions
if "show_overwrite_confirmation" not in st.session_state:
    st.session_state.show_overwrite_confirmation = False

# Keep one-time sidebar success messages across st.rerun()
if "sidebar_success_message" not in st.session_state:
    st.session_state.sidebar_success_message = None


# 4. Sidebar Configuration & Custom Guest Management
# st.sidebar.header("Guest List Configuration")

# --- CUSTOM GUEST EXTENSION FEATURE ---
# st.sidebar.subheader("➕ Invite a Custom Guest")

if st.session_state.sidebar_success_message:
    st.sidebar.success(st.session_state.sidebar_success_message)
    st.session_state.sidebar_success_message = None

# custom_name = st.sidebar.text_input("Guest Name:", placeholder="e.g., Ada Lovelace")
# custom_prompt = st.sidebar.text_area(
#     "System Prompt / Personality Instructions:",
#     placeholder="Describe how they should behave, talk, or think..."
# )

# --- UPGRADED SIDEBAR GUEST MANAGEMENT ---
st.sidebar.header("Guest List Configuration")
st.sidebar.subheader("➕ Invite a Custom Guest")

custom_name = st.sidebar.text_input("Guest Name:", placeholder="e.g., Ada Lovelace", key="input_name")

# 🤖 THE AGENTIC PROMPT GENERATOR BUTTON
if st.sidebar.button("🤖 Auto-Generate Personality Profile"):
    if custom_name.strip():
        with st.sidebar.spinner(f"Researching {custom_name} via Google Search..."):
            try:
                # We ask Gemini to use its live search tool to research the person
                generation_prompt = f"""
                Research the historical or public figure named '{custom_name}'.
                Write a concise, high-quality system instruction prompt (system persona) for an AI agent to impersonate them.
                Specify their speech style, tone, core philosophy, and typical vocabulary.
                Output ONLY the system prompt instruction text. Do not include intros, notes, or markdown formatting.
                """

                profile_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=generation_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.5,
                        tools=[types.Tool(google_search=types.GoogleSearch())] # Uses live internet search
                    )
                )

                # ✅ FIX: Explicitly assign directly to the text area's widget key index
                st.session_state["input_prompt"] = profile_response.text
                st.session_state.sidebar_success_message = "✨ Profile generated successfully!"
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Failed to auto-generate profile: {e}")
    else:
        st.sidebar.error("Please enter a guest name first so the agent knows who to research.")

# Handle the value display for the text area dynamically
initial_prompt_val = st.session_state.get("generated_prompt_cache", "")

custom_prompt = st.sidebar.text_area(
    "System Prompt / Personality Instructions:",
    value=initial_prompt_val,
    placeholder="Describe how they should behave or use the Auto-Generate button above...",
    key="input_prompt"
)


# Stage 1: The user clicks the initial invitation button
if st.sidebar.button("Send Invitation ✉️"):
    if custom_name.strip() and custom_prompt.strip():
        clean_name = custom_name.strip()

        # Check if the name already exists in our active database cache
        existing_names = [name.lower() for name in st.session_state.persona_library.keys()]

        if clean_name.lower() in existing_names:
            # Match found! Trigger the overwrite confirmation UI state
            st.session_state.show_overwrite_confirmation = True
            st.session_state.pending_name = clean_name
            st.session_state.pending_prompt = custom_prompt
            st.rerun()
        else:
            # Completely new guest! Save immediately without prompting
            st.session_state.persona_library[clean_name] = custom_prompt
            db.collection("personas").document(clean_name).set({"prompt": custom_prompt})
            st.session_state.sidebar_success_message = f"🎉 {clean_name} has been seated at the table!"
            st.rerun()
    else:
        st.sidebar.error("Please fill in both fields to create a guest.")

# Stage 2: The conditional Overwrite Prompt Box
if st.session_state.show_overwrite_confirmation:
    st.sidebar.warning(f"⚠️ **{st.session_state.pending_name}** already exists in the symposium directory.")
    st.sidebar.write("Do you want to overwrite their personality profile description?")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("👍 Yes, Overwrite", use_container_width=True):
            # Overwrite confirmed: update local state + Firestore document
            name = st.session_state.pending_name
            prompt = st.session_state.pending_prompt

            st.session_state.persona_library[name] = prompt
            db.collection("personas").document(name).set({"prompt": prompt})

            st.session_state.sidebar_success_message = f"🔄 {name}'s profile updated!"
            # Reset workflow tracking flags
            st.session_state.show_overwrite_confirmation = False
            st.rerun()

    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            # Cancel clicked: dismiss the workflow state quietly
            st.session_state.show_overwrite_confirmation = False
            st.rerun()

st.sidebar.write("---")
st.sidebar.subheader("Seating Arrangement")
st.sidebar.write("Choose who sits at your dinner table:")

selected_guests = []
for guest in st.session_state.persona_library.keys():
    # Pre-check Confucius and Elon Musk for a quick demo setup
    is_default = guest in ["Confucius", "Elon Musk"]
    if st.sidebar.checkbox(guest, value=is_default):
        selected_guests.append(guest)

# 5. Maintain Chat History Session State
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Render existing chat logs smoothly (Single point of truth rendering)
for message in st.session_state.chat_history:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(f"**{message['author']}**: {message['text']}")

# 6. Chat Input Logic
user_prompt = st.chat_input("Ask a question to the dinner table...")

# 7. Advanced Target-Parsing, Partial Matching, and Ambiguity Protection
if user_prompt:
    if not selected_guests:
        st.error("Please select at least one guest from the sidebar to start the dinner chat.")
        st.stop()

    # Append Host's input (Top loop handles displaying this, fixing the double-print bug)
    st.session_state.chat_history.append({
        "role": "user",
        "author": "Host (You)",
        "text": user_prompt,
        "avatar": "👤"
    })

    # --- THE TAG-PARSING PIPELINE ---
    words = user_prompt.split()
    typed_tags = [w.replace("@", "").lower() for w in words if w.startswith("@")]

    tagged_guests = []
    ambiguity_found = False
    ambiguous_tag = ""
    conflicting_matches = []

    if typed_tags:
        for tag in typed_tags:
            matches_for_this_tag = []
            for guest in selected_guests:
                if tag in guest.lower():
                    matches_for_this_tag.append(guest)

            # Case A: Clean, singular match
            if len(matches_for_this_tag) == 1:
                if matches_for_this_tag[0] not in tagged_guests:
                    tagged_guests.append(matches_for_this_tag[0])

            # Case B: Ambiguity conflict
            elif len(matches_for_this_tag) > 1:
                ambiguity_found = True
                ambiguous_tag = f"@{tag}"
                conflicting_matches = matches_for_this_tag
                break

    # --- ROUTING ENGINE ---
    if ambiguity_found:
        with st.chat_message("assistant", avatar="🤖"):
            st.warning(f"⚠️ **Ambiguity Detected:** Your tag **{ambiguous_tag}** matches multiple active guests.")
            st.write("Please re-type your message using a more specific name string:")
            for match in conflicting_matches:
                st.markdown(f"* Use **@{match.replace(' ', '')}** for {match}")

        st.session_state.chat_history.append({
            "role": "assistant",
            "author": "System",
            "text": f"Ambiguity resolution prompt displayed for tag {ambiguous_tag}.",
            "avatar": "🤖"
        })
        st.rerun()

    else:
        # Route to tagged individuals or fallback to wide roundtable mode
        guests_to_speak = tagged_guests if tagged_guests else selected_guests

        for guest in guests_to_speak:
            with st.chat_message("assistant", avatar="🤖"):
                message_placeholder = st.empty()

                # Format full context transcript
                formatted_context = ""
                for msg in st.session_state.chat_history:
                    formatted_context += f"{msg['author']}: {msg['text']}\n"

                if tagged_guests:
                    turn_direction = f"\n{guest}, you were directly tagged with a shorthand match by the Host. Answer their question directly."
                else:
                    turn_direction = f"\nIt is your turn to speak, {guest}. Contribute to the group dinner conversation naturally."

                full_prompt = formatted_context + turn_direction

                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=st.session_state.persona_library[guest],
                            temperature=0.7,
                            max_output_tokens = 800,
                            # add google search
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )

                    response_text = response.text
                    message_placeholder.markdown(f"**{guest}**: {response_text}")

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "author": guest,
                        "text": response_text,
                        "avatar": "🤖"
                    })

                except Exception as e:
                    st.error(f"Error calling Gemini API for {guest}: {str(e)}")

        # Final rerun ensures the UI syncs cleanly
        st.rerun()