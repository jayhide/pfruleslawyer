"""Async streaming logic for the rules lawyer API."""

import asyncio
from typing import AsyncGenerator

import anthropic
from dotenv import load_dotenv

from pfruleslawyer.rag import (
    MODEL_IDS,
    SEARCH_TOOL,
    FOLLOW_LINK_TOOL,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    format_context,
    execute_search,
)
from pfruleslawyer.search import RulesVectorStore

load_dotenv()


async def stream_rules_question(
    question: str,
    n_results: int = 7,
    model: str = "sonnet",
    rerank: bool = True,
    use_tools: bool = True,
    reranker_model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream a rules question answer, yielding events as they occur.

    Yields dicts with 'event' and 'data' keys for SSE formatting.

    Events:
        - text: Text chunk from Claude's response
        - tool_call: Claude is calling a tool
        - tool_result: Tool execution completed
        - error: An error occurred
        - done: Response complete
    """
    # Initialize resources (sync operations run in executor)
    loop = asyncio.get_event_loop()
    store = await loop.run_in_executor(None, RulesVectorStore)
    client = anthropic.AsyncAnthropic()

    # Initial search (synchronous - done before streaming starts)
    results = await loop.run_in_executor(
        None,
        lambda: store.query(
            question, n_results=n_results, rerank=rerank, reranker_model=reranker_model
        ),
    )
    seen_ids = {r["id"] for r in results}

    # Format initial context
    context = format_context(results, max_sections=n_results)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)
    messages = [{"role": "user", "content": user_prompt}]

    # Agentic loop
    max_tool_calls = 5
    tool_calls = 0

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

        except anthropic.APIError as e:
            yield {"event": "error", "data": {"message": str(e)}}
            return

        # If no tool use, we're done
        if final_message.stop_reason != "tool_use" or not tool_uses:
            yield {"event": "done", "data": {"complete": True}}
            return

        # Check tool call limit
        if tool_calls >= max_tool_calls:
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
                yield {
                    "event": "tool_call",
                    "data": {"tool": "search_rules", "query": query},
                }

                # Execute the search (sync, run in executor)
                search_results, new_ids = await loop.run_in_executor(
                    None,
                    lambda q=query: execute_search(
                        q,
                        store,
                        n_results=n_results,
                        rerank=rerank,
                        verbose=False,
                        seen_ids=seen_ids,
                        reranker_model=reranker_model,
                    ),
                )
                seen_ids.update(new_ids)

                yield {
                    "event": "tool_result",
                    "data": {"tool": "search_rules", "sections_found": len(new_ids)},
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
                yield {"event": "tool_call", "data": {"tool": "follow_link", "url": url}}

                # Resolve the link (sync, run in executor)
                result = await loop.run_in_executor(
                    None, lambda u=url: store.resolve_link(u)
                )

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
                        "data": {"tool": "follow_link", "found": True},
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
