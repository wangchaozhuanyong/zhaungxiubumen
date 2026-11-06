"""Argument declarations only; importing this module never loads release evidence."""

import argparse


def build_parser(description, *, target_choices=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", choices=target_choices, required=True,
                        help="Exact registered target; validated when executing, not while displaying help")
    parser.add_argument("--operation", choices=["publish", "rollback"], required=True)
    parser.add_argument("--dry-run-run-id", type=int, required=True)
    parser.add_argument("--operations-decision", required=True)
    parser.add_argument("--policy-decision-id", required=True)
    parser.add_argument("--github-actor-id", type=int, required=True)
    parser.add_argument("--parent-permit-id")
    parser.add_argument("--parent-run-id", type=int)
    parser.add_argument("--issue-and-dispatch", action="store_true")
    return parser
