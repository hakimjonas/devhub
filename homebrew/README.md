# DevHub Homebrew Installation

This directory contains the Homebrew formula for DevHub CLI tool.

## For Users

### Installing DevHub via Homebrew

Currently, DevHub is not yet available in the official Homebrew core or a public tap. Here are the installation options:

#### Option 1: Install from Local Formula (Development)

```bash
# Clone the repository
git clone https://github.com/hakimjonas/devhub.git
cd devhub

# Install using local formula
brew install --build-from-source homebrew/devhub.rb
```

#### Option 2: Install from Future Tap (Coming Soon)

Once DevHub is published to a Homebrew tap:

```bash
# Add the tap (example - not yet available)
brew tap hakimjonas/devhub

# Install DevHub
brew install devhub
```

#### Option 3: Install HEAD Version (Latest Development)

```bash
# Install latest development version
brew install --HEAD homebrew/devhub.rb
```

### Verification

After installation, verify DevHub works correctly:

```bash
# Check version
devhub --version

# Run health checks
devhub doctor

# View help
devhub --help
```

## For Maintainers

### Publishing to Homebrew

To publish DevHub to Homebrew, follow these steps:

#### 1. Create a GitHub Release

```bash
# Tag and push a release
git tag v0.1.0
git push origin v0.1.0

# Create release on GitHub with assets
gh release create v0.1.0 --generate-notes
```

#### 2. Update SHA256 Checksum

Calculate the SHA256 of the release tarball:

```bash
# Download the tarball
curl -L https://github.com/hakimjonas/devhub/archive/v0.1.0.tar.gz -o devhub-0.1.0.tar.gz

# Calculate SHA256
sha256sum devhub-0.1.0.tar.gz

# Update the sha256 field in devhub.rb with the calculated hash
```

#### 3. Create Homebrew Tap Repository

```bash
# Create a new repository named homebrew-devhub
# Repository should be at: https://github.com/hakimjonas/homebrew-devhub

# Copy the formula
cp homebrew/devhub.rb /path/to/homebrew-devhub/Formula/devhub.rb

# Commit and push
cd /path/to/homebrew-devhub
git add Formula/devhub.rb
git commit -m "Add DevHub formula v0.1.0"
git push origin main
```

#### 4. Submit to Homebrew Core (Optional)

For inclusion in Homebrew core:

1. Ensure the project meets [Homebrew's requirements](https://github.com/Homebrew/brew/blob/master/docs/Acceptable-Formulae.md)
2. The project should be stable and notable
3. Submit a PR to [homebrew-core](https://github.com/Homebrew/homebrew-core)

### Testing the Formula

Test the formula locally before publishing:

```bash
# Test installation
brew install --build-from-source homebrew/devhub.rb

# Run formula tests
brew test devhub

# Test uninstallation
brew uninstall devhub

# Audit formula
brew audit --strict homebrew/devhub.rb
```

### Updating Dependencies

When updating Python dependencies, update both:

1. `pyproject.toml` dependency versions
2. Resource checksums in `homebrew/devhub.rb`

Use `brew-pip-audit` or similar tools to check for security updates.

### Version Updates

For new releases:

1. Update version in `pyproject.toml`
2. Update URL and SHA256 in `homebrew/devhub.rb`
3. Update version assertions in tests
4. Tag and release

## Dependencies

The formula automatically installs:

- **Python 3.13+**: Required runtime
- **git**: For repository operations
- **gh** (GitHub CLI): For GitHub API interactions
- **Python packages**: All dependencies listed in pyproject.toml

## Troubleshooting

### Common Issues

1. **Python version conflicts**:
   ```bash
   brew uninstall devhub
   brew install --build-from-source homebrew/devhub.rb
   ```

2. **Missing GitHub CLI**:
   ```bash
   brew install gh
   ```

3. **Permission issues**:
   ```bash
   # Check brew permissions
   brew doctor
   ```

### Development Testing

Test changes to the formula:

```bash
# Validate formula syntax
brew audit --strict homebrew/devhub.rb

# Test installation in clean environment
brew uninstall devhub 2>/dev/null || true
brew install --build-from-source homebrew/devhub.rb

# Run comprehensive tests
brew test devhub
devhub doctor
```

## Formula Maintenance

The formula should be maintained to:

- Keep dependencies updated
- Follow Homebrew style guidelines
- Test on macOS versions supported by Homebrew
- Monitor for security updates
- Update for Python version changes

For questions about the Homebrew formula, please open an issue on the main DevHub repository.