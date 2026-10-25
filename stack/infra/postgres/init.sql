-- Two databases, one container:
--   guardrails — harness system of record (runs/objectives/turns/scores)
--   litellm    — LiteLLM proxy: model/route config, keys, spend logs
CREATE DATABASE guardrails;
CREATE DATABASE litellm;
