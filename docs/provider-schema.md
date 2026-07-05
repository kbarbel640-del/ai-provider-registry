# Provider Schema

## Fields

| Field       | Type     | Description                          | Required |
|-------------|----------|--------------------------------------|----------|
| name        | string   | Provider name                        | Yes      |
| api_style   | string   | API style (e.g., `openai`, `anthropic`) | Yes      |
| auth        | object   | Authentication method and docs       | Yes      |
| pricing     | object   | Pricing model and docs               | Yes      |
| supports    | array    | List of supported capabilities       | Yes      |
| models      | array    | List of supported models             | Yes      |
| api_spec    | string   | URL to the API specification (OpenAPI, Discovery, etc.) | No       |
| endpoint    | string   | API base URL                         | No       |