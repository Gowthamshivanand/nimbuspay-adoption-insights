/** Read an answer aloud. Returns true if speech started, false if it stopped, null if the browser has no speech. */
export function toggleSpeech(text: string): boolean | null {
  const s = window.speechSynthesis;
  if (!s) return null;
  if (s.speaking || s.pending) { s.cancel(); return false; }
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return null;
  const u = new SpeechSynthesisUtterance(clean.slice(0, 1500));
  u.rate = 1;
  u.lang = "en-GB";
  s.speak(u);
  return true;
}

/** Fill the composer from the microphone. Returns false if this browser has no speech recognition. */
export function startMic(onText: (text: string) => void): boolean {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const R = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!R) return false;
  const rec = new R();
  rec.lang = "en-GB";
  rec.interimResults = false;
  rec.onresult = (e) => {
    const text = e.results?.[0]?.[0]?.transcript || "";
    if (text) onText(text);
  };
  rec.start();
  return true;
}

type SpeechRec = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results?: { 0?: { 0?: { transcript?: string } } } }) => void) | null;
  start: () => void;
};
