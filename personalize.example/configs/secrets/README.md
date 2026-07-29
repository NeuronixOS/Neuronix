# personalize/configs/secrets/

Private files merge to `~/configs/secrets/`. **Never** put real tokens in
`personalize.example/` — only in private `personalize/configs/secrets/`.

## Example files

```text
secrets/
  github-token          # single-line token (e.g. for a Hypr bind)
```

## Example `github-token`

```text
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

One secret per file; no trailing commentary required.
