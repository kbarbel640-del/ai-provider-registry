# API Styles

Different providers use different API conventions.
This document maps common API styles to their characteristics.

## openai

The de facto standard. Used by OpenAI, Groq, Together, DeepSeek, Cerebras, Perplexity, OpenRouter.

- Endpoint: `{base}/chat/completions`
- Auth: `Authorization: Bearer {key}`
- Request: `{ model, messages[], temperature, stream, ... }`
- Streaming: SSE with `data: {...}` lines

## anthropic

Used by Anthropic Claude.

- Endpoint: `{base}/messages`
- Auth: `x-api-key: {key}`
- Request: `{ model, messages[], max_tokens, stream, ... }`
- Streaming: SSE with `event: content_block_delta`

## google

Used by Google Gemini.

- Endpoint: `{base}/models/{model}:generateContent`
- Auth: `?key={api_key}`
- Request: `{ contents[], generationConfig, ... }`
- Streaming: `{base}/models/{model}:streamGenerateContent`

## cohere

Used by Cohere.

- Endpoint: `{base}/chat`
- Auth: `Authorization: Bearer {key}`
- Request: `{ message, model, preamble, ... }`
- Streaming: SSE

## Compatibility

Providers marked `api_style: openai` accept OpenAI SDK as a drop-in client.
