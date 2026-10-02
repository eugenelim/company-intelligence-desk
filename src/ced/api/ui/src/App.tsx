import React, { useEffect, useMemo, useReducer } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type EventEnvelope = {
  schema_version: number;
  run_id: string;
  seq: number;
  type: string;
  principal: string;
  step_id: string | null;
  agent_role: string | null;
  payload_ref: string | null;
  idempotency_key: string | null;
};

type ConnectionState =
  | "loading"
  | "waiting"
  | "streaming"
  | "reconnecting"
  | "terminal"
  | "unavailable"
  | "offline";

type State = {
  connection: ConnectionState;
  events: Record<number, EventEnvelope>;
  order: number[];
  cursor: number;
  error: string | null;
  retryToken: number;
  // Whether the browser last reported losing its network. Held apart from
  // `connection` so no later event can overwrite it; the shown state is
  // derived from both at render, with Terminal outranking it.
  browserOffline: boolean;
};

type Action =
  | { type: "snapshot"; events: EventEnvelope[] }
  | { type: "stream-open" }
  | { type: "event"; event: EventEnvelope }
  | { type: "reconnecting" }
  | { type: "terminal"; event: EventEnvelope }
  | { type: "unavailable"; message: string }
  | { type: "offline" }
  | { type: "online" }
  | { type: "retry" };

const terminalEvents = new Set(["run.completed", "run.failed", "run.cancelled"]);

const initialState: State = {
  connection: "loading",
  events: {},
  order: [],
  cursor: 0,
  error: null,
  retryToken: 0,
  browserOffline: false,
};

function addEvent(state: State, event: EventEnvelope): State {
  if (state.events[event.seq]) {
    return state;
  }
  const nextEvents = { ...state.events, [event.seq]: event };
  const nextOrder = [...state.order, event.seq].sort((left, right) => left - right);
  return {
    ...state,
    events: nextEvents,
    order: nextOrder,
    cursor: Math.max(state.cursor, event.seq),
  };
}

function endsInTerminal(events: EventEnvelope[]): boolean {
  const last = events.at(-1);
  return last !== undefined && terminalEvents.has(last.type);
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "snapshot": {
      const seeded = action.events.reduce(addEvent, { ...initialState });
      return {
        ...seeded,
        // Carry the retry token forward.  Reseeding it from initialState would
        // change the connect effect's dependency back to 0 on the first
        // snapshot after a retry, re-running the effect and opening a second
        // stream against the same run.
        retryToken: state.retryToken,
        browserOffline: state.browserOffline,
        // A history that already ends in a terminal event is a finished run:
        // its final state is announced now, and no stream is opened for it.
        connection: endsInTerminal(action.events)
          ? "terminal"
          : seeded.order.length <= 1
            ? "waiting"
            : "streaming",
      };
    }
    case "stream-open":
      return {
        ...state,
        connection: state.order.length <= 1 ? "waiting" : "streaming",
        error: null,
      };
    case "event": {
      const next = addEvent(state, action.event);
      return {
        ...next,
        connection: next.order.length <= 1 ? "waiting" : "streaming",
        error: null,
      };
    }
    case "terminal":
      return { ...addEvent(state, action.event), connection: "terminal", error: null };
    case "reconnecting":
      return state.connection === "terminal" ? state : { ...state, connection: "reconnecting" };
    case "unavailable":
      return { ...state, connection: "unavailable", error: action.message };
    case "offline":
      return { ...state, browserOffline: true };
    case "online":
      return { ...state, browserOffline: false };
    case "retry":
      return { ...state, connection: "loading", error: null, retryToken: state.retryToken + 1 };
  }
}

function runIdFromLocation(): string {
  const match = window.location.pathname.match(/^\/runs\/([^/]+)$/);
  if (!match) {
    return "";
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    // A malformed percent sequence names no run. Keep the raw segment so the
    // history request still goes out, fails, and the page reaches Unavailable
    // instead of throwing during render and leaving a blank page.
    return match[1];
  }
}

function labelFor(connection: ConnectionState, terminalEventType?: string): string {
  switch (connection) {
    case "loading":
      return "Loading committed events";
    case "waiting":
      return "Waiting for worker events";
    case "streaming":
      return "Streaming committed events";
    case "reconnecting":
      return "Reconnecting from last sequence";
    case "terminal":
      // Name the outcome so the live region announces what actually happened.
      switch (terminalEventType) {
        case "run.completed":
          return "Run completed";
        case "run.failed":
          return "Run failed";
        case "run.cancelled":
          return "Run cancelled";
        default:
          return "Terminal event received";
      }
    case "unavailable":
      return "Run unavailable";
    case "offline":
      return "Browser is offline";
  }
}

function statusClass(connection: ConnectionState, terminalEventType?: string): string {
  if (connection === "terminal") {
    switch (terminalEventType) {
      case "run.completed":
        return "status-terminal-completed";
      case "run.failed":
        return "status-terminal-failed";
      case "run.cancelled":
        return "status-terminal-cancelled";
      default:
        return "status-terminal";
    }
  }
  return `status-${connection}`;
}

function RunPage(): React.ReactElement {
  const runId = useMemo(runIdFromLocation, []);
  const [state, dispatch] = useReducer(reducer, initialState);
  const rows = state.order.map((seq) => state.events[seq]);
  const latest = rows.at(-1);
  const terminalEventType = state.connection === "terminal" ? latest?.type : undefined;
  // Offline outranks every non-terminal state while the browser reports no
  // network; a finished run keeps its final state.
  const shown: ConnectionState =
    state.connection !== "terminal" && state.browserOffline ? "offline" : state.connection;
  const detail = shown === "offline" ? (state.error ?? "Network connection lost") : state.error;
  const label = labelFor(shown, terminalEventType);
  const eventCount = state.order.length;

  useEffect(() => {
    const markOffline = () => dispatch({ type: "offline" });
    const markOnline = () => dispatch({ type: "online" });
    window.addEventListener("offline", markOffline);
    window.addEventListener("online", markOnline);
    return () => {
      window.removeEventListener("offline", markOffline);
      window.removeEventListener("online", markOnline);
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let source: EventSource | null = null;
    const controller = new AbortController();

    async function connect(): Promise<void> {
      // Fetch committed-event history before opening the stream.
      try {
        const response = await fetch(
          `/runs/${encodeURIComponent(runId)}/events?after=0`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          dispatch({
            type: "unavailable",
            message: `Event history returned ${response.status}`,
          });
          return;
        }
        const page = await response.json();
        if (stopped) return;
        dispatch({ type: "snapshot", events: page.events });
        if (endsInTerminal(page.events)) return;
      } catch {
        if (!stopped) {
          dispatch({ type: "unavailable", message: "Event history request failed" });
        }
        return;
      }

      if (stopped) return;

      // One native EventSource reads the committed stream.  The server sets no
      // event: field, so a single onmessage handler receives every frame —
      // including a committed type added to the domain vocabulary later, which
      // a per-type addEventListener enumeration could never cover.  The URL
      // keeps a deliberately stale after=0: the native transport reconnects on
      // its own and supplies Last-Event-ID from the last id: field it saw, and
      // the server prefers that header over the query cursor.
      const streamUrl = `/runs/${encodeURIComponent(runId)}/events/stream?after=0`;
      source = new EventSource(streamUrl);
      source.onopen = () => dispatch({ type: "stream-open" });
      source.onmessage = (message: MessageEvent<string>) => {
        const event = JSON.parse(message.data) as EventEnvelope;
        if (terminalEvents.has(event.type)) {
          dispatch({ type: "terminal", event });
          source?.close();
        } else {
          dispatch({ type: "event", event });
        }
      };
      source.onerror = () => {
        // readyState CLOSED (2): the connection failed permanently (e.g. non-200
        // response); dispatch unavailable so the Retry control appears.
        // readyState CONNECTING (0): the native transport will retry on its own;
        // dispatch reconnecting to update the status heading.
        // source is non-null here: the callback is only called while the
        // EventSource is live.  The non-null assertion is safe.
        if (source!.readyState === EventSource.CLOSED) {
          dispatch({ type: "unavailable", message: `Stream request failed: ${streamUrl}` });
        } else {
          dispatch({ type: "reconnecting" });
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      controller.abort();
      source?.close();
    };
  }, [runId, state.retryToken]);

  return (
    <main className="shell">
      <a className="skip-link" href="#events">
        Skip to events
      </a>
      <header className="run-header">
        <div>
          <p className="eyebrow">Run evidence</p>
          <h1>Run {runId}</h1>
        </div>
        <dl className="summary" aria-label="Run summary">
          <div>
            <dt>State</dt>
            <dd>{latest?.type ?? "pending"}</dd>
          </div>
          <div>
            <dt>Cursor</dt>
            <dd>{state.cursor}</dd>
          </div>
        </dl>
      </header>

      <section
        className={`status ${statusClass(shown, terminalEventType)}`}
        aria-labelledby="status-title"
      >
        <div>
          <h2 id="status-title">{label}</h2>
          {/* The live region includes the label so screen readers announce
              transitions — a state change without a new event (e.g. streaming
              → reconnecting) does not change the event count, so a count-only
              region would be silent. */}
          <p role="status" aria-live="polite">
            {`${label}: `}
            {detail ??
              `Applied ${eventCount} committed event${eventCount === 1 ? "" : "s"}.`}
          </p>
        </div>
        {(shown === "unavailable" || shown === "offline") && (
          <button type="button" onClick={() => dispatch({ type: "retry" })}>
            Retry
          </button>
        )}
      </section>

      <section id="events" className="events" aria-labelledby="events-title">
        <h2 id="events-title">Committed event sequence</h2>
        {shown === "loading" && (
          <ol className="event-list" aria-busy="true" aria-label="Loading events">
            {[1, 2, 3].map((slot) => (
              <li className="event-row skeleton" key={slot}>
                <span />
                <span />
              </li>
            ))}
          </ol>
        )}
        {shown !== "loading" && (
          <ol className="event-list">
            {rows.map((event) => (
              <li className="event-row" key={event.seq}>
                <div className="spine">
                  <span className="seq">#{event.seq}</span>
                  <span className="type">{event.type}</span>
                </div>
                <dl className="metadata">
                  <div>
                    <dt>Principal</dt>
                    <dd>{event.principal}</dd>
                  </div>
                  <div>
                    <dt>Agent role</dt>
                    <dd>{event.agent_role ?? "none"}</dd>
                  </div>
                  <div>
                    <dt>Payload ref</dt>
                    <dd>{event.payload_ref ?? "none"}</dd>
                  </div>
                  <div>
                    <dt>Idempotency key</dt>
                    <dd>{event.idempotency_key ?? "none"}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<RunPage />);
