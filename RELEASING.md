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

This will update `package.json` and `pyproject.toml` to reflect the new version.
Review the output of this command carefully, as when it's done it will create and push a
commit and tag.


## Publishing

Create a GitHub release and select the tag pushed in the previous version-bumping step.

Generate release notes automatically, and manually clean up any items that end-users
might not care about.
