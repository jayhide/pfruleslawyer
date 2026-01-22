import type {
  Settings,
  SSEEvent,
  HealthResponse,
  StatsResponse,
} from '../types';

/**
 * Stream a rules question to the API and yield SSE events.
 */
export async function* streamQuestion(
  question: string,
  settings: Settings
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      n_results: settings.n_results,
      model: settings.model,
      rerank: settings.rerank,
      use_tools: settings.use_tools,
      reranker_model: settings.reranker_model,
      verbose: settings.verbose,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEventType: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEventType = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEventType) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { event: currentEventType, data } as SSEEvent;
        } catch {
          console.warn('Failed to parse SSE data:', line);
        }
        currentEventType = null;
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    const lines = buffer.split('\n');
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEventType = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEventType) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { event: currentEventType, data } as SSEEvent;
        } catch {
          console.warn('Failed to parse SSE data:', line);
        }
      }
    }
  }
}

/**
 * Check API health.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health');
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get vector store statistics.
 */
export async function getStats(): Promise<StatsResponse> {
  const response = await fetch('/api/stats');
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}
