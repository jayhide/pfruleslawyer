import type { Settings } from '../types';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  settings: Settings;
  onUpdateSetting: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  onReset: () => void;
}

export function SettingsPanel({
  isOpen,
  onClose,
  settings,
  onUpdateSetting,
  onReset,
}: SettingsPanelProps) {
  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-80 bg-white shadow-xl z-50 transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Settings</h2>
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-gray-100 transition-colors"
              aria-label="Close settings"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Settings content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Model selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Model
              </label>
              <div className="space-y-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="model"
                    value="sonnet"
                    checked={settings.model === 'sonnet'}
                    onChange={() => onUpdateSetting('model', 'sonnet')}
                    className="w-4 h-4 text-primary-600"
                  />
                  <span className="text-sm text-gray-900">
                    Claude Sonnet{' '}
                    <span className="text-gray-500">(faster)</span>
                  </span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="model"
                    value="opus"
                    checked={settings.model === 'opus'}
                    onChange={() => onUpdateSetting('model', 'opus')}
                    className="w-4 h-4 text-primary-600"
                  />
                  <span className="text-sm text-gray-900">
                    Claude Opus{' '}
                    <span className="text-gray-500">(more capable)</span>
                  </span>
                </label>
              </div>
            </div>

            {/* Results count */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Results to retrieve:{' '}
                <span className="font-normal text-primary-600">
                  {settings.n_results}
                </span>
              </label>
              <input
                type="range"
                min="1"
                max="20"
                value={settings.n_results}
                onChange={(e) =>
                  onUpdateSetting('n_results', parseInt(e.target.value))
                }
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>1</span>
                <span>20</span>
              </div>
            </div>

            {/* Reranking toggle */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Use reranking
                </label>
                <p className="text-xs text-gray-500">
                  Improves result relevance
                </p>
              </div>
              <button
                role="switch"
                aria-checked={settings.rerank}
                onClick={() => onUpdateSetting('rerank', !settings.rerank)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.rerank ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.rerank ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Use tools toggle */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Allow follow-up searches
                </label>
                <p className="text-xs text-gray-500">
                  Let AI search for more rules
                </p>
              </div>
              <button
                role="switch"
                aria-checked={settings.use_tools}
                onClick={() => onUpdateSetting('use_tools', !settings.use_tools)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.use_tools ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.use_tools ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Reranker model */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Reranker model
              </label>
              <select
                value={settings.reranker_model ?? ''}
                onChange={(e) =>
                  onUpdateSetting(
                    'reranker_model',
                    e.target.value === ''
                      ? null
                      : (e.target.value as 'ms-marco' | 'bge-large' | 'llm-haiku')
                  )
                }
                disabled={!settings.rerank}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
              >
                <option value="">Auto (default)</option>
                <option value="ms-marco">MS-MARCO (fast)</option>
                <option value="bge-large">BGE-Large (better)</option>
                <option value="llm-haiku">LLM Haiku (experimental)</option>
              </select>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-200 pt-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                Debug
              </p>
            </div>

            {/* Show reasoning toggle */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Show reasoning
                </label>
                <p className="text-xs text-gray-500">
                  Display AI's thought process
                </p>
              </div>
              <button
                role="switch"
                aria-checked={settings.show_reasoning}
                onClick={() => onUpdateSetting('show_reasoning', !settings.show_reasoning)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.show_reasoning ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.show_reasoning ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Verbose logging toggle */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Verbose logging
                </label>
                <p className="text-xs text-gray-500">
                  Print debug output to server terminal
                </p>
              </div>
              <button
                role="switch"
                aria-checked={settings.verbose}
                onClick={() => onUpdateSetting('verbose', !settings.verbose)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.verbose ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.verbose ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-gray-200">
            <button
              onClick={onReset}
              className="w-full px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Reset to defaults
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
