"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchHealth } from "@/lib/api";
import type { ConnectionState, HealthBody } from "@/lib/types";

const POLL_INTERVAL_MS = 30_000;

export interface HealthState {
  health: HealthBody | null;
  connection: ConnectionState;
  healthLatency: number | null;
  clearSoftError: () => void;
}

export function useHealthStatus(): HealthState & {
  softError: string | null;
  setSoftError: (v: string | null) => void;
  setConnection: (v: ConnectionState) => void;
} {
  const [health, setHealth] = useState<HealthBody | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [healthLatency, setHealthLatency] = useState<number | null>(null);
  const [softError, setSoftError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
      setHealthLatency(typeof h.latency_ms === "number" ? h.latency_ms : null);
      setConnection(h.status === "ok" ? "ok" : "degraded");
      setSoftError(null);
    } catch {
      setConnection("offline");
      setHealth(null);
      setHealthLatency(null);
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    const t = setInterval(() => void refreshHealth(), POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [refreshHealth]);

  const clearSoftError = useCallback(() => setSoftError(null), []);

  return {
    health,
    connection,
    healthLatency,
    softError,
    setSoftError,
    setConnection,
    clearSoftError,
  };
}
