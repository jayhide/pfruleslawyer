import { useRef, useEffect } from 'react';
import type { ChatState } from '../types';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';

interface ChatContainerProps {
  state: ChatState;
}

function WelcomeMessage() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="w-16 h-16 text-primary-500 mb-4"
      >
        <path d="M11.25 4.533A9.707 9.707 0 006 3a9.735 9.735 0 00-3.25.555.75.75 0 00-.5.707v14.25a.75.75 0 001 .707A8.237 8.237 0 016 18.75c1.995 0 3.823.707 5.25 1.886V4.533zM12.75 20.636A8.214 8.214 0 0118 18.75c.966 0 1.89.166 2.75.47a.75.75 0 001-.708V4.262a.75.75 0 00-.5-.707A9.735 9.735 0 0018 3a9.707 9.707 0 00-5.25 1.533v16.103z" />
      </svg>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">
        Pathfinder 1e Rules Expert
      </h2>
      <p className="text-gray-600 max-w-md">
        Ask any question about Pathfinder 1st Edition rules. I'll search through
        the rules database and provide accurate answers with citations.
      </p>
      <div className="mt-6 text-sm text-gray-500 space-y-1">
        <p>Try asking:</p>
        <p className="italic">"How does grappling work?"</p>
        <p className="italic">"What are the penalties for two-weapon fighting?"</p>
        <p className="italic">"How do I calculate my CMD?"</p>
      </div>
    </div>
  );
}

export function ChatContainer({ state }: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new content arrives
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages, state.currentStreamText]);

  const hasMessages = state.messages.length > 0 || state.isStreaming;

  return (
    <div className="flex-1 overflow-y-auto">
      {!hasMessages ? (
        <WelcomeMessage />
      ) : (
        <div className="max-w-4xl mx-auto px-4 py-6">
          {state.messages.map((message) =>
            message.role === 'user' ? (
              <UserMessage key={message.id} content={message.content} />
            ) : (
              <AssistantMessage
                key={message.id}
                content={message.content}
                toolCalls={message.toolCalls}
              />
            )
          )}

          {/* Streaming response */}
          {state.isStreaming && (
            <AssistantMessage
              content={state.currentStreamText || 'Thinking...'}
              toolCalls={state.currentToolCalls}
              isStreaming
            />
          )}

          {/* Error message */}
          {state.error && (
            <div className="flex justify-center mb-4">
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                <strong>Error:</strong> {state.error}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  );
}
