// Settings types - mirrors backend AskRequest model
export interface Settings {
  model: 'sonnet' | 'opus';
  n_results: number; // 1-20, default 7
  rerank: boolean; // default true
  use_tools: boolean; // default true
  reranker_model: 'ms-marco' | 'bge-large' | 'llm-haiku' | null; // default null
  verbose: boolean; // default false - enables server-side debug logging
  show_reasoning: boolean; // default false - show AI reasoning in UI
  show_transcript: boolean; // default false - show transcript debug button
}

export const DEFAULT_SETTINGS: Settings = {
  model: 'sonnet',
  n_results: 7,
  rerank: true,
  use_tools: true,
  reranker_model: null,
  verbose: false,
  show_reasoning: false,
  show_transcript: false,
};

// API request/response types
export interface AskRequest {
  question: string;
  n_results?: number;
  model?: 'sonnet' | 'opus';
  rerank?: boolean;
  use_tools?: boolean;
  reranker_model?: 'ms-marco' | 'bge-large' | 'llm-haiku' | null;
}

export interface AskResponse {
  answer: string;
  question: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface StatsResponse {
  total_sections: number;
  index_loaded: boolean;
}

// Source info for d20pfsrd.com links
export interface SourceInfo {
  url: string;
  name: string;
  title: string;
}

// SSE event types
export interface TextEventData {
  content: string;
}

export interface ToolCallData {
  tool: 'search_rules' | 'follow_link';
  query?: string; // for search_rules
  url?: string; // for follow_link
}

export interface ToolResultData {
  tool: 'search_rules' | 'follow_link';
  sections_found?: number; // for search_rules
  found?: boolean; // for follow_link
  sources?: SourceInfo[]; // for search_rules
  source?: SourceInfo; // for follow_link
}

export interface SourcesEventData {
  sources: SourceInfo[];
}

export interface ErrorData {
  message: string;
}

// Transcript types (matches Claude API message format)
export interface TranscriptContentBlock {
  type: 'text' | 'tool_use' | 'tool_result';
  text?: string;           // for text blocks
  id?: string;             // for tool_use
  name?: string;           // for tool_use
  input?: Record<string, unknown>;  // for tool_use
  tool_use_id?: string;    // for tool_result
  content?: string | TranscriptContentBlock[];  // for tool_result
}

export interface TranscriptMessage {
  role: 'user' | 'assistant';
  content: string | TranscriptContentBlock[];
}

export interface Transcript {
  system_prompt: string;
  messages: TranscriptMessage[];
}

export interface DoneData {
  complete: boolean;
  transcript?: Transcript;
}

export interface TurnCompleteData {
  is_final: boolean;
}

export type SSEEventType = 'text' | 'tool_call' | 'tool_result' | 'sources' | 'turn_complete' | 'error' | 'done';

export type SSEEvent =
  | { event: 'text'; data: TextEventData }
  | { event: 'tool_call'; data: ToolCallData }
  | { event: 'tool_result'; data: ToolResultData }
  | { event: 'sources'; data: SourcesEventData }
  | { event: 'turn_complete'; data: TurnCompleteData }
  | { event: 'error'; data: ErrorData }
  | { event: 'done'; data: DoneData };

// Chat/message types
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCallData[];
  reasoning?: string; // AI's reasoning text before tool calls
  sources?: SourceInfo[]; // Source URLs for referenced content
  isStreaming?: boolean;
  transcript?: Transcript; // Full API transcript for debugging
}

export interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentTurnText: string; // Text from current agentic turn
  accumulatedReasoning: string; // Reasoning from previous turns
  currentToolCalls: ToolCallData[];
  currentSources: SourceInfo[]; // Sources accumulated during streaming
  currentTranscript: Transcript | null; // Transcript from done event
  error: string | null;
}

export const initialChatState: ChatState = {
  messages: [],
  isStreaming: false,
  currentTurnText: '',
  accumulatedReasoning: '',
  currentToolCalls: [],
  currentSources: [],
  currentTranscript: null,
  error: null,
};
