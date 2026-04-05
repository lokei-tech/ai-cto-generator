import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    file_tree: list[str] = field(default_factory=list)
    config_files: dict[str, str] = field(default_factory=dict)
    source_files: dict[str, list[str]] = field(default_factory=dict)
    total_files: int = 0
    total_dirs: int = 0


SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", "target",
    ".next", ".nuxt", ".output", "venv", ".venv", "env", ".env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "coverage", ".coverage", ".tox", "site-packages",
    ".idea", ".vscode", ".vs", "obj", "bin",
}

CONFIG_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock", "composer.json", "composer.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    ".csproj", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "jsconfig.json", "babel.config.js", "webpack.config.js",
    "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
    "nuxt.config.js", "nuxt.config.ts", "tailwind.config.js", "tailwind.config.ts",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "docker-compose.prod.yml", "docker-compose.dev.yml",
    "Makefile", "CMakeLists.txt", "meson.build",
    "pyrightconfig.json", ".eslintrc", ".eslintrc.js", ".eslintrc.json",
    ".eslintrc.cjs", ".prettierrc", ".prettierrc.json", ".prettierrc.js",
    "jest.config.js", "jest.config.ts", "vitest.config.js", "vitest.config.ts",
    "pytest.ini", "conftest.py", ".pre-commit-config.yaml",
    "Cargo.toml", "pubspec.yaml", "Podfile", "Podfile.lock",
    "android/app/build.gradle", "ios/Podfile",
    "terraform.tf", "main.tf", "Pulumi.yaml", "cdk.json",
    ".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/",
    "prisma/schema.prisma", "alembic.ini", "fly.toml", "netlify.toml",
    "vercel.json", "render.yaml", "railway.toml",
    ".editorconfig", ".gitignore", ".dockerignore",
    "README.md", "LICENSE", "CHANGELOG.md",
}

LANG_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".scala": "scala",
    ".clj": "clojure",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".tf": "terraform",
    ".hcl": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
}


def scan_project(project_path: str, max_depth: int = 8, max_files: int = 2000) -> ScanResult:
    result = ScanResult()
    root = Path(project_path).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Path not found: {project_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {project_path}")

    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        depth = len(rel_dir.parts)

        if depth > max_depth:
            dirnames.clear()
            continue

        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for f in filenames:
            if file_count >= max_files:
                return result

            rel_path = rel_dir / f if str(rel_dir) != "." else Path(f)
            rel_str = str(rel_path).replace("\\", "/")
            result.file_tree.append(rel_str)

            ext = Path(f).suffix.lower()
            filename_lower = f.lower()

            if filename_lower in CONFIG_FILES or rel_str in CONFIG_FILES:
                full_path = Path(dirpath) / f
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    result.config_files[rel_str] = content
                except (PermissionError, OSError):
                    pass

            if ext in LANG_EXTENSIONS:
                lang = LANG_EXTENSIONS[ext]
                if lang not in result.source_files:
                    result.source_files[lang] = []
                result.source_files[lang].append(rel_str)

            file_count += 1

        result.total_dirs += 1
        result.total_files += len(filenames)

    result.file_tree.sort()
    return result
