import json
import re
from dataclasses import dataclass, field
from src.scanner import ScanResult


@dataclass
class ProjectContext:
    project_name: str = "Unknown"
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    test_framework: str = ""
    lint_tools: list[str] = field(default_factory=list)
    ci_cd: list[str] = field(default_factory=list)
    database: list[str] = field(default_factory=list)
    architecture_pattern: str = ""
    entry_points: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    src_dirs: list[str] = field(default_factory=list)
    docker: bool = False
    monorepo: bool = False
    file_tree_summary: str = ""
    key_patterns: list[str] = field(default_factory=list)
    raw_context: str = ""


FRAMEWORK_SIGNALS = {
    "django": ["django", "DJANGO"],
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "react": ["react", "react-dom"],
    "next.js": ["next"],
    "vue": ["vue"],
    "nuxt": ["nuxt"],
    "svelte": ["svelte", "sveltekit"],
    "angular": ["@angular/core"],
    "express": ["express"],
    "nest.js": ["@nestjs/core"],
    "rails": ["rails"],
    "laravel": ["laravel"],
    "spring": ["spring-boot", "springframework"],
    "flutter": ["flutter"],
    "react native": ["react-native"],
    "electron": ["electron"],
    "tauri": ["tauri"],
    "remix": ["@remix-run"],
    "astro": ["astro"],
    "solid.js": ["solid-js"],
    "golang gin": ["gin-gonic"],
    "actix": ["actix"],
    "rocket": ["rocket"],
    "django rest": ["djangorestframework"],
    "sqlalchemy": ["sqlalchemy"],
    "prisma": ["prisma"],
    "drizzle": ["drizzle"],
    "typeorm": ["typeorm"],
    "hibernate": ["hibernate"],
    "celery": ["celery"],
    "redis": ["redis"],
    "grpc": ["grpc"],
    "graphql": ["graphql", "apollo", "graphene"],
    "tailwind": ["tailwindcss"],
    "bootstrap": ["bootstrap"],
    "material-ui": ["@mui", "material-ui"],
    "chakra": ["@chakra-ui"],
    "shadcn": ["shadcn"],
    "storybook": ["storybook"],
    "webpack": ["webpack"],
    "vite": ["vite"],
    "esbuild": ["esbuild"],
    "jest": ["jest"],
    "vitest": ["vitest"],
    "pytest": ["pytest"],
    "mocha": ["mocha"],
    "playwright": ["playwright"],
    "cypress": ["cypress"],
    "terraform": ["terraform", "hashicorp"],
    "pulumi": ["@pulumi"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws cdk": ["aws-cdk"],
    "pandas": ["pandas"],
    "pytorch": ["torch"],
    "tensorflow": ["tensorflow"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "langchain": ["langchain"],
    "openai sdk": ["openai"],
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "server.py", "index.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "index.tsx", "main.js", "main.ts", "main.tsx",
    "server.js", "server.ts", "app.js", "app.ts",
    "main.go", "main.rs", "Main.java", "Program.cs",
    "app.rb", "index.php", "App.tsx", "App.vue", "App.svelte",
}

TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "e2e", "integration", "unit"}

ARCH_PATTERNS = {
    "microservices": ["services/", "service-", "/gateway", "/api-gateway"],
    "monorepo": ["packages/", "apps/", "libs/", "workspace.json", "pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json"],
    "mvc": ["models/", "views/", "controllers/", "routes/"],
    "serverless": ["serverless.yml", "serverless.yaml", "lambda", "functions/"],
    "event-driven": ["events/", "handlers/", "listeners/", "queues/"],
    "layered": ["domain/", "infrastructure/", "application/", "presentation/"],
    "feature-based": ["features/", "modules/"],
}


def extract_context(scan: ScanResult) -> ProjectContext:
    ctx = ProjectContext()

    ctx.languages = sorted(set(scan.source_files.keys()))

    all_deps = set()
    all_config_text = ""

    for filename, content in scan.config_files.items():
        all_config_text += f"\n--- {filename} ---\n{content}"

        if filename == "package.json":
            try:
                pkg = json.loads(content)
                ctx.project_name = pkg.get("name", ctx.project_name)
                deps = set()
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    deps.update(pkg.get(section, {}).keys())
                all_deps.update(deps)
            except (json.JSONDecodeError, KeyError):
                pass

        elif filename == "requirements.txt":
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    all_deps.add(line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip().lower())

        elif filename == "pyproject.toml":
            ctx.project_name = _extract_toml_name(content) or ctx.project_name
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("["):
                    dep = line.split("=")[0].split(">")[0].split("<")[0].strip().strip('"').strip("'")
                    if dep and dep not in ("python",):
                        all_deps.add(dep.lower())

        elif filename == "go.mod":
            first_line = content.strip().splitlines()[0] if content.strip() else ""
            if first_line.startswith("module "):
                ctx.project_name = first_line.split(" ", 1)[1].split("/")[-1]
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("//") and not line.startswith("module") and not line.startswith("go ") and not line.startswith("require") and not line.startswith(")"):
                    all_deps.add(line.split(" ")[0].split("/")[-1].lower())

        elif filename == "Cargo.toml":
            ctx.project_name = _extract_toml_name(content) or ctx.project_name
            for line in content.splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("[") and not line.startswith("#"):
                    dep = line.split("=")[0].strip()
                    if dep:
                        all_deps.add(dep.lower())

        elif filename.startswith(".github/workflows/"):
            ctx.ci_cd.append("GitHub Actions")
        elif filename == ".gitlab-ci.yml":
            ctx.ci_cd.append("GitLab CI")
        elif filename == "Jenkinsfile":
            ctx.ci_cd.append("Jenkins")

        if filename == "Dockerfile" or filename.startswith("docker-compose"):
            ctx.docker = True

    for dep in all_deps:
        dep_lower = dep.lower()
        for fw_name, signals in FRAMEWORK_SIGNALS.items():
            if any(sig.lower() in dep_lower for sig in signals):
                if fw_name not in ctx.frameworks:
                    ctx.frameworks.append(fw_name)

    ctx.frameworks.sort()
    ctx.libraries = sorted([d for d in all_deps if d.lower() not in {f.lower() for f in ctx.frameworks}])[:30]

    if any(f in ctx.frameworks for f in ("pytest", "jest", "vitest", "mocha", "unittest")):
        ctx.test_framework = [f for f in ("pytest", "jest", "vitest", "mocha") if f in ctx.frameworks][0] if any(f in ctx.frameworks for f in ("pytest", "jest", "vitest", "mocha")) else ""

    for lt in ("eslint", "prettier", "ruff", "black", "flake8", "mypy", "pyright", "clippy", "gofmt", "rubocop"):
        if lt in ctx.frameworks or lt.lower() in {d.lower() for d in all_deps}:
            ctx.lint_tools.append(lt)

    db_signals = {
        "postgresql": ["postgresql", "psycopg", "pg"],
        "mysql": ["mysql", "pymysql", "mysqlclient"],
        "sqlite": ["sqlite", "sqlite3"],
        "mongodb": ["mongodb", "mongoose", "pymongo", "motor"],
        "redis": ["redis"],
        "elasticsearch": ["elasticsearch"],
        "dynamodb": ["dynamodb"],
        "supabase": ["supabase"],
        "firebase": ["firebase"],
        "prisma": ["prisma"],
        "mariadb": ["mariadb"],
        "cassandra": ["cassandra"],
        "neo4j": ["neo4j"],
    }
    for db_name, signals in db_signals.items():
        if any(sig in all_config_text.lower() for sig in signals):
            if db_name not in ctx.database:
                ctx.database.append(db_name)

    for pattern_name, markers in ARCH_PATTERNS.items():
        for marker in markers:
            if any(marker in ft for ft in scan.file_tree):
                if pattern_name == "monorepo":
                    ctx.monorepo = True
                if not ctx.architecture_pattern:
                    ctx.architecture_pattern = pattern_name
                break

    for ft in scan.file_tree:
        base = ft.split("/")[-1]
        if base in ENTRY_POINT_NAMES:
            ctx.entry_points.append(ft)

    for ft in scan.file_tree:
        parts = ft.split("/")
        if len(parts) > 1 and parts[0].lower() in TEST_DIR_NAMES:
            if parts[0] not in ctx.test_dirs:
                ctx.test_dirs.append(parts[0])
        if len(parts) > 1 and parts[0] in ("src", "lib", "app", "apps", "packages", "services"):
            if parts[0] not in ctx.src_dirs:
                ctx.src_dirs.append(parts[0])

    tree_lines = []
    for ft in scan.file_tree[:80]:
        depth = ft.count("/")
        indent = "  " * depth
        tree_lines.append(f"{indent}{ft.split('/')[-1]}")
    ctx.file_tree_summary = "\n".join(tree_lines)

    if "async" in all_config_text.lower() and ("fastapi" in ctx.frameworks or "aiohttp" in ctx.frameworks):
        ctx.key_patterns.append("async/await")
    if "typescript" in ctx.languages:
        ctx.key_patterns.append("TypeScript strict typing")
    if "prisma" in ctx.frameworks:
        ctx.key_patterns.append("Prisma ORM schema-first")
    if "graphql" in ctx.frameworks:
        ctx.key_patterns.append("GraphQL API")
    if "tailwind" in ctx.frameworks:
        ctx.key_patterns.append("Tailwind CSS utility classes")
    if "celery" in ctx.frameworks:
        ctx.key_patterns.append("Celery async task queue")

    ctx.raw_context = _build_raw_context(ctx, scan)

    return ctx


def _extract_toml_name(content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("name ="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _build_raw_context(ctx: ProjectContext, scan: ScanResult) -> str:
    parts = []
    parts.append(f"Project: {ctx.project_name}")
    parts.append(f"Languages: {', '.join(ctx.languages) if ctx.languages else 'Not detected'}")
    parts.append(f"Frameworks: {', '.join(ctx.frameworks) if ctx.frameworks else 'None detected'}")
    parts.append(f"Test Framework: {ctx.test_framework or 'Not detected'}")
    parts.append(f"Lint/Format: {', '.join(ctx.lint_tools) if ctx.lint_tools else 'None detected'}")
    parts.append(f"Database: {', '.join(ctx.database) if ctx.database else 'None detected'}")
    parts.append(f"Architecture: {ctx.architecture_pattern or 'Not detected'}")
    parts.append(f"Monorepo: {'Yes' if ctx.monorepo else 'No'}")
    parts.append(f"Docker: {'Yes' if ctx.docker else 'No'}")
    parts.append(f"CI/CD: {', '.join(ctx.ci_cd) if ctx.ci_cd else 'None detected'}")
    parts.append(f"Entry Points: {', '.join(ctx.entry_points) if ctx.entry_points else 'Not detected'}")
    parts.append(f"Source Dirs: {', '.join(ctx.src_dirs) if ctx.src_dirs else 'Not detected'}")
    parts.append(f"Test Dirs: {', '.join(ctx.test_dirs) if ctx.test_dirs else 'Not detected'}")
    parts.append(f"Key Patterns: {', '.join(ctx.key_patterns) if ctx.key_patterns else 'None'}")
    parts.append("")
    parts.append("File Tree:")
    parts.append(ctx.file_tree_summary)
    return "\n".join(parts)
