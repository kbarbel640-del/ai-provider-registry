# NVIDIA NIM API – Freie API-Endpunkte Dokumentation

> Stand: Juni 2026 | Basis: docs.api.nvidia.com + Live-Verifikation

---

## 1. Übersicht & Free Tier

NVIDIA bietet über das **NVIDIA Developer Program** kostenlosen API-Zugriff auf 100+ KI-Modelle.

| Merkmal | Wert |
|---|---|
| **Registrierung** | build.nvidia.com (kostenlos) |
| **API-Key** | `nvapi-...` Format |
| **Rate Limit** | ~40 Requests pro Minute (pro Modell) |
| **Token-Kosten** | Keine (rein rate-limit-basiert) |
| **Nutzung** | Nur Prototyping / Entwicklung / Forschung |
| **Produktion** | NVIDIA AI Enterprise Lizenz nötig (ab $4.500/GPU/Jahr) |

---

## 2. Authentifizierung

Alle Endpunkte verwenden **Bearer Token**:

```
Authorization: Bearer nvapi-<DEIN_KEY>
Content-Type: application/json
Accept: application/json
```

---

## 3. OpenAI-kompatible Endpunkte

Diese Endpunkte sind **kompatibel mit der OpenAI Chat Completions API**.

### 3.1 Modelle auflisten

```
GET https://integrate.api.nvidia.com/v1/models
```

**Response** (Auszug):
```json
{
  "data": [
    {"id": "meta/llama-3.3-70b-instruct", ...},
    {"id": "mistralai/mixtral-8x7b-instruct", ...},
    ...
  ]
}
```

> **Hinweis:** Dieser Endpunkt ist **öffentlich** – auch ohne API-Key erreichbar.

### 3.2 Chat Completions (LLM)

```
POST https://integrate.api.nvidia.com/v1/chat/completions
```

**Payload** (identisch mit OpenAI):
```json
{
  "model": "meta/llama-3.3-70b-instruct",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hallo!"}
  ],
  "temperature": 0.2,
  "top_p": 0.7,
  "max_tokens": 1024,
  "stream": false,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "stop": null,
  "tools": null,
  "tool_choice": null
}
```

**Verifizierte Parameter**:
- `model` (string, required): z.B. `meta/llama-3.3-70b-instruct`
- `messages` (array, required): OpenAI-konformes Nachrichtenformat
- `temperature` (0–1, default 0.2)
- `top_p` (≤ 1, default 0.7)
- `max_tokens` (1–4096, default 1024)
- `stream` (boolean, default false): SSE-Streaming (`data: [DONE]`)
- `frequency_penalty` (-2 bis 2)
- `presence_penalty` (-2 bis 2)
- `stop` (string | array | null): Stop-Token(s)
- `tools` / `tool_choice`: Function Calling wird unterstützt

> **NVIDIA-spezifisch:** Die Response enthält zusätzlich ein `nvext`-Feld mit Timing- und Worker-Informationen (z.B. `nvext.timing.ttft_ms` für Time-to-First-Token). Dieses Feld ist optional und nicht Teil des OpenAI-Standards.

**Response** (OpenAI-konform):
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1780954777,
  "model": "meta/llama-3.3-70b-instruct",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Antworttext",
      "refusal": null,
      "annotations": null,
      "tool_calls": []
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 41,
    "completion_tokens": 4,
    "total_tokens": 45
  }
}
```

---

## 4. Vision / Multimodal (über Chat-Endpoint)

Vision-Modelle werden über denselben Chat-Endpoint, aber mit **Multimodal-Nachrichten** angesteuert.

```
POST https://integrate.api.nvidia.com/v1/chat/completions
```

**Payload**:
```json
{
  "model": "meta/llama-3.2-11b-vision-instruct",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Beschreibe dieses Bild"},
      {"type": "image_url", "image_url": {
        "url": "data:image/jpeg;base64,<BASE64>"
      }}
    ]
  }],
  "max_tokens": 1024,
  "temperature": 0.5
}
```

---

## 5. Bildgenerierung (GenAI – Proprietär)

**NICHT OpenAI-kompatibel.** Eigener Endpunkt, eigenes Payload-Format.

### 5.1 Text-to-Image

```
POST https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell
```

**Payload**:
```json
{
  "prompt": "Beschreibung des gewünschten Bildes",
  "width": 1024,
  "height": 1024,
  "steps": 4,
  "samples": 1,
  "seed": 0
}
```

---

## 6. Abweichungen zu OpenAI

| Bereich | OpenAI | NVIDIA NIM |
|---|---|---|
| **Base URL** | `https://api.openai.com/v1` | `https://integrate.api.nvidia.com/v1` |
| **Chat Endpoint** | `/chat/completions` | `/chat/completions` ✅ gleich |
| **Modelle auflisten** | `/models` | `/models` ✅ gleich |
| **Streaming** | SSE (`data: [DONE]`) | SSE (`data: [DONE]`) ✅ gleich |
| **Image Generation** | `/v1/images/generations` | **`https://ai.api.nvidia.com/v1/genai/{model}`** ❌ proprietär |
| **Vision** | Chat-Endpoint mit `image_url` | Chat-Endpoint mit `image_url` ✅ gleich |
| **Rate Limits** | Token-basiert (TPM/RPM) | Nur RPM (~40/min), keine Token-Kosten |
