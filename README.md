# ollama-test-1

Quantization safety red-teaming pipeline — uses PyRIT to automate attacks
against locally-served GGUF models and measures how quantization degrades
safety guardrails. See `exploiter_plan.md` for the full research design.

## Quick Start

### 1. Python environment

```bash
uv sync
```

### 2. Build llama.cpp with ROCm (AMD 7900 XTX)

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100
cmake --build build --config Release -j$(nproc)
```

### 3. Download the target model

Primary model: **Llama 3.1 8B Instruct** (GGUF).
Download from HuggingFace, e.g. Q4_K_M:

```bash
wget https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
```

Per the research plan, test across quantization tiers:
**Q2_K, Q3_K_M, Q4_K_M, Q5_K_M, Q6_K, Q8_0, FP16**.

### 4. Start the llama.cpp server

```bash
./llama.cpp/build/bin/llama-server \
  -m models/meta-llama-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -ngl 99
```

This exposes an OpenAI-compatible API at `http://127.0.0.1:8080/v1`.

### 5. Configure PyRIT target

Edit `.pyrit/.env`:

```
OPENAI_CHAT_ENDPOINT="http://127.0.0.1:8080/v1"
OPENAI_CHAT_KEY="not-needed"
OPENAI_CHAT_MODEL="llama3"
```

The `OPENAI_CHAT_MODEL` value must match the model name the server
reports — check with `curl http://127.0.0.1:8080/v1/models`.

### 6. Set the scorer API key

The LiteLLM proxy uses Claude Haiku 4.5 as the safety scorer:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or set an .env ffile with these text:
```
ANTHROPIC_API_KEY="sk-ant-..."
```

### 7. Run the red team

```bash
python redteam.py
```
