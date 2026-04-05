import argparse
import sys
from src.scanner import scan_project
from src.context_extractor import extract_context
from src.agent_builder import build_agent_prompts
from src.llm_generator import generate_hybrid, generate_pure_llm_sync
from src.ide_exporter import export_to_ide, IDE_FORMATS


def main():
    parser = argparse.ArgumentParser(description="AI CTO Agent Generator")
    parser.add_argument("project_path", nargs="?", help="Path to the project directory")
    parser.add_argument("--mode", choices=["scanner", "hybrid", "pure_llm"], default="hybrid", help="Generation mode")
    parser.add_argument("--ide", nargs="+", default=["all"], help="Target IDEs (or 'all')")
    parser.add_argument("--api-key", default="", help="LLM API key (required for hybrid/pure_llm)")
    parser.add_argument("--base-url", default="https://api.openai.com/v1", help="LLM base URL")
    parser.add_argument("--model", default="gpt-4o", help="LLM model name")
    parser.add_argument("--description", default="", help="Project description (for pure_llm mode)")

    args = parser.parse_args()

    if args.mode == "pure_llm" and not args.description:
        print("Error: --description is required for pure_llm mode")
        sys.exit(1)

    if args.mode != "scanner" and not args.api_key:
        print("Error: --api-key is required for hybrid and pure_llm modes")
        sys.exit(1)

    if args.mode != "pure_llm" and not args.project_path:
        print("Error: project_path is required for scanner and hybrid modes")
        sys.exit(1)

    ide_keys = list(IDE_FORMATS.keys()) if "all" in args.ide else args.ide

    if args.mode == "scanner":
        print(f"Scanning {args.project_path}...")
        scan = scan_project(args.project_path)
        print(f"Found {scan.total_files} files, {scan.total_dirs} directories")

        print("Extracting context...")
        ctx = extract_context(scan)
        print(f"Project: {ctx.project_name}")
        print(f"Languages: {', '.join(ctx.languages) if ctx.languages else 'N/A'}")
        print(f"Frameworks: {', '.join(ctx.frameworks) if ctx.frameworks else 'N/A'}")

        print("Building agent prompts...")
        prompts = build_agent_prompts(ctx)

    elif args.mode == "hybrid":
        print(f"Scanning {args.project_path}...")
        scan = scan_project(args.project_path)
        print(f"Found {scan.total_files} files, {scan.total_dirs} directories")

        print("Extracting context...")
        ctx = extract_context(scan)
        print(f"Project: {ctx.project_name}")
        print(f"Frameworks: {', '.join(ctx.frameworks) if ctx.frameworks else 'N/A'}")

        print("Generating with LLM (hybrid)...")
        import asyncio
        prompts = asyncio.run(generate_hybrid(ctx, args.api_key, args.base_url, args.model))
        print("LLM generation complete")

    elif args.mode == "pure_llm":
        print("Generating with LLM (pure)...")
        prompts = generate_pure_llm_sync(args.description, args.api_key, args.base_url, args.model)
        print("LLM generation complete")

    print(f"Exporting to {len(ide_keys)} IDE(s)...")
    ctx_for_export = ctx if args.mode != "pure_llm" else None
    export_path = args.project_path if args.project_path else "."
    generated = export_to_ide(export_path, ctx_for_export, prompts, ide_keys)

    for g in generated:
        print(f"  ✓ {g}")

    print("Done!")


if __name__ == "__main__":
    main()
