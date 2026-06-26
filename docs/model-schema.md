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
