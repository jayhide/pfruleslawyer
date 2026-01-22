// Settings types - mirrors backend AskRequest model
export interface Settings {
  model: 'sonnet' | 'opus';
  n_results: number; // 1-20, default 7
  rerank: boolean; // default true
  use_tools: boolean; // default true
  reranker_model: 'ms-marco' | 'bge-large' | null; // default null
  verbose: boolean; // default false - enables server-side debug logging
}

export const DEFAULT_SETTINGS: Settings = {
  model: 'sonnet',
  n_results: 7,
  rerank: true,
  use_tools: true,
  reranker_model: null,
  verbose: false,
};

// API request/response types
export interface AskRequest {
  question: string;
  n_results?: number;
  model?: 'sonnet' | 'opus';
  rerank?: boolean;
  use_tools?: boolean;
  reranker_model?: 'ms-marco' | 'bge-large' | null;
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
}

export interface ErrorData {
  message: string;
}

export interface DoneData {
  complete: boolean;
}

export type SSEEventType = 'text' | 'tool_call' | 'tool_result' | 'error' | 'done';

export type SSEEvent =
  | { event: 'text'; data: TextEventData }
  | { event: 'tool_call'; data: ToolCallData }
  | { event: 'tool_result'; data: ToolResultData }
  | { event: 'error'; data: ErrorData }
  | { event: 'done'; data: DoneData };

// Chat/message types
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCallData[];
  isStreaming?: boolean;
}

export interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentStreamText: string;
  currentToolCalls: ToolCallData[];
  error: string | null;
}

export const initialChatState: ChatState = {
  messages: [],
  isStreaming: false,
  currentStreamText: '',
  currentToolCalls: [],
  error: null,
};
