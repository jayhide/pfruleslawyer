import { useReducer, useCallback, useRef } from 'react';
import type { ChatState, Settings, Message, ToolCallData } from '../types';
import { initialChatState } from '../types';
import { streamQuestion } from '../services/api';

type ChatAction =
  | { type: 'START_STREAMING'; question: string }
  | { type: 'APPEND_TEXT'; text: string }
  | { type: 'ADD_TOOL_CALL'; toolCall: ToolCallData }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'COMPLETE_STREAMING' }
  | { type: 'CLEAR' }
  | { type: 'ABORT' };

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'START_STREAMING': {
      const userMessage: Message = {
        id: generateId(),
        role: 'user',
        content: action.question,
        timestamp: new Date(),
      };
      return {
        ...state,
        messages: [...state.messages, userMessage],
        isStreaming: true,
        currentStreamText: '',
        currentToolCalls: [],
        error: null,
      };
    }

    case 'APPEND_TEXT':
      return {
        ...state,
        currentStreamText: state.currentStreamText + action.text,
      };

    case 'ADD_TOOL_CALL':
      return {
        ...state,
        currentToolCalls: [...state.currentToolCalls, action.toolCall],
      };

    case 'SET_ERROR':
      return {
        ...state,
        isStreaming: false,
        error: action.error,
      };

    case 'COMPLETE_STREAMING': {
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: state.currentStreamText,
        timestamp: new Date(),
        toolCalls:
          state.currentToolCalls.length > 0
            ? state.currentToolCalls
            : undefined,
      };
      return {
        ...state,
        messages: [...state.messages, assistantMessage],
        isStreaming: false,
        currentStreamText: '',
        currentToolCalls: [],
      };
    }

    case 'CLEAR':
      return initialChatState;

    case 'ABORT':
      return {
        ...state,
        isStreaming: false,
        // Keep any accumulated text as a partial message
        ...(state.currentStreamText && {
          messages: [
            ...state.messages,
            {
              id: generateId(),
              role: 'assistant' as const,
              content: state.currentStreamText + '\n\n*[Response interrupted]*',
              timestamp: new Date(),
              toolCalls:
                state.currentToolCalls.length > 0
                  ? state.currentToolCalls
                  : undefined,
            },
          ],
        }),
        currentStreamText: '',
        currentToolCalls: [],
      };

    default:
      return state;
  }
}

/**
 * Custom hook for managing streaming questions and chat state.
 */
export function useStreamingQuestion() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const abortControllerRef = useRef<AbortController | null>(null);

  const askQuestion = useCallback(
    async (question: string, settings: Settings) => {
      // Abort any existing request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      abortControllerRef.current = new AbortController();
      dispatch({ type: 'START_STREAMING', question });

      try {
        for await (const event of streamQuestion(question, settings)) {
          // Check if aborted
          if (abortControllerRef.current?.signal.aborted) {
            dispatch({ type: 'ABORT' });
            return;
          }

          switch (event.event) {
            case 'text':
              dispatch({ type: 'APPEND_TEXT', text: event.data.content });
              break;
            case 'tool_call':
              dispatch({ type: 'ADD_TOOL_CALL', toolCall: event.data });
              break;
            case 'tool_result':
              // Tool results are informational - we could show them in UI
              // For now, we just track the tool calls
              break;
            case 'error':
              dispatch({ type: 'SET_ERROR', error: event.data.message });
              return;
            case 'done':
              dispatch({ type: 'COMPLETE_STREAMING' });
              return;
          }
        }
        // If stream ends without 'done' event
        dispatch({ type: 'COMPLETE_STREAMING' });
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          dispatch({ type: 'ABORT' });
        } else {
          dispatch({
            type: 'SET_ERROR',
            error: error instanceof Error ? error.message : String(error),
          });
        }
      } finally {
        abortControllerRef.current = null;
      }
    },
    []
  );

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      dispatch({ type: 'ABORT' });
    }
  }, []);

  const clearChat = useCallback(() => {
    dispatch({ type: 'CLEAR' });
  }, []);

  return {
    state,
    askQuestion,
    abort,
    clearChat,
  };
}
