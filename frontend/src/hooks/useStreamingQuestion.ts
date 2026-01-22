import { useReducer, useCallback, useRef } from 'react';
import type { ChatState, Settings, Message, ToolCallData, SourceInfo } from '../types';
import { initialChatState } from '../types';
import { streamQuestion } from '../services/api';

type ChatAction =
  | { type: 'START_STREAMING'; question: string }
  | { type: 'APPEND_TEXT'; text: string }
  | { type: 'ADD_TOOL_CALL'; toolCall: ToolCallData }
  | { type: 'ADD_SOURCES'; sources: SourceInfo[] }
  | { type: 'TURN_COMPLETE'; isFinal: boolean }
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
        currentTurnText: '',
        accumulatedReasoning: '',
        currentToolCalls: [],
        currentSources: [],
        error: null,
      };
    }

    case 'APPEND_TEXT':
      return {
        ...state,
        currentTurnText: state.currentTurnText + action.text,
      };

    case 'ADD_TOOL_CALL':
      return {
        ...state,
        currentToolCalls: [...state.currentToolCalls, action.toolCall],
      };

    case 'ADD_SOURCES': {
      // Deduplicate sources by URL
      const existingUrls = new Set(state.currentSources.map(s => s.url));
      const newSources = action.sources.filter(s => !existingUrls.has(s.url));
      return {
        ...state,
        currentSources: [...state.currentSources, ...newSources],
      };
    }

    case 'TURN_COMPLETE': {
      if (action.isFinal) {
        // Final turn - current text is the answer, don't move to reasoning
        return state;
      }
      // Not final - this turn's text was reasoning, accumulate it
      const newReasoning = state.currentTurnText
        ? state.accumulatedReasoning
          ? state.accumulatedReasoning + '\n\n---\n\n' + state.currentTurnText
          : state.currentTurnText
        : state.accumulatedReasoning;
      return {
        ...state,
        accumulatedReasoning: newReasoning,
        currentTurnText: '',
      };
    }

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
        content: state.currentTurnText,
        timestamp: new Date(),
        toolCalls:
          state.currentToolCalls.length > 0
            ? state.currentToolCalls
            : undefined,
        reasoning: state.accumulatedReasoning || undefined,
        sources:
          state.currentSources.length > 0
            ? state.currentSources
            : undefined,
      };
      return {
        ...state,
        messages: [...state.messages, assistantMessage],
        isStreaming: false,
        currentTurnText: '',
        accumulatedReasoning: '',
        currentToolCalls: [],
        currentSources: [],
      };
    }

    case 'CLEAR':
      return initialChatState;

    case 'ABORT': {
      // Combine any accumulated reasoning with current turn text for the partial message
      const partialContent = state.currentTurnText || state.accumulatedReasoning;
      return {
        ...state,
        isStreaming: false,
        // Keep any accumulated text as a partial message
        ...(partialContent && {
          messages: [
            ...state.messages,
            {
              id: generateId(),
              role: 'assistant' as const,
              content: (state.currentTurnText || state.accumulatedReasoning) + '\n\n*[Response interrupted]*',
              timestamp: new Date(),
              toolCalls:
                state.currentToolCalls.length > 0
                  ? state.currentToolCalls
                  : undefined,
              sources:
                state.currentSources.length > 0
                  ? state.currentSources
                  : undefined,
            },
          ],
        }),
        currentTurnText: '',
        accumulatedReasoning: '',
        currentToolCalls: [],
        currentSources: [],
      };
    }

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
              // Extract sources from tool results
              if (event.data.sources) {
                dispatch({ type: 'ADD_SOURCES', sources: event.data.sources });
              } else if (event.data.source) {
                dispatch({ type: 'ADD_SOURCES', sources: [event.data.source] });
              }
              break;
            case 'sources':
              dispatch({ type: 'ADD_SOURCES', sources: event.data.sources });
              break;
            case 'turn_complete':
              dispatch({ type: 'TURN_COMPLETE', isFinal: event.data.is_final });
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
