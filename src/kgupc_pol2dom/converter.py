"""Run the pinned p2d converter in a process with Python UTF-8 mode enabled."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('label')
    parser.add_argument('external_id')
    parser.add_argument('language')
    parser.add_argument('testset')
    args = parser.parse_args()
    from p2d import GlobalConfig, ProcessError, convert
    try:
        convert(args.source, args.output, short_name=args.label, testset_name=args.testset,
                external_id=args.external_id, hide_sample=True, with_statement=False, with_attachments=True,
                global_config=GlobalConfig(language_preference=[args.language, 'english']))
    except (ProcessError, ValueError, OSError) as error:
        print(f'p2d conversion failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
