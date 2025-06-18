# Versioning Process Prompt

When asked to create a new version of the project, follow these steps in order:

## 1. Update Project Files

### Update version in pyproject.toml
```toml
[tool.poetry]
name = "project_name"
version = "X.X.X"  # Update to new version
```

### Update CHANGELOG.md
Add new entry at the top of the file:
```markdown
## [X.X.X] - YYYY-MM-DD
### Added/Changed/Fixed
- ✨ Description of changes
```

### Update README.md
If the project uses version tags (like AIA_TAG_UTILS), update them:
```bash
export PROJECT_TAG=X.X.X
```

## 2. Create Git Commit and Tag

```bash
# Stage all changes
git add .

# Create commit with conventional commit message
git commit -m "feat: description of changes"

# Create version tag (must be exactly vX.X.X)
git tag vX.X.X
```

## 3. Push to Repository

```bash
# Push commit
git push

# Push tag
git push --tags
```

## Important Notes

1. Always use semantic versioning (MAJOR.MINOR.PATCH)
2. Tag names must be exactly in the format `vX.X.X`
3. Keep CHANGELOG.md entries clear and descriptive
4. Ensure version numbers are consistent across all files
5. Follow conventional commit messages (feat:, fix:, chore:, etc.)

## Example

For version 1.2.3:
1. Update version to "1.2.3" in pyproject.toml
2. Add changelog entry for [1.2.3]
3. Update any version tags in README.md
4. Commit changes
5. Create tag v1.2.3
6. Push commit and tag

Remember to maintain consistency across all version references in the project. 