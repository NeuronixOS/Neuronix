# secrets/ (reference — empty in stock / example)

Private files land at `~/configs/secrets/` after merge.

Typical private overlay (`personalize/` only):

```text
secrets/github-token    # single-line token; Ctrl+Alt+U may wl-copy it
```

Do **not** put real secrets in `default/` or `personalize.example/`.
Copy `github-token.example` → `github-token` under your private `personalize/configs/secrets/`.
