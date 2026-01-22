import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ToolCallData, SourceInfo } from '../types';
import { SourcesList } from './SourcesList';

interface AssistantMessageProps {
  content: string;
  toolCalls?: ToolCallData[];
  reasoning?: string;
  sources?: SourceInfo[];
  showReasoning?: boolean;
  isStreaming?: boolean;
  isPending?: boolean; // Show with muted styling during streaming
}

function ToolCallBadge({ toolCall }: { toolCall: ToolCallData }) {
  const isSearch = toolCall.tool === 'search_rules';
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">
      {isSearch ? (
        <>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-3 h-3"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
          {toolCall.query}
        </>
      ) : (
        <>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-3 h-3"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"
            />
          </svg>
          Link
        </>
      )}
    </span>
  );
}

export function AssistantMessage({
  content,
  toolCalls,
  reasoning,
  sources,
  showReasoning,
  isStreaming,
  isPending,
}: AssistantMessageProps) {
  const [reasoningExpanded, setReasoningExpanded] = useState(false);

  return (
    <div className="flex justify-start mb-4">
      <div className={`max-w-[85%] bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm ${isPending ? 'opacity-60' : ''}`}>
        {/* Tool calls */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {toolCalls.map((tc, i) => (
              <ToolCallBadge key={i} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Reasoning section (collapsible) */}
        {reasoning && showReasoning && (
          <div className="mb-3 border-l-2 border-gray-300 pl-3">
            <button
              onClick={() => setReasoningExpanded(!reasoningExpanded)}
              className="text-sm text-gray-500 flex items-center gap-1 hover:text-gray-700"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className={`w-4 h-4 transition-transform ${reasoningExpanded ? 'rotate-90' : ''}`}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
              {reasoningExpanded ? 'Hide reasoning' : 'Show reasoning'}
            </button>
            {reasoningExpanded && (
              <div className="mt-2 text-sm text-gray-600 prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{reasoning}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div className="prose prose-sm max-w-none prose-p:my-2 prose-headings:my-2 prose-ul:my-2 prose-li:my-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>

        {/* Streaming indicator */}
        {isStreaming && (
          <span className="inline-block w-2 h-4 bg-primary-600 animate-pulse ml-1" />
        )}

        {/* Sources list (only show when not streaming) */}
        {!isStreaming && sources && sources.length > 0 && (
          <SourcesList sources={sources} />
        )}
      </div>
    </div>
  );
}
