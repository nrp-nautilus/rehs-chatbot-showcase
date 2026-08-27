import os
import streamlit as st
from search import search
from dotenv import load_dotenv
from openai import OpenAI
from openai import BadRequestError
from openai import APITimeoutError
from openai import APIConnectionError
import time
import httpx
import re
from command_router import run_kubernetes_command


load_dotenv()
client = OpenAI(api_key=os.environ["NRP_LLM_TOKEN"],
                base_url=os.environ.get("NRP_LLM_BASE_URL", "https://ellm.nrp-nautilus.io/v1"))

st.set_page_config(page_title="NRP Helper", page_icon="🤖")
st.title("🤖 NRP Helper", anchor = False)
st.caption("Your Trusted Assistant for NRP Knowledge")

with st.sidebar:
    st.header("Settings")
    if st.button("🗑️ Clear chat"):
        st.session_state.pop("messages", None)
        st.rerun()

system_prompt ={
            "role": "system", "content": 
            """
                You are an NRP documentation assistant.

                Answer questions about the National Research Platform (NRP), Kubernetes, and related topics.

                For every question:
                - First use the documentation provided in the user's message.
                - If the documentation contains the answer, answer using it.
                - If the documentation does not contain the answer but the question is still about NRP, Kubernetes, or a closely related topic, you may use your general knowledge.
                - If the question is unrelated to NRP, Kubernetes, or the provided documentation, respond exactly:

                "I am an NRP Helper. I can only answer questions about the National Research Platform (NRP), Kubernetes, and related topics using the provided documentation."
            """
            }

if "messages" not in st.session_state:
    st.session_state.messages = [system_prompt]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(msg["content"])

STOP_WORDS = {
    "a", "an", "the", "is", "are", "i", "you", "we",
    "do", "does", "did", "can", "could", "would", "should",
    "how", "what", "where", "when", "why", "which",
    "to", "of", "for", "in", "on", "with", "and", "or",
    "my", "your", "me", "please",
}

def rerank(question: str, chunks: list[dict]) -> list[dict]:
    normalized_question = question.lower().strip()

    query_words = [
        word
        for word in re.findall(r"\b[a-z0-9]+\b", normalized_question)
        if word not in STOP_WORDS
    ]

    query_word_set = set(query_words)

    # Build general two-word and three-word phrases.
    query_phrases = []

    for size in (2, 3):
        for index in range(len(query_words) - size + 1):
            phrase = " ".join(query_words[index:index + size])
            query_phrases.append(phrase)

    for chunk in chunks:
        title = chunk["title"].lower()
        text = chunk["text"].lower()
        combined_text = f"{title} {text}"

        title_words = set(
            re.findall(r"\b[a-z0-9]+\b", title)
        )

        text_words = set(
            re.findall(r"\b[a-z0-9]+\b", text)
        )

        title_matches = len(query_word_set & title_words)
        text_matches = len(query_word_set & text_words)

        # What fraction of the important query words occur in the chunk?
        coverage = (
            text_matches / len(query_word_set)
            if query_word_set
            else 0
        )

        # Reward matching any query phrase, not specific commands.
        phrase_matches = sum(
            1 for phrase in query_phrases
            if phrase in combined_text
        )

        chunk["rank_score"] = (
            chunk["score"]
            - title_matches * 0.08
            - text_matches * 0.03
            - coverage * 0.15
            - phrase_matches * 0.08
        )

    return sorted(chunks, key=lambda chunk: chunk["rank_score"])


def rewrite_single_query(question: str) -> str:
    query = question.lower().strip()

    query = re.sub(
        r"^(?:how\s+(?:do|can|could|would)\s+(?:i|you)\s+|"
        r"how\s+to\s+)",
        "",
        query,
    )

    query = re.sub(r"[?.!,;:]+$", "", query)

    return " ".join(query.split()) or question


def rewrite_search_query(question: str) -> str:
    questions = question.splitlines()

    rewritten_questions = [
        rewrite_single_query(item)
        for item in questions
        if item.strip()
    ]

    return " ".join(rewritten_questions)

def token_stream(messages):
    request_start = time.time()

    print("Sending request to LLM...", flush=True)

    
    stream = client.chat.completions.create(
        model="qwen3-small",
        messages=messages,
        stream=True,
        timeout=60,
        temperature=0.8,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )

    print(
        f"LLM request returned stream object after "
        f"{time.time() - request_start:.2f} seconds",
        flush=True,
    )

    first_token_received = False

    for chunk in stream:
        if not chunk.choices:
            continue

        content = chunk.choices[0].delta.content

        if content:
            if not first_token_received:
                print(
                    f"First token received after "
                    f"{time.time() - request_start:.2f} seconds",
                    flush=True,
                )
                first_token_received = True

            yield content

def rewrite_follow_up_with_ai(messages, current_question):
    recent_history = [
        message
        for message in messages
        if message["role"] in {"user", "assistant"}
    ][-4:]

    rewrite_messages = [
        {
            "role": "system",
            "content": (
                "/no think\n\n"
                "Rewrite the latest user question as a standalone search query. "
                "Use conversation history only to resolve references such as "
                "'it', 'them', 'that', or 'there'. "
                "If the latest question is independent, return it unchanged. "
                "Do not answer the question. "
                "Return only the rewritten query."
            ),
        },
        *recent_history,
        {
            "role": "user",
            "content": current_question,
        },
    ]

    response = client.chat.completions.create(
        model="qwen3-small",
        messages=rewrite_messages,
        temperature=0,
        timeout=30,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )

    return response.choices[0].message.content.strip()

if prompt := st.chat_input("Ask about NRP..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    is_command, command_result = run_kubernetes_command(prompt)

    if is_command:
        with st.chat_message("assistant"):
            st.code(command_result, language="text")

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": command_result,
            }
        )

        st.stop()

    try:
        with st.spinner("Searching NRP docs..."):
            standalone_query = rewrite_follow_up_with_ai(
                st.session_state.messages[:-1],
                prompt,
            )
            search_query = rewrite_search_query(standalone_query)
            retrieved = search(search_query, k=10)
            reranked = rerank(search_query, retrieved)

            print("All retrieved and reranked chunks:", flush=True)
            for index, chunk in enumerate(reranked, start=1):
                print(
                    f"{index}. {chunk['title']} | "
                    f"distance: {chunk['score']:.3f} | "
                    f"reranked: {chunk['rank_score']:.3f}",
                    flush=True,
                )

            if not reranked:
                st.error("No documentation chunks were returned by search.")
                st.stop()

            chunks = reranked[:5]

            print(f"Original question: {prompt}", flush=True)
            print(f"Rewritten search query: {search_query}", flush=True)

            print("\nChunks being sent to the LLM:", flush=True)

            for index, chunk in enumerate(chunks, start=1):
                print(
                    f"\n===== Chunk {index}: {chunk['title']} =====\n"
                    f"Source: {chunk['source_url']}\n"
                    f"Distance: {chunk['score']:.3f}\n"
                    f"Reranked: {chunk['rank_score']:.3f}\n\n"
                    f"{chunk['text']}\n",
                    flush=True,
                )

    except BadRequestError as error:
        print(f"Embedding gateway error: {error}", flush=True)
        st.error(
            "The NRP embedding service is currently unavailable. "
            "Please try again shortly."
        )
        st.stop()
    
    context = "\n\n---\n\n".join(f"[Source: {c['title']}]\n{c['text']}" for c in chunks)
    print("\n" + "=" * 80, flush=True)
    print("FULL CONTEXT SENT TO LLM", flush=True)
    print("=" * 80, flush=True)
    print(context, flush=True)
    print("=" * 80 + "\n", flush=True)

    grounded = f"""
    
    Example: what is kubernetes?
    Kubernetes is an open-source container orchestration platform.

    /no think

    DOCUMENTATION:
    {context}

    QUESTION:
    {prompt}
    """
    conversation_history = [
        message
        for message in st.session_state.messages[1:-1]
        if message["role"] in {"user", "assistant"}
    ]

    messages_for_llm = [
        system_prompt,
        *conversation_history,
        {
            "role": "user",
            "content": grounded,
        },
    ]

    with st.chat_message("assistant"):
        print("Calling LLM...", flush=True)
        prompt_characters = sum(
            len(message.get("content", ""))
            for message in messages_for_llm
        )

        print(f"Messages sent: {len(messages_for_llm)}", flush=True)

        print(f"Total prompt size: {prompt_characters} characters", flush=True)
        try:
            with st.spinner("Generating answer..."):
                answer = st.write_stream(token_stream(messages_for_llm))

        except (APITimeoutError, httpx.ReadTimeout) as error:
            print(f"LLM timeout: {error}", flush=True)
            st.error(
                "The model stopped responding before completing the answer. "
                "Please try again."
            )
            st.stop()

        except APIConnectionError as error:
            print(f"LLM connection error: {error}", flush=True)
            st.error("Could not connect to the LLM service.")
            st.stop()
        print("LLM finished", flush=True)

        with st.expander("📚 Sources"):
            for chunk in chunks:
                st.markdown(
                    f"- [{chunk['title']}]({chunk['source_url']}) "
                    f"*(distance: {chunk['score']:.3f}, "
                    f"reranked: {chunk['rank_score']:.3f})*"
                )

    st.session_state.messages.append({"role": "assistant", "content": answer})