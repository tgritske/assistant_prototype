import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { FormPanel } from "./components/FormPanel";
import { DispatchModal } from "./components/DispatchModal";
import { ScenarioPicker } from "./components/ScenarioPicker";
import { StatusBar } from "./components/StatusBar";
import { SuggestionsPanel } from "./components/SuggestionsPanel";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { TranslationPanel } from "./components/TranslationPanel";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useCallState } from "./hooks/useCallState";
import { useDispatchSocket } from "./hooks/useDispatchSocket";
import type { FormFields } from "./types/dispatch";

export default function App() {
  const { state, onServerMessage, setConnected, editField, dismissSuggestion, clearError } =
    useCallState();

  const { status, send, sendBinary } = useDispatchSocket({ onMessage: onServerMessage });

  const { isRecording, error: micError, start: startMic, stop: stopMic } =
    useAudioCapture(sendBinary);

  useEffect(() => setConnected(status === "open"), [status, setConnected]);

  // Elapsed call timer
  const [elapsed, setElapsed] = useState(0);
  const [showDispatch, setShowDispatch] = useState(false);
  const callStartedAt = useRef<number | null>(null);
  useEffect(() => {
    if (state.inCall && callStartedAt.current === null) {
      callStartedAt.current = Date.now();
    }
    if (!state.inCall) {
      callStartedAt.current = null;
      setElapsed(0);
      return;
    }
    const t = setInterval(() => {
      if (callStartedAt.current)
        setElapsed((Date.now() - callStartedAt.current) / 1000);
    }, 500);
    return () => clearInterval(t);
  }, [state.inCall]);

  // Stop mic when call ends (scenario finished or manual stop)
  useEffect(() => {
    if (!state.inCall && isRecording) stopMic();
  }, [state.inCall, isRecording, stopMic]);

  const playScenario = useCallback(
    (id: string) => {
      send({ type: "play_scenario", scenario_id: id });
    },
    [send]
  );
  const stopCall = useCallback(() => {
    stopMic();
    send({ type: "stop_call" });
  }, [send, stopMic]);

  const startLiveMic = useCallback(async () => {
    send({ type: "start_call", input_mode: "live_audio" });
    await startMic();
  }, [send, startMic]);

  const sendManualEdit = useCallback(
    (field: keyof FormFields, value: unknown) => {
      editField(field, value);
      send({ type: "manual_edit", field, value });
    },
    [editField, send]
  );

  const speak = useCallback(
    (text: string, language: string, translate = false) => {
      send({ type: "tts_request", text, language, translate });
    },
    [send]
  );

  const onDispatch = useCallback(() => {
    setShowDispatch(true);
  }, []);

  const canDispatch = Boolean(state.form.incident_type && state.form.location);

  // false = expanded (demo mode); change to true for production default
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="h-screen flex flex-col bg-[var(--color-bg)]">
      <StatusBar
        connected={state.connected}
        inCall={state.inCall}
        callId={state.callId}
        elapsed={elapsed}
        llmBackend={state.llmBackend}
        llmModel={state.llmModel}
        llmMode={state.llmMode}
      />

      {(state.errorMessage || micError) && (
        <div className="bg-amber-950/40 border-b border-amber-900 text-amber-200 text-xs px-4 py-2 flex justify-between items-center">
          <span>
            <span className="font-semibold tracking-wide uppercase text-[10px] mr-2 px-1.5 py-0.5 rounded border border-amber-700 bg-amber-950/60">
              {micError ? "Mic Error" : "Notice"}
            </span>
            {micError ?? state.errorMessage}
          </span>
          <button onClick={clearError} className="opacity-60 hover:opacity-100 px-2">
            <X size={14} />
          </button>
        </div>
      )}

      <main
        className="flex-1 min-h-0 grid"
        style={{ gridTemplateColumns: `${sidebarOpen ? 260 : 40}px 1fr 360px minmax(0,40%)` }}
      >
        <ScenarioPicker
          scenarios={state.scenarios}
          inCall={state.inCall}
          activeId={state.scenarioId}
          onPlay={playScenario}
          onStop={stopCall}
          onLiveMic={startLiveMic}
          micActive={isRecording}
          collapsed={!sidebarOpen}
          onToggleCollapse={() => setSidebarOpen((v) => !v)}
        />

        <TranscriptPanel
          transcript={state.operatorTranscript}
          interimText={state.operatorTranscriptInterim}
          originalTranscript={state.transcript}
          originalInterimText={state.transcriptInterim}
          highlights={state.highlights}
          inCall={state.inCall}
          callerLanguage={state.callerLanguage}
          callerLanguageName={state.callerLanguageName}
          playbackAudioUrl={state.playbackAudioUrl}
        />

        <div className="flex flex-col min-h-0 border-r border-[var(--color-border)]">
          <SuggestionsPanel
            suggestions={state.suggestions}
            onDismiss={dismissSuggestion}
            onDone={dismissSuggestion}
            callerLanguage={state.callerLanguage}
            callerLanguageName={state.callerLanguageName}
            onSpeak={speak}
          />
          <TranslationPanel
            callerLanguage={state.callerLanguage}
            callerLanguageName={state.callerLanguageName}
            onSpeak={speak}
            lastTTSAudio={state.lastTTSAudio}
          />
        </div>

        <FormPanel
          form={state.form}
          aiFilled={state.aiFilledFields}
          manualEdits={state.manualEdits}
          priority={state.priority}
          priorityReasoning={state.priorityReasoning}
          onEdit={sendManualEdit}
          onDispatch={onDispatch}
          canDispatch={canDispatch}
        />
      </main>

      {showDispatch && (
        <DispatchModal
          form={state.form}
          priority={state.priority}
          priorityReasoning={state.priorityReasoning}
          callId={state.callId}
          elapsed={elapsed}
          onCancel={() => setShowDispatch(false)}
          onConfirm={() => {
            setShowDispatch(false);
            stopCall();
          }}
        />
      )}
    </div>
  );
}
