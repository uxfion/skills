# Sizing and tuning a model server

Take the mainstream, cheap wins and stop there: what the model card and the vLLM recipe recommend, and what vLLM turns on with one switch (its attention kernels, prefix caching, a model's own MTP head). Confirm each with one quick comparison on the real workload. Leave niche tuning alone: external draft models, hand-set batch and chunk sizes, performance modes. Options that change the numbers (FP8 KV cache, quantised weights) stay out of runs whose results must compare with earlier ones.

The figures below are Qwen3.8-27B (BF16, 55.6 GB on disk) on vLLM 0.32 in 2026-10, a worked example of each method.

## Memory and capacity

Each GPU holds its share of the weights, a runtime overhead (CUDA graphs, activations) and the KV cache. vLLM takes `--gpu-memory-utilization` of the GPU's total memory, gives what the weights and the runtime leave to the KV cache, and refuses to start unless that cache holds one request of `--max-model-len`. Read the real numbers from the start-up log:

- `Model loading took … GiB`: the weights (50.1 GiB without the vision tower; 25.15 GiB per GPU with tensor parallel 2).
- `Available KV cache memory: … GiB`: what is left for the cache; the runtime is the difference (~6 GiB on one GPU, ~3.5 GiB per GPU with tensor parallel 2).
- `GPU KV cache size: N tokens, Maximum concurrency for L tokens per request: X`: the capacity. Memory ÷ tokens gives the cost of a token (~65 KiB here, the hybrid model's Mamba state included).

Set `--max-model-len` from the callers: their longest context plus the output they allow per turn. Agent sessions whose context reached 59k at the 95th percentile, with 32k output per turn, needed 128k; another task reaching 163k needed 200k or more.

What that makes for one model copy, at vLLM's default `--gpu-memory-utilization` of 0.92:

| Sessions in flight | One GPU | Two GPUs, tensor parallel (each) |
|---|---|---|
| 1, context up to 128k | ≈ 75 GB | ≈ 38 GB |
| 1, context up to 262k | ≈ 84 GB | ≈ 43 GB |
| 40, ~30k tokens each | ≈ 138 GB | ≈ 70 GB |

So one RTX PRO 6000 or H20 (96 GB) holds a copy and ~12–20 long sessions, one H200 (141 GB) ~40, and RTX 5090s (32 GB) need four. Generation speed follows memory bandwidth: ~1.8 TB/s for the RTX PRO 6000 and RTX 5090, 4.0 for the H20, 4.8 for the H200.

## Concurrency

Multi-turn sessions (agents) live on the prefix cache: each turn resends the whole conversation, and only its new part is computed while the earlier turns sit in the cache. When the KV cache fills, those cached prefixes go first, every turn recomputes its whole context, and throughput collapses while the server looks busy. Two RTX PRO 6000 at 0.60 each (924k tokens): 16 sessions ran at 200–210 tok/s with the cache half full; 32 sessions filled it to 95–100% and generation swung between 9 and 300 tok/s, ~110 on average, with only 3 preemptions.

- Keep the KV cache below ~70% at peak: sessions ≈ 0.7 × cache tokens ÷ the tokens one session holds, counting once what sessions share (a common system prompt). Here 25–35k per session.
- `--max-num-seqs` caps the requests running at once; the caller limits the sessions it keeps in flight.
- Watch `status`'s `load`: `kv_cache_usage`, `waiting`, `preemptions`, `prefix_cache_hit_rate`, `generation_tokens_per_s`.
- A hybrid model (Mamba or gated-delta-net layers) holds one Mamba cache block per running request, and vLLM refuses to start when `--max-num-seqs` exceeds the blocks it has (its default is 1024 on GPUs of 70 GiB or more, else 256). It enlarges the attention block to the Mamba state's size (784 tokens here), so blocks ≈ cache tokens ÷ that size: 680 on one RTX PRO 6000 at 0.92.

## Parallel layout

- When one GPU holds a copy, use data parallel (`--data-parallel-size`): one copy per GPU behind one URL, requests balanced by load, nothing exchanged between GPUs. Tensor parallel only when a copy does not fit; its size must divide the attention, KV and linear-attention heads (`config.json`; here 2, 4 or 8, never 3).
- Two H200 in data parallel served 12 sessions at ~600 tok/s in total, ~50 per session. Two RTX PRO 6000 in tensor parallel, each shared with another user's training, gave 200–330 in total.

## Speculative decoding

- A recipe's version notes go stale: check a "needs a fix no release carries yet" against the installed version (`gh api repos/vllm-project/vllm/compare/v<version>...<merge commit>` shows `behind` when the release has it). The Qwen3.8 recipe's MTP note was stale by 0.32.0.
- Try it once on the real workload: off against the recipe's value, nothing in between. Acceptance is `vllm:spec_decode_num_accepted_tokens_total` ÷ `vllm:spec_decode_num_draft_tokens_total` from `/metrics`.
- Gains shrink with long contexts, sampling at high temperature and many concurrent requests. On 12 concurrent ~26k-token thinking requests at temperature 1.0: 202 tok/s off, 205 with 3 draft tokens (42% accepted), 198 with 5 (31%), against the recipe's 92% acceptance on short prompts. Left off.

## Sampling

Parameters a client leaves out come from the model's `generation_config.json` (vLLM's `--generation-config auto`; Qwen3.8-27B: temperature 1.0, top_p 0.95, top_k 20). Claude Code sends none; agent harnesses such as pi can set them per request. Identical reruns need `VLLM_BATCH_INVARIANT=1` on the server and a seed in every request.
