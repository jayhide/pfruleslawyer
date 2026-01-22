import { useState, useCallback, useEffect } from 'react';
import type { Settings } from '../types';
import { DEFAULT_SETTINGS } from '../types';

const STORAGE_KEY = 'pf-rules-settings';

/**
 * Custom hook for managing settings with localStorage persistence.
 */
export function useSettings() {
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // Merge with defaults to handle new settings added in updates
        return { ...DEFAULT_SETTINGS, ...parsed };
      }
    } catch {
      console.warn('Failed to load settings from localStorage');
    }
    return DEFAULT_SETTINGS;
  });

  // Persist to localStorage when settings change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      console.warn('Failed to save settings to localStorage');
    }
  }, [settings]);

  const updateSetting = useCallback(
    <K extends keyof Settings>(key: K, value: Settings[K]) => {
      setSettings((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
  }, []);

  return { settings, updateSetting, resetSettings };
}
