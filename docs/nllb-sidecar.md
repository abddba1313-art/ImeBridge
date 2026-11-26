# NLLB sidecar (optional second engine)

The bridge can route a configurable list of languages (default: Uzbek, and any
FLORES-mapped language you add) to a **local NLLB-200 service** instead of the
main GGUF model. This exists because a 1.8B decoder-only translator genuinely
fails on low-resource languages (loop repeats, wrong language output) while
NLLB-200 distilled handles them cleanly.

The sidecar is deliberately **not** part of this repo's runtime: it needs
`ctranslate2` + the NLLB model (CC-BY-NC), which would bloat every install.
Run your own server, point the bridge at it in Settings → "③ Translation
behavior" → **NLLB service URL**; leave the URL empty to disable routing
completely (the bridge then behaves exactly like a single-engine build).

## Protocol

Any HTTP service that speaks **OpenAI-compatible `POST /v1/chat/completions`**
on the configured port (the shipped reference build uses `127.0.0.1:1237`) and
interprets the single user message as this three-line machine request:

```
LANG_IN:<flores_code>
LANG_OUT:<flores_code>
<text, may contain newlines — everything after line 2 is payload>
```

Example request body:

```json
{
  "model": "nllb-200",
  "messages": [{"role": "user", "content": "LANG_IN:zho_Hans\nLANG_OUT:uzn_Latn\n请问最近的医院在哪里？"}],
  "stream": false
}
```

The reply must be a normal OpenAI `choices[0].message.content` containing only
the translated text. The bridge also probes `GET /v1/models` for health.

Language names ↔ FLORES-200 codes mapping lives in
[`src/nllb_lang.py`](../src/nllb_lang.py) (25 languages). Unknown languages
simply stay on the main model — routing is triple-gated (URL set + language in
route list + both codes mappable) and every gate failure falls back silently.

## Reference implementation

The shipped companion `NLLB翻译服务.exe` (onefile, ~38 MB) is
Flask/FastAPI-free: a tiny HTTP server wrapping
`ctranslate2Translator` with the `facebook/nllb-200-distilled-600M` CT2 model
(`nllb-ct2/` folder next to the exe). If you want your own, any of these work:

- `rtfb/nllb` Docker image (drop a 3-line protocol shim in front)
- a ~40-line Python script: `ctranslate2.Translator` + the parse/build helpers
  in `src/nllb_lang.py` (`parse_request` / `build_request` are import-free)

## Polish mode (small language → Chinese)

With `nllb_polish` enabled (default), for the specific direction
*routed-language → Chinese* the bridge runs a two-stage chain: NLLB produces
the (accurate) first pass, then the main GGUF model acts as a post-editing
engine — Chinese fluency is where the LLM is strong and NLLB is weak. If the
polish call fails or returns empty, the raw NLLB output is kept: a
punctuation-imperfect but semantically correct translation always beats a
model collapse.
