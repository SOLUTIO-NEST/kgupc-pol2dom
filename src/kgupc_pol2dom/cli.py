import argparse
import json
import subprocess
import sys
from pathlib import Path

from .renderer import render_contest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download Polygon problems, render Korean PDFs and deploy to DOMjudge")
    parser.add_argument("--version", action="version", version="kgupc-pol2dom 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="Build PDFs in a local contest work directory")
    render.add_argument("source", type=Path)
    render.add_argument("--toolkit-lock", type=Path)
    listing = commands.add_parser("polygon-list", help="List the contest selected by POLYGON_CONTEST_URL")
    listing.add_argument("contest_id", nargs="?", help="Optional ID or URL; must agree with .env")
    preparation = commands.add_parser("prepare", help="Fetch a contest into a local directory outside Git")
    preparation.add_argument("--output", type=Path, help="Defaults to ~/kgupc-work/contest-<ID>")
    preparation.add_argument("--language", default="korean")
    preparation.add_argument("--testset", default="tests")
    preparation.add_argument("--letters", nargs="+")
    preparation.add_argument("--replace", action="store_true")
    preparation.add_argument("--working-copy", action="store_true")
    preparation.add_argument("--render", action="store_true", help="Build combined and individual PDFs")
    dom_listing = commands.add_parser("domjudge-list", help="Check DOMjudge connection and list target contest IDs")
    dom_listing.add_argument("--env-file", type=Path)
    deployments = []
    for name, description in (("bundle", "Download Polygon Full packages, render PDFs and create DOMjudge ZIPs"),
                              ("deploy", "Synchronize the configured DOMjudge contest with Polygon; remove problems absent from Polygon")):
        deployment = commands.add_parser(name, help=description)
        deployment.add_argument("--output", type=Path, help="Defaults to ~/kgupc-work/deploy-<Polygon ID>")
        deployment.add_argument("--letters", nargs="+", help="Update only selected letters; preserve unselected contest problems")
        deployment.add_argument("--language", default="korean")
        deployment.add_argument("--testset", default="tests")
        deployment.add_argument("--build-packages", action="store_true", help="Allow Polygon to build missing Full packages (does not commit changes)")
        deployment.add_argument("--env-file", type=Path)
        deployments.append(deployment)
    upload = commands.add_parser("upload", help="Upload a completed local bundle without fetching Polygon again")
    upload.add_argument("run", type=Path, help="Run directory containing deployment.json")
    upload.add_argument("--env-file", type=Path)
    export = commands.add_parser("export-archive", help="Export a complete local bundle as a standalone editable contest folder; no network or archive access")
    export.add_argument("run", type=Path, help="Final run directory containing deployment.json")
    export.add_argument("--name", required=True, help="Contest folder name, e.g. 2026-fall")
    export.add_argument("--output", type=Path, help="Parent output directory; defaults to ./build/archive (must be Git-ignored inside this repository)")
    importer = commands.add_parser("import-polygon", help="Update an existing local contest outside Git")
    importer.add_argument("config", type=Path)
    importer.add_argument("--contest", type=Path, required=True)
    importer.add_argument("--letters", nargs="+")
    importer.add_argument("--replace", action="store_true", help="Back up and replace selected problem directories")
    importer.add_argument("--render", action="store_true", help="Validate PDFs before publishing")
    importer.add_argument("--working-copy", action="store_true")
    for command in (listing, preparation, importer):
        command.add_argument("--env-file", type=Path, help="Defaults to .env in the current directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            render_contest(args.source, lock=args.toolkit_lock)
        elif args.command == "export-archive":
            from .archive_export import export_archive
            export_archive(args.run, args.name, output=args.output)
        else:
            from .api import PolygonClient, load_settings
            from .importer import contest_problems, import_contest, load_config
            from .targeting import require_private_directory, resolve_target
            settings = load_settings(args.env_file)
            if args.command in ("prepare", "bundle", "deploy"):
                from .metadata import metadata_from_settings
                metadata = metadata_from_settings(settings)
            if args.command in ("bundle", "deploy") and not args.letters:
                from .archive_export import export_archive, require_export_directory, validate_contest_name
                archive_name = validate_contest_name(settings.get("CONTEST_SLUG"))
                require_export_directory(Path.cwd() / "build/archive" / archive_name)
            if args.command == "domjudge-list":
                from .domjudge import DOMjudgeClient
                client = DOMjudgeClient.from_settings(settings)
                print(json.dumps({"server": client.request("/info"), "contests": client.contests()}, ensure_ascii=False, indent=2))
            elif args.command in ("bundle", "deploy", "upload"):
                from .deployment import build_bundle, upload_bundle
                from .domjudge import DOMjudgeClient, target_contest
                target = resolve_target(settings)
                if args.command in ("deploy", "upload"):
                    dom = DOMjudgeClient.from_settings(settings)
                    dom_target = target_contest(settings)
                    dom.contest(dom_target)  # Fail early before downloads if URL/auth/target is wrong.
                    print(f"DOMjudge target: {dom.url}, contest {dom_target}", flush=True)
                if args.command == "upload":
                    upload_bundle(dom, settings, args.run)
                else:
                    output = require_private_directory(args.output or Path.home() / "kgupc-work" / f"deploy-{target}")
                    polygon = PolygonClient.from_settings(settings, allow_package_builds=args.build_packages)
                    run = build_bundle(polygon, target, output, letters=args.letters, language=args.language,
                                       testset=args.testset, build_packages=args.build_packages, dom_contest=target_contest(settings),
                                       metadata=metadata)
                    if not args.letters:
                        export_archive(run, archive_name, replace_generated=True)
                    if args.command == "deploy":
                        upload_bundle(dom, settings, run)
            elif args.command == "polygon-list":
                target = resolve_target(settings, explicit=args.contest_id)
                print(f"Polygon contest: {target}", file=sys.stderr)
                print(json.dumps(contest_problems(PolygonClient.from_settings(settings), target),
                                 ensure_ascii=False, indent=2))
            elif args.command == "prepare":
                from .preparation import prepare_contest
                target = resolve_target(settings)
                # Reject repository paths before the first authenticated request.
                require_private_directory(args.output or Path.home() / "kgupc-work" / f"contest-{target}")
                print(f"Polygon contest: {target}", flush=True)
                prepare_contest(PolygonClient.from_settings(settings), target, args.output, letters=args.letters,
                                replace=args.replace, working_copy=args.working_copy, render=args.render,
                                language=args.language, testset=args.testset, metadata=metadata)
            else:
                config = load_config(args.config)
                target = resolve_target(settings, configured=config.get("contestId"))
                config = {**config, "contestId": target}
                require_private_directory(args.contest)
                print(f"Polygon contest: {target}", flush=True)
                import_contest(PolygonClient.from_settings(settings), config, args.contest, letters=args.letters,
                               replace=args.replace, working_copy=getattr(args, "working_copy", False),
                               render=args.render)
    except (ValueError, OSError) as error:
        print(f"kgupc-pol2dom error: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0
