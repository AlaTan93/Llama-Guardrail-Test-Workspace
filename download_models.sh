#!/bin/bash

REPO="featherless-ai-quants/meta-llama-Llama-3.1-8B-Instruct-GGUF"
BASE_URL="https://huggingface.co/${REPO}/resolve/main"
OUTDIR="./models"
PARALLEL=4

# All quantisation variants
FILES=(
    "meta-llama-Llama-3.1-8B-Instruct-Q2_K.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q3_K_S.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q3_K_M.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q3_K_L.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q4_K_S.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q5_K_S.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q5_K_M.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q6_K.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-Q8_0.gguf"
    "meta-llama-Llama-3.1-8B-Instruct-IQ4_XS.gguf"
)

mkdir -p "${OUTDIR}"

download() {
    local file="$1"
    local url="${BASE_URL}/${file}"
    local dest="${OUTDIR}/${file}"
    
    if [ -f "${dest}" ]; then
        echo "↻ Resuming: ${file}"
    else
        echo "↓ Downloading: ${file}"
    fi
    
    wget -q --show-progress -c -O "${dest}" "${url}"
    
    if [ $? -eq 0 ]; then
        echo "✓ Done: ${file}"
    else
        echo "✗ Failed: ${file}"
    fi
}

export -f download
export BASE_URL OUTDIR

printf "%s\n" "${FILES[@]}" | xargs -P "${PARALLEL}" -I {} bash -c 'download "{}"'

echo ""
echo "All downloads complete. Files saved to: ${OUTDIR}"