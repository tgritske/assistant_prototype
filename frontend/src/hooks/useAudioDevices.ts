import { useCallback, useEffect, useState } from "react";

export interface AudioInputDevice {
  deviceId: string;
  groupId: string;
  label: string;
}

export function useAudioDevices() {
  const [devices, setDevices] = useState<AudioInputDevice[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setDevices(
        all
          .filter((device) => device.kind === "audioinput")
          .map((device, index) => ({
            deviceId: device.deviceId,
            groupId: device.groupId,
            label: device.label || `Audio Input ${index + 1}`,
          }))
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    navigator.mediaDevices?.addEventListener?.("devicechange", refresh);
    return () => {
      navigator.mediaDevices?.removeEventListener?.("devicechange", refresh);
    };
  }, [refresh]);

  return { devices, error, refresh };
}
