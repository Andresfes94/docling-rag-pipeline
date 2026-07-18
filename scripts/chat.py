#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path (streamlit subprocess needs this)
_proj_root = str(Path(__file__).resolve().parent.parent)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

logging.basicConfig(level=logging.WARNING)

import httpx
import streamlit as st

from src.llm.rag import answer_question, retrieve_context
from src.llm.client import LLMClient

st.set_page_config(
    page_title="RAG Chat — Financial Documents",
    page_icon="📊",
    layout="wide",
)

AVAILABLE_MODELS = [
    "llama3.2",
    "mistral",
    "deepseek-r1:1.5b",
    "deepseek-r1:7b",
    "llama3.1",
    "deepseek-r1:8b",
    "deepseek-r1:14b",
]

PROVIDERS = {
    "Ollama (localhost:11434)": "ollama",
    "LM Studio (localhost:1234)": "lmstudio",
}

API_URL = "http://localhost:8000"


@st.cache_resource
def check_api():
    try:
        resp = httpx.get(f"{API_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


@st.cache_resource
def get_ollama_models():
    try:
        client = LLMClient(provider="ollama")
        return client.list_models()
    except Exception:
        return []


def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "model" not in st.session_state:
        st.session_state.model = "llama3.2"
    if "provider" not in st.session_state:
        st.session_state.provider = "ollama"
    if "k" not in st.session_state:
        st.session_state.k = 5


def render_source_chunks(chunks: list[dict]):
    if not chunks:
        st.caption("No sources retrieved.")
        return
    for i, ch in enumerate(chunks):
        score = ch.get("score", 0)
        pct = f"{score*100:.0f}%"
        cols = st.columns([3, 1, 1])
        cols[0].markdown(f"**{ch.get('source', '?')}** — p.{ch.get('page', '?')}")
        cols[1].markdown(f"`{pct}`")
        preview = (ch.get("text", "")[:120] + "...") if len(ch.get("text", "")) > 120 else ch.get("text", "")
        cols[2].markdown(f"📄 *{preview}*")


init_session()

# ── Sidebar ──
with st.sidebar:
    st.title("📊 RAG Chat")
    st.caption("Retrieval-Augmented Generation for Financial Documents")

    api_ok = check_api()
    st.markdown(
        f"{'🟢' if api_ok else '🔴'} API: {'Connected' if api_ok else 'Offline'}",
    )

    ollama_models = get_ollama_models()
    if ollama_models:
        available = [m for m in AVAILABLE_MODELS if any(m in om for om in ollama_models)]
        if available:
            st.session_state.model = st.selectbox(
                "Model",
                available,
                index=available.index(st.session_state.model) if st.session_state.model in available else 0,
            )

    provider_label = st.selectbox(
        "Provider",
        list(PROVIDERS.keys()),
        index=0,
    )
    st.session_state.provider = PROVIDERS[provider_label]

    st.session_state.k = st.slider("Chunks to retrieve (k)", min_value=1, max_value=10, value=st.session_state.k)

    if st.button("🗑 Clear History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    if st.button("🔄 Reset All", use_container_width=True):
        st.session_state.messages = []
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    st.caption("Documents indexed: Math Finance, Quant Trading, PHASE404")

# ── Main chat area ──
st.title("💬 Ask your documents")

if not api_ok:
    st.error("API server is not reachable. Start it with:\n\n```\nuvicorn src.api.server:app\n```")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sources" in msg and msg["sources"]:
            with st.expander("📎 Sources used"):
                render_source_chunks(msg["sources"])

if prompt := st.chat_input("Ask a question about your documents..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.status("Thinking...", expanded=True) as status:
            st.write("🔍 Retrieving relevant passages...")
            try:
                result = answer_question(
                    question=prompt,
                    k=st.session_state.k,
                    model=st.session_state.model,
                    provider=st.session_state.provider,
                    api_url=API_URL,
                )
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

            status.update(label="✅ Complete!", state="complete")

        answer = result["answer"]
        sources = result.get("sources", [])
        all_chunks = result.get("all_chunks", [])
        latency = result.get("latency", 0)
        model = result.get("model", st.session_state.model)
        tokens = result.get("llm_tokens", 0)

        st.markdown(answer)

        meta_cols = st.columns(4)
        meta_cols[0].metric("Model", model)
        meta_cols[1].metric("Latency", f"{latency:.1f}s")
        meta_cols[2].metric("Tokens", tokens)
        meta_cols[3].metric("Chunks", len(all_chunks))

        if sources:
            with st.expander(f"📎 Sources used ({len(sources)} chunks)"):
                render_source_chunks(sources)

        if all_chunks and not sources:
            with st.expander(f"All retrieved chunks ({len(all_chunks)} total)"):
                render_source_chunks(all_chunks)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources or all_chunks,
        "model": model,
        "latency": latency,
        "tokens": tokens,
    })
