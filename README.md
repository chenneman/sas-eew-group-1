# SAS EEW Group 1

## Getting Started

### 1. Install `uv`
`uv` is recommended for handling the Python environment.
- **How to install:** Go to [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) and follow the instructions for your operating system (Mac or Windows).
- Restart your Terminal or IDE after the installation finishes.

### 2. Get the Code (Cloning)
To get the project onto your computer with write access so you can save changes:
1. **Get a Token:** Go to GitHub Settings > Developer Settings > Personal Access Tokens. Create a "Fine-grained personal access token" or "Tokens (classic)" with `repo` access. Copy it.
2. Add the token to your favorite IDE, for **VS Code:** 
   - Press `Command + Shift + P` (Mac) or `Ctrl + Shift + P` (Windows) and type **Git: Clone**.
   - When asked for the URL, use this:
     `https://github.com/chenneman/sas-eew-group-1.git`

### 3. Set Up & Run
Once the project is open:
1. Open a **terminal** inside the directory.
2. **Install everything automatically:**
   ```bash
   uv sync
   ```
3. **Run an example:**
   ```bash
   uv run python examples/elevator_animated_yield.py
   ```
---

## Development
### Branches
- `main` - The main branch. This is never edited directly.

Create a new branch for every new feature or bugfix, and open a pull request to merge it into `main`.
Feature branches are best created from within GitHub issues/tasks. 