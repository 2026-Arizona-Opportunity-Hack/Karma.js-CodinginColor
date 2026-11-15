import { useEffect, useRef, useState } from "react";

// The browser's own speech-to-text. No audio reaches our server or is stored (AST-3).
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionCtor = new () => Recognition;

function ctor(): RecognitionCtor | undefined {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export function useSpeech(onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const active = useRef<Recognition | null>(null);
  const handler = useRef(onText);
  useEffect(() => {
    handler.current = onText;
  });
  const supported = typeof window !== "undefined" && ctor() !== undefined;

  const stop = () => active.current?.stop();
  useEffect(() => () => active.current?.stop(), []);

  const toggle = () => {
    const Ctor = ctor();
    if (!Ctor) return;
    if (active.current) return stop();
    const r = new Ctor();
    r.lang = "en-US";
    r.continuous = false;
    r.interimResults = false;
    r.onresult = (event) => {
      const heard = Array.from(event.results)
        .map((alt) => alt[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (heard) handler.current(heard);
    };
    r.onend = r.onerror = () => {
      active.current = null;
      setListening(false);
    };
    active.current = r;
    setListening(true);
    r.start();
  };

  return { supported, listening, toggle, stop };
}
