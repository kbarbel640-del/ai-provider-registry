# Model Schema

## Fields

| Field          | Type     | Description                              | Required |
|----------------|----------|------------------------------------------|----------|
| name           | string   | Model family name                        | Yes      |
| provider       | string   | Parent/creator provider                  | Yes      |
| context_window | integer  | Maximum context length in tokens         | Yes      |
| capabilities   | array    | List of supported capabilities           | Yes      |
| variants       | array    | Specific model variants and their providers | Yes      |

## Variant Fields

| Field    | Type   | Description                          | Required |
|----------|--------|--------------------------------------|----------|
| name     | string | Specific model name/ID               | Yes      |
| provider | string | Provider serving this variant        | Yes      |

## Optional Variant Fields (enriched from models.dev)

Variants may carry facts merged from `catalog/models-dev/models.json`
(`python3 sync_modelsdev.py families --write`). These fields are optional:

| Field         | Type    | Description                              |
|---------------|---------|------------------------------------------|
| context_window | integer | Maximum context length in tokens        |
| output_limit   | integer | Maximum output tokens                   |
| release_date   | string  | YYYY-MM-DD model release date           |
| tags           | array   | Capability/trait tags (reasoning, tools, json_mode, vision, audio, multimodal, open_weights, …) |
