# Live Rebuttal Coach — Project Context
Created: 2026-04-14

## What This Is
A standalone companion web app that runs alongside ReSimpli during live seller calls.
It listens to the call audio in real-time, detects objections, and surfaces rebuttal
suggestions on screen within seconds — so the acquisitions manager always has a
sharp response ready.

---

## The Problem It Solves
Buying Hero's acquisitions team takes live seller calls through ReSimpli (web-based CRM
built on Twilio). When sellers throw objections ("I have someone offering more", "I need
more time", "My neighbor got $X"), there's no live support. This app is that support.

---

## Chosen Approach: System Audio Loopback (Option B)

### Why
- No ReSimpli API integration required
- Works immediately without waiting on ReSimpli webhooks/support
- VB-Cable (free, Windows) routes speaker audio to a virtual mic
- App treats virtual mic as its audio source — works with any calling app

### Audio Flow
```
ReSimpli call (browser) → speakers/headset
                        → VB-Cable virtual device (loopback)
                            → Live Rebuttal Coach app (mic input = VB-Cable)
                                → Deepgram real-time WebSocket STT
                                    → Claude API (objection detection + rebuttals)
                                        → Rebuttal cards on screen
```

---

## Tech Stack (planned)
| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | React + Vite + Tailwind | Same as acquisition trainer, fast to build |
| STT | Deepgram real-time WebSocket | Built for phone audio, far more reliable than Web Speech API for continuous use |
| AI | Claude claude-sonnet-4-6 streaming | Fast streaming rebuttals, already integrated in other apps |
| Backend | FastAPI (Python) or Node | Needed to proxy Deepgram WebSocket + call Claude securely |
| Deployment | Vercel (frontend) + Render (backend) | Same as acquisition trainer |

---

## Key UX Requirements
- Open in a browser tab while ReSimpli is in another tab
- User selects VB-Cable as the audio input on first launch
- Shows live rolling transcript (so user can confirm it's hearing correctly)
- When objection detected → pops up 2-3 rebuttal card options instantly
- Cards should be scannable in 1 second — short, punchy lines
- Must not distract — dark UI, minimal chrome
- Should work on a second monitor or tablet next to the call

---

## Rebuttal Logic (Claude prompt design)
- Classify each seller utterance: objection / question / neutral / positive signal
- If objection → identify type (price, timing, competing offer, emotional, skepticism)
- Return 2-3 rebuttals ranked by likely effectiveness
- Rebuttals must follow Buying Hero negotiation philosophy:
  - Anchor with logic, not emotion
  - Never retrade
  - Protect seller dignity
  - Use silence as leverage
  - Defend with cost of repairs / carrying costs / resale risk

---

## Objection Types to Handle
- "I need more money" / "That's too low"
- "I have another offer" / "Someone offered me more"
- "I need to think about it" / "Call me next week"
- "I need to talk to my family"
- "I owe more than that"
- "My house is worth more" / "Zillow says..."
- "I'm not in a rush"
- "I'll just list it with an agent"
- "I don't know if I trust you"

---

## Setup Steps (when ready to build)
1. User installs VB-Cable: https://vb-audio.com/Cable/ (free, Windows)
2. In Windows Sound settings: set VB-Cable as default recording device
3. In ReSimpli: ensure call audio plays through speakers (not headset-only)
4. Open Live Rebuttal Coach app → select VB-Cable as mic input → click Start

---

## Dependencies to Install (when building)
```bash
# Backend
pip install fastapi uvicorn deepgram-sdk anthropic python-dotenv websockets

# Frontend
npm create vite@latest live-rebuttal-coach -- --template react
npm install tailwindcss @tailwindcss/vite
```

---

## Deepgram Notes
- Use real-time streaming WebSocket API (not batch)
- Model: `nova-2` — best for phone audio
- Enable `smart_format`, `punctuate`, `interim_results`
- Cost: ~$0.01/min — very cheap
- API key needed: https://console.deepgram.com

---

## Files to Create When Building
```
live-rebuttal-coach/
  backend/
    main.py          — FastAPI + WebSocket proxy for Deepgram + Claude
    .env             — DEEPGRAM_API_KEY, ANTHROPIC_API_KEY
  frontend/
    src/
      App.jsx        — Main UI: transcript feed + rebuttal cards
      hooks/
        useAudioStream.js   — mic capture + WebSocket to backend
        useRebuttals.js     — rebuttal state management
    .env             — VITE_API_URL
  CONTEXT.md         — this file
```

---

## Status
NOT STARTED. Context file created 2026-04-14.
Next session: start with backend WebSocket → Deepgram integration first,
then build the rebuttal card UI.
