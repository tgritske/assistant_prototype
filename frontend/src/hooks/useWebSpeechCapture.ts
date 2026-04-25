import { useCallback, useEffect, useRef, useState } from "react";

const SpeechRecognitionAPI =
  (window as any).SpeechRecognition ||
  (window as any).webkitSpeechRecognition;

const LANG_MAP: Record<string, string> = {
  ru: "ru-RU", en: "en-US", es: "es-US",
  zh: "zh-CN", ar: "ar-SA", uk: "uk-UA",
  fr: "fr-FR", de: "de-DE", vi: "vi-VN",
  pl: "pl-PL", hi: "hi-IN", ja: "ja-JP",
  ko: "ko-KR", tl: "tl-PH", it: "it-IT",
  pt: "pt-BR",
};

export function speechLangCode(lang: string | null | undefined): string {
  if (!lang) return "ru-RU";
  return LANG_MAP[lang] ?? LANG_MAP[lang.split("-")[0]] ?? lang;
}

export function useWebSpeechCapture(
  onResult: (text: string, isFinal: boolean) => void
) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recRef = useRef<any>(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  // Keep the active language so restarts inherit it
  const langRef = useRef<string>("ru-RU");
  // Prevent re-entry during teardown
  const stoppingRef = useRef(false);
  const activeRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);

  const _createAndStart = useCallback((lang: string) => {
    if (!SpeechRecognitionAPI) return;
    const rec = new SpeechRecognitionAPI();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang;
    rec.maxAlternatives = 1;
    recRef.current = rec;

    rec.onresult = (e: any) => {
      let interim = "";
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else interim += t;
      }
      if (finalText) onResultRef.current(finalText.trim(), true);
      else if (interim) onResultRef.current(interim.trim(), false);
    };

    rec.onerror = (e: any) => {
      // "no-speech" is normal — ignore. Other errors surface to UI.
      if (e.error !== "no-speech" && e.error !== "aborted") {
        setError(`Microphone error: ${e.error}`);
        activeRef.current = false;
        setIsRecording(false);
      }
    };

    rec.onend = () => {
      recRef.current = null;
      // Auto-restart keeps recognition alive past the browser time limit.
      if (activeRef.current && !stoppingRef.current) {
        if (restartTimerRef.current !== null) {
          window.clearTimeout(restartTimerRef.current);
        }
        restartTimerRef.current = window.setTimeout(() => {
          restartTimerRef.current = null;
          _createAndStart(langRef.current);
        }, 150);
      }
    };

    rec.start();
  }, []);

  const start = useCallback(async (lang?: string) => {
    setError(null);
    if (!SpeechRecognitionAPI) {
      setError("Speech recognition not supported — please use Chrome or Edge");
      return;
    }
    const resolvedLang = lang ?? langRef.current;
    langRef.current = resolvedLang;
    stoppingRef.current = false;
    activeRef.current = true;

    // Stop any existing instance before starting a new one
    if (recRef.current) {
      try { recRef.current.stop(); } catch { }
      recRef.current = null;
    }

    _createAndStart(resolvedLang);
    setIsRecording(true);
  }, [_createAndStart]);

  const stop = useCallback(() => {
    stoppingRef.current = true;
    activeRef.current = false;
    if (recRef.current) {
      try { recRef.current.stop(); } catch { }
      recRef.current = null;
    }
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    setIsRecording(false);
  }, []);

  // Restart with new language when caller language is identified mid-call
  const setLanguage = useCallback((lang: string) => {
    const bcp = speechLangCode(lang);
    if (bcp === langRef.current) return;
    langRef.current = bcp;
    if (activeRef.current) {
      // Restart the recognizer with the new language
      if (recRef.current) {
        try { recRef.current.stop(); } catch { }
        recRef.current = null;
      }
      if (restartTimerRef.current !== null) {
        window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
      _createAndStart(bcp);
    }
  }, [_createAndStart]);

  useEffect(() => () => stop(), [stop]);

  return { isRecording, error, start, stop, setLanguage };
}
