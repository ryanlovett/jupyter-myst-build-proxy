# Releasing

## Dependencies

```bash
pipx install tbump
```

Or with uv:

```bash
uv tool install tbump
```


## Bumping version

```bash
tbump 0.5.0
```


## Publishing

Create a GitHub release with the corresponding tag.
The tag should always start with `v`, e.g. `v0.5.0`.

Generate release notes automatically, and manually clean up any items that end-users
might not care about.
