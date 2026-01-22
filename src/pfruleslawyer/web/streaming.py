"""Async streaming logic for the rules lawyer API."""

import asyncio
import sys
import time
from typing import AsyncGenerator

import anthropic
from dotenv import load_dotenv

from pfruleslawyer.core import TimingContext
from pfruleslawyer.rag import (
    MODEL_IDS,
    SEARCH_TOOL,
    FOLLOW_LINK_TOOL,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    format_context,
    execute_search,
    Colors,
    format_score_breakdown,
)
from pfruleslawyer.search import RulesVectorStore

load_dotenv()


def log_initial_search(question: str, results: list[dict], verbose: bool = False) -> None:
    """Log initial search results to stderr (mirrors CLI output)."""
    print(f"{Colors.CYAN}[Initial search]{Colors.RESET} \"{question}\"", file=sys.stderr)
    print(f"{Colors.CYAN}Found {len(results)} relevant sections:{Colors.RESET}", file=sys.stderr)

    for r in results:
        source = r.get('source_name', r['source_file'])
        print(f"  {Colors.YELLOW}- {r['title']}{Colors.RESET} {Colors.DIM}({source}){Colors.RESET}", file=sys.stderr)

        # Show score breakdown
        for line in format_score_breakdown(r):
            print(line, file=sys.stderr)

        # In verbose mode, print the full section content
        if verbose:
            content = r.get("content", "")
            # Strip the metadata header if present
            if "\n\n" in content:
                parts = content.split("\n\n", 1)
                if len(parts) > 1:
                    content = parts[1]
            print(f"\n{Colors.DIM}{content}{Colors.RESET}\n", file=sys.stderr)
            print(f"{Colors.DIM}---{Colors.RESET}", file=sys.stderr)

    print(file=sys.stderr)


def log_context(context: str, user_prompt: str, verbose: bool = False) -> None:
    """Log context information to stderr."""
    print(f"Context length: {len(context)} chars", file=sys.stderr)

    if verbose:
        print(f"\n{Colors.DIM}{'='*60}{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.CYAN}[Full prompt sent to model]{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.DIM}{'='*60}{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.DIM}{user_prompt}{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.DIM}{'='*60}{Colors.RESET}\n", file=sys.stderr)


def log_tool_call(tool_name: str, tool_calls: int, query: str | None = None, url: str | None = None) -> None:
    """Log a tool call to stderr."""
    if tool_name == "search_rules":
        print(f"{Colors.CYAN}[Search {tool_calls}]{Colors.RESET} \"{query}\"", file=sys.stderr)
    elif tool_name == "follow_link":
        print(f"{Colors.CYAN}[Follow link {tool_calls}]{Colors.RESET} {url}", file=sys.stderr)


def log_follow_link_result(result: dict, verbose: bool = False) -> None:
    """Log follow_link result to stderr."""
    if "error" in result:
        print(f"  {Colors.RED}Error: {result['error']}{Colors.RESET}", file=sys.stderr)
    else:
        print(f"  {Colors.YELLOW}-> {result['title']}{Colors.RESET} {Colors.DIM}({result['source_name']}){Colors.RESET}", file=sys.stderr)

        if verbose:
            print(f"\n{Colors.DIM}{result['content']}{Colors.RESET}\n", file=sys.stderr)
            print(f"{Colors.DIM}---{Colors.RESET}", file=sys.stderr)


def log_reasoning(text: str) -> None:
    """Log model reasoning (shown when model uses tools)."""
    print(f"{Colors.MAGENTA}[Reasoning] {text}{Colors.RESET}", file=sys.stderr)


def log_max_tool_calls(max_calls: int) -> None:
    """Log max tool calls warning."""
    print(f"{Colors.RED}[Warning] Reached max tool calls ({max_calls}), returning current response{Colors.RESET}", file=sys.stderr)


async def stream_rules_question(
    question: str,
    n_results: int = 7,
    model: str = "sonnet",
    rerank: bool = True,
    use_tools: bool = True,
    reranker_model: str | None = None,
    verbose: bool = False,
    timing: bool = False,
) -> AsyncGenerator[dict, None]:
    """Stream a rules question answer, yielding events as they occur.

    Yields dicts with 'event' and 'data' keys for SSE formatting.

    Events:
        - text: Text chunk from Claude's response
        - tool_call: Claude is calling a tool
        - tool_result: Tool execution completed
        - timing: Timing data for an operation (when timing=True)
        - error: An error occurred
        - done: Response complete

    Args:
        question: The rules question to ask
        n_results: Number of sections to retrieve
        model: Model to use ('sonnet' or 'opus')
        rerank: Whether to use cross-encoder reranking
        use_tools: Whether to allow model to issue searches
        reranker_model: Reranker model to use
        verbose: Whether to print verbose debug output to stderr
        timing: Whether to emit timing events in the SSE stream
    """
    # Initialize timing context if requested
    ctx = TimingContext() if timing else None

    # Initialize resources (sync operations run in executor)
    loop = asyncio.get_event_loop()

    start = time.perf_counter()
    store = await loop.run_in_executor(None, RulesVectorStore)
    if ctx:
        duration_ms = (time.perf_counter() - start) * 1000
        ctx.record("Vector store init", duration_ms)
        yield {"event": "timing", "data": {"operation": "vector_store_init", "duration_ms": round(duration_ms)}}

    client = anthropic.AsyncAnthropic()

    # Initial search (synchronous - done before streaming starts)
    start = time.perf_counter()
    results = await loop.run_in_executor(
        None,
        lambda: store.query(
            question, n_results=n_results, rerank=rerank, reranker_model=reranker_model
        ),
    )
    if ctx:
        duration_ms = (time.perf_counter() - start) * 1000
        ctx.record("Initial search", duration_ms)
        yield {"event": "timing", "data": {"operation": "initial_search", "duration_ms": round(duration_ms)}}

    seen_ids = {r["id"] for r in results}

    # Emit sources event for initial search results
    initial_sources = [
        {"url": r["source_file"], "name": r.get("source_name", r["source_file"]), "title": r["title"]}
        for r in results
    ]
    yield {"event": "sources", "data": {"sources": initial_sources}}

    # Log initial search results
    log_initial_search(question, results, verbose=verbose)

    # Format initial context
    context = format_context(results, max_sections=n_results)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)
    messages = [{"role": "user", "content": user_prompt}]

    # Log context info
    log_context(context, user_prompt, verbose=verbose)

    # Agentic loop
    max_tool_calls = 5
    tool_calls = 0
    model_turn = 0

    while True:
        kwargs = {
            "model": MODEL_IDS[model],
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        }
        if use_tools:
            kwargs["tools"] = [SEARCH_TOOL, FOLLOW_LINK_TOOL]

        # Stream this turn
        text_content = ""
        tool_uses = []
        current_tool_use = None
        current_tool_input_json = ""
        model_turn += 1
        model_start = time.perf_counter()

        try:
            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            # Starting a tool use block
                            current_tool_use = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                            }
                            current_tool_input_json = ""

                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            # Yield text chunk immediately
                            yield {"event": "text", "data": {"content": event.delta.text}}
                            text_content += event.delta.text
                        elif event.delta.type == "input_json_delta":
                            # Accumulate tool input JSON
                            current_tool_input_json += event.delta.partial_json

                    elif event.type == "content_block_stop":
                        # If we were building a tool use, finalize it
                        if current_tool_use is not None:
                            import json

                            try:
                                current_tool_use["input"] = json.loads(
                                    current_tool_input_json
                                )
                            except json.JSONDecodeError:
                                current_tool_use["input"] = {}
                            tool_uses.append(current_tool_use)
                            current_tool_use = None
                            current_tool_input_json = ""

                # Get final message for stop reason
                final_message = await stream.get_final_message()

                # Record model timing
                if ctx:
                    duration_ms = (time.perf_counter() - model_start) * 1000
                    ctx.record(f"Model call {model_turn}", duration_ms)
                    yield {"event": "timing", "data": {"operation": f"model_call_{model_turn}", "duration_ms": round(duration_ms)}}

        except anthropic.APIError as e:
            yield {"event": "error", "data": {"message": str(e)}}
            return

        # If no tool use, we're done - this turn was the final answer
        if final_message.stop_reason != "tool_use" or not tool_uses:
            # Emit final timing summary
            if ctx:
                yield {"event": "timing_summary", "data": ctx.as_dict()}
            yield {"event": "turn_complete", "data": {"is_final": True}}
            yield {"event": "done", "data": {"complete": True}}
            return

        # Log reasoning if model provided text before tool calls
        if text_content and verbose:
            log_reasoning(text_content)

        # Check tool call limit
        if tool_calls >= max_tool_calls:
            log_max_tool_calls(max_tool_calls)
            # Emit final timing summary
            if ctx:
                yield {"event": "timing_summary", "data": ctx.as_dict()}
            yield {"event": "turn_complete", "data": {"is_final": True}}
            yield {
                "event": "error",
                "data": {"message": f"Max tool calls ({max_tool_calls}) reached"},
            }
            return

        # Process tool calls
        tool_results = []
        for tool_use in tool_uses:
            if tool_use["name"] == "search_rules":
                query = tool_use["input"].get("query", "")
                tool_calls += 1

                # Log and emit event
                log_tool_call("search_rules", tool_calls, query=query)
                yield {
                    "event": "tool_call",
                    "data": {"tool": "search_rules", "query": query},
                }

                # Execute the search (sync, run in executor)
                # Note: execute_search already prints results via print_search_results
                tool_start = time.perf_counter()
                search_results, new_ids, new_results = await loop.run_in_executor(
                    None,
                    lambda q=query: execute_search(
                        q,
                        store,
                        n_results=n_results,
                        rerank=rerank,
                        verbose=verbose,
                        seen_ids=seen_ids,
                        reranker_model=reranker_model,
                    ),
                )
                if ctx:
                    duration_ms = (time.perf_counter() - tool_start) * 1000
                    ctx.record("Tool: search_rules", duration_ms)
                    yield {"event": "timing", "data": {"operation": "tool_search_rules", "duration_ms": round(duration_ms)}}
                seen_ids.update(new_ids)

                # Extract source info from new results
                sources = [
                    {"url": r["source_file"], "name": r.get("source_name", r["source_file"]), "title": r["title"]}
                    for r in new_results
                ]
                yield {
                    "event": "tool_result",
                    "data": {"tool": "search_rules", "sections_found": len(new_ids), "sources": sources},
                }

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": search_results,
                    }
                )

            elif tool_use["name"] == "follow_link":
                url = tool_use["input"].get("url", "")
                tool_calls += 1

                # Log and emit event
                log_tool_call("follow_link", tool_calls, url=url)
                yield {"event": "tool_call", "data": {"tool": "follow_link", "url": url}}

                # Resolve the link (sync, run in executor)
                tool_start = time.perf_counter()
                result = await loop.run_in_executor(
                    None, lambda u=url: store.resolve_link(u)
                )
                if ctx:
                    duration_ms = (time.perf_counter() - tool_start) * 1000
                    ctx.record("Tool: follow_link", duration_ms)
                    yield {"event": "timing", "data": {"operation": "tool_follow_link", "duration_ms": round(duration_ms)}}

                # Log the result
                log_follow_link_result(result, verbose=verbose)

                if "error" in result:
                    content = f"Error: {result['error']}"
                    if "available_sections" in result:
                        content += (
                            f"\nAvailable sections: {', '.join(result['available_sections'])}"
                        )
                    yield {
                        "event": "tool_result",
                        "data": {"tool": "follow_link", "found": False},
                    }
                else:
                    content = f"### {result['title']} (from {result['source_name']})\n\n{result['content']}"

                    # Check for duplicate and track
                    result_id = result.get("id")
                    if result_id:
                        if result_id in seen_ids:
                            content = f"*This section was already retrieved*\n\n{content}"
                        else:
                            seen_ids.add(result_id)

                    yield {
                        "event": "tool_result",
                        "data": {
                            "tool": "follow_link",
                            "found": True,
                            "source": {"url": url, "name": result["source_name"], "title": result["title"]},
                        },
                    }

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": content,
                    }
                )

        # Add assistant response and tool results to messages
        # Need to reconstruct the content blocks
        assistant_content = []
        if text_content:
            assistant_content.append({"type": "text", "text": text_content})
        for tu in tool_uses:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tu["id"],
                    "name": tu["name"],
                    "input": tu["input"],
                }
            )

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

        # Signal that this turn's text was reasoning (not the final answer)
        yield {"event": "turn_complete", "data": {"is_final": False}}
