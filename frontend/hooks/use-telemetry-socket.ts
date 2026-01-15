"use client";

import { useEffect } from "react";

import type { TelemetryEvent } from "@/lib/types";
import { useWorkbenchStore } from "@/store/workbench";

export function useTelemetrySocket(): void {
  const applyTelemetry = useWorkbenchStore((state) => state.applyTelemetry);
  const addTelemetry = useWorkbenchStore((state) => state.addTelemetry);
  const setSocketOnline = useWorkbenchStore((state) => state.setSocketOnline);

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_DRI_WS_URL;
    if (!url) return;

    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    let attempts = 0;

    const connect = () => {
      socket = new WebSocket(url);
      socket.onopen = () => {
        attempts = 0;
        setSocketOnline(true);
        addTelemetry("SOCKET  telemetry channel connected");
      };
      socket.onmessage = (message) => {
        try {
          applyTelemetry(JSON.parse(String(message.data)) as TelemetryEvent);
        } catch {
          addTelemetry("WARN    ignored malformed telemetry event");
        }
      };
      socket.onclose = () => {
        setSocketOnline(false);
        if (stopped) return;
        attempts += 1;
        timer = setTimeout(connect, Math.min(1_000 * 2 ** attempts, 15_000));
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [addTelemetry, applyTelemetry, setSocketOnline]);
}

