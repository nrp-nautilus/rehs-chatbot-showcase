import os
import streamlit as st
from rsearch import search
from dotenv import load_dotenv
from openai import OpenAI
from openai import BadRequestError
from openai import APITimeoutError
from openai import APIConnectionError
import time
import httpx
import re


load_dotenv()
client = OpenAI(api_key=os.environ["NRP_LLM_TOKEN"],
                base_url=os.environ.get("NRP_LLM_BASE_URL", "https://ellm.nrp-nautilus.io/v1"))

st.set_page_config(page_title="Recycle Assistant", page_icon="♻️")
st.title("♻️ Recycle Assistant", anchor = False)
st.caption("Helping You Recycle Effectively Using Trusted Documentation")

with st.sidebar:
    st.header("Settings")
    if st.button("🗑️ Clear chat"):
        st.session_state.pop("messages", None)
        st.rerun()
#                 if the question's answer is not in the documentation, say 
# "The provided documentation does not contain information regarding {question}"
#                 if the question is not recycle related, say 
#                 "I am a Recycle helper assistant and this question is not to 
#                 do with Recycling. Please only ask questions regarding recycling"  
system_prompt ={
            "role": "system", "content": 
            """
                You are a Recycling assistant, who always provides detailed in depth information.

                For every question You answer ONLY from the documentation provided in the user's message.             
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
        temperature=0.2,
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

if prompt := st.chat_input("Ask about Recycling..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    try:
        with st.spinner("Searching Recycling docs..."):
            standalone_query = rewrite_follow_up_with_ai(
                st.session_state.messages[:-1],
                prompt,
            )
            search_query = rewrite_search_query(standalone_query)
            retrieved = search(search_query, k=10)
            reranked = rerank(search_query, retrieved)

            # print("All retrieved and reranked chunks:", flush=True)
            # for index, chunk in enumerate(reranked, start=1):
            #     print(
            #         f"{index}. {chunk['title']} | "
            #         f"distance: {chunk['score']:.3f} | "
            #         f"reranked: {chunk['rank_score']:.3f}",
            #         flush=True,
            #     )

            if not reranked:
                st.error("No documentation chunks were returned by search.")
                st.stop()

            chunks = reranked[:5]

            print(f"Original question: {prompt}", flush=True)
            print(f"Rewritten search query: {search_query}", flush=True)
            print(f"Standalone query: {standalone_query}")

            print("\nChunks being sent to the LLM:", flush=True)

            # for index, chunk in enumerate(chunks, start=1):
            #     print(
            #         f"\n===== Chunk {index}: {chunk['title']} =====\n"
            #         f"Source: {chunk['source_url']}\n"
            #         f"Distance: {chunk['score']:.3f}\n"
            #         f"Reranked: {chunk['rank_score']:.3f}\n\n"
            #         f"{chunk['text']}\n",
            #         flush=True,
            #     )

    except BadRequestError as error:
        print(f"Embedding gateway error: {error}", flush=True)
        st.error(
            "The NRP embedding service is currently unavailable. "
            "Please try again shortly."
        )
        st.stop()
    
    context = "\n\n---\n\n".join(f"[Source: {c['title']}]\n{c['text']}" for c in chunks)
    # print("\n" + "=" * 80, flush=True)
    # print("FULL CONTEXT SENT TO LLM", flush=True)
    # print("=" * 80, flush=True)
    # print(context, flush=True)
    # print("=" * 80 + "\n", flush=True)

    grounded = f"""
    
    Example: Are plastic grocery bags recyclable in califoria, 
    Plastic grocery bags should never be placed in curbside recycling bins, 
    as they wrap around sorting equipment and cause facility shutdowns. 
    However, you can recycle them by dropping them off at 
    dedicated collection bins located at the front of major supermarkets a
    nd retail stores (like Target, Walmart, and local grocery stores).

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