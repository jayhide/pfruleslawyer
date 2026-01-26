import { useEffect, useState } from 'react';
import type { Transcript, TranscriptMessage, TranscriptContentBlock } from '../types';

interface TranscriptModalProps {
  transcript: Transcript;
  isOpen: boolean;
  onClose: () => void;
}

function ContentBlockRenderer({ block }: { block: TranscriptContentBlock }) {
  if (block.type === 'text') {
    return (
      <div className="whitespace-pre-wrap text-sm">{block.text}</div>
    );
  }

  if (block.type === 'tool_use') {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 my-2">
        <div className="text-xs font-semibold text-blue-700 mb-1">
          Tool Use: {block.name}
        </div>
        <pre className="text-xs bg-blue-100 rounded p-2 overflow-x-auto">
          {JSON.stringify(block.input, null, 2)}
        </pre>
      </div>
    );
  }

  if (block.type === 'tool_result') {
    const content = typeof block.content === 'string'
      ? block.content
      : JSON.stringify(block.content, null, 2);

    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-3 my-2">
        <div className="text-xs font-semibold text-green-700 mb-1">
          Tool Result
        </div>
        <pre className="text-xs bg-green-100 rounded p-2 overflow-x-auto max-h-64 overflow-y-auto">
          {content}
        </pre>
      </div>
    );
  }

  return null;
}

function MessageRenderer({ message, index }: { message: TranscriptMessage; index: number }) {
  const isUser = message.role === 'user';
  const bgClass = isUser ? 'bg-gray-100' : 'bg-white';
  const borderClass = isUser ? 'border-gray-300' : 'border-primary-200';

  const renderContent = () => {
    if (typeof message.content === 'string') {
      return <pre className="text-sm whitespace-pre-wrap overflow-x-auto">{message.content}</pre>;
    }

    return (
      <div>
        {message.content.map((block, i) => (
          <ContentBlockRenderer key={i} block={block} />
        ))}
      </div>
    );
  };

  return (
    <div className={`${bgClass} border ${borderClass} rounded-lg p-4 mb-4`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-xs font-semibold uppercase ${isUser ? 'text-gray-600' : 'text-primary-600'}`}>
          {message.role}
        </span>
        <span className="text-xs text-gray-400">Message {index + 1}</span>
      </div>
      {renderContent()}
    </div>
  );
}

export function TranscriptModal({ transcript, isOpen, onClose }: TranscriptModalProps) {
  const [systemExpanded, setSystemExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCopy = async () => {
    const text = JSON.stringify(transcript, null, 2);
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">API Transcript</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-1"
            >
              {copied ? (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-green-600">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  Copied!
                </>
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                  </svg>
                  Copy JSON
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              aria-label="Close"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* System Prompt (collapsible) */}
          <div className="mb-6">
            <button
              onClick={() => setSystemExpanded(!systemExpanded)}
              className="flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-gray-900"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className={`w-4 h-4 transition-transform ${systemExpanded ? 'rotate-90' : ''}`}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
              System Prompt
              <span className="text-xs text-gray-400 font-normal">
                ({transcript.system_prompt.length} chars)
              </span>
            </button>
            {systemExpanded && (
              <div className="mt-2 bg-purple-50 border border-purple-200 rounded-lg p-4">
                <pre className="text-sm whitespace-pre-wrap overflow-x-auto text-purple-900">
                  {transcript.system_prompt}
                </pre>
              </div>
            )}
          </div>

          {/* Messages */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              Messages ({transcript.messages.length})
            </h3>
            {transcript.messages.map((message, index) => (
              <MessageRenderer key={index} message={message} index={index} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
